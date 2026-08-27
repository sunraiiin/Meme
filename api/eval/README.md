# Meme 离线评测（eval）

用业界标准指标，**自包含、可复现**地评测 RAG 检索与记忆系统（抽取 / 去重 / 检索）。

> 自带语料和标注、自己写入再评测，不读取现有用户业务数据。默认使用独立模型配置；本地也可以只复用应用中已加密保存的模型连接，密钥不会复制到评测文件。
> 不进生产镜像（`api/.dockerignore` 已排除 `eval/`），但进 git / 开源供他人复现。

---

## 设计要点

- **安全模型配置**：默认从 `eval/.env.eval` 建立独立客户端；`--model-user-id` 仅在本地读取该用户的加密模型配置，评测数据仍写入隔离命名空间，报告不会保存真实用户 ID 或密钥。
- **固定命名空间**：所有评测数据写在 `EVAL_USER_ID`（固定 UUID）名下，与真实用户隔离，可一键清理。
- **写入到评测全闭环**：`setup` 复用 app 真实的分块/向量化/萃取链路把 fixtures 写进 ES/Neo4j（顺带也验证了写入链路），再评测。
- **双输出**：① 数值报告（Markdown 指标表）② 明细（JSON：每题召回了啥/命中没、每段抽了啥 vs gold），看明细可定位问题、调系统策略。
- **证据清单**：每次报告记录 Git commit、工作区状态、夹具 SHA-256、样本规模、模型名称和运行参数，避免只留下无法复核的分数。
- **正负样本并行**：除“应该召回什么”外，同时测无相关知识和缺失个人事实是否会被强行召回。

---

## 目录

```
eval/
├── .env.eval.example     模型配置模板（复制为 .env.eval 填 key）
├── eval_config.py        独立配置/应用加密配置建 client + EVAL_USER_ID
├── run_manifest.py       Git、数据指纹、模型与参数快照
├── stats.py              延迟统计与 bootstrap 置信区间
├── metrics.py            标准指标：Recall@k/Prec@k/MRR/nDCG、集合P/R/F1、Pairwise F1
├── clients.py            ES 检索变体（纯向量/BM25/混合/+rerank）+ 客户端清理
├── fixtures/             自带测试数据
│   ├── corpus/*.md       知识库语料（写入 ES）
│   ├── dialogues.json    对话（萃取进 Neo4j）
│   └── gold/             正向检索、负样本、抽取、去重与身份安全标注
├── pipeline/
│   ├── setup.py          写入：语料→ES、对话→Neo4j（EVAL_USER_ID 名下）
│   └── teardown.py       清理：删 EVAL_USER_ID 的 ES + Neo4j 数据
├── tasks/
│   ├── retrieval.py      RAG 对照、记忆检索、负样本拒绝与延迟
│   ├── extraction.py     抽取 实体级/三元组级 P/R/F1
│   ├── dedup.py          去重 Pairwise P/R/F1
│   └── identity.py       canonical self、外部同名保护与幂等性
├── reporters.py          输出报告 + 明细
├── run_eval.py           ⭐ 总入口
└── results/              报告与明细（git 忽略）
```

## 自带数据集场景

对齐业界标准评测的题型设计，开箱即可跑：

- **RAG 检索**（仿 BEIR / NQ / HotpotQA 开放域问答）：`fixtures/corpus/` 10 篇通用百科（居里夫人、镭、诺贝尔奖、青霉素、长城、珠峰、大熊猫、光合作用、太阳系、长江），`gold/retrieval.json` 22 题，含**单跳**（答案在单篇）与**多跳**（需跨多篇，如「发现镭的科学家获了什么奖」要串起居里夫人↔诺贝尔奖）。
- **记忆系统**(中文长对话个人陈述):`fixtures/dialogues.json` 是同一人设跨多段的个人陈述(上海产品经理、老家成都、复旦新闻系、养布偶猫团子、爱爬山摄影、学日语、喝拿铁、用 iPhone+索尼相机、妹妹林晓在成都);gold 的抽取三元组**严格使用受控词表谓词**(属于类型 / 位于 / 拥有 / 偏好 / 了解 / 使用 / 关联于…)。**项目记忆萃取流水线为中文优先**,prompts 与受控词表全中文,英文场景不在评测覆盖内(原计划接入的 LongMemEval-S 已下架,避免翻译噪声与实体名失真)。
- **拒绝错误召回**：RAG 和记忆各有 8 个负样本，用 NoHitAccuracy 与 FalsePositiveRate 衡量系统在没有答案时能否停止召回，而不是永远返回最近邻。
- **身份安全**：9 个确定性用例覆盖本人姓名、别名、第三方同名、角色名、改名、否定和重复写入，报告错误绑定率与稳定 self 保持率。

> 想换成贴合自己数据的场景，直接替换 `fixtures/` 下对应文件即可（语料文件名即 `relevant_doc_ids`）。

## 准备

1. 起存储：`docker compose up -d postgres elasticsearch neo4j redis`。
2. 复制 `eval/.env.eval.example` → `eval/.env.eval`，填 embedding（必需）、chat（必需）、rerank（可选）的 key。
3. （可选）把 `fixtures/` 的语料/对话/gold 换成你自己的，更贴合真实数据。

若本地应用已经配置模型，可以不创建 `.env.eval`：

```bash
uv run python -m eval.run_eval --model-user-id <本地用户UUID> --reset
```

该参数只复用模型连接，不会把真实用户资料写入评测集或报告。

## 运行（在 api/ 目录）

```bash
uv run python -m eval.run_eval                  # 全流程：模型自检 + 写入 + 全部评测（保留数据）
uv run python -m eval.run_eval --reset          # 重跑：先清空旧数据再写入（推荐，记忆写入非幂等）
uv run python -m eval.run_eval --skip-setup     # 数据已写过，直接评测
uv run python -m eval.run_eval --skip-check     # 跳过模型可用性自检
uv run python -m eval.run_eval --only retrieval # 只跑 RAG 正向检索与负样本拒绝
uv run python -m eval.run_eval --only identity  # 只跑确定性的本人身份安全用例
uv run python -m eval.run_eval --teardown       # 跑完清理评测数据
```

> 正式跑前会先做**模型可用性自检**：分别调用 embedding / chat / rerank 确认连得通（embedding 还会校验维度是否与 ES 索引一致），不通的必需模型直接中止、rerank 不通则自动跳过其对比列，避免灌了一半数据才发现 key/url 写错。
> 全程带**进度日志**（写入第几篇语料 / 第几段对话萃取、评测第几题），方便看卡在哪一步。

结果在 `eval/results/`：`report-时间.md`（指标表）+ `details-时间.json`（逐条明细）。

## 指标

| 任务 | 指标 |
|------|------|
| RAG 检索（四配置）| Recall@k、Precision@k、MRR、nDCG@k |
| RAG/记忆负样本 | NoHitAccuracy、FalsePositiveRate |
| 记忆检索 | Recall@k、Precision@k、MRR、nDCG@k |
| 三元组抽取 | 实体级 / 三元组级 Precision、Recall、F1 |
| 实体去重 | Pairwise Precision、Recall、F1 |
| 身份归一化 | CaseAccuracy、UnsafeSelfLinkRate、StableSelfRate |

## 诚实声明

自建集是**小规模业务回归集**，主要用于定位退化和解释失败，不代表通用能力。C-MTEB/HotpotQA 若只运行子集，必须同时报告样本规模、随机种子和置信区间；HotpotQA 还存在训练数据污染风险，只适合比较系统配置，不作模型泛化能力断言。
