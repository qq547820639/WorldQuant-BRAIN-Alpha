# Alpha 生产系统全面诊断与质量攻坚 — 综合评估报告

> **评估日期**: 2026-05-17 04:09  
> **评估范围**: `brain_alpha_ops` v0.3.0 全模块（39 `.py` + 12 `.js` + 8 YAML + 3 JSON + 17 tests）  
> **评估方法**: 全代码审计 + 配置文件交叉比对 + 数据层覆盖分析 + 已有实验复盘 + 历史文档追溯  
> **前置文档**: 本报告继承并更新了 `COMPREHENSIVE_DIAGNOSIS_20260516.md`、`TECH_COMPLIANCE_VERIFICATION_20260516.md`、`SCORING_SYSTEM_EVALUATION_20260516.md`、`REVIEW.md` 等历史评估

---

## 一、项目整体印象报告（一页纸）

### 1.1 项目定位

BRAIN Alpha Ops 是一个面向 WorldQuant BRAIN 量化平台的 **Alpha 全生命周期自动化管理系统**，以「**创作 → 估分 → 评价 → 迭代 → 收敛**」五环节闭环为核心设计理念。系统采用本地优先 + 零外部 Web 框架的极简架构，通过 singleton 加载 7,642 个官方字段、66 个算子、16 个数据集（另有 9 个低字段数 dataset 未轮换），是同类个人/开源工具中技术合规性最高的实现之一。

### 1.2 总体评分（六维度）

| 维度 | 评分 | 关键判断 |
|------|:----:|----------|
| **功能完整性** | **4.0/5** | 五环节闭环完整；Round 4 拒绝率 0%；但通过率仅 2.1%，52% Sharpe 为负 |
| **技术合规性** | **4.0/5** | 字段/算子 100% BRAIN API 来源；`context_defaults.py` fallback 有观察项 |
| **参数准确性** | **4.3/5** | 阈值与官网零偏差；支持 Delay-0/1 分档；评分公式权重标记为"经验" |
| **数据链路** | **3.5/5** ↓ | 16 Dataset ID 主流可用；但低字段数 dataset 未轮换；metrics 提取路径曾错误 |
| **用户体验** | **2.5/5** ↓ | SSE 管道已被移除；无实时进度反馈；前端为裸 API 交互风格 |
| **评分体系** | **4.1/5** | 三层 31 项 + 6 层门禁；可校准可演进；Bootstrap CI + Spearman 趋势检验 |

**综合评分**: **3.7 / 5.0** — 「工程骨架坚实，产能与体验两条腿跛行」

### 1.3 核心优势（5 项）

| # | 优势 | 证据 |
|---|------|------|
| 1 | **全链路闭环无断点** | 生成器（3 模式 70/20/10）→ 本地预筛 → 评分排序 → 官方验证 → 官方回测 → 质量门禁 → 安全门禁 → 自动提交 |
| 2 | **数据 100% 官方** | `OfficialDataLoader` 单例从 BRAIN API 拉取的 `official_*.json` 三文件作为唯一数据源，`FieldDatasetMapper` 双向索引 |
| 3 | **评分科学性** | 三层加权评分（prior 30% + empirical 45% + checklist 25%），支持 Grid Search 自动校准、Bootstrap CI |
| 4 | **安全门禁严密** | 提交账本去重 + 表达式相似度检测（阈值 0.9）+ 微小变体拦截 + 速率限制 + Mock ID 检测 |
| 5 | **假设驱动生产** | 8 个 YAML 结构化假设 + schema 校验 + EMA 经验权重自进化 |

### 1.4 核心痛点（6 项，按严重度排序）

| # | 痛点 | 严重度 | 现状 |
|---|------|:------:|------|
| 1 | **明文密码泄露** (R-01) | 🔴 严重 | `test_auth.py`、`test_api_format.py` 等 5 处硬编码真实账号密码，**未修复** |
| 2 | **Web API 无鉴权** (R-03) | 🔴 严重 | `/api/run`、`/api/submit`、`/api/shutdown` 无 CSRF/Origin 校验，**未修复** |
| 3 | **前端语法错误** (R-05) | 🔴 严重 | SSE 回调内 `await` 语法错误，SSE 管道被整块删除而非修复 → 无实时进度 |
| 4 | **产能阻塞** | 🔴 严重 | 通过率仅 2.1%（52% Sharpe 为负），模板多样性不足导致 Max Sharpe 仅 1.38 |
| 5 | **静默吞异常** (M-11) | 🟡 中等 | 提交记录、Account ledger、AlphaCheck 等关键路径 `try/except pass` |
| 6 | **依赖不可复现** (M-09) | 🟡 中等 | `pyproject.toml` 缺 `requests`/`pytest`，无 lockfile，版本号不一致 |

---

## 二、系统能力 vs 目标能力 Gap 分析矩阵

### 2.1 五环节闭环 Gap

| 环节 | 目标能力 | 当前能力 | Gap | 严重度 |
|------|----------|----------|-----|:------:|
| **创作** | 多样性高、字段覆盖广、假设驱动的 Alpha 表达式生成 | 三模式（70%假说驱动/20%经验/10%随机）；`validated_generator.py` 接入预校验（拒绝率 0%）| 模板仅 ~10 个骨架，52% Sharpe 为负，Max Sharpe 仅 1.38 | 🟡 一般 |
| **估分** | 与官方一致的评分模拟 | `OfficialBrainAPI.submit_simulation() → poll → fetch_result()` 完整模拟链路 | Fitness 交叉验证偶现偏差 > 0.05 | 🟡 一般 |
| **评价** | 多维度、结构化、可解释的评分 | 三层 31 项 + 6 层门禁 + Bootstrap CI | 缺少官方 Alpha Check 逐项回传至前端 | 🟡 一般 |
| **迭代** | 诊断→突变→AB 对比→优化 | `diagnostics.py` + `iterative_optimizer.py` + `experience.py` | 优化器未与 hypothesis_library 充分耦合 | 🟢 优化 |
| **收敛** | 持续监控质量趋势、检测停滞并切换策略 | `convergence.py` Bootstrap CI + Spearman + 7 策略轮换 | 策略切换条件偏保守（连续 5 轮） | 🟢 优化 |

### 2.2 技术合规 Gap（红线逐项）

| 合规红线 | 要求 | 当前状态 | Gap | 严重度 |
|----------|------|----------|-----|:------:|
| **字段来源** | 100% BRAIN API 真实字段 | ✅ 7,642 字段全部来自 `/data-fields` API | `context_defaults.py` 含 30 字段 fallback，仅在无 JSON 时启用 | 🟢 观察 |
| **算子来源** | 100% BRAIN API 真实算子 | ✅ 66 算子全部来自 `/operators` API | 历史 3 个虚构算子已删除 | ✅ 合规 |
| **阈值配置** | 与官网标准零偏差 | ✅ `run_config.json` 中全部阈值与 BRAIN 官方一致 | Delay-0/1 分档已实现 | ✅ 合规 |
| **Dataset ID** | 全量可用 | ⚠️ 16 个主流 ID 可用，9 个低字段 dataset 未轮换验证 | `option9`/`option8`/`socialmedia12` 等未纳入循环 | 🟡 一般 |
| **参数溯源** | 可追溯至 API 文档 | ⚠️ 硬门禁标注了 `source: "BRAIN_Official"`，但 prior 维度权重标记为"经验" | 缺少评分维度权重的官方文档引用 | 🟡 一般 |
| **要素覆盖** | 官网生产要素充分应用 | ✅ 66 算子 × 16 dataset 全覆盖，9 类主题骨架 | 低字段数 dataset 未纳入三模式轮换 | 🟢 优化 |
| **代码对齐** | 相关逻辑强制对齐官网规范 | ⚠️ `alpha_checks.py` 中 20+ 检查引用官方标准，但 `scoring.py` 中 soft gate 无官方引用 | 需补充 scoring 公式的文档溯源注释 | 🟡 一般 |

### 2.3 评分体系 Gap

| 能力要求 | 当前状态 | Gap | 严重度 |
|----------|----------|-----|:------:|
| **真实模拟能力** | ✅ 完整 API 模拟链路（认证→提交→轮询→获取→检查→提交），双格式字段名兼容 | `fetch_result()` 错误时静默跳过，无 metrics 重置 | 🟡 一般 |
| **门禁判断能力** | ✅ 6 层门禁（本地预过滤 → prior 60/70 → 官方验证 → 官方模拟 → 回测指标 → 安全政策）| prior 维度权重缺乏文档溯源 | 🟡 一般 |
| **维度丰富性** | ✅ 三层 31 项评分：prior 8 维 + empirical 14 维 + checklist 9 维 | 评分维度覆盖无遗漏 | ✅ 合规 |
| **结构化** | ✅ 每维度有定义/公式/权重；`scoring_params.py` 支持参数化校准；`scorecard` schema versioned（v2.3）| 权重目前多为硬编码默认值 | 🟢 优化 |
| **可解释性** | ⚠️ `decision_band` + `calibration.prior_minus_empirical` 有归因信息，`diagnostics.py` 支持失败分析 | 归因信息未传递至前端 | 🟡 一般 |
| **可校准性** | ✅ `AutoCalibrator`（在线 Grid Search）+ `calibrate_weights.py`（离线校准），需 ≥30 样本触发 | 校准结果注入 `run_config.json` 的手动步骤未自动化 | 🟢 优化 |
| **可演进性** | ✅ `ScoringParams` + `prior_weights_override` + `custom_gates` 支持新增维度和算法升级 | 架构设计支持扩展 | ✅ 合规 |

### 2.4 用户体验 Gap

| 场景 | 目标 | 当前 | Gap | 严重度 |
|------|------|------|-----|:------:|
| **操作引导** | 明确的操作流程引导 | Web 控制台为 State Card 驱动，但缺少 Wizard/Guide 模式 | 🔴 严重 |
| **实时反馈** | 进度条/状态码/日志流 | pipeline 有 `progress_callback` 机制，但前端 SSE 已被移除（语法错误后整块删除） | 🔴 严重 |
| **错误处理** | 可理解、可操作的错误信息 | 后端 8 种类型化错误（`AppError` 等），前端仅显示 text | 🟡 一般 |
| **结果展示** | 直观可视化 | 4 种 Chart.js 图表，但功能受限；detail modal 有结构化展示 | 🟡 一般 |
| **断点续跑** | 支持中断恢复 | lifecycle.jsonl 记录完整，但无显式"从上次中断处继续"入口 | 🟡 一般 |
| **参数保存** | 配置可持久化 | `config/run_config.json` + `presets.json` 7 组预设 | 🟢 优化 |
| **历史回溯** | 可查看历史流水 | `lifecycle.jsonl` + `events.jsonl` + `candidates.jsonl` 持久化 | 🟢 优化 |

---

## 三、Alpha 生产质量攻坚清单

### 3.1 问题总览

**问题总数**: 25 项  
**按严重度分布**: 🔴 阻塞 6 | 🟠 严重 6 | 🟡 一般 8 | 🟢 优化 5

### 3.2 🔴 阻塞级（Blockers — 生产不可用或安全隐患）

| ID | 问题 | 位置 | 影响 | 修复方案 | 验收标准 |
|----|------|------|------|----------|----------|
| **B-01** | 明文真实账号密码 | `test_auth.py:7-8`、`test_api_format.py:6-7`、`test_api_root.py:6-7`、`test_datasets_api.py:6-7`、`docs/CODE_QUALITY_AUDIT_20260514.md:28-29` | 凭据泄露 → 账号接管 | ① 立即轮换密码/Token；② 删除明文；③ 改为环境变量读取；④ 清理 Git 历史 | 所有文件中无硬编码账号密码；Git 历史不包含原始凭据 |
| **B-02** | Token/Cookie 打印到控制台 | `fetch_official_context.py:48-54`、`test_auth.py:20-48`、`test_api_format.py:23-31` | 日志/CI 输出泄露敏感信息 | ① 统一封装 `redact()` 函数；② 默认不打印认证响应体；③ 只输出状态码和脱敏诊断 ID | 控制台输出无 Token/Cookie 明文；脱敏函数覆盖所有认证路径 |
| **B-03** | Web API 无鉴权/CSRF/Origin 校验 | `web.py:199-304` 所有 POST 端点 | `/api/run`、`/api/submit`、`/api/shutdown` 可被恶意本地页面触发 | ① 默认绑定 `127.0.0.1`；② 生成一次性会话 Token；③ 校验 Origin/Host；④ 移除 SSE 的 CORS `*` | 所有状态变更接口要求有效会话 Token；外部页面无法发起请求 |
| **B-04** | 前端脚本语法错误 + SSE 已删除 | `web/index.html:1353-1377`（已删除但未重写） | 控制台交互失效，无实时进度反馈 | ① 修复 SSE 回调中的 `await` 语法错误（加 `async`）；② 重新实现 SSE 管道反馈；③ 加入前端语法检查 | SSE 进度流正常工作；前端所有功能可用 |
| **B-05** | traceback 暴露给前端 | `web.py:410-415, 784-790, 904-919` | 异常含调用栈/请求体，扩大信息泄露面 | ① 服务端保留完整 traceback；② 客户端只返回 error_id + 简短消息；③ 对 `BrainAPIError.payload` 脱敏 | 前端不显示任何 traceback；错误码对应可查询的内部日志 |
| **B-06** | 大型敏感数据无 .gitignore | 根目录缺少 `.gitignore` | `events.jsonl`（348MB）、`cloud_alphas.jsonl`（42MB）、`api_cache/` 等易误提交 | ① 创建 `.gitignore`；② 排除 `data/*.jsonl`、`data/api_cache/`、`*.log`、构建产物；③ 提供脱敏样例 | `.gitignore` 涵盖所有敏感/大数据文件；`git status` 干净 |

### 3.3 🟠 严重级（Major — 影响生产质量或稳定性）

| ID | 问题 | 位置 | 影响 | 修复方案 | 验收标准 |
|----|------|------|------|----------|----------|
| **M-01** | 产能阻塞：通过率 2.1% | 全 pipeline | 52% Sharpe 为负、Max Sharpe 仅 1.38、均值 -0.092 | ① 新增 20+ 主题模板骨架；② 将低字段 dataset 纳入轮换；③ 增加 `option9`/`socialmedia12` 等低频数据集探索权重 | Round 5 实验通过率 ≥ 10%；Max Sharpe ≥ 2.0；均值 Sharpe ≥ 0.5 |
| **M-02** | 静默吞异常 | `web.py:1318-1319,1339-1342`、`pipeline.py:1721-1722,1786-1787`、`official.py:349-350` | 提交记录丢失、安全检查降级无感知 | ① 至少记录 `logging.warning`；② 提交/安全路径把 fail 转为阻断或显式降级状态；③ 添加失败计数指标 | 所有 `pass` 替换为 logging + 降级处理 |
| **M-03** | CLI 暴露密码参数 | `cli.py:29-31, 74-79` | `--password`/`--token` 进入 shell 历史/进程列表 | ① 标记为仅限临时调试；② 添加 `--password-prompt` 隐藏输入；③ 文档警示 | CLI `--help` 有安全警告；默认交互式输入 |
| **M-04** | 配置加载无类型/范围校验 | `config.py:252-257, 274-285` | 错误的配置值在运行时才失败 | ① 添加类型/枚举/范围校验层；② 数值统一做 min/max；③ 枚举限制已知值 | 配置文件修改后启动时即报校验错误 |
| **M-05** | Web payload 数值无上限 | `web.py:1408-1445` | 候选数/仿真数无上限可致资源耗尽 | ① 为所有参数定义服务端上限；② 拒绝 NaN/Infinity/负数；③ 返回结构化校验错误 | 超大 payload 返回 422 + 明确错误消息 |
| **M-06** | 官方 API 分页无硬上限 | `official.py:174-192, 212-230, 252-269` | 上游异常时无限循环写缓存 | ① 加入 `max_pages`/`max_items`；② 记录上一页 ID 哈希检测重复；③ 显示截断原因 | 分页循环有保护上限；重复页自动断出 |

### 3.4 🟡 一般级（Minor — 体验或工程债务）

| ID | 问题 | 修复方案 |
|----|------|----------|
| **L-01** | `pipeline.py` 超 2500 行，职责不清 | 拆分为 service/router/repository/serializer；每个阶段独立状态机 |
| **L-02** | 包版本号不一致（`pyproject.toml` v0.1.0 vs `__init__.py` v0.3.0） | 统一为 `importlib.metadata.version()` 单一来源 |
| **L-03** | 前端缺少 a11y 语义 | 补充 ARIA 属性、焦点管理、`aria-live` |
| **L-04** | M-01 XSS 风险（innerHTML 拼接未转义字段） | `escapeHtml()` 对所有动态内容 |
| **L-05** | 构建产物/缓存混在工作区 | 添加 `.gitignore` + 清理 pyc/cache |
| **L-06** | 缺少 CI/CD | 添加 GitHub Actions：`compileall` + `pytest` + 前端语法检查 + `ruff`/`mypy` |
| **L-07** | 依赖声明不完整 | 补齐 `dependencies` + `[optional-dependencies].test` + lockfile |
| **L-08** | M-07 分页上限（与 M-06 关联） | 同上 M-06 |

### 3.5 🟢 优化级（Enhancement）

| ID | 问题 | 建议 |
|----|------|------|
| **E-01** | 评分权重标记为"经验" | 对照 BRAIN 文档，为 prior 8 个维度补充学术引用或平台最佳实践引用 |
| **E-02** | 前端操作引导缺失 | 添加首次使用 Wizard / 关键步骤 Tooltip / 快速入门面板 |
| **E-03** | 低字段数 dataset 未轮换 | 将 `option9`/`option8`/`socialmedia12` 等纳入 `dataset_strategy: rotate` |
| **E-04** | 收敛策略切换过于保守 | 将 stall 判定从 5 轮降低到 3 轮，增加 adaptive 模式 |
| **E-05** | 断点续跑入口缺失 | 在 Web 端添加"从上次中断处继续"入口，读取 `lifecycle.jsonl` 最后状态 |

---

## 四、技术合规红线逐项验证

### 4.1 红线 1: 字段与算子 → ✅ 通过（有观察）

| 检查项 | 结果 | 证据 |
|--------|:----:|------|
| 字段 100% 来自 BRAIN API | ✅ | 7,642 字段全部来自 `data/official_fields.json`（4.88 MB），通过 `/data-fields` API 分页拉取 |
| 算子 100% 来自 BRAIN API | ✅ | 66 算子全部来自 `data/official_operators.json`（24 KB），通过 `/operators` API 拉取 |
| 无自定义扩展字段 | ✅ | `OfficialDataLoader.get_fields()` 为唯一字段源，无硬编码字段列表在生成器内 |
| 无自定义扩展算子 | ✅ | 历史 3 个虚构算子（`ts_weighted_mean`、`group_decay`、`cross_sectional_decay`）已删除 |
| `context_defaults.py` fallback | ⚠️ | 30 个 fallback 字段 + 8 个 fallback 算子均为真实字段/算子，但仅在 JSON 缺失时启用 |
| **观察项** | | 建议在加载时与 `official_*.json` 交叉验证，防止官方 API 变更后 fallback 过时 |

### 4.2 红线 2: 阈值配置 → ✅ 通过（零偏差）

| 阈值参数 | 配置值 | BRAIN 官方标准 | 偏差 |
|----------|:------:|----------------|:----:|
| `min_sharpe` (Delay-1) | 1.25 | LOW_SHARPE ≥ 1.25 | **0** |
| `min_sharpe` (Delay-0) | 2.0 | LOW_SHARPE ≥ 2.0 | **0** |
| `min_fitness` (Delay-1) | 1.0 | LOW_FITNESS ≥ 1.0 | **0** |
| `min_fitness` (Delay-0) | 1.3 | LOW_FITNESS ≥ 1.3 | **0** |
| `platform_max_turnover` | 0.70 | HIGH_TURNOVER > 70% | **0** |
| `target_max_turnover` | 0.30 | 顾问质量目标 < 30% | **0** |
| `min_turnover` | 0.01 | LOW_TURNOVER < 1% | **0** |
| `max_self_correlation` | 0.70 | SELF_CORRELATION ≥ 0.70 | **0** |
| `max_weight_concentration` | 0.10 | CONCENTRATED_WEIGHT > 10% | **0** |
| `sub_universe_sharpe_min_ratio` | 0.75 | LOW_SUB_UNIVERSE_SHARPE | **0** |

**例外规则验证**: ✅ SELF_CORRELATION 的 Sharpe 优势例外（new_alpha.Sharpe ≥ related_alpha.Sharpe × 1.10 → PASS）已正确实施。

### 4.3 红线 3: Dataset ID → ⚠️ 部分合规

| 检查项 | 状态 | 说明 |
|--------|:----:|------|
| 主流 Dataset ID 可用性 | ✅ | 16 个 dataset 完整可用（model77 / fundamental2 / analyst4 / news12 / pv1 / model16 / fundamental6 / model51 / option9 / news18 / option13 / socialmedia12 / fundamental1 / model5 / option8 / news6） |
| 字段-数据集双向映射 | ✅ | `FieldDatasetMapper` 构建 `dataset_to_fields` / `field_to_datasets` 双向索引 |
| 低字段数 dataset 轮换 | ⚠️ | `option9`(74)、`option8`(?), `socialmedia12`(?) 等低字段 dataset 未纳入循环 |
| 生成阶段字段验证 | ✅ | `validated_generator.py` 接入后拒绝率 0%（Round 4） |

### 4.4 红线 4: 参数溯源 → ⚠️ 部分合规

| 溯源项 | 状态 |
|--------|:----:|
| QualityThresholds → BRAIN Alpha Check 标准 | ✅ 全部标注 |
| scoring.py 硬门禁 → `source: "BRAIN_Official"` | ✅ |
| prior_score 8 个维度权重 → | ⚠️ 标记为"经验"，无文档引用 |
| empirical_score 14 项权重 → | ⚠️ 标记为"校准默认值" |
| 表达式语法 / compiler limit → | ✅ FastExpr 官方规范 |

### 4.5 红线 5: 要素覆盖 → ✅ 通过

| 覆盖项 | 状态 |
|--------|:----:|
| 66 个算子覆盖 | ✅ `generator.py` / `theme_engine.py` 全面引用 |
| 16+9 个数据集覆盖 | ⚠️ 主流 16 个覆盖，9 个低字段数未轮换 |
| 9 大主题骨架（momentum/reversal/value/quality/volatility/liquidity/growth/size/hybrid） | ✅ `theme_engine.py` 52+ 模板 |
| 8 个 YAML 市场假设 | ✅ 覆盖 value_reversal / earnings_revision / analyst_behavior / liquidity_premium / low_volatility / microstructure / quality_profitability / sentiment_short |
| 7 个 market preset | ✅ USA(4) / EUR(1) / GLB(1) / CHN(1) |
| 3 种 neutralization（SUBINDUSTRY / SECTOR / MARKET） | ✅ 全量覆盖 |
| 3 种 universe（TOP1000 / TOP3000 / TOP3000） | ✅ 全量覆盖 |

### 4.6 红线 6: 代码对齐 → ⚠️ 部分合规

| 检查项 | 状态 |
|--------|:----:|
| BRAIN Alpha Check 逻辑与官方文档对齐 | ✅ `alpha_checks.py` 20+ 检查逐项引用官方标准 |
| FastExpr 语法规范对齐 | ✅ `generator.py` 表达式构建遵循官方语法 |
| API 端点路径对齐 | ✅ `official.py` 路径与官方 REST API 文档一致 |
| 评分公式 vs 官方文档 | ⚠️ scoring 中的 soft gate 无官方引用注释 |

---

## 五、评分系统评价

### 5.1 架构总览

```
┌──────────────────────────────────────────────────────┐
│              Alpha 评分体系 (scoring.py v2.3)          │
├──────────────────────────────────────────────────────┤
│                                                      │
│  total_score = 0.30 × prior + 0.45 × empirical       │
│              + 0.25 × checklist                      │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ Layer 1: prior_score (8 维度)                │     │
│  │  • economic_logic     (0.20)                 │     │
│  │  • structure          (0.15)                 │     │
│  │  • field_operator_support (0.15)             │     │
│  │  • data_compliance    (0.10)                 │     │
│  │  • horizon_turnover   (0.10)                 │     │
│  │  • risk_control_proxy (0.10)                 │     │
│  │  • diversity          (0.10)                 │     │
│  │  • explainability     (0.10)                 │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ Layer 2: empirical_score (14 项)             │     │
│  │  [硬] Sharpe / Fitness / Turnover(low/high)  │     │
│  │  [硬] SelfCorr / ProdCorr / Concentration    │     │
│  │  [硬] SubUniverseSharpe                      │     │
│  │  [软] Returns / Drawdown / Margin / IR       │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ Layer 3: submission_checklist (9 项)         │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  门禁层级 (6 层):                                    │
│  L0: 本地预过滤 → L1: prior ≥ 60/70 →               │
│  L2: 官方验证 → L3: 官方模拟 →                       │
│  L4: 回测指标门禁 → L5: 安全门禁                     │
│                                                      │
│  校准能力:                                           │
│  • AutoCalibrator (Grid Search, ≥30 样本)            │
│  • calibrate_weights.py (离线 Pearson + 归一化)      │
│  • Bootstrap CI (90% 置信区间)                        │
│  • Spearman 秩相关趋势检验                           │
└──────────────────────────────────────────────────────┘
```

### 5.2 逐能力评估

| 能力 | 评分 | 评价 |
|------|:----:|------|
| **真实模拟能力** | **4.3/5** | 完整 API 模拟链路，双格式兼容；`fetch_result()` 错误时静默是唯一缺陷 |
| **门禁判断能力** | **4.3/5** | 6 层门禁体系清晰，Pass/Fail 自动判断，标准可追溯至 `run_config.json` |
| **维度丰富性** | **4.5/5** | 三层 31 项覆盖收益/风险/稳定性/换手率/相关性/集中度等多维度 |
| **结构化程度** | **4.0/5** | 每维度有明确定义和计算公式，scorecard 有 schema version；权重配置可覆盖 |
| **可解释性** | **3.5/5** | 有 `diagnostics.py` + `decision_band` + prior-empirical diff；但归因信息未到达前端 |
| **可校准性** | **4.0/5** | AutoCalibrator 在线 + calibrate_weights 离线；需手动注入配置 |
| **可演进性** | **4.0/5** | `ScoringParams` + `custom_gates` 架构支持扩展；新维度添加成本低 |

**评分体系综合评分**: **4.1 / 5.0**

---

## 六、用户体验优化方案

### 6.1 现状诊断

| 维度 | 状态 | 严重度 |
|------|------|:------:|
| 操作引导 | Web 控制台为上手指南缺失的 State Card 交互模式，无 Wizard/Guide/Onboarding | 🔴 |
| 实时反馈 | 前端 SSE 管道已被整体移除（旧代码语法错误被删除），当前无实时进度推送 | 🔴 |
| 错误展示 | 后端 8 种 `AppError` 子类，前端仅显示 text，无错误码/建议操作 | 🟡 |
| 结果展示 | 4 种图表（score trend / Sharpe dist / gate pie / turnover），detail modal 有结构化字段表 | 🟡 |
| 断点续跑 | lifecycle.jsonl 完整记录但无用户界面入口 | 🟡 |
| 参数保存 | `run_config.json` + 7 组 presets 可用 | 🟢 |
| 历史回溯 | `lifecycle.jsonl` + `events.jsonl` + `candidates.jsonl` 有数据但无可视化历史回放 | 🟡 |

### 6.2 优化方案（分阶段）

**Phase 1: 紧急修复（阻塞项，1-2天）**

| # | 任务 | 涉及文件 | 优先级 |
|---|------|----------|:------:|
| 1 | **恢复 SSE 管道**：修复 `index.html` 中 `source.onmessage = async (event) => {...}`；重新实现 progress 事件 | `web/index.html`、`web/index_template.html` | P0 |
| 2 | **前端进度可视化**：通过 SSE 推送 cycle 进度（生成N/验证N/回测N/评分N），更新 progress bar | `web/js/views/monitor.js`、`web/js/components/progress.js` | P0 |
| 3 | **错误信息结构化**：前端展示 `AppError.type` + `error_id` + `suggestion`（后端 web.py 需同时修改不输出 traceback） | `web.py`、`web/js/views/monitor.js` | P0 |

**Phase 2: 体验增强（2-3天）**

| # | 任务 | 涉及文件 |
|---|------|----------|
| 4 | **首次使用引导**：在 Web 控制台添加 Onboarding 面板（3 步：配置→启动→查看结果） | `web/index.html` 新增 onboarding view |
| 5 | **操作状态可视化**：将 State Card 升级为流程式步骤条（Stepper），显示当前所处阶段 | `web/js/views/monitor.js` |
| 6 | **结果展示增强**：scorecard 详情面板（prior/empirical/checklist 雷达图 + 归因分析）+ `diagnostics.py` 输出可视化 | `web/js/views/detail.js`、`web/js/views/charts.js` |
| 7 | **断点续跑入口**：Web 端添加"从上次中断处继续"按钮，读取 `lifecycle.jsonl` | `web/js/views/monitor.js`、`web.py` 新增 `/api/resume` |

**Phase 3: 持续优化（持续）**

| # | 任务 |
|---|------|
| 8 | 历史回放功能（时间线视图，按 cycle 浏览 score/check/submission） |
| 9 | 添加 a11y 支持（ARIA 属性、焦点管理、键盘导航） |
| 10 | 集成 `run_config.json` 的 Web 编辑器（表单式配置，非 JSON 编辑） |
| 11 | 实验日志仪表盘（从 `experiments/` 目录聚合展示） |

---

## 七、总结与建议优先级

### 7.1 执行优先级矩阵

```
                    高影响
                      │
          B-01 B-02   │   B-03 B-04 B-05
          B-06 M-01   │   B-04 M-02
          (立即修复)   │   (本周内)
                      │
  ────────────────────┼────────────────────
                      │
          L-01~L-08   │   E-01~E-05
          (本月内)     │   (下迭代)
                      │
                    低影响
```

### 7.2 建议执行顺序

| 优先级 | 批次 | 任务 | 预计工时 |
|:------:|------|------|:------:|
| **P0** | 安全修复 | B-01 凭据清理 + B-02 输出脱敏 + B-06 .gitignore | 2h |
| **P0** | 安全修复 | B-03 Web 鉴权 + B-05 traceback 脱敏 | 4h |
| **P1** | 核心能力恢复 | B-04 SSE 管道恢复 + 实时进度 | 6h |
| **P1** | 质量攻坚 | M-01 产能提升（新增模板 + dataset 扩展）| 8h |
| **P1** | 稳定性 | M-02 吞异常修复 + M-03 CLI 密码 + M-04 配置校验 | 4h |
| **P2** | 工程债务 | L-01~L-08 逐一修复 | 16h |
| **P3** | 体验优化 | Phase 2 + Phase 3 UX 任务 | 24h |

---

## 附录 A: 文件统计

| 类别 | 数量 | 说明 |
|------|:----:|------|
| Python 源文件 | 39 | brain_alpha_ops/ 下全部 .py |
| JavaScript 模块 | 12 | web/js/ 下模块化前端 |
| HTML 模板 | 2 | index.html + index_template.html |
| YAML 假设 | 8 | 7 个假设 + 1 个 schema |
| JSON 配置 | 5 | run_config + presets + 3 个 official_*.json |
| 测试文件 | 17 | tests/ 目录 |
| 文档 | 44 | docs/ 目录 markdown/mermaid |
| 实验脚本 | 23 | experiments/ 目录 |

## 附录 B: 关键配置文件

| 文件 | 大小 | 用途 |
|------|------|------|
| `data/official_fields.json` | 4.88 MB | 7,642 个 BRAIN 字段 |
| `data/official_operators.json` | 24 KB | 66 个 BRAIN 算子 |
| `data/official_datasets.json` | 1.5 KB | 16 个 BRAIN 数据集 |
| `config/run_config.json` | ~3 KB | 全系统运行参数 |
| `config/presets.json` | ~3 KB | 7 组市场预设 |
| `web/index.html` | 109 KB | 单页前端应用 |

## 附录 C: 历史文档引用

本报告继承并更新了以下历史评估文档的结论：

- `REVIEW.md` (2026-05-14) — 安全审查，21 项问题（🔴5 🟡11 🟢5）
- `COMPREHENSIVE_DIAGNOSIS_20260516.md` — 综合诊断，综合评分 3.9/5.0
- `TECH_COMPLIANCE_VERIFICATION_20260516.md` — 技术合规红线验证，全部通过
- `SCORING_SYSTEM_EVALUATION_20260516.md` — 评分体系评估，综合 4.1/5.0
- `UX_OPTIMIZATION_PLAN_20260516.md` — 用户体验优化方案
