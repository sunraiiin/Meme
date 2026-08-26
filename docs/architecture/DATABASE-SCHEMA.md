# Meme 数据库表与字段

> 本文记录 Meme 当前 PostgreSQL 业务表的 ORM 结构，来源于 `api/app/models/`。
> 当前共 33 张业务表。字段类型使用逻辑类型表示，实际物理类型由 SQLAlchemy/Alembic
> 映射到 PostgreSQL。

## 1. 存储边界

| 存储 | 保存内容 |
| --- | --- |
| PostgreSQL | 用户、完整对话消息、知识库/文件元数据、记忆任务状态、Agent 配置、研究报告、Trace 等结构化业务数据 |
| Neo4j | 记忆图谱：`Dialogue`、`Chunk`、`Statement`、`Entity`、`Event`、`Community`、`Insight` 节点及其关系 |
| Elasticsearch | 文档 Chunk、图片 OCR/描述、记忆陈述等检索索引 |
| Redis | Celery 队列、缓存、流式事件和短期运行状态 |
| 本地/对象存储 | 上传文件、图片、音频等二进制内容；PostgreSQL 通常只保存 `file_key` |

`messages` 保存完整对话消息；`memories` 保存进入记忆萃取流程的用户输入及图谱写入结果，二者不是同一张表。

## 2. 账号与对话

### `users` 用户

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 用户主键 |
| `username` | VARCHAR(64) | 非空、唯一、索引 | 登录用户名 |
| `nickname` | VARCHAR(64) | 可空 | 展示昵称 |
| `email` | VARCHAR(255) | 可空、唯一、索引 | 邮箱 |
| `avatar` | VARCHAR(512) | 可空 | 头像地址或存储 key |
| `password_hash` | VARCHAR(255) | 非空 | 密码哈希，不保存明文密码 |
| `briefing_seen_at` | TIMESTAMPTZ | 可空 | 用户最近查看任务简报的时间 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `conversations` 对话

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 对话主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 对话所有者 |
| `title` | VARCHAR(256) | 默认“新对话” | 对话标题 |
| `is_group` | BOOLEAN | 默认 `false`，索引 | 是否多 Agent/多人群聊 |
| `member_persona_ids` | JSONB | 可空 | 群聊中的角色卡 ID 列表，保序 |
| `enable_tools` | BOOLEAN | 默认 `false` | 群聊是否允许工具调用 |
| `join_code` | VARCHAR(16) | 可空、索引 | 多人群聊邀请码 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `messages` 消息

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 消息主键 |
| `conversation_id` | UUID | 非空，FK → `conversations.id`，级联删除，索引 | 所属对话 |
| `role` | VARCHAR(16) | 非空 | `user`、`assistant` 或 `system` |
| `content` | TEXT | 非空 | 完整消息正文 |
| `sender_persona_id` | UUID | 可空 | 群聊中发消息的角色卡 ID；当前不设数据库外键 |
| `sender_user_id` | UUID | 可空 | 多人群聊中发消息的真人用户 ID；当前不设数据库外键 |
| `meta_data` | JSONB | 可空 | 引用、工具调用、Token、图片等附加信息 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |

### `group_members` 群聊真人成员

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 成员记录主键 |
| `conversation_id` | UUID | 非空，FK → `conversations.id`，级联删除，索引 | 群聊 ID |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 真人用户 ID |
| `role` | VARCHAR(16) | 默认 `member` | `owner` 或 `member` |
| `nickname` | VARCHAR(64) | 可空 | 群内昵称 |
| `joined_at` | TIMESTAMPTZ | `now()` | 加入时间 |

唯一约束：`conversation_id + user_id`。

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

### `conversation_shares` 对话分享快照

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 分享主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 分享创建者 |
| `conversation_id` | UUID | 非空、索引 | 来源对话 ID；不设 FK，保证删除对话后快照仍可访问 |
| `share_token` | VARCHAR(64) | 非空、唯一、索引 | 公开访问令牌 |
| `title` | VARCHAR(256) | 默认“对话分享” | 标题快照 |
| `snapshot` | JSONB | 默认 `[]` | 脱敏消息快照 |
| `user_avatar` | TEXT | 可空 | 用户头像快照 |
| `ai_avatar` | TEXT | 可空 | AI 头像快照 |
| `ai_name` | VARCHAR(64) | 可空 | AI 名称快照 |
| `is_active` | BOOLEAN | 默认 `true`，索引 | 是否仍可访问 |
| `expire_at` | TIMESTAMPTZ | 可空 | 过期时间；空表示永久 |
| `view_count` | INTEGER | 默认 `0` | 浏览次数 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

## 3. Agent 与模型配置

### `agent_configs` Agent 总配置

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 配置主键 |
| `user_id` | UUID | 非空、唯一，FK → `users.id`，级联删除，索引 | 用户；每用户一条 |
| `system_prompt` | TEXT | 默认空字符串 | 全局系统提示词 |
| `temperature` | FLOAT | 默认 `0.7` | 生成温度 |
| `enable_knowledge` | BOOLEAN | 默认 `true` | 是否启用知识库工具 |
| `enable_memory` | BOOLEAN | 默认 `true` | 是否启用记忆工具 |
| `enable_web_search` | BOOLEAN | 默认 `false` | 是否启用联网搜索 |
| `enable_active_recall` | BOOLEAN | 默认 `true` | 是否自动召回记忆 |
| `enable_cross_session` | BOOLEAN | 默认 `false` | 是否注入跨会话上下文 |
| `show_avatar` | BOOLEAN | 默认 `false` | 是否展示头像 |
| `human_mode` | BOOLEAN | 默认 `false` | 是否启用真人聊天风格 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `agent_personas` 角色卡

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 角色卡主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(64) | 非空 | 角色名称 |
| `avatar_key` | VARCHAR(512) | 可空 | 头像存储 key |
| `system_prompt` | TEXT | 默认空字符串 | 人设、语气和行为提示词 |
| `temperature` | FLOAT | 默认 `0.7` | 角色生成温度 |
| `is_active` | BOOLEAN | 默认 `false`，索引 | 是否当前启用 |
| `in_group_only` | BOOLEAN | 默认 `false` | 是否只作为群聊角色存在 |
| `sort` | INTEGER | 默认 `0` | 列表排序 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `persona_groups` 角色卡组/场景

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 卡组主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(64) | 非空 | 场景名称 |
| `description` | TEXT | 默认空字符串 | 场景描述 |
| `icon` | VARCHAR(16) | 默认空字符串 | 场景图标 |
| `member_persona_ids` | JSONB | 默认 `[]` | 成员角色卡 ID 列表 |
| `enable_tools` | BOOLEAN | 默认 `false` | 开群聊时是否启用工具 |
| `is_builtin` | BOOLEAN | 默认 `false` | 是否由内置模板复制 |
| `sort` | INTEGER | 默认 `0` | 列表排序 |
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
| `capability` | JSONB | 默认 `[]` | 能力标记，如函数调用、视觉 |
| `is_default` | BOOLEAN | 默认 `false` | 是否该类型默认模型 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `mcp_servers` MCP 服务

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | MCP 服务主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(128) | 非空 | 服务名称 |
| `transport` | VARCHAR(32) | 默认 `streamable_http` | 传输方式 |
| `url` | VARCHAR(512) | 非空 | MCP 服务地址 |
| `auth_type` | VARCHAR(16) | 默认 `none` | 认证方式 |
| `auth_config` | JSONB | 可空 | 加密/脱敏的认证配置 |
| `enabled` | BOOLEAN | 默认 `true` | 是否启用 |
| `status` | VARCHAR(16) | 默认 `unknown` | 连接状态 |
| `last_error` | VARCHAR(1024) | 可空 | 最近一次错误 |
| `tools_cache` | JSONB | 可空 | 同步得到的工具清单缓存 |
| `synced_at` | TIMESTAMPTZ | 可空 | 工具清单同步时间 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `tool_configs` 工具开关

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 配置主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `tool_key` | VARCHAR(128) | 非空、索引 | 工具唯一 key |
| `tool_type` | VARCHAR(16) | 默认 `builtin` | 内置工具或 MCP 工具 |
| `enabled` | BOOLEAN | 默认 `true` | 是否启用 |
| `config` | JSONB | 可空 | 工具专属配置 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `skills` 技能

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 技能主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(64) | 非空 | 技能名称 |
| `description` | VARCHAR(256) | 默认空字符串 | 技能说明 |
| `icon` | VARCHAR(16) | 默认 🧩 | 技能图标 |
| `prompt` | TEXT | 默认空字符串 | 技能提示词 |
| `tool_keys` | JSONB | 默认 `[]` | 允许使用的工具 key 列表 |
| `kb_id` | UUID | 可空，FK → `knowledge_bases.id`，置空删除，索引 | 关联知识库 |
| `config` | JSONB | 默认 `{}` | 技能运行配置 |
| `enabled` | BOOLEAN | 默认 `true` | 是否启用 |
| `is_builtin` | BOOLEAN | 默认 `false` | 是否内置技能 |
| `sort` | INTEGER | 默认 `0` | 列表排序 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

## 4. 知识库与媒体

### `knowledge_bases` 知识库

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 知识库主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(128) | 非空 | 知识库名称 |
| `description` | VARCHAR(512) | 可空 | 知识库描述 |
| `icon` | VARCHAR(32) | 可空 | 图标 |
| `color` | VARCHAR(16) | 可空 | 展示颜色 |
| `is_default` | BOOLEAN | 默认 `false`，索引 | 是否默认知识库 |
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
| `source_type` | VARCHAR(16) | 默认 `file` | 文件、URL 等来源类型 |
| `source_url` | VARCHAR(1024) | 可空 | 外部来源地址 |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | 解析状态 |
| `progress` | FLOAT | 默认 `0.0` | 解析进度 |
| `chunk_num` | INTEGER | 默认 `0` | 生成的 Chunk 数 |
| `error_msg` | TEXT | 可空 | 解析错误 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `images` 图片库

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 图片主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `kb_id` | UUID | 可空，FK → `knowledge_bases.id`，级联删除，索引 | 关联知识库 |
| `file_name` | VARCHAR(512) | 非空 | 文件名 |
| `file_ext` | VARCHAR(16) | 非空 | 文件扩展名 |
| `file_size` | INTEGER | 默认 `0` | 文件大小 |
| `file_key` | VARCHAR(512) | 非空 | 图片存储 key |
| `description` | TEXT | 可空 | 多模态生成的描述 |
| `ocr_text` | TEXT | 可空 | OCR 文本 |
| `objects` | JSONB | 可空 | 识别出的物体列表 |
| `scene` | VARCHAR(256) | 可空 | 场景标签 |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | 识别状态 |
| `error_msg` | TEXT | 可空 | 识别错误 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `songs` 音乐

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 歌曲主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `title` | VARCHAR(255) | 非空、索引 | 歌曲名 |
| `artist` | VARCHAR(255) | 默认空字符串 | 歌手 |
| `album` | VARCHAR(255) | 可空 | 专辑 |
| `file_key` | VARCHAR(512) | 可空 | 音频存储 key |
| `source_url` | TEXT | 可空 | 音频来源地址 |
| `cover_url` | TEXT | 可空 | 封面地址 |
| `lyric` | TEXT | 可空 | 歌词 |
| `valence` | FLOAT | 默认 `0.0` | 情绪效价 |
| `arousal` | FLOAT | 默认 `0.3` | 情绪唤醒度 |
| `mood_tags` | JSONB | 可空 | 音乐情绪标签 |
| `tag_status` | VARCHAR(16) | 默认 `pending` | 情绪标签处理状态 |
| `playable` | BOOLEAN | 可空 | 是否可播放 |
| `duration` | INTEGER | 可空 | 时长，单位秒 |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `play_histories` 播放历史

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 播放记录主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 播放用户 |
| `song_id` | UUID | 可空 | 歌曲 ID；当前不设数据库外键 |
| `title` | VARCHAR(255) | 默认空字符串 | 播放时的歌曲名快照 |
| `artist` | VARCHAR(255) | 默认空字符串 | 播放时的歌手快照 |
| `played_at` | TIMESTAMPTZ | `now()`，索引 | 播放时间 |

## 5. 记忆与用户画像

### `memories` 记忆萃取任务

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 记忆任务主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `raw_text` | TEXT | 非空 | 进入记忆萃取的原始用户输入 |
| `source` | VARCHAR(16) | 默认 `manual` | `auto` 或 `manual` |
| `source_message_id` | UUID | 可空 | 来源对话消息 ID |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | `pending`、`extracting`、`done`、`failed` |
| `error_msg` | TEXT | 可空 | 萃取错误 |
| `graph_dialogue_id` | VARCHAR(64) | 可空 | Neo4j 来源 `Dialogue` ID |
| `graph_stats` | JSONB | 可空 | 本次写入的 Chunk、Statement、Entity、Event 等统计 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `memory_corrections` 记忆实体纠错审计

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 纠错记录主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 操作用户 |
| `entity_id` | VARCHAR(128) | 非空、索引 | Neo4j 实体 ID |
| `action` | VARCHAR(16) | 非空、索引 | `confirm`、`correct` 或 `delete` |
| `before` | JSONB | 默认 `{}` | 修改前快照 |
| `after` | JSONB | 可空 | 修改后快照 |
| `reason` | VARCHAR(256) | 可空 | 操作原因 |
| `source_dialogue_id` | VARCHAR(128) | 可空 | 关联图谱来源 Dialogue |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |

### `memory_curation_operations` 记忆管家操作审计

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 操作主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 操作用户 |
| `plan_id` | VARCHAR(64) | 非空、索引 | 一次操作计划 ID |
| `operation_id` | VARCHAR(64) | 非空、索引 | 计划内操作 ID |
| `request` | TEXT | 非空 | 用户原始请求 |
| `operation_kind` | VARCHAR(64) | 非空、索引 | 操作类型 |
| `risk` | VARCHAR(16) | 非空 | 风险等级 |
| `requires_confirmation` | BOOLEAN | 默认 `true` | 是否需要用户确认 |
| `status` | VARCHAR(16) | 默认 `confirmed`，索引 | 操作状态 |
| `before` | JSONB | 默认 `{}` | 执行前快照 |
| `after` | JSONB | 可空 | 执行后快照 |
| `error` | TEXT | 可空 | 执行错误 |
| `confirmed_at` | TIMESTAMPTZ | `now()` | 确认时间 |
| `executed_at` | TIMESTAMPTZ | 可空 | 执行时间 |
| `undone_at` | TIMESTAMPTZ | 可空 | 撤销时间 |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |

### `emotion_records` 单轮情绪记录

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 情绪记录主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 用户 |
| `conversation_id` | UUID | 可空 | 对话 ID；当前不设数据库外键 |
| `message_id` | UUID | 可空 | 消息 ID；当前不设数据库外键 |
| `emotion_type` | VARCHAR(32) | 非空、索引 | 主情绪类型 |
| `intensity` | FLOAT | 默认 `0.0` | 情绪强度 |
| `valence` | FLOAT | 默认 `0.0` | 情绪效价，通常为 -1 到 1 |
| `arousal` | FLOAT | 默认 `0.0` | 情绪唤醒度 |
| `keywords` | JSONB | 可空 | 情绪关键词 |
| `trigger` | VARCHAR(255) | 可空 | 情绪触发事件 |
| `summary` | TEXT | 可空 | 情绪摘要 |
| `created_at` | TIMESTAMPTZ | `now()`，索引 | 创建时间 |

### `emotion_profiles` 当前情绪画像

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 画像主键 |
| `user_id` | UUID | 非空、唯一，FK → `users.id`，级联删除，索引 | 用户；每用户一条 |
| `dominant_emotion` | VARCHAR(32) | 默认“平静” | 当前主情绪 |
| `avg_valence` | FLOAT | 默认 `0.0` | 平均效价 |
| `avg_arousal` | FLOAT | 默认 `0.0` | 平均唤醒度 |
| `sample_count` | INTEGER | 默认 `0` | 聚合样本数 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `tags` 用户标签

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 标签主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(64) | 非空 | 标签名称 |
| `color` | VARCHAR(16) | 默认 `#155EEF` | 展示颜色 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |

### `favorites` 收藏

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 收藏主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `target_type` | VARCHAR(16) | 非空 | 收藏目标类型 |
| `target_id` | VARCHAR(64) | 非空 | 目标 ID；多类型通用引用，不设 FK |
| `snapshot` | JSONB | 可空 | 收藏时的内容快照 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |

## 6. 任务、研究与执行追踪

### `agent_tasks` 定时 Agent 任务

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 任务主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `name` | VARCHAR(128) | 非空 | 任务名称 |
| `instruction` | TEXT | 非空 | 自然语言研究指令 |
| `kb_ids` | JSONB | 可空 | 检索范围；空表示默认范围 |
| `trigger_type` | VARCHAR(16) | 默认 `daily` | `daily`、`weekly` 或 `interval` |
| `trigger_time` | VARCHAR(8) | 可空 | 每日/每周触发时间，格式 `HH:MM` |
| `trigger_weekday` | INTEGER | 可空 | 每周触发日，0 表示周一 |
| `trigger_interval_hours` | INTEGER | 可空 | 间隔小时数 |
| `enabled` | BOOLEAN | 默认 `true`，索引 | 是否启用 |
| `last_run_at` | TIMESTAMPTZ | 可空 | 最近运行时间 |
| `last_status` | VARCHAR(16) | 默认空字符串 | 最近运行状态 |
| `next_run_at` | TIMESTAMPTZ | 可空、索引 | 下次运行时间 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `research_reports` 深度研究报告

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 报告主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `topic` | TEXT | 非空 | 用户原始研究需求 |
| `title` | VARCHAR(255) | 可空 | 生成的报告标题 |
| `status` | VARCHAR(16) | 默认 `pending`，索引 | 研究状态 |
| `report_md` | TEXT | 可空 | 最终 Markdown 报告 |
| `outline` | JSONB | 可空 | 提纲和查询计划 |
| `sources` | JSONB | 可空 | 参考来源列表 |
| `error_msg` | TEXT | 可空 | 研究错误 |
| `task_id` | UUID | 可空 | 关联定时任务 ID；当前不设数据库外键 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

### `daily_reviews` 每日简报

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 简报主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `review_date` | DATE | 非空、索引 | 简报日期 |
| `content` | TEXT | 非空 | 简报正文 |
| `care` | TEXT | 可空 | 关怀/提醒内容 |
| `stats` | JSONB | 可空 | 汇总统计 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |

### `loop_runs` Verifier Loop 运行

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 一次完整 Loop 主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `task_type` | VARCHAR(32) | 非空、索引 | `research` 或 `agent_task` |
| `task_id` | UUID | 可空、索引 | 关联业务任务 ID；不设 FK |
| `status` | VARCHAR(16) | 默认 `running`，索引 | `running`、`passed`、`failed`、`exceeded` |
| `iterations` | INTEGER | 默认 `0` | 已执行轮数 |
| `final_score` | FLOAT | 可空 | 最终加权分数 |
| `pass_threshold` | FLOAT | 默认 `0.7` | 通过阈值快照 |
| `max_iterations` | INTEGER | 默认 `2` | 最大迭代轮数 |
| `generator_model` | VARCHAR(128) | 可空 | Generator 模型名 |
| `verifier_model` | VARCHAR(128) | 可空 | Verifier 模型名 |
| `verifier_kind` | VARCHAR(16) | 可空 | `same` 或 `cross` |
| `rubric_name` | VARCHAR(32) | 可空 | 评分标准名称 |
| `note` | TEXT | 可空 | 失败或超限原因 |
| `started_at` | TIMESTAMP | 默认 `now()` | 开始时间 |
| `finished_at` | TIMESTAMP | 可空 | 完成时间 |

### `loop_iterations` Verifier Loop 迭代明细

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 迭代主键 |
| `run_id` | UUID | 非空，FK → `loop_runs.id`，级联删除，索引 | 所属 Loop |
| `iteration_no` | INTEGER | 非空 | 轮次序号，从 1 开始 |
| `artifact_snapshot` | JSONB | 默认 `{}` | 产物摘要，不保存全文 |
| `scores` | JSONB | 默认 `{}` | Verifier 各维度评分 |
| `feedback` | JSONB | 默认 `{}` | Verifier 反馈 |
| `decision` | VARCHAR(16) | 非空 | `pass`、`retry_patch`、`retry_rewrite` 或 `exceed` |
| `repair_action` | JSONB | 可空 | 本轮修复动作 |
| `duration_ms` | INTEGER | 可空 | 本轮耗时 |
| `created_at` | TIMESTAMP | `now()` | 创建时间 |

### `agent_traces` Agent Trace

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 数据库主键 |
| `trace_id` | UUID | 非空、唯一、索引 | 对外展示的 Trace ID |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 所属用户 |
| `task_type` | VARCHAR(32) | 非空、索引 | `research`、`chat`、`agent_task`、`verify` 或 `repair` |
| `task_id` | UUID | 可空、索引 | 关联业务对象 ID；不设 FK |
| `task_name` | VARCHAR(256) | 可空 | 人类可读的任务名 |
| `root_span_id` | UUID | 可空 | 根 Span ID |
| `status` | VARCHAR(16) | 默认 `running`，索引 | `running`、`ok` 或 `error` |
| `error_message` | TEXT | 可空 | 错误信息 |
| `started_at` | TIMESTAMP | `now()`、索引 | 开始时间 |
| `finished_at` | TIMESTAMP | 可空 | 完成时间 |
| `duration_ms` | INTEGER | 可空 | 总耗时 |
| `total_input_tokens` | INTEGER | 默认 `0` | 输入 Token 总数 |
| `total_output_tokens` | INTEGER | 默认 `0` | 输出 Token 总数 |
| `total_cached_tokens` | INTEGER | 默认 `0` | 缓存命中 Token 总数 |
| `total_cost_cny` | FLOAT | 默认 `0.0` | 总成本 |
| `models_used` | JSONB | 默认 `[]` | 使用过的模型列表 |
| `loop_run_id` | UUID | 可空、索引 | 关联 Verifier Loop |
| `attributes` | JSONB | 默认 `{}` | 用户端、调试等扩展属性 |

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
| `iteration_id` | UUID | 可空、索引 | 关联 Loop 迭代 |

### `report_shares` 研究报告分享

| 字段 | 类型 | 可空/默认 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 分享主键 |
| `user_id` | UUID | 非空，FK → `users.id`，级联删除，索引 | 分享创建者 |
| `report_id` | UUID | 非空、索引 | 来源报告 ID；当前不设数据库外键 |
| `share_token` | VARCHAR(64) | 非空、唯一、索引 | 公开访问令牌 |
| `title` | VARCHAR(256) | 非空 | 标题快照 |
| `content_md` | TEXT | 默认空字符串 | 报告 Markdown 快照 |
| `sources` | JSONB | 可空 | 来源列表快照 |
| `is_active` | BOOLEAN | 默认 `true`，索引 | 是否有效 |
| `expire_at` | TIMESTAMPTZ | 可空 | 过期时间；空表示永久 |
| `view_count` | INTEGER | 默认 `0` | 浏览次数 |
| `created_at` | TIMESTAMPTZ | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | `now()` | 更新时间 |

## 7. 关系与维护说明

### 主要外键关系

- `users` 是大多数用户域表的根表，删除用户会级联删除其对话、配置、知识库、媒体、记忆任务和审计数据。
- `conversations` → `messages`、`group_members`、`message_feedbacks`。
- `knowledge_bases` → `documents`、`images`；`skills.kb_id` 在知识库删除时置空。
- `loop_runs` → `loop_iterations`；`agent_traces` → `agent_spans`。
- 部分跨业务关联（如 `research_reports.task_id`、`report_shares.report_id`、`memories.graph_dialogue_id`）有意不设 PostgreSQL 外键，用业务逻辑保持解耦和审计记录。

### 维护原则

- ORM 模型、Alembic migration 和本文应保持同步；新增/删除字段时需要同时检查三者。
- API Key、MCP 认证信息等敏感字段必须保持加密存储，文档只记录字段用途，不记录实际值。
- `JSONB` 字段用于可演进的配置、快照和结构化结果；需要高频筛选的核心字段仍应使用独立列和索引。
- 本文只描述 PostgreSQL 业务表，不把 Neo4j 图谱节点误写成关系型表。
