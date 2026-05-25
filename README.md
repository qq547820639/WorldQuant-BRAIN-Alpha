# BRAIN Alpha Ops

**WorldQuant BRAIN 量化研究助手** — 帮你高效生成 Alpha、自动筛选、本地评分、官方回测，并安全提交到 BRAIN 平台。

整个工具围绕一条清晰的工作流设计：生成 → 筛选 → 验证 → 回测 → 提交。你可以通过命令行、脚本或者本地网页控制台来操作，所有交互都走 WorldQuant BRAIN 官方 API，确保账号安全。

---

## 它能做什么？

- **Alpha 自动生成**：结合假设驱动、经验反馈和随机探索三种策略，自动生成候选 Alpha 表达式
- **智能筛选**：本地评分系统预先过滤低质量候选，只把最有潜力的送官方验证，节省 API 配额
- **官方对接**：自动调用 BRAIN 官方 API 进行 Alpha 检查（Check）、模拟回测（Simulation）和提交
- **多层门禁**：Sharpe、Fitness、换手率、集中度、表达式去重等多道质量关卡，不合格的不放行
- **Web 控制台**：本地网页界面，可视化查看候选池、回测进度、达标状态，支持一键检查和提交
- **研究记忆**：自动记录每次实验的结果和教训，辅助后续生成策略优化
- **安全第一**：凭证走环境变量，不落盘；自动提交默认关闭，需要手动或配置开启

---

## 环境要求

- **Python** >= 3.10
- 一个 WorldQuant BRAIN 账号（注册地址：https://platform.worldquantbrain.com）

---

## 安装

```powershell
# 克隆项目
git clone https://github.com/qq547820639/WorldQuant-BRAIN-Alpha.git
cd WorldQuant-BRAIN-Alpha

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -e .
```

Web 控制台完全基于 Python 标准库，无需额外安装前端依赖。

如果需要运行测试或开发，安装可选依赖：

```powershell
pip install -e ".[test,dev]"
```

---

## 快速开始

### 第一步：设置凭证

把 BRAIN 账号信息设成环境变量，**不要直接写在配置文件里**：

```powershell
$env:BRAIN_USERNAME = "your@email.com"
$env:BRAIN_PASSWORD = "your_password"
```

如果你用的是 token，可以设 `$env:BRAIN_TOKEN`。

### 第二步：检查配置

项目自带了一份默认配置 `config/run_config.json`，先验证一下：

```powershell
python -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

如果有问题会直接报出来，方便修正。

### 第三步：跑起来

**命令行模式** — 完整研究流水线：

```powershell
python run_pipeline.py
```

**Web 控制台模式** — 打开本地网页界面：

```powershell
python launch_web.py
```

浏览器会自动打开 `http://127.0.0.1:8765`，在这里你可以看到候选 Alpha 的完整生命周期。

---

## Web 控制台

Web 控制台提供一个直观的选项卡式界面，覆盖 Alpha 从生成到提交的全过程：

| 视图 | 说明 |
|------|------|
| 候选池 | 本轮生成的所有 Alpha，展示表达式和本地评分 |
| 等待回测 | 已通过本地筛选，排队等待官方回测 |
| 回测中 | 正在 BRAIN 平台执行模拟回测 |
| 达标 | 回测通过质量门槛的 Alpha |
| 可提交 | 满足所有提交条件的 Alpha，可以一键提交 |
| 已提交 | 成功提交到 BRAIN 的记录 |
| 不达标 | 未通过质量门槛的 Alpha 及失败原因 |
| 云端数据 | 同步显示 BRAIN 平台上已有的 Alpha 记录 |
| 研究记忆 | 历史实验的总结和经验 |
| 生命周期 | 完整的 Alpha 状态流转时间线 |

主要功能：
- **批量检查 & 提交**：选中多个 Alpha 一次性执行，提交操作互斥避免重复
- **云端同步**：自动拉取 BRAIN 平台已有 Alpha，做去重对比
- **连续生产**：支持持续多轮运行，每轮自动生成新候选
- **风险提示**：提交前展示风险等级和注意事项

---

## CLI 命令参考

所有命令都通过 `python -m brain_alpha_ops.cli <命令>` 调用。常用的是前几个，其他按需使用：

### 核心流水线

| 命令 | 说明 |
|------|------|
| `run` | 运行完整研究流水线 |
| `guided-run` | 带进度引导和检查点的研究流水线 |

```powershell
# 运行一轮，生成 12 个候选
python -m brain_alpha_ops.cli run --config config/run_config.json --cycles 1 --candidates 12

# 带引导模式的流水线（支持断点续跑）
python -m brain_alpha_ops.cli guided-run --config config/run_config.json
```

### 配置管理

| 命令 | 说明 |
|------|------|
| `init-config` | 生成默认配置文件 |
| `validate-config` | 校验配置文件是否合法 |

### 评分与诊断

| 命令 | 说明 |
|------|------|
| `score` | 对候选 Alpha 执行完整评分流水线 |
| `diagnose` | 生产诊断：差距矩阵、升级建议 |
| `anti-overfit` | 确定性反过拟合检查 |
| `rolling-validate` | 滚动窗口验证 |

### Assistant（LLM 辅助研究）

| 命令 | 说明 |
|------|------|
| `assistant-context` | 导出 LLM 可用的研究上下文 |
| `assistant-request` | 生成与模型无关的 LLM 请求 |
| `assistant-parse` | 解析标准化 LLM 响应 |
| `assistant-guidance` | 将 LLM 响应转为生成指南 |
| `assistant-save-guidance` | 持久化 LLM 建议供后续复用 |
| `assistant-guidance-audit` | 审计已保存指南的有效性 |
| `assistant-cross-review` | 对 LLM 响应做交叉审查 |

### 数据与记忆

| 命令 | 说明 |
|------|------|
| `memory-summary` | 查看本地研究记忆摘要 |
| `memory-guidance` | 导出生成器可用的研究记忆 |
| `expression-index` | 查看/查询表达式历史（SQLite） |
| `record-index` | 查看/查询 BRAIN Alpha 记录（SQLite） |
| `research-observability` | 研究健康状态、回测统计、错误日志 |

### 合规

| 命令 | 说明 |
|------|------|
| `redline` | 六大技术红线合规验证 |

---

## 配置说明

配置文件位于 `config/run_config.json`。主要板块：

### 基本设置
- **`environment`**：固定为 `"production"`，不提供 mock 模式
- **`auto_submit`**：是否允许自动提交（默认 `false`，建议手动控制）
- **`credentials`**：配置环境变量名称即可，不要填真实密码

### BRAIN 参数（`ops.settings`）
控制 Alpha 的基础属性：市场（USA/EUR/GLB）、股票池（TOP1000/2000/3000）、延迟、中性化、截尾等。

### 资源预算（`ops.budget`）
- **`max_candidates_per_cycle`**：每轮生成多少个候选
- **`max_official_validations_per_cycle`**：每轮最多送几个做官方 Alpha Check
- **`max_official_simulations_per_cycle`**：每轮最多送几个做回测
- **`run_forever`**：是否持续循环运行

### 质量门槛（`ops.thresholds`）
与 BRAIN 官方标准对齐的硬性门槛：
- **`min_sharpe`**：最低 Sharpe 比率（默认 1.25）
- **`min_fitness`**：最低 Fitness（默认 1.0）
- **`platform_max_turnover`**：最大换手率（默认 0.70）
- **`max_self_correlation`**：最大自相关性
- **`max_weight_concentration`**：最大权重集中度

### 提交策略（`ops.submission_policy`）
- **`max_auto_submissions_per_day`**：每天最多自动提交数
- **`max_expression_similarity`**：表达式相似度上限，防重复提交
- **`block_micro_variants`**：是否阻止微变体提交

---

## 质量门禁

提交代码或打包前，运行聚合质量检查：

```powershell
# 完整检查（含测试）
python scripts/quality_gate.py

# 快速检查，跳过测试
python scripts/quality_gate.py --skip-tests

# 输出 JSON 格式（适合 CI）
python scripts/quality_gate.py --json
```

质量门禁包含以下环节：
1. Python 语法编译检查
2. 配置合法性校验
3. 依赖策略检查
4. BRAIN 六大技术红线验证
5. 前端 JavaScript 语法检查
6. 敏感信息扫描
7. pytest 测试套件

也可以单独运行某一项：

```powershell
# 技术红线
python -m brain_alpha_ops.compliance.redline_verifier --block --json

# 敏感信息扫描
python scripts/scan_sensitive_artifacts.py --json --fail-on-findings

# 前端语法检查
python scripts/check_frontend_syntax.py --json
```

---

## 项目结构

```
brain_alpha_ops/
├── brain_api/         BRAIN 官方 API 封装和缓存
├── cli.py             命令行入口（20+ 子命令）
├── config.py          配置加载和校验
├── models.py          核心数据模型（候选、门禁、事件等）
├── runner.py          流水线运行适配层
├── compliance/        合规验证（技术红线）
├── data/              数据加载、字段/算子/数据集索引
├── research/          Alpha 生成、评分、回测、流水线
│   └── hypotheses/    假设库（YAML 驱动）
├── scoring/           多层评分系统和门禁
├── ux/                用户体验层（引导流程、历史记录）
├── web/               Web 前端（HTML + JS 模块）
│   ├── css/           样式
│   ├── js/            JavaScript 模块（API、状态、视图、组件）
│   └── index.html     控制台页面
├── web.py             Web API 服务端
├── web_*.py           Web 功能模块（提交、回测、评分、会话等）
├── production_diagnostics.py   生产诊断工具
├── observability.py            可观测性支持
└── jsonl.py            JSONL 日志读写
config/
├── run_config.json    主配置文件
└── presets.json       策略预设
scripts/              构建脚本、质量门禁、检查工具
tests/                pytest 测试套件
docs/                 架构设计、评审报告、诊断文档
```

---

## Windows 打包

可以把整个项目打包成一个独立的 `.exe` 文件，方便分发和使用：

```powershell
# 先跑质量检查
python scripts/quality_gate.py --skip-tests --json

# 打包
.\scripts\build_windows.ps1

# 输出文件
dist\BrainAlphaOps.exe
```

直接双击运行会启动 Web 控制台并打开浏览器。如果不想打开浏览器：

```powershell
.\dist\BrainAlphaOps.exe --no-browser --port 8765
```

打包后的验证：

```powershell
.\dist\BrainAlphaOps.exe --smoke-test --port 8765
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/health
```

---

## 开发

### 运行测试

```powershell
pytest                              # 全部测试
pytest -m "not slow"                # 跳过慢测试
pytest tests/test_web_html.py       # 单文件
pytest --cov=brain_alpha_ops        # 带覆盖率
```

### 代码检查

```powershell
ruff check brain_alpha_ops/         # 代码风格
mypy brain_alpha_ops/               # 类型检查
```

---

## 安全提示

- **永远不要**把 BRAIN 用户名、密码或 token 写进代码、配置文件或 commit 到 Git
- 凭证统一通过环境变量 `BRAIN_USERNAME` / `BRAIN_PASSWORD` / `BRAIN_TOKEN` 传入
- 如果怀疑凭证泄露，立即在 BRAIN 平台重置密码或 token
- 自动提交功能默认关闭，开启后也会受到频率、相似度和质量门槛的多重限制

---

## 许可

Internal use.
