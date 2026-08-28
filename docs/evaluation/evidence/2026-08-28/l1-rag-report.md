# Meme 评测报告 20260827-204135

> 小规模自建 gold 集的离线自测，非大规模 benchmark。
> 记忆/抽取名称匹配口径：归一化 + 包含（更完整或更具体的名视为命中，如「日本京都」命中「京都」），通用自指「用户」仅精确匹配。RAG 文档按文件名精确匹配。

## 运行清单

- 生成时间(UTC): 2026-08-27T12:41:19.535532+00:00
- Git commit: `b1d6ac2ad82c69c5149c8564927e34aa3fe302a1`
- 工作区包含未提交改动: False
- 夹具 SHA-256: `b7e83ccaae73220467866fe74407ef341199ca7cb589f06ad9ab074d5970ddd2`
- 模型来源: encrypted-app-config
- Embedding: qwen3.7-text-embedding
- Chat: glm-4.6v
- Rerank: (not configured)
- Verifier: qwen3.8-max
- 夹具规模: `{"dedup": 3, "extraction": 10, "memory_identity": 9, "memory_retrieval": 19, "memory_retrieval_negative": 8, "rag_negative": 8, "retrieval": 22, "corpus_documents": 10, "dialogues": 17}`
- 参数: `{"embedding_dimensions": 1024, "skip_check": true, "skip_setup": true, "only": "retrieval", "corpus_limit": 1000, "query_limit": 100, "sample": 100, "verifier": "none", "seed": 42}`

### RAG 检索

| 配置 | Recall@5 | Prec@5 | MRR | nDCG@5 | AvgLatencyMs | P95LatencyMs |
|---|---|---|---|---|---|---|
| 纯向量 | 1.0 | 0.2273 | 1.0 | 0.9964 | 247.26 | 446.68 |
| 纯BM25 | 1.0 | 0.2273 | 1.0 | 0.9944 | 26.79 | 41.12 |
| 混合 | 1.0 | 0.2273 | 1.0 | 0.9964 | 267.04 | 442.64 |
| 混合·单文档题 | 1.0 | 0.2 | 1.0 | 1.0 | 268.55 | 487.95 |
| 混合·多文档题 | 1.0 | 0.4 | 1.0 | 0.9732 | 257.46 | 274.1 |

### RAG 负样本

| 配置 | NoHitAccuracy | FalsePositiveRate | AvgReturned | AvgLatencyMs | P95LatencyMs |
|---|---|---|---|---|---|
| 纯向量 | 0.0 | 1.0 | 5.0 | 216.84 | 281.88 |
| 纯BM25 | 0.125 | 0.875 | 3.75 | 21.33 | 32.18 |
| 混合 | 0.0 | 1.0 | 5.0 | 245.81 | 294.1 |
