# C-MTEB T2Retrieval (L2) 评测报告 20260827-210824

**评测元信息**
- 数据集: C-MTEB/T2Retrieval
- 切分: dev
- corpus 篇数: 1000
- query 条数: 100
- 评测命名空间: eee10000-0000-0000-0000-0000000000c2
- embedding 模型: qwen3.7-text-embedding
- rerank 模型: （未配置）
- 本次写入: 1000 篇

**运行证据**
- Git commit: `b1d6ac2ad82c69c5149c8564927e34aa3fe302a1`
- 工作区包含未提交改动: False
- 夹具 SHA-256: `b7e83ccaae73220467866fe74407ef341199ca7cb589f06ad9ab074d5970ddd2`
- 模型来源: encrypted-app-config
- 模型: `{"embedding": "qwen3.7-text-embedding", "chat": "glm-4.6v", "rerank": "(not configured)", "verifier": "qwen3.8-max"}`
- 参数: `{"embedding_dimensions": 1024, "benchmark": "cmteb-t2", "corpus_limit": 1000, "query_limit": 100, "sample": 100, "verifier": "none", "seed": 42}`

> C-MTEB T2Retrieval 评测：用真实中文搜索场景的 corpus 与 query，证明系统在公共基准上的相对水平。仅作系统设计对比，不作绝对水平断言。
> 指标遵循 C-MTEB 官方协议（k=10）；source_id 用 corpus 原 cid。

| 配置 | nDCG@10 | Recall@10 | MRR@10 |
|---|---|---|---|
| 纯向量 | 0.9688 | 0.9426 | 0.99 |
| 纯BM25 | 0.8825 | 0.8559 | 0.9583 |
| 混合 | 0.9728 | 0.9521 | 0.9867 |