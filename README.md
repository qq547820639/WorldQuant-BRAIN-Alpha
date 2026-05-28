# brain-alpha-ops

WorldQuant BRAIN Alpha 研究的本地工作台。

`brain-alpha-ops` 把 Alpha 候选生成、官方回测、云端 Alpha 同步、提交前检查、风险原因追踪和交付门禁放在同一个本地工具里。项目默认使用生产环境的 WorldQuant BRAIN API，默认不自动提交 Alpha，凭据推荐只通过环境变量或本地 Web 会话输入。

> 版本：v0.3.0
> 运行环境：Python 3.10+
> 交付形态：PyPI 包 + 本地 Web 控制台
> Web 服务：Python 标准库 HTTP Server
> 前端：内联 Web 控制台，另含 React 18 控制台源码

## 核心能力

- 本地 Web 控制台：在浏览器中完成连接、同步、生产搜索、检查和提交前确认。
- 生产配置校验：`run_config.json` 支持片段覆盖，加载时会合并默认值并执行 schema 与过程校验。
- 官方 BRAIN 对齐：区域、Universe、Delay、Neutralization、Alpha Type、API 路径和阈值来自统一 canonical 定义。
- 提交保护：默认关闭自动提交，提交前执行云端同步、重复检查、官方指标和安全门禁。
- 研究记忆：保留候选、回测、云端 Alpha、检查结果和诊断信息，便于复盘。
- 安全交付门禁：包含秘密扫描、XSS sink 检查、依赖策略、模块尺寸、官方契约和最终发布门禁。

## 快速开始

```bash
git clone <your-repository-url>
cd WorldQuant-BRAIN-Alpha

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[test]"
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

## 凭据配置

不要把 BRAIN 账号、密码、Token、Cookie 写入 README、配置文件、测试文件、截图或提交记录。

推荐使用环境变量：

```bash
export BRAIN_USERNAME="your-email@example.com"
export BRAIN_PASSWORD="your-password"
# 或者使用 token
export BRAIN_TOKEN="your-token"
```

Windows PowerShell：

```powershell
$env:BRAIN_USERNAME="your-email@example.com"
$env:BRAIN_PASSWORD="your-password"
# 或者使用 token
$env:BRAIN_TOKEN="your-token"
```

Web 控制台也支持在本地页面中临时填写账号信息。命令行参数 `--username`、`--password`、`--token` 已废弃，默认会被拒绝，避免凭据进入 shell 历史或进程列表。

## 启动 Web 控制台

```bash
python3 launch_web.py
```

默认地址：

```text
http://127.0.0.1:8765
```

推荐第一次使用顺序：

1. 打开 Web 控制台。
2. 确认运行环境为 production。
3. 输入本地会话凭据，或先设置环境变量。
4. 点击“同步云端数据”。
5. 点击“开始生产搜索”。
6. 在候选池查看排序分、状态和风险原因。
7. 对达标候选执行“检查”。
8. 只在确认通过检查后再处理提交队列。

如果端口被占用，修改 [config/run_config.json](config/run_config.json) 中的 `web.port`，或让服务自动选择可用本地端口。

## CLI 用法

校验配置：

```bash
python3 -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

运行生产管线：

```bash
python3 -m brain_alpha_ops.cli run --config config/run_config.json
```

也可以使用编辑器友好的入口：

```bash
python3 run_pipeline.py --config config/run_config.json --validate-only
python3 run_pipeline.py --config config/run_config.json
```

常用只读诊断：

```bash
python3 -m brain_alpha_ops.cli memory-summary --config config/run_config.json
python3 -m brain_alpha_ops.cli research-observability --config config/run_config.json
python3 -m brain_alpha_ops.cli diagnose --config config/run_config.json --json
python3 -m brain_alpha_ops.cli release-gate --config config/run_config.json --json
```

## 配置文件

默认配置位于 [config/run_config.json](config/run_config.json)。关键字段：

| 字段 | 说明 |
|---|---|
| `environment` | 只支持 `production` |
| `auto_submit` | 默认 `false`，建议保持关闭 |
| `credentials.*_env` | 凭据环境变量名称 |
| `web.host` / `web.port` | 本地 Web 控制台监听地址 |
| `ops.storage_dir` | 运行数据、任务状态和研究记忆目录 |
| `ops.settings` | BRAIN 官方回测设置 |
| `ops.budget` | 候选数量、官方调用预算和运行节奏 |
| `ops.thresholds` | 官方检查和本地质量目标 |
| `ops.submission_policy` | 自动提交限额与重复保护 |
| `ops.official_api` | BRAIN API 路径、超时、缓存和限速设置 |

配置文件可以只写需要覆盖的片段，加载时会合并 dataclass 默认值，再执行完整校验。

## 安全默认值

- 默认只绑定 `127.0.0.1`。
- 默认关闭自动提交。
- 默认不把凭据写入配置文件。
- Web 会话有本地 session 和 CSRF 保护。
- 远程访问需要显式配置并设置管理 Token。
- 测试截图目录 `data/e2e_screenshots/` 已被忽略。
- CI 秘密扫描覆盖测试目录和 Git 历史。
- 认证响应、Token、Cookie 和敏感片段会在用户可见输出中脱敏。

安全扫描：

```bash
python3 scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history
```

## 质量门禁

本地快速验证：

```bash
python3 -m pytest tests/ -v --tb=short
```

交付前建议执行：

```bash
python3 scripts/check_dependency_policy.py
python3 scripts/check_frontend_innerhtml.py
python3 scripts/check_module_size.py
python3 scripts/check_brain_contract.py
python3 scripts/check_diagnosis_gap_coverage.py --strict-freshness
python3 scripts/final_release_gate.py
```

CI 使用 `requirements.lock` 安装依赖，并执行秘密扫描、契约检查和测试套件。

## 前端与 Web 资源

主要 Web 入口：

- [launch_web.py](launch_web.py)
- [brain_alpha_ops/web.py](brain_alpha_ops/web.py)
- [brain_alpha_ops/web/index.html](brain_alpha_ops/web/index.html)
- [brain_alpha_ops/web/index_template.html](brain_alpha_ops/web/index_template.html)
- [brain_alpha_ops/web/js/app.js](brain_alpha_ops/web/js/app.js)

如果修改了 `brain_alpha_ops/web/js/`、`brain_alpha_ops/web/css/` 或模板文件，需要同步内联 HTML：

```bash
python3 brain_alpha_ops/web/build_inline.py --check --json
```

## 目录结构

```text
brain_alpha_ops/
  brain_api/              官方 BRAIN API 适配与 canonical 定义
  compliance/             红线检查与发布合规
  research/               Alpha 生成、回测、评分、记忆与管线
  scoring/                官方评分、门禁和归因
  web/                    本地 Web 控制台资源
  web_*.py                Web API、任务、会话和安全模块
config/
  run_config.json         默认运行配置
data/
  api_cache/              官方上下文缓存
  *.jsonl                 本地运行与研究记录
docs/
  *.md                    交付、诊断和验收文档
scripts/
  *.py                    CI、质量门禁和交付检查脚本
tests/
  test_*.py               单元、契约和集成测试
```

## 故障排查

| 现象 | 处理方式 |
|---|---|
| Web 页面打不开 | 确认 `launch_web.py` 仍在运行；检查 `web.port` 是否被占用 |
| 页面显示未连接 | 检查环境变量或 Web 控制台中的账号输入 |
| 同步云端失败 | 检查凭据、网络、BRAIN 登录状态和限速 |
| 没有候选 | 先同步云端数据，再保持默认参数运行生产搜索 |
| 检查按钮不可用 | 确认存在达标候选，且没有其他任务正在运行 |
| 提交按钮不可用 | 查看“风险 / 原因”列，确认候选已通过提交前检查 |
| 配置校验失败 | 运行 `python3 -m brain_alpha_ops.cli validate-config --config config/run_config.json` 查看具体字段 |

## 交付状态

当前交付重点：

- P0：硬编码凭据清理、敏感截图忽略、CI 秘密扫描全覆盖。
- P1：测试依赖声明、lockfile、配置校验、XSS sink 检查。
- P2：命令行凭据参数废弃、认证响应脱敏。
- P3：可访问性和架构拆分持续迭代。

详细任务目标见 [docs/TASK_OBJECTIVES.md](docs/TASK_OBJECTIVES.md)。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
