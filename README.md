# BRAIN Alpha Ops

BRAIN Alpha Ops 是面向 WorldQuant BRAIN 的本地 Alpha 研究与生产辅助工具。项目把候选 Alpha 生成、本地预筛选、官方 Check、官方 Simulation、提交前检查、运行历史、Web 控制台和诊断门禁组织成一条可审计的工作流。

项目的目标不是绕过 BRAIN 平台规则，而是把关键动作尽量对齐官方 API、官方字段、官方算子、官方数据集和可追踪配置，减少手工试错、重复提交和不安全操作。

## 当前状态

最近一次本地源码验证时间：2026-05-26。

| 项目 | 当前结果 |
|---|---|
| 全量测试 | 755 passed |
| CI 修复验证 | `tests/test_tasks.py` 与 `tests/test_windows_packaging.py` 聚焦通过 |
| 官方上下文文件 | 字段、算子、数据集、元数据和刷新状态均被打包清单覆盖 |
| Windows 打包清单 | `BrainAlphaOps.spec` 已作为源码文件纳入仓库 |
| Web 控制台 | 本地标准库服务，无独立前端构建链路 |

最终发布判断仍应把源码测试和打包后 `dist\BrainAlphaOps.exe` 的真实启动验证分开处理。测试通过说明源码行为健康；EXE 是否能在目标机器启动，是独立发布门禁。

## 核心能力

- 生成候选 Alpha：支持假设驱动、经验反馈、随机探索、主题模板和助手指导等生成路径。
- 本地预筛选：用表达式检查、去重、数据合规、风险门槛、参数审计和质量评分减少无效官方调用。
- 官方 API 对接：支持认证、官方字段/算子/数据集刷新、Alpha Check、Simulation、云端 Alpha 同步和提交。
- 安全提交：默认关闭自动提交，提交前执行官方 Check、相似度、质量门槛和提交策略约束。
- Web 控制台：在本地浏览器查看候选池、云端 Alpha、回测队列、运行状态、历史记录、风险提示和诊断结果。
- 研究记忆：保存运行摘要、候选结果、经验反馈、checkpoint、表达式索引和云端记录索引。
- 质量门禁：串联配置校验、文本编码、模块体量、官方上下文、BRAIN contract、诊断 Gap、敏感信息扫描和测试。
- Windows 打包：通过 PyInstaller 生成 `BrainAlphaOps.exe`，并携带官方上下文、Web 页面、假设库和提示词模板。

## 环境要求

- Python 3.10 或更高版本
- Windows PowerShell，用于本地 EXE 打包脚本
- WorldQuant BRAIN 账号，用于真实官方接口
- 可选：PyInstaller，用于构建 Windows EXE

Web 控制台服务端使用 Python 标准库实现，不需要 Node、Vite 或其他前端构建工具。

## 安装

```powershell
git clone https://github.com/qq547820639/WorldQuant-BRAIN-Alpha.git
cd WorldQuant-BRAIN-Alpha

python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -e .
```

开发和测试环境：

```powershell
pip install -e ".[test,dev]"
```

如果在 Codex 桌面环境中运行，通常使用内置 Python，并让 `PYTHONPATH` 包含 `.codex_pydeps`：

```powershell
$env:PYTHONPATH = ".codex_pydeps"
& "C:\Users\54782\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest -q --basetemp .pytest_tmp
```

## 凭据设置

不要把 BRAIN 用户名、密码或 token 写进代码、配置文件、README、日志或提交记录。运行时通过进程环境变量传入：

```powershell
$env:BRAIN_USERNAME = "your@email.com"
$env:BRAIN_PASSWORD = "your_password"
```

如果使用 token：

```powershell
$env:BRAIN_TOKEN = "your_token"
```

[config/run_config.json](config/run_config.json) 只保存环境变量名称，不保存真实凭据。

## 快速开始

校验配置：

```powershell
python -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

刷新官方字段、算子和数据集上下文：

```powershell
python fetch_official_context.py --config config/run_config.json --json
```

运行一轮研究流水线：

```powershell
python -m brain_alpha_ops.cli run --config config/run_config.json --cycles 1 --candidates 20
```

运行带 checkpoint 和进度阶段的引导模式：

```powershell
python -m brain_alpha_ops.cli guided-run --config config/run_config.json
```

启动本地 Web 控制台：

```powershell
python launch_web.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## Web 控制台

Web 控制台适合日常操作和排查。它覆盖候选生成、云端同步、批量 Check、Simulation 状态、提交前检查、运行历史和诊断视图。

| 视图 | 用途 |
|---|---|
| 候选池 | 查看当前生成、保留和评分后的 Alpha 候选 |
| 待回测 | 查看通过本地门槛、准备进入官方 Simulation 的候选 |
| 回测中 | 查看正在等待官方 Simulation 结果的任务 |
| 达标 | 查看通过质量门槛的候选 |
| 可提交 | 查看满足提交前置条件的候选 |
| 已提交 | 查看已经提交到 BRAIN 的记录 |
| 不达标 | 查看失败候选和原因 |
| 云端数据 | 同步和去重 BRAIN 平台已有 Alpha |
| 研究记忆 | 查看历史运行摘要、经验反馈和对比 |
| 诊断 | 查看红线、参数、数据链路、评分、UX 和 Gap 覆盖状态 |

Web 控制台默认只监听本机 `127.0.0.1`。如果需要远程访问，先审查 [config/run_config.json](config/run_config.json) 中的 `web.allow_remote` 和管理 token 设置。

## 常用 CLI

所有命令都通过 `python -m brain_alpha_ops.cli <command>` 调用。

| 命令 | 用途 |
|---|---|
| `run` | 运行完整研究流水线 |
| `guided-run` | 运行带 checkpoint、阶段进度和历史记录的引导流程 |
| `validate-config` | 校验配置文件 |
| `init-config` | 生成默认配置 |
| `diagnose` | 生成生产诊断、Gap 矩阵和升级建议 |
| `score` | 对单个候选 Alpha 执行完整评分 |
| `redline` | 执行六大技术红线检查 |
| `release-gate` | 执行最终发布就绪检查 |
| `memory-summary` | 汇总本地研究记忆 |
| `memory-guidance` | 导出生成器可用的研究记忆指导 |
| `expression-index` | 查询 FASTEXPR 表达式历史索引 |
| `record-index` | 查询云端 Alpha/backtest 记录索引 |
| `research-observability` | 汇总研究健康状态、回测、错误和日志 |
| `assistant-context` | 导出 LLM 可用上下文包 |
| `assistant-request` | 生成 provider-neutral 的 LLM 请求包 |
| `assistant-parse` | 解析并规范化 LLM JSON 响应 |
| `assistant-guidance` | 把 LLM 响应转换成生成器指导 |
| `assistant-save-guidance` | 保存可复用 LLM 指导 |
| `assistant-guidance-audit` | 审计已保存指导的复用价值 |
| `assistant-cross-review` | 对 LLM 响应做交叉审查 |
| `anti-overfit` | 对候选执行反过拟合检查 |
| `rolling-validate` | 对候选执行滚动窗口验证 |

示例：

```powershell
python -m brain_alpha_ops.cli diagnose --config config/run_config.json --json --output docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md
python -m brain_alpha_ops.cli redline --json
python -m brain_alpha_ops.cli release-gate --config config/run_config.json --json
```

## 配置重点

主配置文件是 [config/run_config.json](config/run_config.json)。

| 配置区 | 说明 |
|---|---|
| `environment` | 当前支持 `production` |
| `auto_submit` | 是否允许自动提交，默认 `false` |
| `credentials` | 凭据环境变量名称，不保存真实凭据 |
| `web` | 本地控制台 host、port、浏览器打开策略和管理 token |
| `ops.settings` | BRAIN 平台设置，如 region、universe、delay、neutralization、truncation |
| `ops.budget` | 每轮候选数、官方 Check 数、Simulation 数、并发数和 retained pool |
| `ops.thresholds` | Sharpe、Fitness、Turnover、Correlation、Concentration 等硬门槛 |
| `ops.submission_policy` | 每日提交上限、相似度上限、微变体阻断和提交前 Check |
| `ops.official_api` | 官方 API path、超时、轮询、速率限制和缓存 TTL |

关键默认阈值：

| 阈值 | 默认值 |
|---|---|
| `min_sharpe` | `1.25` |
| `min_sharpe_delay0` | `2.0` |
| `min_fitness` | `1.0` |
| `min_fitness_delay0` | `1.3` |
| `min_turnover` | `0.01` |
| `platform_max_turnover` | `0.70` |
| `max_self_correlation` | `0.70` |
| `max_prod_correlation` | `0.70` |
| `max_weight_concentration` | `0.10` |
| `sub_universe_sharpe_min_ratio` | `0.75` |

## 质量门禁

快速门禁：

```powershell
python scripts/quality_gate.py --skip-tests --json
```

严格官方上下文门禁：

```powershell
python scripts/quality_gate.py --strict-official-context --skip-tests --json
```

完整门禁和测试：

```powershell
python scripts/quality_gate.py --strict-official-context --json
```

常用单项检查：

```powershell
python -m compileall -q brain_alpha_ops scripts tests
python scripts/check_text_encoding.py --root . --json
python scripts/check_module_size.py --json
python scripts/check_official_context.py --config config/run_config.json --strict-freshness --json
python scripts/check_brain_contract.py --config config/run_config.json --strict-freshness --json
python scripts/check_diagnosis_gap_coverage.py --config config/run_config.json --strict-freshness --json
python scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings
```

全量测试：

```powershell
pytest -q --basetemp .pytest_tmp
```

GitHub Actions 中的测试在 Linux 环境运行，因此不要依赖仅存在于本地但未提交的文件。打包相关测试会读取仓库根目录的 `BrainAlphaOps.spec`。

## 生产诊断报告

生成最新诊断报告：

```powershell
python -m brain_alpha_ops.cli diagnose --config config/run_config.json --json --output docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md
```

报告覆盖：

- 六大技术红线
- 官方字段、算子、数据集加载和 freshness
- 参数审计和阈值零偏差
- BRAIN contract 对齐
- 本地评分、API-shaped simulation 和归因摘要
- Web 前端 inline 同步
- checkpoint 和 run-history replay
- 诊断 Gap 矩阵
- 已完成项和未完成项

## Windows EXE 打包

打包前先跑门禁：

```powershell
python scripts/quality_gate.py --strict-official-context --skip-tests --json
```

构建 EXE：

```powershell
.\scripts\build_windows.ps1
```

输出位置：

```text
dist\BrainAlphaOps.exe
```

打包清单由 [BrainAlphaOps.spec](BrainAlphaOps.spec) 维护。它会把以下资源纳入发布包：

- `config/run_config.json`
- `data/official_fields.json`
- `data/official_fields.meta.json`
- `data/official_operators.json`
- `data/official_operators.meta.json`
- `data/official_datasets.json`
- `data/official_datasets.meta.json`
- `data/official_context_refresh_status.json`
- `brain_alpha_ops/web/index.html`
- `brain_alpha_ops/research/hypotheses`
- `brain_alpha_ops/research/prompts`

构建后建议执行真实启动验证：

```powershell
.\dist\BrainAlphaOps.exe --smoke-test --port 8765
```

再检查本地页面和健康接口：

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/api/health
```

## CI 排障

当前 CI 失败修复点：

- 并发任务存储测试不再假设刚创建的 job 一定还在缓存中，因为 `JobStore(max_jobs=75)` 会在多线程创建 150 条 job 时按设计裁剪旧记录。
- `BrainAlphaOps.spec` 不再被 `.gitignore` 排除，Linux checkout 能读取打包清单并验证官方上下文、假设库和提示词模板。

推荐本地复现顺序：

```powershell
pytest tests/test_tasks.py tests/test_windows_packaging.py -q --basetemp .pytest_tmp_ci_fix_focus
pytest tests/ -v --tb=short --basetemp .pytest_tmp_ci_fix_full
```

如果 CI 报 `FileNotFoundError: BrainAlphaOps.spec`，先确认该文件已被 Git 跟踪：

```powershell
git ls-files BrainAlphaOps.spec
```

## 安全边界

- 默认不自动提交 Alpha。
- 真实凭据只通过环境变量传入。
- Web 控制台默认只绑定本机地址。
- 任务持久化会遮蔽密码、token、cookie、Authorization header 等敏感内容。
- 官方调用受速率限制、重试和缓存策略约束。
- 发布前应同时通过源码测试、严格官方上下文门禁、敏感信息扫描和 EXE 启动验证。

## 目录速览

| 路径 | 说明 |
|---|---|
| `brain_alpha_ops/` | 核心 Python 包 |
| `brain_alpha_ops/brain_api/` | BRAIN 官方 API 与 mock API |
| `brain_alpha_ops/research/` | 生成、评分、回测、记忆、假设库和流水线 |
| `brain_alpha_ops/web/` | Web 静态页面 |
| `config/run_config.json` | 默认运行配置 |
| `data/` | 本地缓存、官方上下文、任务和运行数据 |
| `scripts/` | 质量门禁、打包、检查和维护脚本 |
| `tests/` | pytest 测试 |
| `docs/` | 诊断报告、架构说明和审计材料 |

## 贡献前检查

提交前建议至少运行：

```powershell
python scripts/quality_gate.py --skip-tests --json
pytest tests/test_tasks.py tests/test_windows_packaging.py -q --basetemp .pytest_tmp_focus
```

改动触及官方上下文、Web 控制台、提交策略、打包或任务持久化时，运行完整测试并补充对应聚焦测试。
