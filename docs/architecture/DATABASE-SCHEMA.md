# Meme 核心数据结构目录

> 本文面向当前面试主线，记录 Meme 核心 PostgreSQL 表，以及记忆链路使用的
> Redis、Neo4j 和 Elasticsearch 结构。
>
> PostgreSQL 字段来源：`api/app/models/`。当前代码共有 33 张业务表；本文只展开
> 核心流程相关的 14 张表。被隐藏、删除或后置的功能表仍可能保留在代码和历史迁移中，
> 但不在本文展开，不代表本次已经删除这些表。

## 1. 存储边界

| 存储 | 核心职责 |
| --- | --- |
| PostgreSQL | 用户、完整对话、模型配置、知识库/文件元数据、记忆任务、纠错审计、Agent Trace |
| Redis | Celery 队列与结果后端、流式响应缓冲、短期计数器和分布式运行状态 |
| Neo4j | 记忆图谱：来源、分块、陈述、实体、事件、社区和洞察 |
| Elasticsearch | 文档/图片 Chunk 的全文检索和向量检索 |
| 本地/对象存储 | 文档、图片、音频等二进制文件；数据库保存存储 key |

对话原文在 PostgreSQL `messages.content`；进入记忆萃取的用户输入另存于
`memories.raw_text`，结构化记忆则写入 Neo4j。

## 2. PostgreSQL 核心表

### `users` 用户

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 用户主键 |
| `username` | VARCHAR(64) | 非空、唯一、索引 | 登录用户名 |
| `nickname` | VARCHAR(64) | 可空 | 展示昵称 |
| `email` | VARCHAR(255) | 可空、唯一、索引 | 邮箱 |
| `avatar` | VARCHAR(512) | 可空 | 头像地址或存储 key |
| `password_hash` | VARCHAR(255) | 非空 | 密码哈希，不保存明文密码 |
| `briefing_seen_at` | TIMESTAMPTZ | 可空 | 最近查看任务简报时间 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `conversations` 对话

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 对话主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 对话所有者 |
| `title` | VARCHAR(256) | 默认“新对话” | 对话标题 |
| `is_group` | BOOLEAN | 默认 `false`，索引 | 是否群聊；当前核心流程使用单聊 |
| `member_persona_ids` | JSONB | 可空 | 群聊角色卡 ID 列表；高级能力字段 |
| `enable_tools` | BOOLEAN | 默认 `false` | 群聊工具开关 |
| `join_code` | VARCHAR(16) | 可空、索引 | 群聊邀请码 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `messages` 消息

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 消息主键 |
| `conversation_id` | UUID | 非空，FK → `conversations.id`，级联删除，索引 | 所属对话 |
| `role` | VARCHAR(16) | 非空 | `user`、`assistant` 或 `system` |
| `content` | TEXT | 非空 | 完整消息正文 |
| `sender_persona_id` | UUID | 可空 | 群聊角色卡 ID；当前不设数据库外键 |
| `sender_user_id` | UUID | 可空 | 多人群聊真人用户 ID；当前不设数据库外键 |
| `meta_data` | JSONB | 可空 | 引用、工具调用、Token、图片等附加信息 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |

### `message_feedbacks` 消息反馈

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 反馈主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 反馈用户 |
| `message_id` | UUID | 非空，FK → `messages.id`，级联删除，索引 | 被评价消息 |
| `conversation_id` | UUID | 非空，FK → `conversations.id`，级联删除，索引 | 所属对话 |
| `rating` | VARCHAR(8) | 非空 | `up` 或 `down` |
| `comment` | TEXT | 可空 | 文字反馈 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

唯一约束：`user_id + message_id`。

### `agent_configs` Agent 总配置

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 配置主键 |
| `user_id` | UUID | 非空、唯一，FK → `users.id`，级联删除，索引 | 每用户一条 |
| `system_prompt` | TEXT | 默认空字符串 | 全局系统提示词 |
| `temperature` | FLOAT | 默认 `0.7` | 生成温度 |
| `enable_knowledge` | BOOLEAN | 默认 `true` | 知识库能力开关 |
| `enable_memory` | BOOLEAN | 默认 `true` | 记忆能力开关 |
| `enable_web_search` | BOOLEAN | 默认 `false` | 联网搜索开关 |
| `enable_active_recall` | BOOLEAN | 默认 `true` | 主动召回开关 |
| `enable_cross_session` | BOOLEAN | 默认 `false` | 跨会话上下文开关 |
| `show_avatar` | BOOLEAN | 默认 `false` | 是否展示头像 |
| `human_mode` | BOOLEAN | 默认 `false` | 真人聊天风格开关 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `model_configs` 模型配置

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 配置主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `type` | VARCHAR(32) | 非空、索引 | `chat`、`multimodal` 或 `embedding` |
| `provider` | VARCHAR(32) | 非空 | 模型供应商 |
| `name` | VARCHAR(128) | 非空 | 配置显示名 |
| `model_name` | VARCHAR(128) | 非空 | 实际模型名 |
| `api_key_encrypted` | VARCHAR(512) | 非空 | Fernet 加密后的 API Key |
| `base_url` | VARCHAR(255) | 非空 | OpenAI 兼容接口地址 |
| `capability` | JSONB | 默认 `[]` | 函数调用、视觉等能力标记 |
| `is_default` | BOOLEAN | 默认 `false` | 是否该类型默认模型 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `knowledge_bases` 知识库

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 知识库主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(128) | 非空 | 知识库名称 |
| `description` | VARCHAR(512) | 可空 | 知识库描述 |
| `icon` | VARCHAR(32) | 可空 | 图标 |
| `color` | VARCHAR(16) | 可空 | 展示颜色 |
| `is_default` | BOOLEAN | 默认 `false`，索引 | 是否默认库 |
| `chat_enabled` | BOOLEAN | 默认 `false` | 是否允许对话检索 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `documents` 文档元数据

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 文档主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `kb_id` | UUID | 可空，FK → `knowledge_bases.id`，级联删除，索引 | 所属知识库 |
| `file_name` | VARCHAR(512) | 非空 | 原始文件名 |
| `file_ext` | VARCHAR(16) | 非空 | 文件扩展名 |
| `file_size` | INTEGER | 默认 `0` | 文件大小 |
| `file_key` | VARCHAR(512) | 非空 | 文件存储 key |
| `source_type` | VARCHAR(16) | 默认 `file` | 文件或 URL 来源 |
| `source_url` | VARCHAR(1024) | 可空 | 外部来源地址 |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | 解析状态 |
| `progress` | FLOAT | 默认 `0.0` | 解析进度 |
| `chunk_num` | INTEGER | 默认 `0` | 生成的 Chunk 数 |
| `error_msg` | TEXT | 可空 | 解析错误 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `images` 图片知识元数据

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 图片主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `kb_id` | UUID | 可空，FK → `knowledge_bases.id`，级联删除，索引 | 关联知识库 |
| `file_name` | VARCHAR(512) | 非空 | 文件名 |
| `file_ext` | VARCHAR(16) | 非空 | 文件扩展名 |
| `file_size` | INTEGER | 默认 `0` | 文件大小 |
| `file_key` | VARCHAR(512) | 非空 | 图片存储 key |
| `description` | TEXT | 可空 | 多模态描述 |
| `ocr_text` | TEXT | 可空 | OCR 文本 |
| `objects` | JSONB | 可空 | 识别出的对象列表 |
| `scene` | VARCHAR(256) | 可空 | 场景标签 |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | 识别状态 |
| `error_msg` | TEXT | 可空 | 识别错误 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `memories` 记忆萃取任务

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 记忆任务主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `raw_text` | TEXT | 非空 | 进入记忆萃取的原始用户输入 |
| `source` | VARCHAR(16) | 默认 `manual` | `auto` 或 `manual` |
| `source_message_id` | UUID | 可空 | 来源消息 ID |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | `pending`、`extracting`、`done`、`failed` |
| `error_msg` | TEXT | 可空 | 萃取错误 |
| `graph_dialogue_id` | VARCHAR(64) | 可空 | Neo4j 来源 `Dialogue` ID |
| `graph_stats` | JSONB | 可空 | 本次 Chunk、Statement、Entity、Event 统计 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `memory_corrections` 记忆纠错审计

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 纠错记录主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 操作用户 |
| `entity_id` | VARCHAR(128) | 非空、索引 | Neo4j 实体 ID |
| `action` | VARCHAR(16) | 非空、索引 | `confirm`、`correct` 或 `delete` |
| `before` | JSONB | 默认 `{}` | 修改前快照 |
| `after` | JSONB | 可空 | 修改后快照 |
| `reason` | VARCHAR(256) | 可空 | 操作原因 |
| `source_dialogue_id` | VARCHAR(128) | 可空 | 来源 Dialogue ID |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |

### `memory_curation_operations` 记忆管家操作审计

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 操作主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 操作用户 |
| `plan_id` | VARCHAR(64) | 非空、索引 | 操作计划 ID |
| `operation_id` | VARCHAR(64) | 非空、索引 | 计划内操作 ID |
| `request` | TEXT | 非空 | 用户原始请求 |
| `operation_kind` | VARCHAR(64) | 非空、索引 | 操作类型 |
| `risk` | VARCHAR(16) | 非空 | 风险等级 |
| `requires_confirmation` | BOOLEAN | 默认 `true` | 是否需要确认 |
| `status` | VARCHAR(16) | 默认 `confirmed`，索引 | 操作状态 |
| `before` | JSONB | 默认 `{}` | 执行前快照 |
| `after` | JSONB | 可空 | 执行后快照 |
| `error` | TEXT | 可空 | 执行错误 |
| `confirmed_at` | TIMESTAMPTZ | `now()` | 确认时间 |
| `executed_at` | TIMESTAMPTZ | 可空 | 执行时间 |
| `undone_at` | TIMESTAMPTZ | 可空 | 撤销时间 |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |

### `agent_traces` Agent Trace

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 数据库主键 |
| `trace_id` | UUID | 非空、唯一、索引 | 对外展示的 Trace ID |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `task_type` | VARCHAR(32) | 非空、索引 | `research`、`chat`、`agent_task`、`verify` 或 `repair` |
| `task_id` | UUID | 可空、索引 | 关联业务对象 ID；不设 FK |
| `task_name` | VARCHAR(256) | 可空 | 人类可读任务名 |
| `root_span_id` | UUID | 可空 | 根 Span ID |
| `status` | VARCHAR(16) | 默认 `running`，索引 | `running`、`ok` 或 `error` |
| `error_message` | TEXT | 可空 | 错误信息 |
| `started_at` | TIMESTAMP | `now()`、索引 | 开始时间 |
| `finished_at` | TIMESTAMP | 可空 | 完成时间 |
| `duration_ms` | INTEGER | 可空 | 总耗时 |
| `total_input_tokens` | INTEGER | 默认 `0` | 输入 Token 总数 |
| `total_output_tokens` | INTEGER | 默认 `0` | 输出 Token 总数 |
| `total_cached_tokens` | INTEGER | 默认 `0` | 缓存 Token 总数 |
| `total_cost_cny` | FLOAT | 默认 `0.0` | 总成本 |
| `models_used` | JSONB | 默认 `[]` | 使用过的模型列表 |
| `loop_run_id` | UUID | 可空、索引 | 关联 Verifier Loop；高级模块字段 |
| `attributes` | JSONB | 默认 `{}` | 客户端、调试等扩展属性 |

### `agent_spans` Agent Span

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 数据库主键 |
| `span_id` | UUID | 非空、唯一、索引 | Span 业务 ID |
| `parent_span_id` | UUID | 可空、索引 | 父 Span ID；根节点为空 |
| `trace_id` | UUID | 非空，FK → `agent_traces.trace_id`，级联删除，索引 | 所属 Trace |
| `span_type` | VARCHAR(32) | 非空、索引 | planner、retriever、tool_call、verifier、llm_call 等 |
| `name` | VARCHAR(128) | 非空 | Span 展示名称 |
| `status` | VARCHAR(16) | 默认 `running`，索引 | `running`、`ok` 或 `error` |
| `error_message` | TEXT | 可空 | 错误信息 |
| `started_at` | TIMESTAMP | `now()` | 开始时间 |
| `finished_at` | TIMESTAMP | 可空 | 完成时间 |
| `duration_ms` | INTEGER | 可空 | 耗时 |
| `model_name` | VARCHAR(128) | 可空 | LLM Span 使用的模型 |
| `input_tokens` | INTEGER | 默认 `0` | 输入 Token |
| `output_tokens` | INTEGER | 默认 `0` | 输出 Token |
| `cached_tokens` | INTEGER | 默认 `0` | 缓存 Token |
| `cost_cny` | FLOAT | 默认 `0.0` | 本 Span 成本 |
| `payload` | JSONB | 默认 `{}` | 输入/输出摘要和关键参数 |
| `attributes` | JSONB | 默认 `{}` | OpenTelemetry/业务扩展属性 |
| `iteration_id` | UUID | 可空、索引 | 关联高级 Loop 迭代 |

## 3. Redis 结构

Redis 没有关系型“表”，Meme 使用逻辑数据库、队列、Pub/Sub 频道和带前缀的 Key。
本节只列当前核心对话、记忆和任务基础设施使用的结构；群聊在线状态和高级定时任务锁不纳入核心展示目录。

### 逻辑数据库与队列

| 逻辑库/组件 | 结构 | 用途 |
| --- | --- | --- |
| Redis DB 0 | 应用 Redis 客户端 | 短期计数、流式缓冲等运行态 |
| Redis DB 1 | Celery broker | 后台任务队列；当前包含 `default`、`parse`、`memory`、`beat`、`research` 等队列 |
| Redis DB 2 | Celery result backend | Celery 任务结果和状态 |

### 核心 Key

| Key 模式 | 数据结构 | TTL/生命周期 | 字段或内容 |
| --- | --- | --- | --- |
| `chatstream:buf:{conversation_id}` | String(JSON) | 600 秒 | `content`、序号、`citations`、`tool_calls`、`status`；用于 SSE 断线续传 |
| `reflect:pending:{user_id}` | String(Integer) | 业务清零 | 累计新增实体数，达到阈值后触发用户反思任务 |

### Redis 使用原则

- Redis 中的数据是运行态或队列数据，不是长期事实来源；长期对话和记忆仍以 PostgreSQL/Neo4j 为准。
- 流式缓冲设置 TTL，避免生成异常后长期残留用户内容。
- Celery 队列负责异步解析、记忆萃取和后台 Agent 工作，不直接替代业务表。

## 4. Neo4j 记忆图谱结构

Neo4j 节点和关系不是 PostgreSQL 表，但它们共同组成 Meme 的长期记忆数据模型。所有核心节点带 `user_id` 做租户隔离。

### 节点

#### `Dialogue` 来源对话

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束；一次自动/手动记忆来源 |
| `user_id` | String | 用户隔离 |
| `content` | String | 来源全文 |
| `source` | String | `auto` 或 `manual` |
| `source_message_id` | String | 可空；来源消息 |
| `dialog_at` | DateTime | 对话发生时间 |
| `created_at` | DateTime | 写入时间 |

#### `Chunk` 来源片段

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `dialog_id` | String | 所属 Dialogue |
| `content` | String | 片段正文 |
| `speaker` | String | 可空；`user`/`assistant` |
| `sequence` | Integer | 片段顺序 |
| `created_at` | DateTime | 创建时间 |

#### `Statement` 原子陈述

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `chunk_id` | String | 所属 Chunk |
| `statement` | String | 原子陈述文本 |
| `stmt_type` | String | `FACT`、`OPINION`、`PREDICTION` 或 `SUGGESTION` |
| `temporal_type` | String | `STATIC`、`DYNAMIC` 或 `ATEMPORAL` |
| `speaker` | String | 可空 |
| `valid_at` / `invalid_at` | DateTime | 有效期，可空 |
| `dialog_at` | DateTime | 来源对话时间 |
| `embedding` | Float[] | 陈述向量 |
| `importance` / `confidence` | Float | 重要度与置信度 |
| `memory_layer` | String | `short_term` 或 `long_term` |
| `access_count` | Integer | 被召回次数 |
| `last_access_at` | DateTime | 最近召回时间 |
| `has_emotional_state` | Boolean | 是否带情绪状态 |
| `emotion_type` | String | 可空；图谱中的情绪标签 |
| `emotion_intensity` | Float | 可空 |
| `emotion_keywords` | String[] | 情绪关键词 |
| `created_at` | DateTime | 创建时间 |

#### `Entity` 实体

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `name` / `type` | String | 实体名称与受控类型 |
| `description` | String | 实体描述 |
| `aliases` | String[] | 别名集合 |
| `identity_key` | String | 可空；用户本人使用稳定身份键 |
| `is_self` | Boolean | 是否用户本人实体 |
| `name_embedding` | Float[] | 实体名称向量 |
| `community_id` | String | 可空；所属主题社区 |
| `importance` / `confidence` | Float | 重要度与置信度 |
| `memory_layer` | String | `short_term` 或 `long_term` |
| `access_count` / `mention_count` | Integer | 召回次数与提及次数 |
| `last_access_at` | DateTime | 最近召回时间 |
| `connect_strength` | String | `strong`、`weak` 或 `both` |
| `core_facts` / `traits` | String[] | 巩固后的核心事实与特质 |
| `last_consolidated_at` | DateTime | 可空；最近巩固时间 |
| `created_at` | DateTime | 创建时间 |

#### `Event` 事件

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `title` | String | 事件标题 |
| `description` | String | 事件描述 |
| `event_time` | DateTime | 可空；事件发生时间 |
| `embedding` | Float[] | 事件向量 |
| `created_at` | DateTime | 创建时间 |

#### `Community` 主题社区

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `name` | String | 社区名称 |
| `summary` | String | 社区摘要 |
| `member_count` | Integer | 社区成员数 |
| `created_at` | DateTime | 创建时间 |

#### `Insight` 高层洞察

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 唯一约束 |
| `user_id` | String | 用户隔离 |
| `theme` | String | 洞察主题 |
| `content` | String | 洞察正文 |
| `embedding` | Float[] | 洞察向量 |
| `importance` / `confidence` | Float | 重要度与置信度 |
| `source_count` | Integer | 归纳来源数量 |
| `created_at` / `updated_at` | DateTime | 创建与更新时间 |

### 关系

| 关系 | 方向 | 主要属性 | 作用 |
| --- | --- | --- | --- |
| `HAS_CHUNK` | `Dialogue → Chunk` | 无 | 来源对话包含片段 |
| `HAS_STATEMENT` | `Chunk → Statement` | 无 | 片段包含原子陈述 |
| `MENTIONS` | `Statement → Entity` | `user_id`、`connect_strength`、`created_at` | 陈述提及实体 |
| `RELATION` | `Entity → Entity` | `id`、`predicate`、`target_id`、`predicate_surface`、`source_text`、`statement_id`、`value`、有效期、评分与访问次数 | 实体三元组关系 |
| `INVOLVES` | `Event → Entity` | `user_id`、`role`、`created_at` | 事件参与者 |
| `IN_COMMUNITY` | `Entity → Community` | 无 | 实体主题聚类归属 |
| `DERIVED_FROM` | `Insight → Entity` | `created_at` | 洞察的实体依据 |

### Neo4j 约束和索引

- 每类核心节点的 `id` 唯一；`Entity` 额外约束 `(user_id, identity_key)` 唯一。
- 高频过滤字段：`user_id`、实体 `name`、`identity_key`、记忆层级、洞察 `theme`。
- 全文索引：Entity、Statement、Event、Insight 的文本属性，使用中文 CJK 分词。
- 向量索引：Entity 名称、Statement、Event、Insight 各自使用余弦相似度；向量维度由 `embedding_dims` 配置决定，默认 1024。

## 5. Elasticsearch 结构

### 索引 `comet_chunks`

一个统一索引承载文档 Chunk 和图片描述 Chunk，通过 `user_id`、`kb_id`、`source_type` 过滤实现多租户和知识库范围控制。

| 字段 | ES 类型 | 说明 |
| --- | --- | --- |
| `user_id` | keyword | 用户隔离过滤 |
| `kb_id` | keyword | 知识库过滤 |
| `source_type` | keyword | `document` 或 `image` |
| `source_id` | keyword | `documents.id` 或 `images.id` |
| `doc_name` | keyword | 文档名 |
| `chunk_id` | keyword | Chunk 唯一 ID，同时作为 ES `_id` |
| `chunk_type` | keyword | `child`、`parent` 或 `image_desc` |
| `parent_id` | keyword | 子 Chunk 指向父 Chunk |
| `content` | text | `ik_max_word` 写入、`ik_smart` 查询 |
| `tags` | keyword[] | 标签 |
| `vector` | dense_vector | 默认 1024 维，余弦相似度 |
| `created_at` | date | 索引写入时间 |

索引配置：1 个 shard、0 个 replica；child Chunk 用于精确召回，parent Chunk 用于补充上下文，image Chunk 用于图片语义检索。

## 6. 范围说明

前端隐藏、已删除或后置功能对应的数据表不在本文展开。它们仍可能存在于当前代码或历史迁移中，但不属于 Meme 当前核心展示与运行链路；是否清理需要单独评估，本文不代表删除数据库结构。

## 7. 维护原则

- ORM 模型、Alembic migration 和本文应保持同步；新增/删除字段时同时检查三者。
- API Key、MCP 认证信息等敏感字段必须加密存储，文档不记录实际值。
- JSONB 用于可演进的配置、快照和结构化结果；高频筛选字段使用独立列和索引。
- Redis 只保存运行态和队列数据；PostgreSQL/Neo4j 才是长期业务与记忆数据来源。
