"""检索评测：RAG 四配置对比 + 记忆检索。指标 Recall@k / Precision@k / MRR / nDCG@k。

返回 (指标表, 明细列表)。明细记录每题召回了哪些、命中没、漏了哪些，供调策略。
"""
import json
import time
from pathlib import Path

from app.core.memory.retrieval.searcher import search_memory
from eval import clients, metrics
from eval.eval_config import EVAL_USER_ID
from eval.stats import latency_summary

_GOLD = Path(__file__).parent.parent / "fixtures" / "gold"
K = 5
RECALL = 20


def _load(name: str) -> list[dict]:
    return json.loads((_GOLD / name).read_text(encoding="utf-8"))


def _score(
    per_query: list[tuple[list, list]], latencies_ms: list[float] | None = None
) -> dict:
    result = {
        f"Recall@{K}": metrics.avg([metrics.recall_at_k(r, g, K) for r, g in per_query]),
        f"Prec@{K}": metrics.avg([metrics.precision_at_k(r, g, K) for r, g in per_query]),
        "MRR": metrics.avg([metrics.mrr(r, g) for r, g in per_query]),
        f"nDCG@{K}": metrics.avg([metrics.ndcg_at_k(r, g, K) for r, g in per_query]),
    }
    result.update(latency_summary(latencies_ms or []))
    return result


def _subset(
    pairs: list[tuple[list, list]], latencies: list[float], indexes: list[int]
) -> tuple[list[tuple[list, list]], list[float]]:
    return [pairs[i] for i in indexes], [latencies[i] for i in indexes]


def _detail(question: str, gold: list, ranked: list) -> dict:
    topk = ranked[:K]
    return {
        "question": question,
        "gold": gold,
        "retrieved_topk": topk,
        "hit": bool(set(topk) & set(gold)),
        "missed": [g for g in gold if g not in topk],
    }


async def eval_rag(embed_client, rerank_client) -> tuple[dict, list]:
    data = _load("retrieval.json")
    uid = str(EVAL_USER_ID)
    vec, bm, hyb, hyb_rr = [], [], [], []
    vec_ms: list[float] = []
    bm_ms: list[float] = []
    hyb_ms: list[float] = []
    hyb_rr_ms: list[float] = []
    details: list[dict] = []
    total = len(data)
    for i, item in enumerate(data, 1):
        q, gold = item["question"], item.get("relevant_doc_ids", [])
        print(f"    [RAG] {i}/{total} {q[:24]}…")
        started = time.perf_counter()
        rv = await clients.retrieve_vector(embed_client, uid, q, RECALL)
        vec_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        rb = await clients.retrieve_bm25(uid, q, RECALL)
        bm_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        rh = await clients.retrieve_hybrid(embed_client, uid, q, RECALL)
        hybrid_elapsed = (time.perf_counter() - started) * 1000
        hyb_ms.append(hybrid_elapsed)
        vec.append((rv, gold))
        bm.append((rb, gold))
        hyb.append((rh, gold))
        d = {"question": q, "gold": gold,
             "vector_topk": rv[:K], "bm25_topk": rb[:K], "hybrid_topk": rh[:K],
             "hybrid_hit": bool(set(rh[:K]) & set(gold))}
        if rerank_client:
            started = time.perf_counter()
            rr = await clients.rerank_sources(rerank_client, uid, q, rh[:RECALL], K)
            hyb_rr_ms.append(hybrid_elapsed + (time.perf_counter() - started) * 1000)
            hyb_rr.append((rr, gold))
            d["hybrid_rerank_topk"] = rr[:K]
        details.append(d)

    table = {
        "纯向量": _score(vec, vec_ms),
        "纯BM25": _score(bm, bm_ms),
        "混合": _score(hyb, hyb_ms),
    }
    if hyb_rr:
        table["混合+rerank"] = _score(hyb_rr, hyb_rr_ms)

    single_indexes = [i for i, item in enumerate(data) if len(item.get("relevant_doc_ids", [])) == 1]
    multi_indexes = [i for i, item in enumerate(data) if len(item.get("relevant_doc_ids", [])) > 1]
    if single_indexes:
        pairs, timings = _subset(hyb, hyb_ms, single_indexes)
        table["混合·单文档题"] = _score(pairs, timings)
    if multi_indexes:
        pairs, timings = _subset(hyb, hyb_ms, multi_indexes)
        table["混合·多文档题"] = _score(pairs, timings)
    return table, details


async def eval_memory(embed_client) -> tuple[dict, list]:
    data = _load("memory_retrieval.json")
    answer_pairs: list[tuple[list, list]] = []
    context_pairs: list[tuple[list, list]] = []
    details: list[dict] = []
    latencies_ms: list[float] = []
    total = len(data)
    for i, item in enumerate(data, 1):
        q = item["question"]
        answer_gold = item.get("answer_entities", [])
        context_gold = item.get("context_entities", [])
        all_gold = answer_gold + context_gold
        print(f"    [记忆检索] {i}/{total} {q[:24]}…")
        started = time.perf_counter()
        hits = await search_memory(
            embed_client=embed_client, user_id=EVAL_USER_ID, query=q, top_k=RECALL
        )
        latencies_ms.append((time.perf_counter() - started) * 1000)
        ranked_raw = [h.get("name") for h in hits if h.get("name")]
        ranked = metrics.canonicalize(ranked_raw, all_gold)
        answer_ranked = metrics.canonicalize(ranked_raw, answer_gold)
        context_ranked = metrics.canonicalize(ranked_raw, context_gold)
        answer_pairs.append((answer_ranked, answer_gold))
        context_pairs.append((context_ranked, context_gold))
        d = _detail(q, answer_gold, answer_ranked)
        d["answer_entities"] = answer_gold
        d["context_entities"] = context_gold
        d["context_retrieved_topk"] = context_ranked[:K]
        d["all_gold_canonicalized_topk"] = ranked[:K]
        d["retrieved_raw_topk"] = ranked_raw[:K]  # 保留原始召回名便于排查
        details.append(d)
    return {
        "答案实体召回(主指标)": _score(answer_pairs, latencies_ms),
        "上下文实体覆盖(辅助指标)": _score(context_pairs, latencies_ms),
    }, details


def _rejection_score(rows: list[dict]) -> dict:
    total = len(rows)
    rejected = sum(1 for row in rows if row["returned_count"] == 0)
    returned = sum(row["returned_count"] for row in rows)
    latencies = [row["latency_ms"] for row in rows]
    result = {
        "NoHitAccuracy": round(rejected / total, 4) if total else 0.0,
        "FalsePositiveRate": round((total - rejected) / total, 4) if total else 0.0,
        "AvgReturned": round(returned / total, 2) if total else 0.0,
    }
    result.update(latency_summary(latencies))
    return result


async def eval_rag_negative(embed_client) -> tuple[dict, list]:
    """评估无相关资料问题是否仍会被强行匹配到某份文档。"""
    data = _load("rag_negative.json")
    uid = str(EVAL_USER_ID)
    variants = {
        "纯向量": lambda q: clients.retrieve_vector(embed_client, uid, q, RECALL),
        "纯BM25": lambda q: clients.retrieve_bm25(uid, q, RECALL),
        "混合": lambda q: clients.retrieve_hybrid(embed_client, uid, q, RECALL),
    }
    table: dict[str, dict] = {}
    details: list[dict] = []
    for name, retrieve in variants.items():
        rows: list[dict] = []
        for item in data:
            started = time.perf_counter()
            ranked = await retrieve(item["question"])
            row = {
                "variant": name,
                "question": item["question"],
                "category": item.get("category"),
                "returned_count": len(ranked[:K]),
                "retrieved_topk": ranked[:K],
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            rows.append(row)
            details.append(row)
        table[name] = _rejection_score(rows)
    return table, details


async def eval_memory_negative(embed_client) -> tuple[dict, list]:
    """评估图谱中不存在的个人事实是否被错误召回。"""
    data = _load("memory_retrieval_negative.json")
    rows: list[dict] = []
    for item in data:
        started = time.perf_counter()
        hits = await search_memory(
            embed_client=embed_client,
            user_id=EVAL_USER_ID,
            query=item["question"],
            top_k=RECALL,
        )
        rows.append(
            {
                "question": item["question"],
                "category": item.get("category"),
                "returned_count": len(hits[:K]),
                "retrieved_topk": [hit.get("name") for hit in hits[:K]],
                "top_score": hits[0].get("score") if hits else None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    return {"图谱无关事实拒绝": _rejection_score(rows)}, rows
