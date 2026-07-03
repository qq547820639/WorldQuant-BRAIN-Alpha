# WorldQuant-BRAIN-Alpha 六波次重构 Spec

## Why

基于报告全文分析结论，本项目（BRAIN Alpha Ops，WorldQuant BRAIN 平台 Alpha 因子生产系统）当前存在三类核心问题：① **正确性盲区**——评分仅用 PSR/Sharpe 而缺 DSR（Deflated Sharpe Ratio）与置换检验预筛，存在系统性过拟合误判风险；② **安全脆弱**——`official_request.py` 存在已知 P0 token bug，认证回退后 token 未正确恢复，且 `_request()` 方法 170+ 行耦合 6 个暴露的认证状态变量；③ **架构债务**——`AlphaResearchPipeline` 9 个 Mixin 继承链 + `web_*.py` 82 个文件双重分发系统 + 评分权重 5+ 处分散配置 + 配置验证 6 个模块各自为政，导致维护成本高、回归风险大。

本规格按 **6 个波次、3 个优先级**（P0 正确性/安全、P1 架构/代码质量、P2 前端/清理）系统化推进重构，总工时 44 小时，所有变更通过特性开关/adapter 层保证可回滚，并将 6 项核心指标纳入 CI 硬门槛实现单向收敛。

## What Changes

### 波次 1：P0 正确性（无前置依赖）
- **新增** `scoring/dsr.py`，实现 DSR（Deflated Sharpe Ratio，基于 Bailey & Lopez de Prado 2014）解析计算公式
- **新增** 在 `ScoringContext` 中记录累计试验次数 N，支持 DSR 阈值判定（DSR > 0.95 通过、DSR < 0.50 直接过滤）
- **新增** `PermutationFilter` 组件，在预筛管线插入 1,000 次环形置换（circular permutation）预筛，仅 p < 0.05 候选推送至 API 回测；不通过者标记 `REJECTED_BY_PERMUTATION_TEST`
- 两项均通过特性开关控制，支持回退到原始 Sharpe / 跳过置换检验

### 波次 2：P0 安全（依赖波次 1）
- **修改** `official_request.py`，补充 `restore_token()` 恢复逻辑，修复认证回退成功后原始 bearer token 未恢复的 P0 bug
- **新增** `AuthStateMachine` 类 + `AuthStrategy` 协议，封装 `authenticate()`→`on_failure()`→`refresh()`→`restore_token()` 状态转换链
- **新增** `BearerAuth`、`CookieAuth`、`BasicAuth` 三个 `AuthStrategy` 实现
- **修改** `_request()` 简化为三步调用：`auth_sm.current()` → `send()` → `if 401: auth_sm.fallback()`
- 锁粒度从整个请求周期缩小至仅认证状态切换瞬间

### 波次 3：P1 架构（依赖波次 1-2）
- **修改** `AlphaResearchPipeline` 转为纯编排器，`run()` 缩减为对 `PipelineServices` 的线性编排调用（≤15 行）
- **修改** 9 个 Mixin 的 public 方法迁移到对应服务类，Mixin 变为 thin adapter
- 当所有调用通过 `pipeline.services.X` 时**移除 Mixin 继承**
- **新增** `PipelineServices` 18 个服务的完整依赖图（`importlab`/`pydeps`），识别并解除循环导入环
- **修改** 拆分 `test_pipeline.py`（82KB）为按功能域的独立模块
- **新增** `WebHandler` Protocol 类型替代 `Any` 注解
- **删除** `web_compat_facade.py` 和 `web_legacy_exports.py`（逐路由迁移、特性开关验证后）
- 合并或删除冗余的 `web_*.py` 文件

### 波次 4：P1 代码质量（依赖波次 3）
- **新增** `ScoringPolicy`（`frozen=True` dataclass），封装所有评分配置（权重、阈值、门控规则）
- **新增** `ScoringPolicy.from_config()` 工厂方法，合并 `ScoringConfig` + `QualityThresholds` + `scoring_params.py`
- **新增** `ScoringPolicy.with_regime(regime)` 方法支持市场体制动态调整
- **新增** `ScoringPolicy.explain()` 生成归因树供前端展示
- **新增** `ConfigParser`，实现 `parse_config(raw_dict) -> tuple[OpsConfig, list[ValidationError]]`
- `ConfigParser` 内部按管道顺序：jsonschema → dataclass → domain validation，任一阶段失败收集错误并继续
- **新增** `validate_update(current, patch)` 支持热更新验证

### 波次 5：P2 前端（可与波次 3-4 并行）
- **新增** 拆分 `CandidateTable.tsx`（2,107 行）为 5 个独立组件：`CandidateTableContainer`、`CandidateTableView`、`CandidateTablePagination`、`CandidateTableFilters`、`CandidateTableRowEditor`
- 数据流遵循 unidirectional data flow

### 波次 6：P2 清理（可与波次 3-4 并行）
- **新增** `LifecycleStatusNormalizer`，封装 `_LEGACY_STATUS_MAP` 30+ 项映射
- vN 引入 normalizer 并保持向后兼容 → vN+1 发出 `DeprecationWarning` → vN+2 移除遗留状态支持
- **修改** 重组测试目录为 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/static/`、`tests/fixtures/`
- **新增** 共享 mock factory 至 `tests/fixtures/factories.py`（`BrainAPI` mock、`Candidate` factory、`ScoringPolicy` 实例）
- 拆分 >30KB 巨型测试文件（目标从 ~15 个降至 ≤5 个），`test_official_adapter.py`（121KB）按功能域拆分为 4 个 ≤30KB 文件
- **新增** property-based testing（Hypothesis）覆盖评分边界组合

### 跨波次：CI 持续监控
- 将 6 项指标纳入 CI 流水线硬门槛：Mixin 继承链长度、`web_*.py` 文件数、评分权重配置位置数、认证状态变量暴露数、最大 Python 文件行数、>30KB 测试文件数
- 单向收敛：增加即阻断合并（前 4 项）/ 超限需审批（后 2 项）

### 风险缓解（贯穿所有波次）
- 每个修复单元 <10 行代码增量提交，先写测试再改代码
- Mixin adapter 层保证向后兼容，迁移期间不删除旧接口
- Web 双重分发切换采用逐路由特性开关，单条验证无误后才切断旧系统
- DSR 采用分层阈值：假设驱动型 Alpha DSR ≥ 0.30，数据驱动型 ≥ 0.50
- 置换检验 p 值在 0.05±0.01 区间自动触发 10,000 次高精度重算

## Impact

- **Affected specs**：
  - `overhaul-alpha-production-quality`（评分服务化 — 波次 1/4 与之协同，避免重复）
  - `remediate-major-defects-evaluation`（认证容错 — 波次 2 与之协同）
  - `tech-debt-cleanup`（前端 TS strict / Docker — 波次 5 独立推进）
  - `comprehensive-simplification-refactor`（架构简化 — 波次 3 与之协同）
  - `holistic-codebase-assessment`（评估报告 — 本规格响应其发现）

- **Affected code**：
  - `brain_alpha_ops/scoring/dsr.py`（新增，波次 1.1）
  - `brain_alpha_ops/scoring/`（`gates.py`、`local_quality.py`、`schema.py` — 波次 1.1 接入 DSR）
  - `brain_alpha_ops/research/candidate_pool_service_/_local_prefilter.py` 或新增 `PermutationFilter`（波次 1.2）
  - `brain_alpha_ops/research/scoring/scoring.py`、`brain_alpha_ops/research/scoring_params.py`（波次 1.1 + 4.1）
  - `brain_alpha_ops/brain_api/official_request.py`（波次 2.1 token bug 修复）
  - `brain_alpha_ops/brain_api/official_auth.py`（波次 2.2 AuthStateMachine）
  - `brain_alpha_ops/research/pipeline/pipeline.py`、`pipeline_mixins.py`（波次 3.1）
  - `brain_alpha_ops/research/pipeline_services.py`、`pipeline_services_container.py`（波次 3.1 容器）
  - `brain_alpha_ops/web/` 全部 `web_*.py` 文件（波次 3.2，82 个）
  - `brain_alpha_ops/scoring/`（`ScoringPolicy` 新增 — 波次 4.1）
  - `brain_alpha_ops/config_*.py`、`brain_alpha_ops/config_validation_helpers.py`、`brain_alpha_ops/config_domain_validation.py`、`brain_alpha_ops/config_type_validation.py`、`brain_alpha_ops/config_schema.py`（波次 4.2 ConfigParser）
  - `brain_alpha_ops/web/react_app/src/components/CandidateTable.tsx`（波次 5.1，2,107 行）
  - `brain_alpha_ops/candidate_lifecycle.py`、`brain_alpha_ops/research/candidate_pool.py`（波次 6.1 LifecycleStatusNormalizer）
  - `tests/`（全量重组 — 波次 6.2）
  - `.github/workflows/quality-gate.yml`、`scripts/check_module_size.py`、新增 `scripts/check_refactor_metrics.py`（CI 硬门槛）
  - `pyproject.toml`（新增 Hypothesis 依赖 — 波次 6.2）

- **Affected tests**：新增 DSR 单元测试（N=1/10/100/200）、置换检验过滤率测试、AuthStateMachine 三重失败组合测试、Mixin adapter 向后兼容测试、`PipelineServices` 循环导入检测（`pydeps`）、`ScoringPolicy` 冻结性 + regime 切换测试、`ConfigParser` 管道式验证测试、CandidateTable 组件 Storybook 测试、LifecycleStatusNormalizer 迁移测试、property-based 评分边界测试。

## ADDED Requirements

### Requirement: DSR 指标接入评分管线
系统 SHALL 在评分管线中提供 DSR（Deflated Sharpe Ratio）指标，基于 Bailey & Lopez de Prado 2014 解析公式实现。`ScoringContext` SHALL 记录累计试验次数 N。系统 SHALL 设置分层阈值：DSR > 0.95 通过、DSR < 0.50 直接过滤；假设驱动型 Alpha DSR ≥ 0.30，数据驱动型 ≥ 0.50。系统 SHALL 通过特性开关支持回退到原始 Sharpe。

#### Scenario: DSR N=1 等价于 PSR
- **WHEN** 累计试验次数 N=1
- **THEN** DSR 计算结果 SHALL 等价于 PSR（向后兼容）

#### Scenario: DSR 阈值过滤
- **WHEN** 候选 DSR < 0.50
- **THEN** 候选 SHALL 被直接过滤，不进入下一阶段
- **WHEN** 候选 DSR > 0.95
- **THEN** 候选 SHALL 通过该维度

#### Scenario: 特性开关回退
- **WHEN** 特性开关 `use_dsr=false`
- **THEN** 评分 SHALL 回退到原始 Sharpe，DSR 不参与判定

### Requirement: 预筛置换检验过滤器
系统 SHALL 在预筛管线中插入 `PermutationFilter`，对候选 Alpha 实施 1,000 次环形置换（circular permutation）置换检验，仅 p < 0.05 的候选 SHALL 推送至 API 回测。不通过的候选 SHALL 被标记为 `REJECTED_BY_PERMUTATION_TEST`。置换次数 SHALL 为可配置参数（默认 1,000，高精度 10,000）。p 值在 0.05±0.01 区间 SHALL 自动触发 10,000 次高精度重算。系统 SHALL 提供旁路开关支持跳过置换检验。

#### Scenario: 84×160 数据集置换性能
- **WHEN** 对 84×160 数据集执行 1,000 次环形置换
- **THEN** 计算 SHALL 在 < 1 秒内完成

#### Scenario: 纯随机信号过滤率
- **WHEN** 输入纯随机信号
- **THEN** 在 p < 0.05 阈值下被过滤率 SHALL ≥ 95%

#### Scenario: 边界 p 值触发高精度重算
- **WHEN** 候选 p 值落在 [0.04, 0.06] 区间
- **THEN** 系统 SHALL 自动触发 10,000 次高精度置换重算

### Requirement: Token Bug 局部修复
系统 SHALL 在 `official_request.py` 认证回退成功后正确恢复原始 bearer token。系统 SHALL 提供 `restore_token()` 恢复逻辑。系统 SHALL 在并发请求下保证 token 不丢失。

#### Scenario: cookie 回退成功后恢复 token
- **WHEN** bearer token 失败后 cookie 回退成功
- **THEN** 后续请求 SHALL 使用恢复后的原始 bearer token
- **AND** 原始 bearer token 不被 cookie 覆盖

### Requirement: AuthStateMachine 封装认证状态
系统 SHALL 提供 `AuthStrategy` 协议（含 `apply(request)` + `is_valid()`）与 `AuthStateMachine` 类。系统 SHALL 实现 `BearerAuth`、`CookieAuth`、`BasicAuth` 三个具体策略。`AuthStateMachine` SHALL 封装 `authenticate()`→`on_failure()`→`refresh()`→`restore_token()` 状态转换链。`_request()` SHALL 简化为三步调用：`auth_sm.current()` → `send()` → `if 401: auth_sm.fallback()`。锁粒度 SHALL 从整个请求周期缩小至仅认证状态切换瞬间。新增 OAuth 2.0 策略 SHALL 只需实现协议，无需修改状态机核心。

#### Scenario: _request 行数缩减
- **WHEN** 审查 `_request()` 方法
- **THEN** 行数 SHALL 从 170+ 降至 ≤20

#### Scenario: 认证状态变量封装
- **WHEN** 审查 `_request()` 内部
- **THEN** 暴露的认证状态变量 SHALL 从 6 个降至 0 个

#### Scenario: 三重失败组合
- **WHEN** cookie 过期 + token 无效 + basic 凭据错误同时发生
- **THEN** AuthStateMachine SHALL 按策略链有序降级，不抛未捕获异常

### Requirement: Pipeline Mixin → Composition 迁移
系统 SHALL 将 `AlphaResearchPipeline` 转为纯编排器，`run()` 方法 SHALL 缩减为对 `PipelineServices` 的线性编排调用（≤15 行）。9 个 Mixin 的 public 方法 SHALL 迁移到对应服务类，Mixin 变为 thin adapter。当所有调用通过 `pipeline.services.X` 时 SHALL 移除 Mixin 继承。系统 SHALL 通过 `importlab`/`pydeps` 绘制 `PipelineServices` 18 个服务依赖图，识别并解除循环导入环。系统 SHALL 拆分 `test_pipeline.py`（82KB）为按功能域的独立模块。Mixin adapter 层 SHALL 保证向后兼容，迁移期间不删除旧接口。

#### Scenario: Mixin 数量收敛
- **WHEN** 审查 pipeline 包
- **THEN** Mixin 数量 SHALL 从 9 降至 ≤3（3 个月目标为 0）

#### Scenario: run() 行数收敛
- **WHEN** 审查 `AlphaResearchPipeline.run()`
- **THEN** 行数 SHALL 从 120+ 降至 ≤15

#### Scenario: 无循环导入
- **WHEN** `pydeps` 验证 `PipelineServices` 依赖图
- **THEN** 不存在循环导入环

#### Scenario: 向后兼容
- **WHEN** 迁移期间调用 Mixin public 方法
- **THEN** adapter 层 SHALL 转发到对应服务，行为不变

### Requirement: Web 分发系统统一
系统 SHALL 创建 `WebHandler` Protocol 类型替代 `Any` 注解。系统 SHALL 逐路由迁移旧 handler 到新系统（特性开关控制流量），每条路由验证无误后才切断旧系统。系统 SHALL 删除 `web_compat_facade.py` 和 `web_legacy_exports.py`。系统 SHALL 合并或删除冗余的 `web_*.py` 文件。系统 SHALL 消除双重分发系统并行。

#### Scenario: web 文件数收敛
- **WHEN** 审查 `brain_alpha_ops/web/` 目录
- **THEN** `web_*.py` 文件数 SHALL 从 82 降至 ≤60（6 个月目标 ≤50）

#### Scenario: 双重分发消除
- **WHEN** 路由请求到达
- **THEN** 仅由单一 `PayloadRouteDispatcher` 处理，无并行分发

### Requirement: 评分权重统一为 ScoringPolicy
系统 SHALL 提供 `ScoringPolicy`（`frozen=True` dataclass），封装所有评分配置（权重、阈值、门控规则）。系统 SHALL 提供 `ScoringPolicy.from_config()` 工厂方法，合并 `ScoringConfig` + `QualityThresholds` + `scoring_params.py`。系统 SHALL 提供 `ScoringPolicy.with_regime(regime)` 方法支持市场体制动态调整。系统 SHALL 提供 `ScoringPolicy.explain()` 生成归因树供前端展示。评分权重配置位置数 SHALL 从 5+ 降至 1。`ScoringPolicy` SHALL 通过 `PipelineServices` 容器注入管线。`frozen=True` SHALL 保证运行时不可变。

#### Scenario: 配置位置统一
- **WHEN** 调整评分策略
- **THEN** 只需编辑 `ScoringPolicy` 一处

#### Scenario: 冻结不可变
- **WHEN** 运行时尝试修改 `ScoringPolicy` 字段
- **THEN** SHALL 抛出 `FrozenInstanceError`

#### Scenario: 市场体制切换
- **WHEN** 调用 `policy.with_regime("high_volatility")`
- **THEN** 返回新的 `ScoringPolicy` 实例，原实例不变

### Requirement: 配置验证整合为 ConfigParser
系统 SHALL 提供 `ConfigParser`，实现 `parse_config(raw_dict) -> tuple[OpsConfig, list[ValidationError]]`。`ConfigParser` 内部 SHALL 按管道顺序执行：jsonschema → dataclass → domain validation。任一阶段失败 SHALL 收集错误并继续后续阶段（非短路返回）。所有错误 SHALL 统一为结构化格式（字段路径 + 规则名 + 失败值 + 建议修复）。系统 SHALL 提供 `validate_update(current, patch)` 支持热更新验证。6 个配置验证模块 SHALL 通过单一入口调用。一次调用 SHALL 返回全部配置问题。

#### Scenario: 非短路错误收集
- **WHEN** jsonschema 阶段发现 2 个错误
- **THEN** dataclass 与 domain 阶段 SHALL 继续执行并收集各自错误
- **AND** 最终返回所有错误列表

#### Scenario: 错误格式统一
- **WHEN** 任意阶段产生错误
- **THEN** 错误对象 SHALL 含字段路径、规则名、失败值、建议修复

### Requirement: CandidateTable 组件拆分
系统 SHALL 将 `CandidateTable.tsx`（2,107 行）拆分为 5 个独立组件：`CandidateTableContainer`（数据获取 + 状态管理）、`CandidateTableView`（纯渲染）、`CandidateTablePagination`（分页）、`CandidateTableFilters`（筛选 UI）、`CandidateTableRowEditor`（行内编辑）。每个组件 SHALL ≤400 行。数据流 SHALL 遵循 unidirectional data flow。`CandidateTableView` SHALL 可独立通过 Storybook 测试。所有现有功能 SHALL 不受影响。

#### Scenario: 组件行数约束
- **WHEN** 审查拆分后的 5 个组件
- **THEN** 每个组件 SHALL ≤400 行

#### Scenario: 现有功能保留
- **WHEN** 拆分后运行现有测试
- **THEN** 所有功能 SHALL 通过

### Requirement: LifecycleStatusNormalizer 遗留状态清理
系统 SHALL 提供 `LifecycleStatusNormalizer`，封装 `_LEGACY_STATUS_MAP` 30+ 项映射。vN 版本 SHALL 引入 normalizer 并保持向后兼容。vN+1 版本 SHALL 对遗留状态发出 `DeprecationWarning`。vN+2 版本 SHALL 移除遗留状态支持。新增状态 SHALL 必须通过规范 `LifecycleState` enum。遗留状态映射项 SHALL 从 30+ 逐步降至 ≤10。迁移过程中 SHALL 无功能回归。

#### Scenario: 向后兼容
- **WHEN** vN 版本接收到遗留状态字符串
- **THEN** normalizer SHALL 映射到规范 `LifecycleState`，行为不变

#### Scenario: 弃用告警
- **WHEN** vN+1 版本接收到遗留状态
- **THEN** SHALL 发出 `DeprecationWarning`

### Requirement: 测试架构五层重组
系统 SHALL 将测试目录重组为 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/static/`、`tests/fixtures/`。系统 SHALL 提取共享 mock factory（`BrainAPI` mock、`Candidate` factory、`ScoringPolicy` 实例）至 `tests/fixtures/factories.py`。系统 SHALL 拆分 >30KB 巨型测试文件（目标从 ~15 个降至 ≤5 个）。`test_official_adapter.py`（121KB）SHALL 按功能域拆分为 4 个 ≤30KB 文件。`conftest.py` SHALL 从 2.8KB 扩充承载共享 fixtures。系统 SHALL 新增 property-based testing（Hypothesis）覆盖评分边界组合。

#### Scenario: 巨型测试文件收敛
- **WHEN** 审查 `tests/` 目录
- **THEN** >30KB 测试文件数 SHALL 从 ~15 降至 ≤5

#### Scenario: test_official_adapter 拆分
- **WHEN** 审查拆分后的 `test_official_adapter*`
- **THEN** SHALL 为 4 个 ≤30KB 文件

### Requirement: CI 重构指标硬门槛
系统 SHALL 将 6 项指标纳入 CI 流水线，每次 PR 自动校验：Mixin 继承链长度（基线 9 → 3 个月 ≤3 → 6 个月 0，增加即阻断合并）、`web_*.py` 文件数（基线 82 → ≤60 → ≤50，增加即阻断）、评分权重配置位置数（基线 5+ → 1，增加即阻断）、认证状态变量暴露数（基线 6 → 0，增加即阻断）、最大 Python 文件行数（基线 ~800 → <500 → <400，超限需审批）、>30KB 测试文件数（基线 ~15 → ≤5 → ≤2，超限需审批）。

#### Scenario: Mixin 增加阻断合并
- **WHEN** PR 引入新的 Mixin 继承
- **THEN** CI SHALL 阻断合并

#### Scenario: web 文件数增加阻断
- **WHEN** PR 新增 `web_*.py` 文件使总数超过当前基线
- **THEN** CI SHALL 阻断合并

#### Scenario: 文件行数超限需审批
- **WHEN** PR 使最大 Python 文件行数超过 500
- **THEN** CI SHALL 标记需审批，不自动阻断

## MODIFIED Requirements

### Requirement: BRAIN 认证容错（继承自 remediate-major-defects-evaluation）
**Modified**：原要求"401 须尝试 token 刷新与备选认证方法，指数退避后有限次重试"细化为本规格波次 2：通过 `AuthStateMachine` + `AuthStrategy` 协议封装状态转换链，`_request()` 简化为三步调用，锁粒度缩小至认证状态切换瞬间，新增 OAuth 2.0 策略只需实现协议。

### Requirement: 科学评分与质量门禁参与生产决策（继承自 overhaul-alpha-production-quality）
**Modified**：原要求"评分作为生产内嵌自动服务"细化为本规格波次 1 + 4：评分管线 SHALL 接入 DSR 指标 + `PermutationFilter` 预筛（波次 1），评分配置 SHALL 统一为 `ScoringPolicy`（`frozen=True`）并支持 `with_regime()` 动态调整与 `explain()` 归因（波次 4）。

### Requirement: 配置验证（继承自 tech-debt-cleanup）
**Modified**：原要求"jsonschema 恢复完整配置校验"扩展为本规格波次 4：6 个配置验证模块 SHALL 通过 `ConfigParser` 单一入口调用，按 jsonschema → dataclass → domain 管道顺序执行，任一阶段失败收集错误并继续，错误格式统一为结构化（字段路径 + 规则名 + 失败值 + 建议修复）。

## REMOVED Requirements

无。本规格所有变更均通过特性开关/adapter 层保证可回滚，不直接移除现有功能。波次 3.2 中删除 `web_compat_facade.py` 和 `web_legacy_exports.py` 需在逐路由迁移并验证无误后才执行，不构成功能移除。
