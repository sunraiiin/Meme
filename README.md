# Meme

一个面向个人知识管理与 AI 助手场景的重构项目。

## 当前状态

本仓库处于重构初始化阶段。

## 目录结构

```text
api/       FastAPI 后端
web/       React + TypeScript 前端
docker/    基础设施相关 Docker 配置
docs/      Meme 项目自己的架构、决策与路线图文档
```

## 项目文档

- [文档导航](docs/README.md)
- [现有系统与功能依赖地图](docs/architecture/CURRENT-SYSTEM.md)
- [功能边界决策](docs/refactor/FEATURE-DECISIONS.md)
- [目标架构与实施计划](docs/refactor/TARGET-ARCHITECTURE.md)
- [ADR-0001：项目功能范围决策](docs/decisions/0001-product-scope.md)

## 开发原则

- `main` 保持可运行状态。
- 每个需求先建立 Issue，再从独立分支开发。
- 每个独立改动单独提交，并在合并前完成测试和 Diff 审查。
- 不提交真实环境变量、密钥、数据库和构建产物。

## 本地启动

### 环境要求

- Windows 使用启用了 WSL 2 的 Docker Desktop，运行 Linux 容器。
- Node.js 22.13+ 或 24；当前基线使用 Node.js 24 和 npm 11 验证。
- Python 3.12，由 `uv` 管理；当前基线使用 `uv` 0.12 验证。
- 首次完整启动需要为 Elasticsearch、Neo4j、PostgreSQL、Redis、API、Worker 和
  Web 预留足够的内存与磁盘空间。

在 Windows 上首次启用 WSL 2 需要管理员权限，并可能要求重启。Docker Desktop
主程序、容器数据、`uv`、Python 和项目虚拟环境都可以放在 D 盘；WSL 的少量系统
组件仍由 Windows 管理。

### 1. 准备开发环境变量

在仓库根目录复制模板：

```powershell
Copy-Item .env.example .env
```

将 `.env` 中的 `JWT_SECRET` 改成随机长字符串，并生成合法的 `FERNET_KEY`：

```powershell
Set-Location api
uv sync --frozen
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Set-Location ..
```

把命令输出写入本机 `.env`，不要提交该文件。`FERNET_KEY` 一旦用于保存模型密钥，
后续不能随意更换，否则旧数据将无法解密。

### 2. 验证并启动完整服务

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

基础 Compose 会把 `web/nginx.local.conf` 挂载为本地 HTTP 配置，因此访问
`http://localhost:5173` 不需要生产证书。生产环境叠加
`docker-compose.prod.yml` 时会改用 `web/nginx.conf` 和人工上传的证书。

首次构建 Elasticsearch IK 镜像和 Python 依赖需要较长时间。所有服务启动后验证：

```powershell
Invoke-RestMethod http://localhost:8000/api/hello
Invoke-RestMethod http://localhost:8000/api/health
```

浏览器访问 `http://localhost:5173`。停止服务但保留开发数据：

```powershell
docker compose down
```

不要在普通重启流程中使用 `docker compose down -v`，该参数会删除四个存储的数据卷。

### 3. 运行代码基线检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-local-baseline.ps1 -SkipDocker
```

Docker 服务已启动时，去掉 `-SkipDocker`，脚本还会验证 Compose 配置、容器状态和
两个 API 健康端点。脚本不会创建 `.env`、启动容器或修改数据。

### D 盘工具目录示例

当前 Windows 开发机使用以下布局，其他开发者可以使用等价位置：

```text
D:\Meme\api\.venv       项目 Python 虚拟环境
D:\Tools\uv             uv、Python 与缓存
D:\Tools\DockerDesktop  Docker Desktop 主程序
D:\DockerData            Docker WSL 数据盘
```

如果使用这些自定义位置，请确保 `D:\Tools\uv\bin` 和
`D:\Tools\DockerDesktop\resources\bin` 已加入用户 `PATH`。

## 来源与授权

当前代码基线来源于 Comet 项目。Meme 的新增代码、重构记录和文档将单独维护。公开发布前需要确认原始代码的授权范围，并补充适用的许可证说明。
