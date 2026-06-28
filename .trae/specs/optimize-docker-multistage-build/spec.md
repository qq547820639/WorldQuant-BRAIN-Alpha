# Docker 多阶段构建优化 Spec

## Why
当前 `Dockerfile` 采用两阶段构建，但运行时阶段安装了 `.[browser,test,dev]` 全部可选依赖（包含 pytest/ruff/mypy/pip-audit 等开发工具），并携带前端 `node_modules` 与源码，导致生产镜像体积臃肿、攻击面增大、构建产物与开发工具混在一起。需要重构为标准多阶段构建，使运行时镜像仅包含生产依赖与构建产物。

## What Changes
- **重写 `Dockerfile`** 为三阶段多阶段构建：
  - Stage 1 `webbuild`（node:22-bookworm）：安装 npm 依赖并执行 `npm run build`，产出 `dist/`
  - Stage 2 `pybuilder`（python:3.13-slim）：安装完整构建环境 `.[browser,test,dev]`，但仅用 `pip wheel ".[browser]"` 构建生产依赖 wheel（排除 test/dev），并准备清理后的 Python 源码树
  - Stage 3 `runtime`（python:3.13-slim）：仅安装生产依赖 wheel（离线安装，无 test/dev），安装 Chromium 运行时系统库，仅拷贝 `dist/`（无 node_modules/源码），拷贝清理后的 Python 源码
- **新建 `.dockerignore`**：排除 node_modules、dist、__pycache__、虚拟环境、IDE 配置、测试/fixtures/docs 等，优化构建上下文
- **同步 `docker-compose.yml`**：添加 `image: brain-alpha-ops:0.5.0`、`./config:/app/config` bind mount、`brain-alpha-artifacts` 命名卷
- **运行时路径约束**：源码必须位于 `/app/brain_alpha_ops/`，因为 `PROJECT_ROOT = Path(__file__).resolve().parents[2]` 需解析到 `/app/`
- **持久化**：`/app/data` 和 `/app/config` 声明为 VOLUME，`/app/artifacts/evidence` 创建为可写目录
- **健康检查**：HEALTHCHECK 探测 `http://127.0.0.1:8765/api/health`

## Impact
- Affected specs: 无直接依赖的 spec
- Affected code:
  - `/workspace/Dockerfile`（重写为三阶段）
  - `/workspace/.dockerignore`（新建）
  - `/workspace/docker-compose.yml`（同步镜像名与卷配置）
- 关键约束文件（只读参考，不修改）：
  - `brain_alpha_ops/config/_loader.py` — `PROJECT_ROOT = Path(__file__).resolve().parents[2]`，源码必须在 `/app/`
  - `brain_alpha_ops/data/loader/_state.py` — `_resolve_data_root` 依赖 `runtime_project_root()`，data/ 必须在 `/app/data/`
  - `brain_alpha_ops/web/misc/web_html.py` — `react_dist_path()` 返回 `brain_alpha_ops/web/react_app/dist`，dist/ 必须在该路径
  - `pyproject.toml` — optional-dependencies: test/dev/browser，生产仅需 browser + core
  - `brain_alpha_ops/web/react_app/package.json` — 前端构建脚本

## ADDED Requirements

### Requirement: 三阶段多阶段构建
`Dockerfile` SHALL 采用三阶段多阶段构建（webbuild → pybuilder → runtime），每个阶段职责单一。

#### Scenario: 构建阶段隔离
- **WHEN** 执行 `docker build`
- **THEN** Stage 1 构建前端 dist/
- **AND** Stage 2 构建生产依赖 wheel 并清理源码树
- **AND** Stage 3 仅从 Stage 1 拷贝 dist/、从 Stage 2 拷贝清理后的源码与 wheel
- **AND** runtime 阶段不包含 node_modules、前端源码、test/dev 依赖

### Requirement: 生产依赖排除 test/dev
运行时镜像 SHALL 仅包含 `[browser]` extra 与核心依赖，SHALL NOT 包含 `[test]` 或 `[dev]` extras（pytest、ruff、mypy、pip-audit）。

#### Scenario: 运行时无开发工具
- **WHEN** 检查 runtime 镜像已安装的 pip 包
- **THEN** 不存在 pytest、ruff、mypy、pip-audit
- **AND** 存在 playwright 及核心依赖（pyyaml、requests、jsonschema）

### Requirement: 前端仅 dist/ 进入运行时
运行时镜像 SHALL 仅包含前端构建产物 `dist/`，SHALL NOT 包含 `node_modules/`、`src/`、`package.json` 等前端源码与依赖。

#### Scenario: 运行时前端产物
- **WHEN** 检查 runtime 镜像 `brain_alpha_ops/web/react_app/` 目录
- **THEN** 仅存在 `dist/` 子目录
- **AND** 不存在 `node_modules/` 或 `src/`

### Requirement: 运行时路径正确性
Python 源码 SHALL 安装在 `/app/brain_alpha_ops/`，使 `Path(__file__).resolve().parents[2]` 解析为 `/app/`，从而 `data/` 和 `config/` 正确解析为 `/app/data/` 和 `/app/config/`。

#### Scenario: PROJECT_ROOT 解析
- **WHEN** 容器内执行 `from brain_alpha_ops.config import PROJECT_ROOT`
- **THEN** `PROJECT_ROOT` 等于 `/app`
- **AND** `runtime_project_root()` 返回 `/app`

### Requirement: 持久化卷声明
`Dockerfile` SHALL 通过 `VOLUME` 声明 `/app/data` 和 `/app/config`，并在构建时 `mkdir -p` 创建 `/app/data`、`/app/config`、`/app/artifacts/evidence`。

#### Scenario: 卷声明
- **WHEN** 检查 Dockerfile
- **THEN** 存在 `VOLUME ["/app/data", "/app/config"]`
- **AND** 存在 `mkdir -p /app/data /app/config /app/artifacts/evidence`

### Requirement: 端口与健康检查
`Dockerfile` SHALL `EXPOSE 8765` 并配置 HEALTHCHECK 探测 `/api/health` 端点。

#### Scenario: 健康检查配置
- **WHEN** 检查 Dockerfile
- **THEN** 存在 `EXPOSE 8765`
- **AND** 存在 `HEALTHCHECK` 指令探测 `http://127.0.0.1:8765/api/health`

### Requirement: .dockerignore 优化构建上下文
项目根目录 SHALL 包含 `.dockerignore`，排除 node_modules、__pycache__、虚拟环境、IDE 配置、测试与文档目录，减少构建上下文体积。

#### Scenario: 构建上下文精简
- **WHEN** 执行 `docker build`
- **THEN** node_modules、.git、.venv、tests/、docs/ 等不进入构建上下文

### Requirement: docker-compose.yml 同步
`docker-compose.yml` SHALL 与多阶段 Dockerfile 同步，声明镜像名、端口、环境变量、data/config bind mount、artifacts 命名卷与健康检查。

#### Scenario: compose 配置完整
- **WHEN** 检查 docker-compose.yml
- **THEN** 存在 `image: brain-alpha-ops:0.5.0`
- **AND** volumes 包含 `./data:/app/data`、`./config:/app/config`、`brain-alpha-artifacts:/app/artifacts`
- **AND** 顶层 `volumes:` 声明 `brain-alpha-artifacts`

### Requirement: Playwright Chromium 运行时
运行时镜像 SHALL 安装 Playwright Chromium 浏览器及其系统依赖库（libnss3、libgtk-3-0 等），以支持 browser 执行模式。SHALL NOT 删除 `~/.cache`（Chromium 存储位置）。

#### Scenario: 浏览器可用
- **WHEN** 容器内执行 `python -m playwright install chromium`
- **THEN** Chromium 安装成功
- **AND** 运行时镜像包含 `~/.cache/ms-playwright/` 下的浏览器二进制
