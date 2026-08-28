# Meme 评测体系：让质量结论可复核、可定位、可迭代

## 1. 一句话亮点与简历表述

Meme 将 RAG、记忆召回、三元组抽取、实体去重、身份安全和多跳问答拆成分层评测，统一保存运行代码版本、数据指纹、模型参数、聚合指标与逐题明细；通过正负样本和消融实验发现“正向召回很好但不会拒答”、记忆 gold 泄漏及 Verifier 截断等问题，使分数能够真正指导系统改进。

可用于简历的紧凑版本：

> 建立覆盖 RAG、记忆检索、知识抽取、实体去重与身份安全的分层评测体系，固化 Git 版本、数据指纹、模型配置、置信区间和逐题失败明细；在自建中文集及 C-MTEB/HotpotQA 有界实验中完成向量、BM25、混合检索和 Verifier A/B 对照，定位无关召回、标注泄漏与 judge 输出截断等质量问题，并将结果转化为相关性门控、记忆召回和评审策略的迭代依据。

## 2. 一分钟完整讲解

这个项目最初有一些很漂亮的单点分数，但只有最终数字，没有稳定的数据版本、逐题结果和负样本，无法确认分数是否真实代表产品质量。我把评测拆为三层：第一层用小规模中文 gold 集回归 Meme 的真实 RAG 和记忆链路；第二层用 C-MTEB 有界切片比较中文检索策略；第三层用 HotpotQA distractor 观察“检索后再回答”的多跳链路，并在同一批答案上比较同模型与跨模型 Verifier。

每次运行会保存 Git commit、工作区状态、夹具 SHA-256、样本量、模型和参数，报告之外还保存逐题召回、答案和错误。这样不仅能看平均分，还能回答“错在哪”。本轮发现了三个比高分更有价值的问题：RAG 正样本 Recall@5 达到 1.0，但混合检索在 8 个负样本上全部强行返回结果；记忆旧 gold 把「用户」这个上下文实体也算答案，修正后主要答案 Recall@5 从 0.7895 降到 0.5789；Comet 的 same-verifier 通过率 0% 来自 `max_tokens=4` 截断，而不是可靠的 self-critique 结论。评测因此给出了明确的下一步：先做相关性门控和记忆目标召回，再扩大数据和优化模型。

## 3. 为什么要分层评测

单一“回答正确率”无法区分错误来自哪一层：

```text
资料/对话写入
  → 检索是否找到证据
  → 抽取是否得到正确实体和关系
  → 身份与别名是否安全融合
  → 模型是否基于证据回答
  → Verifier 是否正确放行或拒绝
```

因此评测矩阵按可行动性拆分：

| 层级 | 任务 | 核心指标 | 能定位的问题 |
| --- | --- | --- | --- |
| L1 业务回归 | RAG 正/负样本 | Recall@5、MRR、nDCG、NoHitAccuracy | 找不到资料或强行召回噪声 |
| L1 业务回归 | 记忆正/负样本 | Recall@5、MRR、NoHitAccuracy | 个人事实漏召回、上下文泄漏、无关记忆注入 |
| L1 业务回归 | 实体/三元组抽取 | Precision、Recall、F1 | 漏抽、误抽、谓词错误 |
| L1 业务回归 | 实体去重 | Pairwise Precision/Recall/F1 | 错合并或别名未合并 |
| L1 安全回归 | canonical self | CaseAccuracy、UnsafeSelfLinkRate | 把第三方姓名误绑为本人 |
| L2 公共检索 | C-MTEB 有界切片 | nDCG@10、Recall@10、MRR@10 | 检索策略在统一中文数据上的相对差异 |
| L3 端到端 | HotpotQA distractor | Retrieval Recall@4、EM、F1 | 多跳证据与最终回答之间的断点 |
| L3 质量评审 | same/cross Verifier | 通过率、错误放行率、正确误拒率 | Verifier 是否适合当硬门槛 |

## 4. 可复现机制

### 4.1 隔离与清单

L1 使用固定评测用户和独立命名空间写入 Elasticsearch、Neo4j，不读取真实用户资料。模型既可以来自独立 `eval/.env.eval`，也可以只在运行时复用应用已加密保存的连接；用户 ID 和密钥不会进入报告。

每份报告记录：

- UTC 时间和 Git commit。
- 工作区是否包含未提交改动。
- fixture SHA-256 和各任务样本数。
- 实际模型名称及必要运行参数。
- 聚合指标、延迟均值和 P95。
- 可确定采样任务的随机种子和 bootstrap 95% 置信区间。

逐题 JSON 保存候选、命中、答案、分数和错误。HotpotQA 每完成一题增量写 checkpoint，同参数可续跑；单题网络错误记为 0 并继续，避免几十分钟的运行只留下半段终端输出。

### 4.2 正样本之外必须有负样本

最近邻检索永远可以返回“最像”的内容，但最像不等于相关。只测正样本会掩盖这种问题。因此 RAG 和记忆各增加 8 个“系统里没有答案”的问题，并用 NoHitAccuracy 与 FalsePositiveRate 衡量系统能否停止召回。

### 4.3 消融和主链分开报告

HotpotQA 的 `hybrid` 才是 Meme 主检索链路；`bm25` 是为了在不调用 Embedding 时独立观察关键词检索和回答能力的消融基线。报告始终保存 `hotpot_retrieval`，文档也不把两者分数混用。

## 5. 2026-08-28 基线结果

完整原始报告和逐题明细见 [证据目录](../evaluation/evidence/2026-08-28/README.md)。下表只保留能支持工程判断的核心数字。

### 5.1 自建中文业务回归集

| 模块 | 样本 | 结果 | 结论 |
| --- | --- | --- | --- |
| RAG 正向检索 | 10 文档、22 题 | 向量/BM25/混合 Recall@5 均为 1.0；混合 nDCG@5=0.9964 | 小集上的正确来源召回稳定，无法据此证明复杂资料能力 |
| RAG 负样本 | 8 题 | 混合 NoHitAccuracy=0，FalsePositiveRate=1.0 | 当前缺少统一绝对相关性门控 |
| 记忆主要答案召回 | 19 题 | Recall@5=0.5789，MRR=0.2105，nDCG=0.3028 | 人物、地点、职业、偏好等目标实体存在明显漏召回 |
| 记忆负样本 | 8 题 | NoHitAccuracy=0，FalsePositiveRate=1.0 | 无关个人问题仍会注入最近邻记忆 |
| 记忆抽取 | 10 段 | 实体 F1=0.6829，三元组 F1=0.5567 | 抽取仍是图谱质量主要瓶颈之一 |
| 实体去重 | 3 组 | Pairwise P=0.6667、R=0.5、F1=0.5556 | 既有漏合并，也不能只报 Precision 掩盖保守策略 |
| 身份安全 | 9 例 | CaseAccuracy=1.0，UnsafeSelfLinkRate=0 | 确定性 canonical self 规则在当前回归集通过 |

旧记忆报告的 Recall@5=0.7895、MRR=0.8596 是“主要答案 + 上下文实体”混合口径；几乎每题都把 canonical self「用户」列为相关，因此第一名命中「用户」也会得分。证据目录保留旧报告以便审计，但项目叙事使用排除上下文实体后的 0.5789，不用被污染的高分。

### 5.2 C-MTEB T2Retrieval 有界切片

| 配置 | nDCG@10 | Recall@10 | MRR@10 |
| --- | --- | --- | --- |
| 向量 | 0.9688 | 0.9426 | 0.9900 |
| BM25 | 0.8825 | 0.8559 | 0.9583 |
| 混合 | 0.9728 | 0.9521 | 0.9867 |

本次仅取 dev 中按加载顺序得到的 1000 个 corpus 和 100 个 query，因此是同一切片上的策略对比，不是 C-MTEB 官方全量成绩。混合在 nDCG 和 Recall 上略优于单路，但差值较小；后续需要 seeded query 采样、纳入每个 query 的全部相关文档并随机加入干扰文档，降低顺序偏差。

### 5.3 HotpotQA BM25 消融

seed 42 的 100 题包含 80 道 bridge、20 道 comparison：

| 指标 | 结果 |
| --- | --- |
| Retrieval Recall@4 | 0.7079，95% CI [0.6535, 0.7624] |
| EM | 0.45，95% CI [0.36, 0.54] |
| F1 | 0.5554，95% CI [0.465, 0.641] |
| 延迟 | 平均 10.43 秒，P95 28.68 秒 |

逐题分析中有 16 题已经找全 supporting facts 但 EM 仍错误，说明生成或答案规范化存在问题；另有 14 题没有找全证据却严格答对，可能来自模型先验或公开数据污染。因此 HotpotQA 只适合本项目内部做同模型、同样本的策略对照。

hybrid 100 题主链在第 86 题遇到 Embedding 服务 `AllocationQuota.FreeTierOnly`，运行中止且没有形成有效报告。代码已经加入每题 checkpoint 和错误隔离；额度恢复后再续跑，当前不引用历史 Comet 分数，也不拿 BM25 结果冒充 hybrid。

### 5.4 Verifier A/B 与截断缺陷

修复后在同一批 30 个 BM25 答案上同时运行 same 和 cross judge：

| Judge | 通过率 | EM 错误放行率 | F1<0.5 错误放行率 | EM 正确误拒率 | 与 EM 一致率 |
| --- | --- | --- | --- | --- | --- |
| same | 0.6000 | 0.5556 | 0.3889 | 0.1667 | 0.6000 |
| cross | 0.5333 | 0.5000 | 0.3125 | 0.1429 | 0.6667 |

cross 在这个小样本上略好，但两者仍会放行较多错误答案，不适合直接作为硬质量门槛。Verifier 更适合输出可观测质量信号，或在重写成本可控时触发下一轮，而不是把一次 0/1 当作最终真相。

Comet 历史报告的 same 通过率 0%、cross 通过率 95% 不能复用。代码检查发现 judge 只允许 `max_tokens=4`，而推理模型会先消耗 token 思考，最终 0/1 被截断；同项目的回答链路本身也注明推理模型至少需要 1024。Meme 将上限改为 1024，并从末尾解析独立的 0/1 后，same 通过率恢复到 60%。这说明评测脚本本身也必须被测试和审计。

## 6. 失败如何转化为迭代计划

1. **先做检索门控。** 用负样本标定向量、BM25 和混合分数阈值，区分“没有答案”和“返回 top-k”；同时记录过滤原因。
2. **修记忆目标召回。** 围绕 8 个失败答案（产品经理、团子、拿铁、王磊、成都、复旦大学、摄影）检查实体向量、陈述召回、一跳扩展和结果聚合，而不是继续堆图谱节点。
3. **提升抽取与去重。** 将逐题 missed/extra 样例加入回归集，分别优化 prompt、受控谓词和候选融合；去重必须同时观察 Precision 与 Recall。
4. **改进公共基准采样。** 对 C-MTEB 使用确定性随机 query 和完整相关文档；任何子集都附带样本构造方式。
5. **补跑 hybrid HotpotQA。** 恢复 Embedding 额度后用相同 seed 和样本运行主链，才可与 BM25 做有效消融。
6. **Verifier 先当信号。** 扩大标注集并用 EM、F1 与人工抽样共同校准，再决定是否触发 rewrite；当前不作为自动修复的唯一条件。

## 7. 如何复现

以下命令在 `api/` 目录执行。`<MODEL_CONFIG_USER_ID>` 仅用于读取本机已加密模型连接，不会写入报告；也可以改用 `eval/.env.eval`。

```powershell
# L1：重建隔离数据并运行全部业务回归
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --reset

# 只重跑某一层
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --skip-setup --only retrieval
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --skip-setup --only memory
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --skip-setup --only extraction
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --skip-setup --only dedup
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --skip-setup --only identity

# L2：当前有界 C-MTEB 对照
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --benchmark cmteb-t2 --corpus-limit 1000 --query-limit 100

# L3：BM25 消融及 Verifier A/B
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --benchmark hotpotqa --sample 100 --hotpot-retrieval bm25 --seed 42 --resume
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --benchmark hotpotqa --sample 30 --hotpot-retrieval bm25 --verifier compare --seed 42 --resume

# L3：额度恢复后补跑 Meme hybrid 主链
uv run python -m eval.run_eval --model-user-id <MODEL_CONFIG_USER_ID> --benchmark hotpotqa --sample 100 --hotpot-retrieval hybrid --seed 42 --resume
```

Hugging Face 数据缓存可通过 `HF_HOME`、`HF_DATASETS_CACHE` 指向空间充足的磁盘。`eval/results/` 默认不入库；要形成可引用基线，应挑选报告和明细复制到新的 `docs/evaluation/evidence/<日期>/`，不得覆盖旧证据。

## 8. 面试完整讲法

可以按“问题—行动—结果—反思”讲，而不用生硬背 STAR 标签：

> 项目原来能跑出 RAG Recall@5=1.0、记忆 Recall@5=0.82 一类数字，但缺少版本、逐题证据和负样本，我无法判断这些数字是否可信。于是我把系统拆成检索、抽取、去重、身份和端到端问答五类任务，给每次运行增加 Git commit、数据指纹、模型参数、置信区间和逐题明细，并加入无答案负样本及 BM25/hybrid、same/cross Verifier 对照。结果发现 RAG 正向召回虽高，但负样本全部误召回；记忆 gold 因把通用“用户”当答案而抬高，按主要答案重算后 Recall@5 只有 0.5789；还定位到 Verifier 的 0% 通过率其实是四个 token 截断。最终我没有继续包装高分，而是得到可复现的质量基线，并把下一阶段明确收敛到相关性门控、记忆召回和评测协议修正。

## 9. 高频追问

### Q1：为什么 Recall@5=1.0 还不能说明 RAG 做得好？

因为 22 道题规模小且都保证有答案。系统对 8 道无答案问题的混合检索 FalsePositiveRate=1.0，说明它会把不相关最近邻也交给模型。完整质量至少要同时观察正向召回、负样本拒绝、排序、生成忠实度和数据覆盖范围。

### Q2：记忆分数为什么从 0.7895 降到 0.5789？

不是代码退化，而是修正了 gold。旧标注把回答需要的实体和背景上下文都算相关，canonical self「用户」几乎每题都存在，因此召回「用户」也算命中。新口径只把真正回答问题的目标实体算相关，更能反映用户问“我的职业是什么”时是否找到“产品经理”。

### Q3：为什么不用同模型 self-critique？

不能先验断言同模型一定不行。本次修复后，cross 的错误放行率和一致率略优于 same，但 30 题不足以得出普遍结论，而且两者都不够可靠。正确做法是在同一批答案上做 A/B，报告放行与误拒，并先把 Verifier 当质量信号。Comet 的 same 0% 主要是输出被四个 token 截断，不能作为模型偏差证据。

### Q4：为什么不用人工逐题阅读所有结果？

指标应由脚本统一计算，人工不需要逐题参与运行。逐题明细的作用是对聚合结果做抽样审计、分析失败类型和修正 gold，而不是手工给每次运行算分。对高风险或主观指标，可以做双人标注和一致性统计。

### Q5：这些结果能够复现吗？

仓库已经保存代码版本、fixture 指纹、模型名称、参数、随机种子、报告和逐题明细。第三方仍需拥有兼容模型连接，生成模型结果也可能有随机波动，因此“可复现”指评测协议和证据链可复核，不承诺每次小数完全一致。

### Q6：为什么 C-MTEB 分数很高却不当官方成绩？

本次只运行按加载顺序截取的 1000 corpus / 100 query，候选范围和官方全量不同，也可能有顺序偏差。它适合同切片内比较三种检索策略，不适合与榜单或别人的全量结果横向比较。

### Q7：下一步最值得做什么？

第一优先级是相关性门控，因为它同时影响 RAG 和记忆的无关上下文注入；第二是针对记忆的 8 个明确漏召回样例修正召回与聚合；之后再补跑 hybrid HotpotQA、扩大抽取与去重 gold。顺序由失败证据决定，而不是由哪个功能更容易展示决定。

## 10. 代码与证据入口

- [评测运行说明](../../api/eval/README.md)
- [统一入口](../../api/eval/run_eval.py)
- [运行清单](../../api/eval/run_manifest.py)
- [指标与统计](../../api/eval/metrics.py)
- [HotpotQA runner](../../api/eval/benchmarks/hotpotqa/runner.py)
- [本次证据基线](../evaluation/evidence/2026-08-28/README.md)
