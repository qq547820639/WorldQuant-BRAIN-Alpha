# 重大缺陷修复与体验改进 Spec

## Why

在完整阅读 brain_alpha_ops **全量源码**（含 compliance / audit_trail / monitoring / production_diagnostics / scoring / web_candidates / web_cloud / data / research 全部子模块）并**交叉核对项目已有的 17 份审计/缺陷文档**后，识别出 **78 项实质性重大问题**，覆盖三大维度：

- **功能缺陷**：约 34 项 — 含**反过拟合 returns→factor_values 回退链导致虚假 PASS（核心防线失效）**、Quality Gate 审计失败跳过状态转换、仿真并发超限 deferred 被计为 failed、BCa Bootstrap n<5 退化为 (0,0) 使统计显著性失效、Pearson 系数被 (n-1)/n 系统性缩小、ProdCorrelation 按表达式长度自动放行、状态机非法转换静默回退、真实提交后审计失败致重复提交、浏览器驱动真实提交流缺失（P0）等
- **用户体验**：13 项 — 含 Web 端永久无法真实提交却强制走完整 HIL、SSE 断连误取消但云端任务仍在运行、错误引导仅覆盖 4/11 类等
- **WebUI**：13 项 — 含阻断阶段按钮仍可点、默认 inline HTML 不存在导致首屏空白、路由不进 URL 等

这些问题已对**生产稳定性、账户安全（重复提交 + 长表达式绕过相关性门禁）、反过拟合完整性（虚假 PASS）和可用性**造成实质性影响。本规格聚焦修复 Critical 与 High 级问题，并给出 Medium 级的改进方向。

## What Changes

### Critical 修复（必做）

**后端核心防线与状态机：**
- 修复反过拟合 `returns`→`factor_values` 回退链导致 `returns` 与 `factor_values` 完全相同、IC/Spearman 恒等于 1.0 虚假 PASS — 回退链须保留语义独立性或显式失败
- 修复 Quality Gate `intercept` 中审计写入与 `transition(gate_rejected)` 同 try 块，审计失败跳过状态转换致候选"已拦截但未转换"不一致 — 解耦，审计失败不阻断状态转换
- **BREAKING**：移除 `candidate_lifecycle.transition()` 非法转换静默回退 `force_transition` 的生产路径，生产环境非法转换必须抛 `IllegalTransitionError`
- 修复仿真并发超限（`CONCURRENT_SIMULATION_LIMIT_EXCEEDED`）时 deferred 候选被同时计为 `failed` 并触发 `stop_new_submissions` — deferred 与 failed 语义分离
- 修复真实提交成功后审计写入失败冒泡为 400 → 用户误重试 → 重复提交 — 审计写入与提交响应解耦
- 修复 `_install_facade_bindings` 静默吞异常导致 `JOB_REGISTRY=None` 后整站 AttributeError — fail-fast
- 修复 web_cloud 同步任务 `_heartbeat_loop` 仅捕获 `(OSError, ValueError, TypeError)`，其它异常致线程静默退出被 watchdog 误判卡死

**研究引擎数值正确性：**
- 修复 BCa Bootstrap 在 stall 检测中以单周期 sharpes（常 n=3-4）为输入退化为 (0,0)，绕过 `prev_hi>0` 守卫使显著性检测失效 — 样本不足时须明确降级标记，不可静默返回 (0,0)
- 修复 Pearson 相关系数 `cov/n` 与 `std/(n-1)` 混用导致 `r × (n-1)/n` 系统性缩小，污染 Spearman/IC/IC_stability 全链路 — 统一总体/样本统计量
- 修复 `ProdCorrelationService` 本地回退按表达式长度估值（≥100→0.25<0.70 自动放行）绕过 prod_correlation 硬门禁 — 本地回退不得放行，须明确 "unknown/blocked"
- **新揭示**：`ProdCorrelationService` 已实现官方 `/alphas/correlations/check` 调用但全仓库无生产代码导入，未接入流水线 — 须接入或显式标注降级模式

**提交安全闭环（P0/P1）：**
- 修复浏览器驱动的真实提交流缺失（P0）：`ApiExecutionAdapter.submit_alpha()` 仍公开真实提交入口且自带 "bypasses browser confirmation" Warning，e2e 测试用 `requests` 而非浏览器 — 生产提交闭环须有真实浏览器流程验证
- 修复提交安全语义不统一 + env 双旁路（P1）：`BRAIN_ALPHA_FORCE_REAL_SUBMIT` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS` 双 env 旁路 + API 层公开 submit 入口并存 — 三层守门语义统一

**WebUI：**
- 修复 PhaseShell 阻断阶段仅视觉淡化但按钮仍可点击 — `inert` / `pointer-events:none`
- 修复默认 inline HTML 不存在导致未构建 React 时首屏仅 `<h1>Template not found</h1>` — 内置引导 HTML
- 修复路由仅注册 `/` 导致面板切换不进 URL、刷新丢视图、后退退出站点 — 核心面板接入路由

**UX：**
- 修复 Web 端 `REAL_SUBMIT_DISABLED_WEB_FLOW` 永久 True 却让用户走完整 HIL 才在终点 403 — 提交流程入口前置提示
- 修复 SSE 断连 5 分钟后前端自动取消任务跟踪但 BRAIN 云端回测仍在运行 — 断连取消须警示云端可能仍在运行

### High 修复（应做）

**后端容错与资源：**
- StallMonitor 超限后静默放弃 → 超限必须 `_on_interrupt` 中断作业并升级告警
- BRAIN 认证仅 basic 单方法、401 无刷新重试 → token 刷新与备选认证回退
- `concurrent_simulate`/`concurrent_check` 超时 `future.cancel()` 无法中断线程 → 可中断执行或显式标记槽位释放
- 并行回测 `future.result()` 无 timeout → 批次级超时熔断
- 心跳线程（web_run_job）异常退出不重启 → 有限次重启
- WebSocket publish 不清理死亡订阅者 → 失败 sender 移出 `_subscribers`
- **V5-001**：`MAX_USER_ALPHAS_PAGES = None` 无界分页 → 加上界保护
- Regime 压力测试全零 Sharpe 误判满分通过 → 全零须判失败
- 重试阈值运算符不一致（`>` vs `>=`）→ 统一
- Ranker `candidate.scorecard.get()` 无 None 防护致整批排序崩溃 → 加防护与降级
- 审计写入 64KB 截断丢失 `gate_decisions`/`triggered_rules` → 分片或保留关键字段
- Evidence `cleanup_old`/`list_sessions` 单点解析失败中断整个循环 → 单文件异常跳过
- 诊断快照无异常隔离，单探针失败终止整体诊断 → 探针间隔离
- 官方 context 回退路径解析为包内 data 目录（site-packages 安装时指向陈旧数据）→ 修正路径解析
- 无身份候选 update 被追加为新行致 `candidates.jsonl` 重复累积 → 强制身份键或拒绝
- BaoStock logout 不在 finally 致会话泄漏 → try/finally
- `FieldDatasetMapper.build()`/`_add_mapping()` 并发不安全 → 统一锁策略
- check 证据持久化失败仅 warning 不传播 → 提交就绪审计基于陈旧证据 → 失败须传播或标记证据 stale
- `save_assistant_guidance` 异常传播导致整个生成结果丢失 → 副产物失败不阻断主结果
- `max_official_concurrent_simulations=0` 被 `or 3` 静默改写为 3 → 显式区分 0 与未设置
- 滚动验证 `decay_ratio` 在 first 为负时符号反转 → 修正公式
- `ic_stability` 分量上限不对称（150 vs 100）→ 统一上限
- `RecordSqliteIndex.refresh` 仅索引尾部 10000 条 → 暴露覆盖率或全量索引
- Placebo 检验全局固定 seed=42 → 按候选派生 seed
- `sub_universe_sharpe` 本地计算按符号下标前半切片（非按权重 top-half）→ 修正或标注

**WebUI：**
- `useCandidateTableData` 刷新循环 → 拆分依赖
- `OfficialBacktestSlots` 每 5s 全量 `refreshAll` → 仅轮询 `/api/backtest_slots`
- JobMonitor SSE 随 Dashboard 卸载断连 → SSE 提升到 App 层
- 所有 Modal 无焦点陷阱 → 接入 FocusTrap
- 双重 Toast 系统 → 移除死代码 ToastProvider

**UX：**
- 批量提交无 dry-run 预览、无撤销、无原子性 → 预览 + 部分失败明细
- 配置保存仅提示「已保存」无「需重启生效」→ 涉及 Final 常量明确提示
- 限流倒计时固定 30s 不读 `retry_after` → 读取后端值
- 前台任务完成无提示 → 补充 toast/徽标

### Medium 改进方向（记录为后续）
- 生命周期审计写入异常被 debug 级静默吞 → 提升日志级别
- LocalBacktestEngine LRU 实为 FIFO → 命中时移到末尾
- phase stalled 判定硬编码 10s 阈值 → 可配置
- History 趋势比较基准错位 → 修正
- Redline No-Custom-Extension 检查依赖可污染的模块级缓存 → 隔离
- 冷却判定函数含副作用写入 → 拆分纯函数
- `load_index_universe` 静默截断到 500 symbols → 报错或按流动性
- CheckpointManager 索引损坏静默重置 → 目录扫描重建
- BCa bootstrap 不可达死代码 → 清理
- 首次启动无引导、launch_web.py 无端口/URL 输出
- 首次 8599 字段下载无总体 ETA
- 历史文件 >10MB 静默跳过加载无提示
- JobStore 持久化 >50MB 跳过加载、中断任务无法续跑
- watchdog 失败消息英文外泄、仅 scan 阶段检测停滞
- live_submit_readiness 累计 15+ 英文 reasons 无中文映射
- ErrorBoundary 返回首页用 hash 与 BrowserRouter 冲突
- 移动端 statusbar 被 mobile-tab-bar 遮挡
- 候选导出下拉无 click-outside 关闭
- GlobalData 30s 轮询不看 visibility
- `renderActiveViewFromContext` 在 render 期调 hook
- 错误引导仅覆盖 4 类连接错误，其余 7+ 类业务错误无恢复入口
- 官方 context 元数据 freshness 过期（P1 follow-up）
- 监控闭环不覆盖前端交互自愈
- 测试过度依赖内部实现与本地桩（验证过拟合）
- `candidate_lifecycle.py` 仍超行限（唯一剩余 grandfathered）

## Impact

- **Affected specs**：`overhaul-alpha-production-quality`、`complete-brain-alpha-ops`、`upgrade-to-public-product`、`improve-frontend-ux`
- **Affected code**（按子系统）：
  - `brain_alpha_ops/scoring/anti_overfit/`（service.py、regime_stress.py、ic_stability.py、placebo.py、utils.py、compliance.py、suite.py、models.py）
  - `brain_alpha_ops/scoring/`（_ranker.py、history.py、scoring_comparison.py）
  - `brain_alpha_ops/audit_trail/`（quality_gate.py、writer.py、lifecycle_writer.py）
  - `brain_alpha_ops/monitoring/evidence.py`
  - `brain_alpha_ops/production_diagnostics/`（_snapshot.py、_probes.py）
  - `brain_alpha_ops/compliance/redline_check_no_custom_extension.py`、`redline_check_thresholds.py`
  - `brain_alpha_ops/web_candidates/`（simulation/_submit.py、simulation_state/_candidates.py、_cooldown.py、check_evidence.py、generation/_generation.py、simulation/__init__.py）
  - `brain_alpha_ops/web_cloud/`（sync_job/_service/_state.py、snapshot/_official_context_read.py）
  - `brain_alpha_ops/data/`（ashare_adapter/_provider.py、field_dataset_mapper.py）
  - `brain_alpha_ops/research/`（convergence/_tracker.py、_bootstrap_mixin.py、prod_correlation.py、rolling_validation.py、checkpoint.py、record_sqlite_index.py、local_backtest/metrics.py、parallel_backtest/_executor.py、local_backtest/engine.py）
  - `brain_alpha_ops/brain_api/`（official_auth.py、official_simulation/_mixin.py、api_execution_adapter.py、pagination_limits.py）
  - `brain_alpha_ops/web/`（__init__.py、ws.py、handlers/phase.py、submissions/web_submission_single.py、web_submission_batch.py、misc/web_html.py、misc/web_rate_limit.py、business/web_run_job.py）
  - `brain_alpha_ops/candidate_lifecycle.py`、`stall_monitor.py`、`runtime_constants.py`
  - `brain_alpha_ops/web/react_app/src/`（main.tsx、App.tsx、components/PhaseShell.tsx、Toast.tsx、ConfirmDialog.tsx、KeyboardShortcutsHelp.tsx、OfficialBacktestSlots.tsx、SubmissionConfirmPanel.tsx、ErrorBoundary.tsx、hooks/useCandidateTableData.ts、useGlobalData.ts、useJobMonitor/、useJobWatchdog.ts、useSSE.ts、useJobDisconnectedState.ts、useConfigForm.ts、helpers/connectionErrorGuide.ts）
  - `launch_web.py`

## ADDED Requirements

### Requirement: 反过拟合回退链不得导致虚假 PASS
The system SHALL NOT allow fallback chains that make `returns` and `factor_values` identical, which would force IC/Spearman correlation to 1.0 and produce a false PASS on anti-overfitting checks.

#### Scenario: returns 数据缺失
- **WHEN** real `returns` data is unavailable
- **THEN** the system SHALL either fail the anti-overfitting check explicitly with reason "missing returns data"
- **OR** use a semantically distinct proxy that is NOT `factor_values`
- **AND NOT** fall back `returns → factor_values` then `forward_returns → returns` making all series identical

### Requirement: Quality Gate 审计失败不得跳过状态转换
The system SHALL decouple audit writing from lifecycle state transition so that an audit write failure does not leave a candidate in an inconsistent "intercepted but not transitioned" state.

#### Scenario: 审计写入失败
- **WHEN** `record_gate_decision()` raises
- **THEN** the candidate SHALL still transition to `gate_rejected`
- **AND** the audit failure SHALL be logged at ERROR level
- **AND NOT** skip the transition leaving the candidate in a non-rejected state

### Requirement: 候选生命周期非法转换必须显式失败
The system SHALL raise `IllegalTransitionError` on illegal lifecycle transitions in production paths, and SHALL NOT silently fall back to `force_transition`.

#### Scenario: 生产路径非法转换
- **WHEN** 生产代码调用 `transition(target)` 且 `lc.transition(target)` 返回 `False`
- **THEN** 抛出 `IllegalTransitionError`
- **AND** 仅当调用方显式传 `force=True` 时才允许 `force_transition`（仅测试用例）

### Requirement: 仿真并发超限须语义分离 deferred 与 failed
The system SHALL NOT mark concurrent-limit-deferred candidates as `failed` nor trigger `stop_new_submissions` for the whole batch.

#### Scenario: CONCURRENT_SIMULATION_LIMIT_EXCEEDED
- **WHEN** BRAIN returns `CONCURRENT_SIMULATION_LIMIT_EXCEEDED`
- **THEN** the candidate SHALL be marked `deferred_concurrency_limit` (not `failed`)
- **AND** `state.failed` SHALL NOT increment
- **AND** `stop_new_submissions` SHALL only pause the affected slot, not the whole batch
- **AND** the candidate SHALL remain eligible for retry after cooldown

### Requirement: 真实提交成功后审计失败不得阻断响应
#### Scenario: 提交成功但审计写失败
- **WHEN** `api.submit_alpha()` 已成功返回 result
- **AND** 后续 `save_lifecycle_record()` 抛出异常
- **THEN** 响应仍返回提交成功
- **AND** 审计失败记录到 ERROR 级日志与监控指标

### Requirement: Facade 绑定安装失败必须 fail-fast
#### Scenario: 绑定安装异常
- **WHEN** `_install_facade_bindings()` 抛出任意异常
- **THEN** 异常向上传播导致服务启动失败，日志记录原始异常堆栈
- **AND NOT** 模块级 `JOB_REGISTRY` 保持 `None` 后在请求期才暴露无关 `AttributeError`

### Requirement: 同步任务心跳线程须容错
The system SHALL not let the sync job heartbeat thread silently die on exceptions beyond `(OSError, ValueError, TypeError)`.

#### Scenario: 心跳循环抛 KeyError
- **WHEN** `store.update()` raises a non-(OSError, ValueError, TypeError) exception
- **THEN** the heartbeat thread SHALL log and continue (or restart within a bounded retry)
- **AND NOT** silently exit causing watchdog to misjudge a healthy sync as stalled

### Requirement: BCa Bootstrap 样本不足须明确降级
The system SHALL NOT silently return (0,0) confidence interval when sample size < 5, which bypasses the `prev_hi > 0` guard and degrades significance detection.

#### Scenario: 单周期 sharpes n<5
- **WHEN** `raw_sharpes` has fewer than 5 samples
- **THEN** the system SHALL mark the CI as "insufficient_samples" (not (0,0))
- **AND** downstream stall detection SHALL treat insufficient samples as "no signal" rather than "significant decline"

### Requirement: Pearson/Spearman/IC 统计量须一致
The system SHALL use consistent population or sample statistics so that correlation coefficients are not systematically shrunk by (n-1)/n.

#### Scenario: 小样本相关系数
- **WHEN** computing Pearson/Spearman/IC with n=3
- **THEN** the result SHALL equal the standard correlation (not 0.667× the standard)
- **AND** IC_stability / regime_stress / placebo scores SHALL not be systematically underestimated

### Requirement: ProdCorrelation 本地回退不得放行
The system SHALL NOT auto-pass the prod_correlation hard gate based on expression length when the official API is unavailable.

#### Scenario: 官方 API 不可用
- **WHEN** `ProdCorrelationService` falls back to local estimation
- **AND** expression length >= 100
- **THEN** the result SHALL be "unknown" or "blocked" (not `passed=True` with estimated_corr=0.25)
- **AND** the candidate SHALL NOT pass the prod_correlation hard gate without official verification

### Requirement: ProdCorrelationService 须接入生产流水线
The system SHALL integrate the implemented `ProdCorrelationService` (official `/alphas/correlations/check`) into the scoring pipeline, or explicitly mark prod_correlation as running in degraded/local-only mode.

#### Scenario: 评分流水线
- **WHEN** the scoring pipeline evaluates prod_correlation
- **THEN** it SHALL call `ProdCorrelationService` (not consume a mock value)
- **OR** explicitly mark the gate as "degraded: local-only" in the audit

### Requirement: 浏览器驱动的真实提交闭环须可验证（P0）
The system SHALL provide a verifiable browser-driven real submission flow, and SHALL NOT rely on `ApiExecutionAdapter.submit_alpha()` (which bypasses browser confirmation) as the production submission path.

#### Scenario: 生产提交验证
- **WHEN** verifying the production submission closure
- **THEN** e2e tests SHALL use a real browser flow (not `requests` hitting local `/api/*`)
- **AND** `ApiExecutionAdapter.submit_alpha()` SHALL be gated to dev/test only

### Requirement: 提交安全语义须统一（P1）
The system SHALL unify the three-layer submission gating semantics and remove ambiguous env bypasses.

#### Scenario: env 旁路
- **WHEN** `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` is set without `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`
- **THEN** real submission SHALL remain disabled
- **AND** the API-layer `submit_alpha()` public entry SHALL require explicit browser-backend confirmation

### Requirement: 阻断阶段必须禁用关键交互
#### Scenario: 阶段未就绪或已阻断
- **WHEN** `statusTone` 为 `pending` 或 `blocked`
- **THEN** 关键操作区应用 `inert` 属性或 `pointer-events: none`
- **AND** 可聚焦元素不可被 Tab 到达

### Requirement: 默认前端首屏必须有可用引导
#### Scenario: React 未构建且 inline 模板缺失
- **WHEN** `react_app/dist/index.html` 不存在 AND inline 模板不存在
- **THEN** 返回内置引导 HTML，含 frontend 选取结果、缺失原因、`npm run build` 指引、端口信息
- **AND NOT** 返回空白英文 `Template not found`

### Requirement: 核心面板切换必须反映到 URL
#### Scenario: 切换面板后刷新
- **WHEN** 用户从 Dashboard 切换到 Scoring 面板
- **THEN** URL 变为 `/scoring`，刷新停留，后退可回 Dashboard

### Requirement: Web 端不可真实提交须前置提示
#### Scenario: 候选进入提交队列
- **WHEN** 候选首次进入提交队列或用户打开提交面板
- **THEN** 明确展示「Web 端不可真实提交，最终提交需在 BRAIN 平台完成」+ BRAIN 平台外链

### Requirement: SSE 断连取消须警示云端可能仍在运行
#### Scenario: SSE 断连超时自动取消
- **WHEN** SSE 断连超过重连上限触发本地任务取消
- **THEN** 展示「BRAIN 云端回测可能仍在运行，请先到 BRAIN 平台确认槽位」+ 槽位查询入口

### Requirement: user_alpha 分页须有上界（V5-001）
The system SHALL enforce an upper bound on `MAX_USER_ALPHAS_PAGES` to prevent unbounded pagination exhausting resources.

#### Scenario: 长期运行同步
- **WHEN** user_alpha sync runs for a long-lived account
- **THEN** pagination SHALL stop at a configurable upper bound
- **AND** the sync SHALL report truncation

### Requirement: Regime 压力测试全零 Sharpe 须判失败
#### Scenario: 所有 regime Sharpe 均为 0
- **WHEN** all regime Sharpes are 0
- **THEN** `regime_stability_score` SHALL be 0 (not 100.0)
- **AND** `passed` SHALL be False

### Requirement: Ranker 须对缺失 scorecard 降级
#### Scenario: candidate.scorecard 为 None
- **WHEN** a candidate's `scorecard` is None
- **THEN** the ranker SHALL skip or default the candidate (not crash the whole sort)
- **AND** log a warning

### Requirement: 审计 64KB 截断须保留关键字段
#### Scenario: 单条审计超 64KB
- **WHEN** a single audit record exceeds 64KB
- **THEN** `gate_decisions` and `triggered_rules` SHALL be preserved (or sharded)
- **AND** only non-essential `details` SHALL be truncated

### Requirement: 无身份候选 update 须拒绝或强制身份键
#### Scenario: alpha_id/official_alpha_id/expression 均缺失
- **WHEN** a candidate update row has no identity key
- **THEN** the system SHALL reject the update (not append as a new row)
- **AND** log a warning

### Requirement: max_official_concurrent_simulations=0 须被尊重
#### Scenario: 配置显式设为 0
- **WHEN** `max_official_concurrent_simulations` is explicitly 0
- **THEN** the system SHALL disable concurrent submission (not silently rewrite to 3)

### Requirement: FieldDatasetMapper 须并发安全
#### Scenario: 并发刷新
- **WHEN** `build()` and `_add_mapping()` run concurrently
- **THEN** the dual index SHALL remain consistent
- **AND** no mapping SHALL be lost

### Requirement: check 证据持久化失败须传播或标记 stale
#### Scenario: check 证据写失败
- **WHEN** `persist_candidate_check_evidence` fails
- **THEN** the failure SHALL propagate OR mark downstream submit-readiness as "stale evidence"
- **AND NOT** silently swallow leaving submit-readiness based on stale data

### Requirement: save_assistant_guidance 失败不得丢失生成结果
#### Scenario: 助手引导持久化失败
- **WHEN** `save_assistant_guidance()` raises
- **THEN** the generation result (candidates/summary/automation/scientific_audit) SHALL still be returned
- **AND** the guidance failure SHALL be logged

### Requirement: 批量提交须提供预览与部分失败明细
#### Scenario: 批量提交部分失败
- **WHEN** batch submission has partial failures
- **THEN** response SHALL include `submitted` and `failed` detail lists
- **AND** frontend SHALL show per-candidate results

### Requirement: 配置生效条件须明确告知
#### Scenario: 修改涉及 Final 常量的配置
- **WHEN** user saves config affecting `runtime_constants` Final values
- **THEN** success message SHALL include "需重启服务生效" and mark affected items

### Requirement: 限流倒计时须读取后端 retry_after
#### Scenario: 触发限流
- **WHEN** backend returns `rate_limit` with `retry_after`
- **THEN** frontend countdown SHALL use that `retry_after` (not hardcoded 30s)

### Requirement: 前台任务完成须有可见提示
#### Scenario: 前台运行时长任务完成
- **WHEN** a long task completes in foreground
- **THEN** a toast or badge SHALL be shown (not only when `document.hidden`)

## MODIFIED Requirements

### Requirement: StallMonitor 超限处理
**Modified**: 超过 `max_retry_count` 后必须调用 `_on_interrupt` 中断作业并升级告警，而非静默 `return`。

### Requirement: BRAIN 认证容错
**Modified**: `authenticate()` 遇 401 须尝试 token 刷新与备选认证方法，指数退避后有限次重试。

### Requirement: 并发模拟/检查超时处理
**Modified**: 超时后须显式释放槽位并标记作业可中断，而非依赖无效 `future.cancel()`。

### Requirement: 并行回测批次超时
**Modified**: 须对 `as_completed` 与 `future.result()` 设置批次级 timeout。

### Requirement: 心跳线程容错（web_run_job）
**Modified**: `_heartbeat_loop` 异常退出前须有限次重启。

### Requirement: WebSocket 死连接清理
**Modified**: `publish` 失败的 sender 须从 `_subscribers` 移除。

### Requirement: 重试阈值运算符统一
**Modified**: `failure_count > threshold` 与 `count >= threshold` 须统一为同一语义。

### Requirement: Evidence 清理单点容错
**Modified**: `cleanup_old`/`list_sessions` 须对单个损坏文件跳过而非中断整个循环。

### Requirement: 诊断快照探针隔离
**Modified**: `build_diagnostic_snapshot` 须对每个探针 try/except，单探针失败不终止整体。

### Requirement: 官方 context 回退路径
**Modified**: 须修正 `parents[2]` 解析为项目根 `data`，而非包内 `brain_alpha_ops/data`。

### Requirement: BaoStock logout 须在 finally
**Modified**: `load_daily_batch` 须用 try/finally 确保 logout。

### Requirement: 滚动验证 decay_ratio 符号
**Modified**: first 为负时公式须修正，score 不得倒置。

### Requirement: ic_stability 分量上限
**Modified**: `mean_score` 与 `stability_score` 上限须统一（如均 100）。

### Requirement: RecordSqliteIndex 覆盖率
**Modified**: refresh 须暴露索引覆盖率或全量索引。

### Requirement: Placebo seed
**Modified**: 须按候选派生 seed，不得全局固定 42。

### Requirement: sub_universe_sharpe 本地计算
**Modified**: 须按权重 top-half 切片（非符号下标前半），或明确标注为非 BRAIN 语义。

### Requirement: 候选表数据加载
**Modified**: `useCandidateTableData` 须消除 `loadCandidates` 对 `globalCandidatesData` 的依赖循环。

### Requirement: 回测槽位轮询
**Modified**: `OfficialBacktestSlots` 须仅轮询 `/api/backtest_slots`。

### Requirement: 任务 SSE 生命周期
**Modified**: 任务 SSE 连接须独立于 Dashboard 视图生命周期，提升到 App 层 context。

### Requirement: Modal 焦点陷阱
**Modified**: 所有 Modal 须接入 `FocusTrap`。

### Requirement: Toast 系统统一
**Modified**: 移除死代码 `ToastProvider`，统一到 `useBaseState` 的 Toast 实现。

## REMOVED Requirements

### Requirement: 候选生命周期非法转换静默回退
**Reason**: 生产路径中 `transition()` 非法转换回退 `force_transition` 破坏状态机不变量，使合规审计、HIL 闸门、提交就绪检查失效。
**Migration**: 生产调用方须处理 `IllegalTransitionError`；仅测试用例显式传 `force=True`。

### Requirement: ProdCorrelation 按表达式长度放行
**Reason**: 本地回退按表达式长度估值（≥100→0.25）绕过 prod_correlation 硬门禁，让高相关长表达式自动通过。
**Migration**: 本地回退须返回 "unknown/blocked"，不得放行；候选须有官方 correlations/check 结果才可通过硬门禁。
