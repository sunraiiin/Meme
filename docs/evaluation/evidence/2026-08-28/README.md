# 2026-08-28 可复核评测证据

本目录固化 Issue #81 的原始 Markdown 报告和逐题 JSON 明细。它们保留运行时的 Git commit、工作区状态、夹具指纹、样本规模、模型名称和参数；不包含 API Key、真实用户 ID 或业务数据。

## 证据索引

| 任务 | 样本与口径 | 报告 | 明细 | 代码版本 |
| --- | --- | --- | --- | --- |
| RAG 业务回归 | 22 个正样本、8 个负样本，top-5 | [报告](l1-rag-report.md) | [明细](l1-rag-details.json) | `b1d6ac2` |
| 记忆检索旧口径 | 19 个混合目标、8 个负样本，top-5 | [报告](l1-memory-legacy-report.md) | [明细](l1-memory-legacy-details.json) | `b1d6ac2` |
| 记忆答案实体重算 | 复用上述 19 条排序，只将主要答案实体视为相关 | — | [重算结果](memory-answer-rescore.json) | `b1d6ac2` |
| 记忆抽取 | 10 段对话，实体级和三元组级宏平均 | [报告](l1-extraction-report.md) | [明细](l1-extraction-details.json) | `b1d6ac2` |
| 实体去重 | 3 组别名，Pairwise 宏平均 | [报告](l1-dedup-report.md) | [明细](l1-dedup-details.json) | `b1d6ac2` |
| 身份安全 | 9 个确定性场景 | [报告](l1-identity-report.md) | [明细](l1-identity-details.json) | `b1d6ac2` |
| C-MTEB T2Retrieval | dev 的有界切片：1000 corpus / 100 query | [报告](cmteb-t2-1000x100-report.md) | [明细](cmteb-t2-1000x100-details.json) | `b1d6ac2` |
| HotpotQA BM25 消融 | seed 42，100 题，top-4 | [报告](hotpotqa-bm25-100-report.md) | [明细](hotpotqa-bm25-100-details.json) | `724c0c0` |
| HotpotQA Verifier A/B | 同一批答案分别交给 same/cross judge，30 题 | [报告](hotpotqa-verifier-bm25-30-report.md) | [明细](hotpotqa-verifier-bm25-30-details.json) | `093ac29` |

## 必须同时阅读的边界

1. 自建集用于业务回归和失败定位，规模不足以证明通用能力。
2. 旧记忆 gold 把主要答案和上下文实体混在一起，几乎每题都包含 canonical self「用户」，导致 Recall@5=0.7895、MRR=0.8596 被抬高。按主要答案实体重算后，Recall@5=0.5789、MRR=0.2105；旧结果只保留作审计，不作为当前质量结论。
3. C-MTEB 本次是加载器按顺序截取的有界切片，并非官方全量榜单协议，可能存在顺序偏差。它只能比较本次相同切片上的向量、BM25 和混合策略。
4. HotpotQA 使用公开 dev 数据，可能已进入模型训练语料；本次 BM25 是不调用 Embedding 的消融实验，不代表 Meme 的 hybrid 主链路。
5. hybrid HotpotQA 主链重跑因 Embedding 服务免费配额耗尽而中止，没有生成有效报告。恢复额度后应使用 checkpoint 续跑，不应用 BM25 分数替代。
6. Verifier 结论以修复后的 `max_tokens=1024` 结果为准。Comet 旧实验使用 `max_tokens=4`，推理模型没有空间输出最终 0/1，因而出现 same 通过率 0%；该旧结果不能用来证明同模型自评必然失败。

## 证据使用规则

- 对外展示指标时必须同时给出数据集、样本量、检索模式和限制。
- 调参后不得覆盖本目录；应新建日期目录，保留前后结果和失败明细。
- 只有报告清单显示干净工作区、夹具指纹可对应、逐题明细可读取时，结果才可用于项目叙事。
