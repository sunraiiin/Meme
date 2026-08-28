# HotpotQA distractor (L3) 评测报告 20260827-215215

**评测元信息**
- 数据集: hotpot_qa / distractor
- 切分: validation
- 采样数: 100
- 类型分布: bridge=80, comparison=20
- embedding 模型: qwen3.7-text-embedding
- chat 模型: glm-4.6v
- rerank 模型: (未配置)
- verifier 配置: none
- verifier 实际生效: none
- 检索模式: bm25

**运行证据**
- Git commit: `724c0c0f730c43822515be71579f9a5e64bb2948`
- 工作区包含未提交改动: False
- 夹具 SHA-256: `b7e83ccaae73220467866fe74407ef341199ca7cb589f06ad9ab074d5970ddd2`
- 模型来源: encrypted-app-config
- 模型: `{"embedding": "qwen3.7-text-embedding", "chat": "glm-4.6v", "rerank": "(not configured)", "verifier": "qwen3.8-max"}`
- 参数: `{"embedding_dimensions": 1024, "benchmark": "hotpotqa", "corpus_limit": 1000, "query_limit": 100, "sample": 100, "hotpot_retrieval": "bm25", "verifier": "none", "seed": 42, "resume": true}`

> HotpotQA distractor 评测:每题给 10 段(2 gold + 8 distractor),系统先检索 top-k 再多跳答。
> hybrid 为 Meme 主链路；BM25 为不调用 embedding 的检索消融对照，不应将二者分数混为同一口径。
> **污染声明**:dev 集发布于 2018 年,目前主流 LLM 训练集大概率覆盖;本评测仅用于系统设计对比(检索/Verifier 配置间),不作绝对水平断言。
> **EM(严格正确率)**:答案归一化后完全一致(忽略大小写/标点/the&a&an),0/1 平均即「严格答对率」。
> **F1(软正确率)**:token 级 precision/recall 调和平均,反映「答对了但措辞略差」(如 答 `Anomalisa (2015 film)` vs gold `Anomalisa` → F1≈0.5)。业界两个一起报。
> verifier 字段说明:none = 无 Verifier baseline;same = 同 chat 模型 self-critique;cross = 跨 family verifier 模型;compare = 对同一答案同时运行二者。
> **漏检率**:Verifier 判过但实际 EM=0 的占比 —— 越低代表 Verifier 越可信。对比 same vs cross 的漏检率即「为什么不能 self-critique」的硬数据。

| 配置 | EM(严格正确率) | EM 95%CI | F1(软正确率) | F1 95%CI | Retr Recall@4 | Recall 95%CI | 样本数 | 失败题数 | AvgLatencyMs | P95LatencyMs |
|---|---|---|---|---|---|---|---|---|---|---|
| answer baseline | 0.45 | [0.36, 0.54] | 0.5554 | [0.465, 0.641] | 0.7079 | [0.6535, 0.7624] | 100 | 1 | 10432.66 | 28681.45 |
| bridge 子集 | 0.4 | [0.2875, 0.5125] | 0.5171 | [0.4143, 0.618] | 0.7125 | [0.65, 0.775] | 80 |  |  |  |
| comparison 子集 | 0.65 | [0.45, 0.85] | 0.7083 | [0.5083, 0.8833] | 0.675 | [0.525, 0.8] | 20 |  |  |  |