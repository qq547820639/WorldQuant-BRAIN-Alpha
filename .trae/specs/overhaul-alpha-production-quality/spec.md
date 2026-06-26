# Alpha 生产系统全栈质量攻坚 - 规格

## Why

本项目（BRAIN Alpha Ops）是基于 WorldQuant BRAIN 平台的 Alpha 因子生产系统。仓库历史审计存在两套相互矛盾的结论：内部审计（`CODE_DIAGNOSTIC_REPORT_20260618`、`BRAINALPHA_AUDIT_V3_20260619`、`PHASE33_DELIVERY_REPORT_20260619`）评定综合分 8.5/10 并认为 P0 已清；而外部顾问报告（`BRAINALPHA_FULLSTACK_AUDIT_20260622`）判定项目"不合格"，核心阻断是"真实浏览器驱动的 BRAIN Web 主路径未打通"，执行后端仍是 API-first（`urllib+CookieJar`）而非 browser-first，监控只覆盖后端任务，测试过度拟合内部桩。`DELIVERY_REPORT_20260622` 确认 9/11 项已交付但延期：大模块拆分、收敛迭代算法、完整 CI/CD 流水线。

本次攻坚的目标是**以 DeepWiki/WQB（`https://deepwiki.com/rocky-d/wqb`）只读审查报告为标准，对齐 WorldQuant 官网最新规则，补齐真实缺口，使系统具备产出可提交合格 Alpha 的端到端能力**。经代码级核查，用户原始 25 个任务模块中部分目标已实质性达成（ConfigPanel 凭据折叠、三槽调度器、反过拟合服务、凭据治理、检查点恢复、StallMonitor），本规格聚焦于**真正未达成或仅部分达成的缺口**，避免重复劳动与过度工程。

核心硬约束（不可违反）：
1. **严格禁止使用测试脚本/历史提交结果/官方回测反馈进行过拟合式搜索**。
2. **必须真实模拟用户通过 Web 界面的实际操作流程**来生成与验证 Alpha（browser-driven 主路径）。
3. **实时状态监控**：检测到卡顿、挂起、状态不明确时必须立即自动中断并修正。
4. **凭据安全**：用户提供测试凭据（`<redacted-test-email>` / `<redacted-test-password>`，由用户本地持有，不在本规格中落字）仅供其本地运行验证使用，**严禁写入代码、测试、日志、截图、报告或提交到仓库**；凭据必须通过环境变量（`BRAIN_USERNAME`/`BRAIN_PASSWORD`/`BRAIN_TOKEN`）或本地安全存储注入。
5. 所有 Python 后端文件 ≤ 350 行，所有前端源文件 ≤ 400 行（项目记忆硬约束，当前已满足，仅维护）。

## What Changes

按实际缺口分为 6 个工作流，对应原始 25 个模块的真实状态：

### 工作流 A：BRAIN 能力集注册表中心化（对应模块 3、14、16）
- **新增** `brain_alpha_ops/data/capability_registry/` 子包，作为官方字段/算子/Dataset ID/Region/Universe/Delay/Decay/Neutralization/Truncation/Pasteurization/NaNHandling/UnitHandling/TestPeriod/Visualization 的**唯一权威来源**。
- 收编当前散落在 7+ 处的能力元数据：`data/field_dataset_mapper.py`、`data/official_context_validation.py`、`research/dataset_selector.py`、`config_models.py:BrainSettings` 默认值、`presets.py`、`runtime_constants.py`、`research/local_backtest/engine.py:supported_operators`、`config_domain_validation.py:_VALID_*` 枚举。
- 注册表条目包含：来源、更新时间、适用范围、默认值、允许值、禁止值、校验规则、错误提示。能力缺失时进入"需要人工确认"状态，禁止擅自扩展。
- 表达式解析器（`research/expression_ast/_parser.py`）、本地回测引擎（`research/local_backtest/engine.py`）、生成器（`research/generation/`）、评分、门禁、模拟提交、结果展示**统一从注册表读取**，消除散落硬编码。
- **BREAKING**（内部）：`LocalBacktestEngine.supported_operators` 硬编码集合改为从注册表派生；`presets.py` 硬编码预设改为引用注册表默认值。

### 工作流 B：候选池状态机统一与生命周期审计（对应模块 12、15、19）
- **将 `candidate_lifecycle.py:LifecycleState` 枚举（9 态、合法迁移图、`TransitionRecord` 审计）接入 pipeline**，替换当前 pipeline 直接 mutate 的 15+ 字符串 `candidate.lifecycle_status`。
- 候选 Alpha 生命周期状态对齐规格要求：`draft`、`locally_scored`、`gate_rejected`、`queued_for_simulation`、`simulating`、`simulation_failed`、`simulation_passed`、`needs_optimization`、`ready_for_review`、`submitted`、`archived`。
- `AuditTrailWriter`（当前仅覆盖评分）扩展至覆盖**生命周期迁移、门禁判定、优化建议、模拟回写**，每条记录含：输入参数、能力集版本、评分版本、门禁版本、模拟配置、结果摘要、变更记录。
- 反过拟合审计日志补全：每个 Alpha 的来源、变体生成原因、使用过的反馈信号、被淘汰原因、优化次数、是否触达官方模拟。高度相似表达式、参数微调刷分、重复提交、异常高频失败重试由质量门禁自动拦截并归档。
- 历史回溯：按状态、日期、Dataset、Region、Universe、评分、门禁失败原因、模拟结果、表达式相似度过滤。

### 工作流 C：官方模拟三槽调度器硬化与候选池解耦（对应模块 11、12）
- `ThreeSlotScheduler`（已存在，`research/simulation_scheduler/_scheduler.py`）已支持 3 槽并发、每槽独立状态机、并发超限/429/5xx 的槽级冷却。本工作流**不重建**，仅硬化：
  - 校验 `BacktestSlotManager`（参数化 `active_limit`）与 `ThreeSlotScheduler`（`max_slots=3`）一致性，消除双调度器漂移风险；web 层 `backtest_slot_limit()` 统一从调度器读取。
  - 任务取消、超时中断、状态不明自愈、失败重试、冷却恢复、审计日志的端到端验证（含 `CONCURRENT_SIMULATION_LIMIT_EXCEEDED`、429、网络异常仅暂停对应槽或触发账号级冷却，不锁死生产链路）。
  - 候选池生产与官方回测解耦：生产器持续维护候选池容量；本地科学评分和质量门禁先快速淘汰/排序/优化；官方模拟作为稀缺验证资源只消费 TopK；官方结果回写触发状态更新/评分校准/优化方向调整，**不阻塞候选池继续生产**。

### 工作流 D：科学评分与质量门禁服务化（对应模块 4、10、15）
- 科学评分（`research/scoring/`、`scoring/`）从看板升级为**生产内嵌自动服务**，参与候选排序、淘汰、优化方向选择、官方模拟优先级决策。
- 质量门禁（`research/submission_gate_service.py`、`scoring/gates.py`、`scoring/release_score_gate.py`、`scoring/anti_overfit/`）参与状态流转，自动决定"继续优化 / 丢弃归档 / 候选进入官方模拟队列 / 进入人工确认"。
- 页面只作为解释器，展示"为什么这样排序、为什么被拦截、下一步动作"。
- 评分归因架构（`scoring/attribution.py`）支持多维分析；所有评分结果、门禁判断、归因理由、触发规则、状态变更可追溯、可回放、可导出。
- 评价标准维度丰富、结构化、可解释、可校准；阈值与 BRAIN 官网标准零偏差（`scoring/gates.py:OFFICIAL_HARD_GATE_NAMES` 已对齐 sharpe/fitness/turnover_min/turnover_platform/self_correlation/prod_correlation/weight_concentration/sub_universe_sharpe）。

### 工作流 E：实时监控、状态一致性与错误体验（对应模块 13、18、9）
- `StallMonitor` + `UnifiedMonitor`（已存在）扩展覆盖：Web 界面、官方模拟队列、候选池生产、评分服务、质量门禁、网络请求、登录会话、缓存状态、测试执行。
- 卡顿、挂起、重复轮询、状态不明确、前后端状态不一致、按钮不可点击、页面空白、接口超时、模拟结果长期未回写必须被自动检测；检测后立即中断、保留上下文快照、输出错误归因、执行修正、重新进入可控状态。
- 统一状态机：Dashboard、ConfigPanel、候选池、评分看板、质量门禁、官方模拟队列、历史记录、系统配置共享一致的状态定义（前端 `useAppState` composition root 已存在，补齐 Context Provider 消除 prop drilling 的状态漂移）。
- 错误体验：所有接口错误转换为用户可理解/可操作/可恢复提示（登录失效、缓存不可用、官方限流、模拟并发超限、Dataset 缺失、字段不合规、表达式非法、网络超时、任务取消、队列阻塞、本地服务未启动），每类错误给出原因、影响范围、建议动作、可点击恢复入口。
- **ConfigPanel 缓存凭据入口（模块 9）**：经核查当前代码（`ConfigPanel.tsx:76-80`、`CredentialsSection.tsx:94-107`、`LocalCacheConnectionSection.tsx:22-83`）**已正确实现**折叠逻辑。本工作流仅补齐回归测试，防止退化。

### 工作流 F：测试体系、CI 门禁、文档与交付（对应模块 6、20、21、22、23、24、25）
- 测试补齐：空值、极值、非法表达式、未知字段、Dataset ID 缺失、官方限流、并发超限、网络异常、会话过期、缓存损坏、任务中断、重复提交、状态恢复、移动端交互（当前缓存损坏、移动端交互为缺口）。
- 前端测试：当前仅 2 个 vitest 文件，补齐关键链路行为测试（不再仅靠 `test_react_*.py` 静态文本检查）。
- CI 门禁（`.github/workflows/quality-gate.yml`）补齐：`tsc -b`、`eslint`、`prettier --check`、`vitest run`、E2E 冒烟、`scripts/check_capability_registry.py`、`scripts/check_brain_contract.py` 接入；`build-release.yml` 加入构建产物冒烟；`scripts/check_module_size.py:BASELINE_LINE_LIMITS` 同步当前实际行数（当前引用已失效的 `pipeline.py:3210` 等）。
- 文档：README 补齐 ConfigPanel 缓存模式、前端测试、CI 门禁清单、`.trae/specs/` 索引；新增开发者手册（架构、模块边界、凭据配置、BRAIN 能力集更新流程、三槽调度器、候选池状态机、故障排查）。
- 缺陷跟踪清单：统一追踪缺陷编号、模块、严重级别、复现步骤、影响范围、根因、修复方案、受影响文件、验证方式、状态、关闭条件。
- 全局影响评估：每次变更前明确目标、预期效果、受影响模块/函数/状态/接口/配置/测试/文档；变更后输出结构化变更报告（影响范围、修改逻辑、潜在风险、回滚方式、验证结果）。
- 最终交付报告：区分"已完成/部分完成/未完成/阻塞/风险/建议下一步"六类状态。

### 跨工作流：子智能体编排（对应模块 8）
- 用户提及的 `/superpowers` 与 `/agent-team-orchestration` 在本环境不可用。改用 Spec 模式内置的 Sub-Agent 机制（`Task` 工具，`general_purpose_task` 类型）并行推进无依赖工作流，主线程负责汇总冲突、统一决策、全局影响评估、最终合并。每类子任务明确输入、输出、边界、检查清单、验收标准。

### 不做（已达成或超出范围）
- **不重建**已存在的 3 槽调度器、反过拟合服务、凭据治理、检查点恢复、StallMonitor、ConfigPanel 折叠逻辑。
- **不改变**核心算法逻辑（Alpha 生成、评分、回测）的数学本质，仅做合规对齐与硬化。
- **不引入**大型新依赖（保持 React 18 + TS + Tailwind + Vite + Python 3.11 stdlib HTTP）。
- **不提交**用户提供的测试凭据到任何文件、日志、截图、报告。
- **不使用**测试脚本进行过拟合式搜索（硬约束）。

## Impact

- **受影响的规格**：
  - `complete-brain-alpha-ops`（ConfigPanel 缓存模式 — 已实现，补回归测试）
  - `upgrade-to-public-product`（错误/空/加载态、可访问性 — 部分达成，补缺口页）
  - `deep-optimization-phase11`（子包 `__all__` — 新增 `capability_registry/` 子包需遵循）
- **受影响的代码**：
  - 新增 `brain_alpha_ops/data/capability_registry/` 子包（工作流 A）
  - `research/candidate_pool.py`、`research/backtest_submission.py`、`research/backtest_polling.py`、`research/submission_gate_service.py`（工作流 B/C — 接入 `LifecycleState` 枚举替换字符串状态）
  - `candidate_lifecycle.py`（工作流 B — 接入 pipeline）
  - `audit_trail/writer.py`（工作流 B — 扩展覆盖范围）
  - `research/local_backtest/engine.py:supported_operators`、`presets.py`、`config_models.py:BrainSettings`（工作流 A — 改为从注册表派生）
  - `research/simulation_scheduler/_scheduler.py`、`research/backtest_slots.py`、`web/misc/web_backtest_slots.py`（工作流 C — 一致性硬化）
  - `research/scoring/`、`scoring/`、`research/submission_gate_service.py`（工作流 D — 服务化）
  - `stall_monitor.py`、`monitoring/unified_monitor.py`（工作流 E — 扩展覆盖）
  - `brain_alpha_ops/web/react_app/src/hooks/useAppState/`（工作流 E — 补 Context Provider）
  - `.github/workflows/quality-gate.yml`、`.github/workflows/build-release.yml`、`scripts/check_module_size.py`（工作流 F）
  - `tests/`（工作流 F — 补缺口场景）
  - `brain_alpha_ops/web/react_app/src/__tests__/`（工作流 F — 补前端行为测试）
  - `README.md` + 新增开发者手册（工作流 F）
- **受影响的测试**：新增覆盖能力集注册表、生命周期状态机、调度器硬化、评分服务化、监控扩展、缓存损坏、移动端交互的测试。
- **凭据安全**：用户提供的测试凭据不进入仓库；`secure_credentials.py` 现有 env-var-only 机制保持不变。

## ADDED Requirements

### Requirement: BRAIN 能力集注册表为唯一权威来源
系统 SHALL 提供位于 `brain_alpha_ops/data/capability_registry/` 的中心化能力集注册表，覆盖官方字段、算子、Dataset ID、Region、Universe、Delay、Decay、Neutralization、Truncation、Pasteurization、NaNHandling、UnitHandling、TestPeriod、Visualization。每个条目 SHALL 包含来源、更新时间、适用范围、默认值、允许值、禁止值、校验规则、错误提示。所有 Alpha 生成、解析、评分、门禁、模拟提交与结果展示 SHALL 从该注册表读取，严禁在业务代码中散落硬编码。

#### Scenario: 能力集注册表覆盖所有生产要素
- **WHEN** 审查 `brain_alpha_ops/data/capability_registry/`
- **THEN** 注册表覆盖字段、算子、Dataset ID、Region、Universe、Delay、Decay、Neutralization、Truncation、Pasteurization、NaNHandling、UnitHandling、TestPeriod、Visualization
- **AND** 每个条目含来源、更新时间、适用范围、默认值、允许值、禁止值、校验规则、错误提示

#### Scenario: 业务代码无散落硬编码
- **WHEN** grep `research/local_backtest/engine.py` 的 `supported_operators`
- **THEN** 该集合从注册表派生，不再硬编码
- **WHEN** grep `presets.py` 的预设
- **THEN** 预设引用注册表默认值，不再硬编码

#### Scenario: 能力缺失进入人工确认
- **WHEN** 注册表中某能力缺失或规则不明确
- **THEN** 系统进入"需要人工确认"状态，禁止擅自扩展或猜测

### Requirement: 候选 Alpha 生命周期状态机接入 pipeline
系统 SHALL 使用 `LifecycleState` 枚举（含 `draft`、`locally_scored`、`gate_rejected`、`queued_for_simulation`、`simulating`、`simulation_failed`、`simulation_passed`、`needs_optimization`、`ready_for_review`、`submitted`、`archived`）及其合法迁移图管理候选 Alpha 状态。Pipeline SHALL 通过 `CandidateLifecycle.transition()` 迁移状态，严禁直接 mutate 字符串 `lifecycle_status`。每次迁移 SHALL 生成 `TransitionRecord` 审计记录。

#### Scenario: pipeline 通过状态机迁移
- **WHEN** pipeline 将候选从 `locally_scored` 推进到 `queued_for_simulation`
- **THEN** 调用 `CandidateLifecycle.transition()`，生成 `TransitionRecord`
- **AND** 不再直接赋值 `candidate.lifecycle_status = "..."`

#### Scenario: 非法迁移被拒绝
- **WHEN** 尝试从 `archived` 迁移到 `simulating`
- **THEN** 状态机抛出非法迁移错误，候选保持 `archived`

### Requirement: 审计轨迹覆盖全生命周期
系统 SHALL 通过 `AuditTrailWriter` 记录候选 Alpha 从生成、评分、门禁、入队、官方模拟、失败恢复、优化迭代到最终归档或提交的完整轨迹。每条记录 SHALL 含输入参数、能力集版本、评分版本、门禁版本、模拟配置、结果摘要、变更记录，确保未来可复现同一轮判断。

#### Scenario: 生命周期迁移可追溯
- **WHEN** 查看某 Alpha 的审计轨迹
- **THEN** 可见从 `draft` 到 `submitted`/`archived` 的完整迁移链，含每次迁移的原因与触发规则

### Requirement: 科学评分与质量门禁参与生产决策
系统 SHALL 将科学评分与质量门禁作为生产内嵌自动服务，参与候选排序、淘汰、优化方向选择、官方模拟优先级决策与状态流转。质量门禁 SHALL 自动决定"继续优化 / 丢弃归档 / 候选进入官方模拟队列 / 进入人工确认"。页面只作为解释器，展示排序理由、拦截原因、下一步动作。所有评分结果、门禁判断、归因理由、触发规则、状态变更 SHALL 可追溯、可回放、可导出。

#### Scenario: 门禁自动决定状态流转
- **WHEN** 候选通过本地评分但未通过质量门禁
- **THEN** 系统自动将其状态迁移到 `needs_optimization` 或 `gate_rejected`，并记录归因理由

### Requirement: 实时监控自动中断异常流程
系统 SHALL 监控 Web 界面、后端任务、官方模拟队列、候选池生产、评分服务、质量门禁、网络请求、登录会话、缓存状态、测试执行。检测到卡顿、挂起、重复轮询、状态不明确、前后端状态不一致、按钮不可点击、页面空白、接口超时、模拟结果长期未回写时，SHALL 立即中断当前异常流程，保留上下文快照，输出错误归因，执行修正，重新进入可控状态。

#### Scenario: 模拟结果长期未回写被检测
- **WHEN** 某官方模拟槽超过阈值时间未回写结果
- **THEN** 监控自动中断该槽，保留快照，输出归因，触发槽级冷却或重试

### Requirement: 错误转换为可操作提示
系统 SHALL 将所有接口错误转换为用户可理解、可操作、可恢复的提示。每类错误（登录失效、缓存不可用、官方限流、模拟并发超限、Dataset 缺失、字段不合规、表达式非法、网络超时、任务取消、队列阻塞、本地服务未启动）SHALL 给出原因、影响范围、建议动作、可点击恢复入口。严禁只展示堆栈、空白页面或未知错误。

#### Scenario: 官方限流错误可恢复
- **WHEN** 官方模拟遇到 429
- **THEN** 前端展示"官方限流，已暂停对应槽并触发冷却，预计 X 秒后恢复"，提供"查看队列状态"入口

### Requirement: CI 质量门禁完整
CI SHALL 包含类型检查（`tsc -b`）、Lint（`eslint`）、格式检查（`prettier --check`）、前端单元测试（`vitest run`）、Python 单元测试、集成测试、E2E 冒烟、安全扫描、BRAIN 能力集一致性检查（`check_capability_registry.py`、`check_brain_contract.py`）、构建产物检查。任何核心门禁失败 SHALL 阻止交付。

#### Scenario: CI 包含前端类型检查
- **WHEN** PR 触发 `quality-gate.yml`
- **THEN** 执行 `npm run typecheck`（`tsc -b`），失败则阻断

### Requirement: 测试覆盖缺口场景
系统 SHALL 提供覆盖缓存损坏、Dataset ID 缺失、移动端交互、并发超限拒绝、会话过期重认证、任务中断恢复的测试。前端 SHALL 提供关键链路的行为测试（jsdom/Playwright），不再仅依赖静态文本检查。

#### Scenario: 缓存损坏测试
- **WHEN** `official_fields.json` 被模拟损坏
- **THEN** 系统检测到损坏，进入"需要人工确认"状态，不崩溃

### Requirement: 凭据零泄露
系统 SHALL 通过环境变量或本地安全存储注入凭据，严禁将账号、密码、Cookie、Token、Session、Header 提交到代码、测试、日志、截图或报告。日志 SHALL 分级并默认隐藏敏感字段。安全检查脚本 SHALL 扫描仓库中的密钥泄露、硬编码凭据、不安全请求、跨域配置、危险文件读写、测试产物泄露。

#### Scenario: 用户提供的测试凭据不进入仓库
- **WHEN** 审查本规格产生的所有代码、测试、文档、截图
- **THEN** 不存在用户提供的测试邮箱或测试密码字面量的任何痕迹（凭据字面量仅由用户本地持有，不写入仓库）
- **AND** 凭据仅通过 `BRAIN_USERNAME`/`BRAIN_PASSWORD`/`BRAIN_TOKEN` 环境变量注入

## MODIFIED Requirements

### Requirement: 三槽调度器一致性（继承自已实现）
`ThreeSlotScheduler`（`research/simulation_scheduler/_scheduler.py`）已支持 3 槽并发、独立状态机、槽级冷却。本规格要求 `BacktestSlotManager`（`research/backtest_slots.py`）与 web 层 `backtest_slot_limit()`（`web/misc/web_backtest_slots.py`）与调度器保持零偏差一致，并补齐任务取消、超时中断、状态不明自愈的端到端验证。

### Requirement: ConfigPanel 缓存模式回归保护（继承自已实现）
当前 `ConfigPanel.tsx:76-80` + `CredentialsSection.tsx:94-107` + `LocalCacheConnectionSection.tsx:22-83` 已正确实现缓存模式凭据折叠。本规格要求补齐回归测试，确保未来变更不退化：缓存可用且未连接时只显示"当前使用本地缓存"/"退出本地会话"/"临时连接官方服务"；凭据输入折叠在"临时连接官方服务"内部；用户未展开时不暴露账号密码；切换连接状态后 Dashboard、ConfigPanel、全局状态、后端会话状态一致。

### Requirement: 反过拟合审计补全（继承自已实现）
`scoring/anti_overfit/` 四层套件（IC 稳定性、regime 压力、安慰剂、半衰期）与 `audit_trail/writer.py` 已存在。本规格要求审计日志补全每个 Alpha 的来源、变体生成原因、使用过的反馈信号、被淘汰原因、优化次数、是否触达官方模拟；高度相似表达式、参数微调刷分、重复提交、异常高频失败重试由质量门禁自动拦截并归档。

## REMOVED Requirements

### Requirement: 重建三槽调度器
**Reason**：`ThreeSlotScheduler`（`research/simulation_scheduler/_scheduler.py:36-118`）已存在并支持 3 槽并发、独立状态机、槽级冷却，用户原始描述"Top3 批次入队但 worker 顺序提交并等待"与实际代码不符。
**Migration**：改为硬化一致性校验与端到端验证，不重建。

### Requirement: 修复 ConfigPanel 无条件渲染凭据输入
**Reason**：当前代码（`ConfigPanel.tsx:76-80`、`CredentialsSection.tsx:94-107`、`LocalCacheConnectionSection.tsx:22-83`）已正确实现折叠逻辑，与规格要求完全一致，bug 不存在。
**Migration**：改为补齐回归测试，防止退化。

## 技术约束

- 所有 BRAIN 平台字段/算子必须基于官方 API（DeepWiki/WQB 为只读标准）。
- 禁止使用测试脚本/历史提交结果/官方回测反馈进行过拟合式搜索。
- 凭据必须通过环境变量或本地安全存储注入，不落盘不日志不提交。
- 提交功能必须有人工确认机制（`REAL_SUBMIT_DISABLED_WEB_FLOW=True` 保持）。
- 所有 Python 后端文件 ≤ 350 行，所有前端源文件 ≤ 400 行。
- 不引入大型新依赖。
- 用户提供的测试凭据（邮箱与密码字面量由用户本地持有，不在本规格中落字）仅供用户本地验证，不进入仓库。
