"""HotpotQA distractor runner：检索 top-k 段落 → 多跳 chat 答 → EM/F1 + 检索 Recall。

设计要点：
- 每题独立 user_id（uuid5(qid)），灌入 → 查 → 清理；不互相干扰、可重入。
- 段落级粒度（source_id = title），便于按 `gold_titles` 算检索 Recall。
- 三组对照：无 Verifier(A) / 同模型 self-critique(B) / 跨模型 Verifier(C) —— ② Verifier Loop 完成后才接入。
  当前先支持 baseline（无 Verifier），保留接口供 ② 接入后扩展。
- 答案评估走 HotpotQA 官方 `exact_match_score` / `f1_score` 口径（normalize + token 级 P/R/F1）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import string
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.rag.chunker import chunk_parent_child
from app.core.rag.es_index import CHUNK_TYPE_CHILD, CHUNKS_INDEX, ensure_index
from app.core.rag.es_store import build_chunk_doc, bulk_index
from app.db.elastic import get_es

from eval import clients
from eval import metrics as M
from eval.benchmarks._common import write_benchmark_details, write_benchmark_report
from eval.benchmarks.hotpotqa.loader import load
from eval.benchmarks.hotpotqa.qa_verifier import judge_qa
from eval.stats import bootstrap_mean_ci, latency_summary

K_RETRIEVE = 4  # 每题检索 top-4 段落给 chat 答（distractor 共 10 段，2 段是 gold）

# 命名空间根：每题 user_id = uuid5(NS_HOTPOT, qid)
_NS_HOTPOT = uuid.UUID("eee30000-0000-0000-0000-0000000000c3")
_CHECKPOINT_DIR = Path(__file__).parents[2] / "results" / "rag" / "checkpoints"
_MAX_EMBED_CHARS = 2000
_CHECKPOINT_PROTOCOL_VERSION = 3


def _qid_to_uid(qid: str) -> str:
    return str(uuid.uuid5(_NS_HOTPOT, qid))


# ── HotpotQA 官方 EM/F1 评测口径（normalize + token） ──

def _normalize_answer(s: str) -> str:
    """官方口径：删除冠词、标点、多余空白、转小写。"""
    s = s.lower()
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _em(pred: str, gold: str) -> float:
    return float(_normalize_answer(pred) == _normalize_answer(gold))


def _f1(pred: str, gold: str) -> float:
    pt = _normalize_answer(pred).split()
    gt = _normalize_answer(gold).split()
    if not pt or not gt:
        return float(pt == gt)
    common = Counter(pt) & Counter(gt)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    p = num_same / len(pt)
    r = num_same / len(gt)
    return 2 * p * r / (p + r)


# ── 灌入与检索 ──

def _embedding_chunks(content: str) -> list[str]:
    chunks = [
        child
        for parent in chunk_parent_child(content)
        for child in parent.children
    ] or [content]
    return [
        part
        for chunk in chunks
        for part in (
            [
                chunk[i:i + _MAX_EMBED_CHARS]
                for i in range(0, len(chunk), _MAX_EMBED_CHARS)
            ] or [chunk]
        )
    ]


async def _ingest_one(
    embed_client, qid: str, paragraphs: list[dict], *, with_vectors: bool = True
) -> None:
    """把单题的 10 段按生产子块粒度灌进 ES。

    HotpotQA 大多段落较短，但存在超长句子。直接将整段交给 embedding
    会触发 provider 400；这里复用业务父子分块，并对超长单句做最后的字符长度保护。
    多个子块仍共用 source_id=title，指标仍按段落标题去重计算。
    """
    uid = _qid_to_uid(qid)
    es_docs: list[dict] = []
    texts: list[str] = []
    titles: list[str] = []
    for p in paragraphs:
        content = " ".join(p["sentences"])
        safe_chunks = _embedding_chunks(content)
        texts.extend(safe_chunks)
        titles.extend([p["title"]] * len(safe_chunks))
    vectors = (
        await embed_client.embed(texts)
        if texts and with_vectors
        else [None] * len(texts)
    )
    for title, content, vec in zip(titles, texts, vectors):
        es_docs.append(build_chunk_doc(
            user_id=uid, source_type="document", source_id=title,
            doc_name=title, chunk_type=CHUNK_TYPE_CHILD,
            content=content, vector=vec,
        ))
    if es_docs:
        await bulk_index(es_docs)


def _checkpoint_signature(
    *, sample: int, seed: int, verifier: str, retrieval_mode: str, embed_model: str,
    chat_model: str, verifier_models: list[str],
) -> dict:
    return {
        "protocol_version": _CHECKPOINT_PROTOCOL_VERSION,
        "sample": sample,
        "seed": seed,
        "verifier": verifier,
        "retrieval_mode": retrieval_mode,
        "embed_model": embed_model,
        "chat_model": chat_model,
        "verifier_models": verifier_models,
    }


def _checkpoint_path(signature: dict) -> Path:
    raw = json.dumps(signature, ensure_ascii=True, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()[:12]
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR / f"hotpotqa-{digest}.json"


def _load_checkpoint(path: Path, signature: dict) -> list[dict]:
    if not path.exists():
        return []
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if body.get("signature") != signature:
        return []
    # 出错题不视为已完成，续跑时会再尝试。
    return [row for row in body.get("details", []) if not row.get("error")]


def _write_checkpoint(
    path: Path, signature: dict, details: list[dict], *, completed: bool = False,
) -> None:
    body = {
        "signature": signature,
        "completed": completed,
        "completed_items": len(details),
        "details": details,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


async def _clear_one(qid: str) -> None:
    es = get_es()
    try:
        await es.delete_by_query(
            index=CHUNKS_INDEX,
            body={"query": {"term": {"user_id": _qid_to_uid(qid)}}},
            refresh=True,
            conflicts="proceed",
        )
    except Exception:  # noqa: BLE001
        pass


# ── chat 回答 ──

_ANSWER_PROMPT = """You are answering a multi-hop question using ONLY the provided paragraphs.

Question: {question}

Paragraphs:
{paragraphs}

Rules:
- Reason briefly and then output the final answer.
- Format: The VERY LAST line of your reply MUST be exactly `ANSWER: <短答案>`
  - `<短答案>` is a short phrase (a name / number / date) or `yes`/`no`.
  - Match the wording in the paragraphs exactly when applicable.
  - No quotation marks, no trailing punctuation, no explanation after `ANSWER:`.
- If the paragraphs do not support a confident answer, still output your best guess on that last line.

Begin."""


_ANSWER_RE_MARKERS = ("ANSWER:", "Answer:", "answer:", "答案:", "Final Answer:", "final answer:")


def _extract_answer(text: str) -> str:
    """从 chat 回复里抽出最终答案。处理推理模型(<think>...</think> + 答案)与普通模型两种输出。

    优先级:
    1. 找最后一个 ANSWER: / 答案: 等 marker,取其后到行尾的字符串
    2. 兜底:取最后一个非空行
    """
    if not text:
        return ""
    # 去除常见 <think>...</think>(reasoning model 输出)
    cleaned = text
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[1]
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = text.strip()

    # 找最后一个 marker(rfind),取其后到行末
    best: str | None = None
    for marker in _ANSWER_RE_MARKERS:
        idx = cleaned.rfind(marker)
        if idx >= 0:
            tail = cleaned[idx + len(marker):]
            # 取 marker 后第一行非空
            for line in tail.splitlines():
                line = line.strip()
                if line:
                    best = line
                    break
            if best:
                break

    if not best:
        # 兜底:取最后一个非空行
        for line in reversed(cleaned.splitlines()):
            s = line.strip()
            if s:
                best = s
                break

    if not best:
        return ""
    return best.strip(string.punctuation + " \"'")


async def _answer(chat_client, question: str, paragraphs: list[tuple[str, str]]) -> str:
    """让 chat 模型基于检索到的 paragraphs 答 HotpotQA。返回最终答案文本。

    max_tokens 调到 1024:推理模型(deepseek-r1 / -v4-pro 等)思考块通常 200~800 token,
    给少了 thinking 没结束就被截断 → 最终答案丢失。
    """
    p_text = "\n\n".join(f"[{title}]\n{content}" for title, content in paragraphs)
    prompt = _ANSWER_PROMPT.format(question=question, paragraphs=p_text)
    text = await chat_client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=1024, temperature=0.0,
    )
    return _extract_answer(text)


# ── 主流程 ──

async def run_benchmark(
    embed_client, chat_client, rerank_client=None, *,
    sample: int = 500,
    verifier: str = "none",
    seed: int = 42,
    resume: bool = False,
    retrieval_mode: str = "hybrid",
    verifier_client_factory=None,
    run_manifest: dict | None = None,
) -> tuple[dict, list]:
    """跑 HotpotQA distractor + 可选的 Verifier A/B 实验。

    Args:
        embed_client / chat_client / rerank_client: 由 run_eval 注入
        sample: 采样数（按 bridge/comparison 分层）
        verifier: none | same | cross | compare
            - none:  仅算 EM/F1 + 检索 Recall(baseline)
            - same:  答完后用 chat_client 同款做 LLM-as-judge,判 verifier_pass=1/0
            - cross: 答完后用单独配置的 verifier 模型判;未配置降级到 same
            - compare: 同一份回答同时交给 same/cross,避免重复生成造成 A/B 混杂
        seed: 采样种子
        verifier_client_factory: 可调用 → 返回 cross 模式用的 LLMClient(由 run_eval 注入,
                                  这样 runner 不直接耦合 eval_config 模块)
    """
    # 同一份 pred 可以交给多个 judge，保证 same/cross 比较只改变审稿模型。
    judge_clients: dict[str, Any] = {}
    judge_kind_actual = "none"
    if verifier == "same":
        judge_clients["same"] = chat_client
        judge_kind_actual = "same"
    elif verifier == "cross":
        if verifier_client_factory is not None:
            cross_client = verifier_client_factory()
        else:
            cross_client = None
        if cross_client is None:
            print("[hotpotqa] --verifier=cross 但未配置 EVAL_VERIFIER_*,降级到 same")
            judge_clients["same"] = chat_client
            judge_kind_actual = "same(降级自 cross)"
        else:
            judge_clients["cross"] = cross_client
            judge_kind_actual = f"cross ({cross_client.model_name})"
    elif verifier == "compare":
        cross_client = verifier_client_factory() if verifier_client_factory else None
        judge_clients["same"] = chat_client
        if cross_client is not None:
            judge_clients["cross"] = cross_client
            judge_kind_actual = f"same + cross ({cross_client.model_name})"
        else:
            judge_kind_actual = "same only(cross 未配置)"
            print("[hotpotqa] compare 未配置跨家族 Verifier,仅运行 same")

    print(f"[hotpotqa] 加载数据集（采样 {sample} 条）… verifier={verifier} (实际: {judge_kind_actual})")
    queries = load(n=sample, seed=seed)
    print(f"  实际采样: {len(queries)} 条（bridge/comparison 按比例）")

    await ensure_index()

    # 累积指标
    em_list: list[float] = []
    f1_list: list[float] = []
    retr_recall_list: list[float] = []  # 检索 top-k 段落对 gold_titles 的覆盖
    verifier_passes: dict[str, list[int]] = {
        kind: [] for kind in judge_clients
    }
    signature = _checkpoint_signature(
        sample=sample,
        seed=seed,
        verifier=verifier,
        retrieval_mode=retrieval_mode,
        embed_model=embed_client.model_name,
        chat_model=chat_client.model_name,
        verifier_models=[
            f"{kind}:{client.model_name}" for kind, client in judge_clients.items()
        ],
    )
    checkpoint_path = _checkpoint_path(signature)
    details: list[dict] = (
        _load_checkpoint(checkpoint_path, signature) if resume else []
    )
    if details:
        print(f"  [resume] 已恢复 {len(details)} 题: {checkpoint_path}")
    for row in details:
        em_list.append(float(row["em"]))
        f1_list.append(float(row["f1"]))
        retr_recall_list.append(float(row["retrieval_recall"]))
        for kind in judge_clients:
            verifier_passes[kind].append(
                int(row.get("verifier_passes", {}).get(kind, 0))
            )
    completed_qids = {row["qid"] for row in details}

    total = len(queries)
    for i, q in enumerate(queries, 1):
        qid = q["qid"]
        if qid in completed_qids:
            print(f"  [hotpotqa] {i}/{total}  qid={qid}  [checkpoint skip]")
            continue
        uid = _qid_to_uid(qid)
        print(f"  [hotpotqa] {i}/{total}  qid={qid}  type={q['qtype']}")
        print(f"    Q: {q['question'][:80]}")
        started = time.perf_counter()
        try:
            # 1. 灌入本题 10 段
            ingest_started = time.perf_counter()
            await _ingest_one(
                embed_client,
                qid,
                q["paragraphs"],
                with_vectors=retrieval_mode == "hybrid",
            )
            ingest_ms = (time.perf_counter() - ingest_started) * 1000
            await asyncio.sleep(0.05)  # 给 ES 一点索引时间
            # 2. 检索 top-k
            retrieval_started = time.perf_counter()
            # 分块后同一 title 可能命中多个 child，先多取候选再按 source_id 去重。
            if retrieval_mode == "hybrid":
                rh = await clients.retrieve_hybrid(
                    embed_client, uid, q["question"], 50
                )
            else:
                rh = await clients.retrieve_bm25(uid, q["question"], 50)
            if rerank_client is not None and len(rh) > K_RETRIEVE:
                rh = await clients.rerank_sources(rerank_client, uid, q["question"], rh, K_RETRIEVE)
            else:
                rh = rh[:K_RETRIEVE]
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            # 3. 收集检索到的段落（按 source_id == title 对回 paragraphs）
            title_to_content = {p["title"]: " ".join(p["sentences"]) for p in q["paragraphs"]}
            retrieved = [(t, title_to_content.get(t, "")) for t in rh if t in title_to_content]
            # 4. 评检索 Recall: top-k 中命中 gold_titles 的数量 / 总 gold
            gold = q["gold_titles"]
            hits_in_topk = [t for t in rh if t in gold]
            retr_recall = len(hits_in_topk) / max(1, len(gold))
            retr_recall_list.append(retr_recall)
            print(f"    ✓ 检索 top-{K_RETRIEVE}: {rh} | 命中 gold={hits_in_topk} (Recall={retr_recall:.2f})")
            # 5. 让 chat 答
            answer_started = time.perf_counter()
            pred = await _answer(chat_client, q["question"], retrieved)
            answer_ms = (time.perf_counter() - answer_started) * 1000
            em = _em(pred, q["answer"])
            f1 = _f1(pred, q["answer"])
            em_list.append(em)
            f1_list.append(f1)
            mark = "✓" if em else ("~" if f1 > 0 else "✗")
            print(f"    {mark} pred='{pred[:60]}' | gold='{q['answer'][:60]}' | EM={em:.0f} F1={f1:.2f}")
            # 6. (可选) Verifier 判合格:same/cross 模式
            item_verifier_passes: dict[str, int] = {}
            for kind, judge_client in judge_clients.items():
                verifier_pass = await judge_qa(
                    judge_client,
                    question=q["question"],
                    pred=pred,
                    retrieved_passages=retrieved,
                )
                verifier_passes[kind].append(verifier_pass)
                item_verifier_passes[kind] = verifier_pass
                # 漏检 = verifier 判过但实际错(em=0)
                leak = int(verifier_pass == 1 and em == 0)
                print(
                    f"    [verifier:{kind}] pass={verifier_pass} leak={leak}"
                )
            details.append({
                "qid": qid,
                "question": q["question"],
                "type": q["qtype"],
                "gold_answer": q["answer"],
                "gold_titles": gold,
                "retrieved_topk_titles": rh,
                "retrieval_recall": round(retr_recall, 4),
                "pred": pred,
                "em": em,
                "f1": round(f1, 4),
                "verifier_passes": item_verifier_passes,
                "latency_ms": {
                    "ingest": round(ingest_ms, 2),
                    "retrieval": round(retrieval_ms, 2),
                    "answer": round(answer_ms, 2),
                    "total": round((time.perf_counter() - started) * 1000, 2),
                },
            })
        except Exception as exc:  # noqa: BLE001
            # 单题的 provider/数据异常记为 0 分并继续，不让整轮评测丢证据。
            print(f"    ✗ 本题失败: {type(exc).__name__}: {str(exc)[:160]}")
            em_list.append(0.0)
            f1_list.append(0.0)
            retr_recall_list.append(0.0)
            for kind in judge_clients:
                verifier_passes[kind].append(0)
            details.append({
                "qid": qid,
                "question": q["question"],
                "type": q["qtype"],
                "gold_answer": q["answer"],
                "gold_titles": q["gold_titles"],
                "retrieved_topk_titles": [],
                "retrieval_recall": 0.0,
                "pred": "",
                "em": 0.0,
                "f1": 0.0,
                "verifier_passes": {kind: 0 for kind in judge_clients},
                "latency_ms": {
                    "total": round((time.perf_counter() - started) * 1000, 2),
                },
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                },
            })
        finally:
            await _clear_one(qid)
            _write_checkpoint(checkpoint_path, signature, details)

    # 基础指标
    em_ci = bootstrap_mean_ci(em_list, seed=seed)
    f1_ci = bootstrap_mean_ci(f1_list, seed=seed)
    recall_ci = bootstrap_mean_ci(retr_recall_list, seed=seed)
    base_row: dict[str, Any] = {
        "EM(严格正确率)": M.avg(em_list),
        "EM 95%CI": f"[{em_ci[0]}, {em_ci[1]}]",
        "F1(软正确率)": M.avg(f1_list),
        "F1 95%CI": f"[{f1_ci[0]}, {f1_ci[1]}]",
        f"Retr Recall@{K_RETRIEVE}": M.avg(retr_recall_list),
        "Recall 95%CI": f"[{recall_ci[0]}, {recall_ci[1]}]",
        "样本数": len(em_list),
        "失败题数": sum(1 for row in details if row.get("error")),
    }
    base_row.update(latency_summary([
        float(row.get("latency_ms", {}).get("total", 0.0))
        for row in details
    ]))
    def _judge_metrics(pass_list: list[int]) -> dict[str, float]:
        n_total = len(pass_list)
        n_pass = sum(pass_list)
        # 漏检率 = (verifier 判过 ∩ 实际 EM=0) / verifier 判过总数
        leak = sum(
            1 for vp, em in zip(pass_list, em_list) if vp == 1 and em == 0
        )
        leak_rate = leak / n_pass if n_pass else 0.0
        false_reject = sum(
            1 for vp, em in zip(pass_list, em_list) if vp == 0 and em == 1
        )
        rejected = n_total - n_pass
        false_reject_rate = false_reject / rejected if rejected else 0.0
        # EM 对别名/修饰词极严；F1>=0.5 作为“实质正确”的确定性近似口径。
        substantial_leak = sum(
            1 for vp, f1 in zip(pass_list, f1_list) if vp == 1 and f1 < 0.5
        )
        substantial_leak_rate = substantial_leak / n_pass if n_pass else 0.0
        substantial_false_reject = sum(
            1 for vp, f1 in zip(pass_list, f1_list) if vp == 0 and f1 >= 0.5
        )
        substantial_false_reject_rate = (
            substantial_false_reject / rejected if rejected else 0.0
        )
        # verifier 与 EM 一致率 = (二者同时为 1 或同时为 0) / total
        agree = sum(1 for vp, em in zip(pass_list, em_list) if vp == int(em))
        agree_rate = agree / n_total if n_total else 0.0
        return {
            "Verifier 判过率": round(n_pass / n_total, 4) if n_total else 0.0,
            "漏检率(judge 通过但 EM=0)": round(leak_rate, 4),
            "误拒率(judge 拒绝但 EM=1)": round(false_reject_rate, 4),
            "实质错误放行率(F1<0.5)": round(substantial_leak_rate, 4),
            "实质正确误拒率(F1>=0.5)": round(
                substantial_false_reject_rate, 4
            ),
            "与 EM 一致率": round(agree_rate, 4),
        }

    if verifier_passes:
        base_row.update(
            {
                "Verifier 判过率": "-",
                "漏检率(judge 通过但 EM=0)": "-",
                "误拒率(judge 拒绝但 EM=1)": "-",
                "实质错误放行率(F1<0.5)": "-",
                "实质正确误拒率(F1>=0.5)": "-",
                "与 EM 一致率": "-",
            }
        )

    table: dict[str, dict[str, Any]] = {
        "answer baseline": base_row,
    }
    for kind, pass_list in verifier_passes.items():
        table[f"judge={kind}"] = {**base_row, **_judge_metrics(pass_list)}
    for qtype in sorted({row["type"] for row in details}):
        indexes = [i for i, row in enumerate(details) if row["type"] == qtype]
        type_em = [em_list[i] for i in indexes]
        type_f1 = [f1_list[i] for i in indexes]
        type_recall = [retr_recall_list[i] for i in indexes]
        type_em_ci = bootstrap_mean_ci(type_em, seed=seed)
        type_f1_ci = bootstrap_mean_ci(type_f1, seed=seed)
        type_recall_ci = bootstrap_mean_ci(type_recall, seed=seed)
        table[f"{qtype} 子集"] = {
            "EM(严格正确率)": M.avg(type_em),
            "EM 95%CI": f"[{type_em_ci[0]}, {type_em_ci[1]}]",
            "F1(软正确率)": M.avg(type_f1),
            "F1 95%CI": f"[{type_f1_ci[0]}, {type_f1_ci[1]}]",
            f"Retr Recall@{K_RETRIEVE}": M.avg(type_recall),
            "Recall 95%CI": f"[{type_recall_ci[0]}, {type_recall_ci[1]}]",
            "样本数": len(indexes),
        }

    meta = {
        "数据集": "hotpot_qa / distractor",
        "切分": "validation",
        "采样数": sample,
        "类型分布": _type_distribution(queries),
        "embedding 模型": embed_client.model_name,
        "chat 模型": chat_client.model_name,
        "rerank 模型": rerank_client.model_name if rerank_client else "(未配置)",
        "verifier 配置": verifier,
        "verifier 实际生效": judge_kind_actual,
        "检索模式": retrieval_mode,
    }
    notes = [
        "HotpotQA distractor 评测:每题给 10 段(2 gold + 8 distractor),系统先检索 top-k 再多跳答。",
        "hybrid 为 Meme 主链路；BM25 为不调用 embedding 的检索消融对照，"
        "不应将二者分数混为同一口径。",
        "**污染声明**:dev 集发布于 2018 年,目前主流 LLM 训练集大概率覆盖;本评测仅用于系统设计对比"
        "(检索/Verifier 配置间),不作绝对水平断言。",
        "**EM(严格正确率)**:答案归一化后完全一致(忽略大小写/标点/the&a&an),0/1 平均即「严格答对率」。",
        "**F1(软正确率)**:token 级 precision/recall 调和平均,反映「答对了但措辞略差」(如 "
        "答 `Anomalisa (2015 film)` vs gold `Anomalisa` → F1≈0.5)。业界两个一起报。",
        "verifier 字段说明:none = 无 Verifier baseline;same = 同 chat 模型 self-critique;"
        "cross = 跨 family verifier 模型;compare = 对同一答案同时运行二者。",
        "**漏检率**:Verifier 判过但实际 EM=0 的占比 —— 越低代表 Verifier 越可信。"
        "对比 same vs cross 的漏检率即「为什么不能 self-critique」的硬数据。",
        "EM 会将别名/修饰词差异也计为错误；报告同时以 F1>=0.5 作为实质正确的"
        "近似口径，两组都必须保留，不用 LLM judge 反过来自证正确。",
    ]
    report = write_benchmark_report(
        "hotpotqa", "HotpotQA distractor (L3)",
        table, meta=meta, extra_notes=notes,
        category="rag",
        manifest=run_manifest,
    )
    detail_path = write_benchmark_details(
        "hotpotqa", details, category="rag", manifest=run_manifest
    )
    _write_checkpoint(checkpoint_path, signature, details, completed=True)
    print(f"  报告: {report}\n  明细: {detail_path}")
    return table, details


def _type_distribution(queries: list[dict]) -> str:
    c = Counter(q["qtype"] for q in queries)
    return ", ".join(f"{k}={v}" for k, v in c.most_common())
