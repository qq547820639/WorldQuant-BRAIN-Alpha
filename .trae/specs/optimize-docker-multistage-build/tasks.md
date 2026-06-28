# Docker 多阶段构建优化 - 实施计划

# Tasks

- [ ] Task 1: 重写 Dockerfile 为三阶段多阶段构建
  - [ ] SubTask 1.1: Stage 1 `webbuild`（node:22-bookworm）— 拷贝 react_app/ 全目录，`npm ci && npm run build` 产出 dist/
  - [ ] SubTask 1.2: Stage 2 `pybuilder`（python:3.13-slim）— 安装完整构建环境 `.[browser,test,dev]`，用 `pip wheel ".[browser]"` 构建生产 wheel（排除 test/dev），删除项目自身 wheel，清理源码树（移除 react_app/、__pycache__、*.pyc）
  - [ ] SubTask 1.3: Stage 3 `runtime`（python:3.13-slim）— apt 安装 Chromium 系统依赖库，离线安装生产 wheel（`--no-index --find-links=/wheels`），`playwright install chromium`，不删除 `~/.cache`
  - [ ] SubTask 1.4: runtime 拷贝 — 从 pybuilder 拷贝清理后的 `brain_alpha_ops/` 源码、`launch_web.py`，从 webbuild 拷贝 `dist/`，拷贝 `data/` 和 `config/` 种子数据
  - [ ] SubTask 1.5: runtime 声明 — `mkdir -p /app/data /app/config /app/artifacts/evidence` + chmod，`VOLUME ["/app/data","/app/config"]`，`EXPOSE 8765`，HEALTHCHECK 探测 `/api/health`，`CMD ["python","launch_web.py"]`

- [ ] Task 2: 新建 .dockerignore 优化构建上下文
  - [ ] SubTask 2.1: 排除前端 node_modules 与 dist（构建时重新生成）
  - [ ] SubTask 2.2: 排除 Python 缓存（__pycache__、*.pyc、*.egg-info、.pytest_cache、build/）
  - [ ] SubTask 2.3: 排除虚拟环境（.venv、venv、env）
  - [ ] SubTask 2.4: 排除版本控制与 IDE 配置（.git、.github、.trae、.mimocode、.vscode、.idea、.DS_Store）
  - [ ] SubTask 2.5: 排除文档/测试/fixtures（docs/、fixtures/、tests/、*.md 但保留 README.md）

- [ ] Task 3: 同步 docker-compose.yml
  - [ ] SubTask 3.1: 添加 `image: brain-alpha-ops:0.5.0`
  - [ ] SubTask 3.2: volumes 添加 `./config:/app/config` bind mount
  - [ ] SubTask 3.3: volumes 添加 `brain-alpha-artifacts:/app/artifacts` 命名卷
  - [ ] SubTask 3.4: 顶层声明 `volumes: brain-alpha-artifacts:`
  - [ ] SubTask 3.5: 验证 YAML 语法有效

- [ ] Task 4: 验证与报告
  - [ ] SubTask 4.1: 确认 Dockerfile 三阶段结构正确（webbuild/pybuilder/runtime）
  - [ ] SubTask 4.2: 确认 runtime 无 test/dev 依赖（pip wheel 仅 `.[browser]`）
  - [ ] SubTask 4.3: 确认 runtime 仅含 dist/（无 node_modules/src）
  - [ ] SubTask 4.4: 确认 PROJECT_ROOT 路径约束（源码在 /app/brain_alpha_ops/）
  - [ ] SubTask 4.5: 确认 VOLUME/EXPOSE/HEALTHCHECK 配置完整
  - [ ] SubTask 4.6: 报告修改文件清单与优化前后镜像预估大小对比

# Task Dependencies
- Task 1、Task 2、Task 3 可并行执行（互相独立）
- Task 4 依赖 Task 1-3 全部完成
