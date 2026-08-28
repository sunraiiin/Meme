# HotpotQA distractor (L3) 评测报告 20260828-102108

**评测元信息**
- 数据集: hotpot_qa / distractor
- 切分: validation
- 采样数: 30
- 类型分布: bridge=24, comparison=6
- embedding 模型: qwen3.7-text-embedding
- chat 模型: glm-4.6v
- rerank 模型: (未配置)
- verifier 配置: compare
- verifier 实际生效: same + cross (qwen3.8-max)
- 检索模式: bm25

**运行证据**
- Git commit: `093ac29a53fb074274ed1199d745f520670d4064`
- 工作区包含未提交改动: False
- 夹具 SHA-256: `b7e83ccaae73220467866fe74407ef341199ca7cb589f06ad9ab074d5970ddd2`
- 模型来源: encrypted-app-config
- 模型: `{"embedding": "qwen3.7-text-embedding", "chat": "glm-4.6v", "rerank": "(not configured)", "verifier": "qwen3.8-max"}`
- 参数: `{"embedding_dimensions": 1024, "benchmark": "hotpotqa", "corpus_limit": 1000, "query_limit": 100, "sample": 30, "hotpot_retrieval": "bm25", "verifier": "compare", "seed": 42, "resume": true}`

> HotpotQA distractor 评测:每题给 10 段(2 gold + 8 distractor),系统先检索 top-k 再多跳答。
> hybrid 为 Meme 主链路；BM25 为不调用 embedding 的检索消融对照，不应将二者分数混为同一口径。
> **污染声明**:dev 集发布于 2018 年,目前主流 LLM 训练集大概率覆盖;本评测仅用于系统设计对比(检索/Verifier 配置间),不作绝对水平断言。
> **EM(严格正确率)**:答案归一化后完全一致(忽略大小写/标点/the&a&an),0/1 平均即「严格答对率」。
> **F1(软正确率)**:token 级 precision/recall 调和平均,反映「答对了但措辞略差」(如 答 `Anomalisa (2015 film)` vs gold `Anomalisa` → F1≈0.5)。业界两个一起报。
> verifier 字段说明:none = 无 Verifier baseline;same = 同 chat 模型 self-critique;cross = 跨 family verifier 模型;compare = 对同一答案同时运行二者。
> **漏检率**:Verifier 判过但实际 EM=0 的占比 —— 越低代表 Verifier 越可信。对比 same vs cross 的漏检率即「为什么不能 self-critique」的硬数据。
> EM 会将别名/修饰词差异也计为错误；报告同时以 F1>=0.5 作为实质正确的近似口径，两组都必须保留，不用 LLM judge 反过来自证正确。

| 配置 | EM(严格正确率) | EM 95%CI | F1(软正确率) | F1 95%CI | Retr Recall@4 | Recall 95%CI | 样本数 | 失败题数 | AvgLatencyMs | P95LatencyMs | Verifier 判过率 | 漏检率(judge 通过但 EM=0) | 误拒率(judge 拒绝但 EM=1) | 实质错误放行率(F1<0.5) | 实质正确误拒率(F1>=0.5) | 与 EM 一致率 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| answer baseline | 0.3333 | [0.1667, 0.5] | 0.4116 | [0.2496, 0.5778] | 0.6667 | [0.5667, 0.7667] | 30 | 0 | 32403.89 | 50199.01 | - | - | - | - | - | - |
| judge=same | 0.3333 | [0.1667, 0.5] | 0.4116 | [0.2496, 0.5778] | 0.6667 | [0.5667, 0.7667] | 30 | 0 | 32403.89 | 50199.01 | 0.6 | 0.5556 | 0.1667 | 0.3889 | 0.1667 | 0.6 |
| judge=cross | 0.3333 | [0.1667, 0.5] | 0.4116 | [0.2496, 0.5778] | 0.6667 | [0.5667, 0.7667] | 30 | 0 | 32403.89 | 50199.01 | 0.5333 | 0.5 | 0.1429 | 0.3125 | 0.1429 | 0.6667 |
| bridge 子集 | 0.25 | [0.0833, 0.4167] | 0.3478 | [0.1812, 0.5397] | 0.6875 | [0.5625, 0.8125] | 24 |  |  |  |  |  |  |  |  |  |
| comparison 子集 | 0.6667 | [0.3333, 1.0] | 0.6667 | [0.3333, 1.0] | 0.5833 | [0.5, 0.75] | 6 |  |  |  |  |  |  |  |  |  |