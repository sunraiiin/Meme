# Meme 评测报告 20260827-205305

> 小规模自建 gold 集的离线自测，非大规模 benchmark。
> 记忆/抽取名称匹配口径：归一化 + 包含（更完整或更具体的名视为命中，如「日本京都」命中「京都」），通用自指「用户」仅精确匹配。RAG 文档按文件名精确匹配。

## 运行清单

- 生成时间(UTC): 2026-08-27T12:42:16.492182+00:00
- Git commit: `b1d6ac2ad82c69c5149c8564927e34aa3fe302a1`
- 工作区包含未提交改动: False
- 夹具 SHA-256: `b7e83ccaae73220467866fe74407ef341199ca7cb589f06ad9ab074d5970ddd2`
- 模型来源: encrypted-app-config
- Embedding: qwen3.7-text-embedding
- Chat: glm-4.6v
- Rerank: (not configured)
- Verifier: qwen3.8-max
- 夹具规模: `{"dedup": 3, "extraction": 10, "memory_identity": 9, "memory_retrieval": 19, "memory_retrieval_negative": 8, "rag_negative": 8, "retrieval": 22, "corpus_documents": 10, "dialogues": 17}`
- 参数: `{"embedding_dimensions": 1024, "skip_check": true, "skip_setup": true, "only": "extraction", "corpus_limit": 1000, "query_limit": 100, "sample": 100, "verifier": "none", "seed": 42}`

### 三元组抽取

| 配置 | Precision | Recall | F1 |
|---|---|---|---|
| 实体级 | 0.6817 | 0.7333 | 0.6829 |
| 三元组级 | 0.5667 | 0.65 | 0.5567 |
