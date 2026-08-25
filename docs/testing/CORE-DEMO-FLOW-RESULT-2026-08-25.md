# 核心演示流程回归结果（2026-08-25）

本记录对应 GitHub Issue #65，用于补充
[核心演示流程回归清单](CORE-DEMO-FLOW.md) 在当前 `main` 的执行结果。

## 基线

- 分支：`main`
- Commit：`bd492de54cefaf32538cd839f9603e6733994ef1`
- 数据与凭据：未写入本记录

## 自动检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 后端 Ruff | 通过 | `uv run ruff check .` |
| 后端单元测试 | 通过 | 53 tests，`unittest discover` |
| 前端 ESLint | 通过 | 0 errors；保留 2 条既有 React Hook warning |
| 前端 production build | 通过 | TypeScript 与 Vite 构建成功 |
| Compose 配置 | 通过 | `docker compose config --quiet` |
| Docker 服务状态 | 阻塞 | Docker Desktop Linux engine 未启动 |
| API `/api/hello` | 未验证 | 本地 8000 端口未监听 |
| API `/api/health` | 未验证 | 本地 8000 端口未监听 |

前端构建仍有上游既有提示：工具模块同时被静态和动态导入，以及产物单 chunk 较大；本次没有改变这些问题。

## 业务流程状态

以下流程需要运行 Docker 服务、演示账号和已测试的模型配置，本次环境未满足条件，因此统一记录为“未验证”，不代表功能失败：

- 登录与模型配置
- 知识库上传、解析和回答引用
- 单人 SSE 流式对话
- 长期记忆、canonical self 与知识图谱
- 跨会话主动召回
- Trace、模型/检索/工具调用与成本信息

## 解除阻塞后的执行顺序

1. 启动 Docker Desktop，确认 Linux engine 可用。
2. 在仓库根目录运行 `docker compose up -d`，确认 PostgreSQL、Elasticsearch、Neo4j、Redis 健康。
3. 重新执行清单第 2 节的 A-F 流程，仅使用脱敏演示数据。
4. 将每项结果和必要的脱敏截图补充到面试演示材料，不把真实账号、API Key 或用户资料提交到仓库。

本记录只反映本次环境状态；产品范围仍以功能决策和 ADR 为准。
