# BRAIN Alpha Ops

BRAIN Alpha Ops 是一个面向 WorldQuant BRAIN 的本地量化研究与生产辅助工具。它把 Alpha 生成、候选筛选、本地评分、官方预检/回测、提交安全门禁、研究记忆、Assistant Guidance 和 Web 控制台放在同一套可配置流程里，目标是以可追踪、可复用、账号安全优先的方式推进 Alpha 研究。

## 核心原则

- 生产环境和 mock 环境严格隔离。
- 低质量候选只做本地预筛和归档，不浪费官方 API 预算。
- 官方模拟、检查结果和提交账本共同决定是否允许提交。
- 自动提交默认关闭；开启后仍必须通过质量、相关性、换手、集中度、重复表达式、微变体和节奏控制等门禁。
- 配置阈值是可调研究策略，不伪装成官方硬规则。
- 凭证优先通过环境变量传入，不写入仓库、日志或运行结果。

## 快速开始

先校验配置文件：

```powershell
python -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

运行本地研究流水线：

```powershell
python run_pipeline.py
```

启动本地 Web 控制台：

```powershell
python launch_web.py
```

常用 CLI：

```powershell
python -m brain_alpha_ops.cli run --config config/run_config.json --cycles 1 --candidates 12
python -m brain_alpha_ops.cli assistant-context --config config/run_config.json
python -m brain_alpha_ops.cli assistant-request --config config/run_config.json
python -m brain_alpha_ops.cli assistant-guidance-audit --config config/run_config.json
python -m pytest
```

Web 控制台默认监听本机地址，提供候选池、等待回测、回测中、达标、可提交、已提交、不达标、云端数据、研究记忆和生命周期视图。连续生产、云端同步、批量检查和提交互斥执行，减少重复点击和官方 API 争用。

## 生产凭证

生产环境需要在 `config/run_config.json` 中设置：

```json
{
  "environment": "production"
}
```

凭证通过环境变量传入：

```powershell
$env:BRAIN_USERNAME="your@email.com"
$env:BRAIN_PASSWORD="your_password"
python run_pipeline.py
```

也可以使用 `BRAIN_TOKEN`。不要把账号、密码或 token 写进配置文件、脚本、文档或日志。

## 配置文件

主要配置入口是 `config/run_config.json`。

- `environment`: `mock` 或 `production`。
- `auto_submit`: 是否允许自动提交，默认 `false`。
- `credentials`: 只建议配置环境变量名，不建议写入真实凭证。
- `web`: 本地控制台 host、port、会话 TTL 和多会话策略。
- `ops.settings`: WorldQuant BRAIN 的 region、universe、delay、neutralization、decay、truncation、language、type 等设置。
- `ops.budget`: 每轮候选数量、官方预检/模拟数量、候选池大小、连续运行、云端同步和 Assistant Guidance 策略。
- `ops.scoring`: prior/empirical/checklist 分层权重、本地排序权重和 Assistant Guidance 评分调整参数。
- `ops.thresholds`: Sharpe、Fitness、Turnover、相关性、集中度等质量阈值。
- `ops.submission_policy`: 自动提交频率、表达式相似度和提交前检查策略。
- `ops.official_api`: 官方 API 路径、超时、轮询、限速重试和缓存目录。

配置加载会进行类型、枚举、数值范围、URL 和 path 校验。坏配置会在启动早期失败，并给出结构化错误。

## Assistant Guidance

项目支持把本地研究记忆和外部 LLM 建议转换为可复用的生成偏置：

```powershell
python -m brain_alpha_ops.cli assistant-context --config config/run_config.json
python -m brain_alpha_ops.cli assistant-request --config config/run_config.json
python -m brain_alpha_ops.cli assistant-save-guidance --config config/run_config.json --input assistant_response.json
python -m brain_alpha_ops.cli assistant-guidance-audit --config config/run_config.json
```

系统会记录 guidance digest、置信度、历史结果和本地排序调整资格。历史表现较弱的 guidance 不会继续作为生成偏置使用。

## 质量门禁

交接、打包或上线前运行聚合质量门禁：

```powershell
python scripts/quality_gate.py
```

它会依次执行 Python 语法编译检查、配置校验、依赖策略检查、六大技术红线验证、前端内联 JavaScript 同步/语法检查、敏感信息扫描和 pytest。需要快速预检时可以跳过测试：

```powershell
python scripts/quality_gate.py --skip-tests
```

机器可读输出：

```powershell
python scripts/quality_gate.py --json
```

单独运行前端语法检查：

```powershell
python scripts/check_frontend_syntax.py --json
```

单独运行 BRAIN 技术红线验证：

```powershell
python -m brain_alpha_ops.compliance.redline_verifier --block --json
```

单独运行敏感信息扫描：

```powershell
python scripts/scan_sensitive_artifacts.py --json --fail-on-findings
python scripts/scan_sensitive_artifacts.py --include-all --json --fail-on-findings
```

如果确认发生真实凭证泄露，应立即轮换账号密码或 token，并清理相关历史记录。

## 项目结构

- `brain_alpha_ops/config.py`: 运行配置、阈值、提交策略和配置校验。
- `brain_alpha_ops/runner.py`: CLI、Web 和编辑器入口共用的运行适配层。
- `brain_alpha_ops/models.py`: 候选、指标、门禁、事件等核心数据结构。
- `brain_alpha_ops/brain_api/`: 官方 API 与 mock API 适配。
- `brain_alpha_ops/research/`: 生成、评分、诊断、安全门禁、研究记忆和流水线。
- `brain_alpha_ops/web.py`: 本地 Web API、任务状态和控制台服务。
- `brain_alpha_ops/web/`: 前端模板和拆分后的 JavaScript 视图。
- `config/`: 运行配置和策略预设。
- `docs/`: 架构、接口、评审和阶段性设计文档。
- `scripts/`: 构建、质量门禁、前端语法检查和敏感信息扫描脚本。
- `tests/`: pytest 测试套件。

## Windows 打包

生成 Windows 可执行文件：

```powershell
.\scripts\build_windows.ps1
```

输出位于 `dist\BrainAlphaOps.exe`。当前构建使用本地 Web 控制台作为主要 UI。

## 当前改造状态

已完成的关键加固包括：

- 集中配置校验与 CLI `validate-config`。
- Web payload 数值解析和上限控制。
- 官方 API 分页最大页数、重复页和总量停止保护。
- Assistant Guidance 的持久化、复用、历史结果追踪和审计。
- 本地研究记忆与离线 LLM 请求上下文打包。
- 前端内联脚本语法检查及测试覆盖。
- 敏感信息扫描 JSON 输出、误报收敛和测试覆盖。
- 本地聚合质量门禁 `scripts/quality_gate.py`，覆盖 Python compileall、配置、依赖策略、红线验证、前端语法、敏感扫描和 pytest。
- 科学评分封装 `brain_alpha_ops/scoring/official_scoring.py`，提供官方 Pass/Fail 对齐模拟、可配置门禁、评分归因和 JSONL 历史追踪。
- 用户体验层 `brain_alpha_ops/ux/guided_pipeline.py`，提供流程引导、进度回调、可操作错误提示、断点文件和运行历史。

建议后续继续推进：

- 清理剩余文档和代码注释中的乱码。
- 将根目录临时联调脚本迁移到 `scripts/`。
- 拆分超长的 `pipeline`、`web` handler 和 official adapter。
- 在 CI 中接入 `quality_gate.py`，并逐步加入 ruff、类型检查和覆盖率阈值。
