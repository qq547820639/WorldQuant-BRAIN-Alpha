# 重大缺陷修复与体验改进 Spec

## Why

在完整阅读 brain_alpha_ops **全量源码**（四轮深度分析覆盖所有子模块：core / web / web/dispatch / brain_api（official/official_alphas/official_context/official_helpers/official_simulation） / research（含全部子包：decoupled_pipeline/simulation_scheduler/repository/pipeline mixins/expression_index/iterative_optimizer/cross_review_pipeline/calibration_engine/auto_calibrator/evolution/knowledge_base/memory/experience/theme_engine 等） / scoring（含 official_scoring/release_score_gate） / compliance / audit_trail / monitoring / production_diagnostics / web_candidates / web_cloud / data / agent_tools / mcp_server / browser（execution_adapter） / llm_service / config / execution_backend / strategy / shared / types / security / deployment / tests / scripts）并**交叉核对项目已有的 17 份审计/缺陷文档**后，识别出 **160+ 项实质性重大问题**，覆盖三大维度：

- **功能缺陷**：约 60 项 — 含**反过拟合 returns→factor_values 回退链导致虚假 PASS（核心防线失效）**、Quality Gate 审计失败跳过状态转换、仿真并发超限 deferred 被计为 failed、BCa Bootstrap n<5 退化为 (0,0)、Pearson 系数被 (n-1)/n 系统性缩小、ProdCorrelation 按表达式长度自动放行、状态机非法转换静默回退、真实提交后审计失败致重复提交、浏览器驱动真实提交流缺失（P0）、**三套 backend 注册机制互不协同 + 生产 pipeline 从未接入 execution_backend**、**MCP stdio 单线程阻塞**、**LLM 配额账本是死代码**、**Browser 提交幂等键淘汰后可重放**、**Browser 登录判定用 nav 选择器误判已登录**、registry 校验把枚举值误当数据字段必然误报、strategy profile_id 不含 delay 哈希冲突、参数审计遗漏 10+ official_api 参数、lifecycle_records 无界增长 OOM 等
- **用户体验**：13 项 — 含 Web 端永久无法真实提交却强制走完整 HIL、SSE 断连误取消但云端任务仍在运行、错误引导仅覆盖 4/11 类等
- **WebUI**：13 项 — 含阻断阶段按钮仍可点、默认 inline HTML 不存在导致首屏空白、路由不进 URL 等
- **安全与部署**：约 24 项（第三轮新发现）— 含**Docker 镜像以 root 运行 + evidence 目录 chmod 777**、**证据归档未脱敏（HAR/截图/网络日志含 Authorization/Cookie 原样落盘）**、**REAL_SUBMIT 可被 PYTEST_CURRENT_TEST 环境变量旁路**、CI npm critical CVE continue-on-error、CI 缺失 pip-audit、Python 版本不一致、日志脱敏正则要求含数字漏脱纯字母 token、security_scan 跳过 >1MB 文件、web_security allow_remote 时 Host 头作信任锚（DNS rebinding）、_launch_monitor 引用不存在的 exe、SBOM 仅含直接依赖等

这些问题已对**生产稳定性、账户安全（重复提交 + 长表达式绕过相关性门禁 + REAL_SUBMIT 旁路 + 证据含凭证）、反过拟合完整性（虚假 PASS）和可用性**造成实质性影响。本规格聚焦修复 Critical 与 High 级问题，并给出 Medium 级的改进方向。

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

## ADDED Requirements (第四轮：解耦流水线 / 校准 / 进化 / Dispatch / 运行时)

### Requirement: DecoupledPipeline SharedState 须线程安全
The system SHALL protect all `SharedState` counters and lists (`produced_count`, `filtered_count`, `officially_simulated_count`, `submitted_count`, `accepted_candidates`, `archive_stats`, `archive_samples`, `blocked_expressions`) with locks, not rely on GIL for compound `+=` / `append` operations.

#### Scenario: 多 worker 并发
- **WHEN** Production/Filter/Optimization/Validation workers run concurrently
- **THEN** counters SHALL not be lost or corrupted
- **AND** cycle termination conditions SHALL be based on accurate counts

### Requirement: ValidationWorker 不得默认 submission_ready=True
The system SHALL NOT default `gate.submission_ready` to `True` for un-scored candidates, as this bypasses the local quality gate.

#### Scenario: 未评分候选
- **WHEN** a candidate has not been scored by FilterWorker (gate empty or missing)
- **THEN** `submission_ready` SHALL default to `False`
- **AND** the candidate SHALL NOT be submitted to official simulation

### Requirement: Candidate 跨 worker 修改须加 per-candidate 锁
The system SHALL synchronize cross-worker mutations to shared `Candidate` objects (lifecycle_status, local_quality, gate, submission dict).

#### Scenario: Filter 与 Validation 并发
- **WHEN** FilterWorker writes gate while ValidationWorker reads it
- **THEN** a per-candidate lock SHALL prevent torn reads
- **AND** submission decisions SHALL be based on consistent state

### Requirement: structure_refine 不得用 rfind(",") 破坏含逗号表达式
The system SHALL NOT truncate inner expressions by `rfind(",")` which breaks multi-argument calls like `if(x>0, a, b)`.

#### Scenario: 含逗号的包装表达式
- **WHEN** `structure_refine` removes a wrapper from `zscore(if(x > 0, a, b))`
- **THEN** the inner expression SHALL remain syntactically valid
- **AND NOT** be truncated to `"if(x > 0, a"`

### Requirement: calibrate_prior_weights 须保留相关性符号
The system SHALL NOT use `abs(pearson_r)` for weight computation, as it loses the correlation direction and may invert weights for negatively-correlated dimensions.

#### Scenario: 负相关维度
- **WHEN** a dimension has `pearson_r = -0.8` (strongly negatively correlated with sharpe)
- **THEN** the weight SHALL reflect the negative direction (e.g., zero or negative weight)
- **AND NOT** assign it the highest weight via `abs(-0.8) = 0.8`

### Requirement: calibrate_scorecard_weights 须用有符号相关性选最优
The system SHALL select optimal scorecard weights by signed correlation, not `abs(corr)`, to avoid picking anti-correlated weights.

#### Scenario: 反相关权重组合
- **WHEN** a (prior, empirical, checklist) combination has `corr = -0.95` with sharpe
- **THEN** it SHALL NOT be selected as optimal
- **AND** optimal SHALL be the max signed correlation

### Requirement: auto_calibrator 须正确导入校准模块
The system SHALL import `calibrate_prior_weights` / `calibrate_scorecard_weights` from the correct module path; the current `from calibrate_weights import ...` references a non-existent module and silently disables weight calibration.

#### Scenario: 自动校准触发
- **WHEN** `AutoCalibrator.calibrate()` runs
- **THEN** dimension weights and three-layer scorecard weights SHALL actually be calibrated
- **AND NOT** return `{"error": "calibrate_weights module not importable"}` silently

### Requirement: EvolutionRunner 须用更新后的 scores 剪枝
The system SHALL re-score mutants/crossovers before pruning, not use the stale `scores` dict from the start of the generation.

#### Scenario: 种群已满
- **WHEN** population reaches `population_size` and mutants are appended
- **THEN** mutants SHALL be scored before pruning
- **AND NOT** default to 0.0 and be immediately eliminated

### Requirement: WebApplicationContext 白名单不得含安全函数
The system SHALL NOT allow `_csrf_for_session`, `_has_valid_admin_token`, `_get_or_create_session`, `_validate_session` to be overwritten via `WebApplicationContext.__setattr__`, as this enables CSRF/auth bypass.

#### Scenario: 注入 handler 覆盖安全函数
- **WHEN** an injected business handler sets `ctx._csrf_for_session = lambda *a: ""`
- **THEN** the assignment SHALL be rejected
- **AND** CSRF and admin token checks SHALL remain enforced

### Requirement: JobStore 跳过加载后不得永久失去持久化
The system SHALL NOT permanently disable persistence (`persistence_load_skipped=True` forever) after a single load skip; it SHALL retry persistence once jobs change.

#### Scenario: 重启后文件过大
- **WHEN** `_load` skips a >50MB file
- **AND** jobs subsequently change
- **THEN** `_persist_locked` SHALL retry writing (not `return` early forever)
- **AND** the skip state SHALL be resettable

### Requirement: compute_run_stats 须接入真实实现
The system SHALL route production `compute_run_stats` / `status_category` calls to the real implementation in `web/state/web_runtime_state.py`, not the stub in `web_runtime_facade/_server.py` that always returns zeros.

#### Scenario: 生产任务统计
- **WHEN** `web_run_job.py` computes task stats
- **THEN** it SHALL use the real `compute_run_stats` (candidates/simulations/submissions counts)
- **AND NOT` return `{"candidates": 0, "simulations": 0, "submissions": 0}` stub

### Requirement: OptimizationWorker 须接收真实 optimizer
The system SHALL pass a real optimizer to `OptimizationWorker`, not `None` which makes the optimization stage dead code.

#### Scenario: 解耦流水线启动
- **WHEN** `DecoupledPipeline` constructs `OptimizationWorker`
- **THEN** a real `IterativeOptimizer` SHALL be passed
- **AND** `optimization_attempts` SHALL reflect real optimization

### Requirement: DecoupledCoordinator.wait_for_completion 须可靠
The system SHALL set worker state to STOPPED on loop exit so `wait_for_completion` can detect completion without relying on timeout.

#### Scenario: workers 正常结束
- **WHEN** workers exit their `_run_loop`
- **THEN** `_state` SHALL transition to STOPPED
- **AND** `wait_for_completion` SHALL return without timeout

### Requirement: RepositoryFileLock 须防 stale 误判与 unlink 竞态
The system SHALL NOT delete lock files based solely on mtime, and SHALL atomically release (close fd without unlinking a possibly-different lock file).

#### Scenario: 长耗时写
- **WHEN** a write operation exceeds `_LOCK_STALE_SECONDS`
- **THEN** other processes SHALL NOT seize the lock
- **AND** `__exit__` SHALL not unlink a lock file that may belong to another process

### Requirement: RecordSqliteIndex 须配置 WAL 与 busy_timeout
The system SHALL set `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout` on `RecordSqliteIndex` connections, consistent with `expression_sqlite_index`.

#### Scenario: 并发写
- **WHEN` multiple threads write to record_sqlite_index
- **THEN** writes SHALL not immediately throw `database is locked`

### Requirement: recoverable_backtest_candidates 须取最新记录
The system SHALL select the newest (max timestamp) record per slot for recovery, not the oldest.

#### Scenario: 崩溃恢复
- **WHEN** multiple active records exist for the same slot
- **THEN** the newest SHALL be used
- **AND NOT` the oldest (which would re-poll ended sims and overwrite latest metrics)

### Requirement: 非 429 poll 错误须有 halt 或 cooldown
The system SHALL trigger `official_calls_halted` or cooldown for non-429 poll errors (500/502/503), not infinitely retry and starve other candidates.

#### Scenario: BRAIN 持续 500
- **WHEN** poll returns 500 repeatedly
- **THEN** the slot SHALL enter cooldown or halt
- **AND** other submission_ready candidates SHALL not be starved

### Requirement: global_cooldown 须自动到期清除
The system SHALL auto-clear `_global_cooldown_until` when it expires, not require manual `resume()`.

#### Scenario: cooldown 到期
- **WHEN** `time.time() > _global_cooldown_until`
- **THEN** slots SHALL become available again automatically

### Requirement: _scheduler_tick 状态匹配须正确
The system SHALL match both `COMPLETE` and `COMPLETED` simulation statuses (not duplicate `COMPLETED`).

#### Scenario: COMPLETE 状态
- **WHEN** BRAIN returns status `COMPLETE`
- **THEN** the slot SHALL be released
- **AND NOT` be ignored due to a duplicate-string bug

### Requirement: ExpressionHistoryIndex.records 不得跨源尾部截断
The system SHALL NOT truncate merged cross-source records to the last `limit`, which discards early sources (candidates.jsonl, lifecycle.jsonl).

#### Scenario: 多源合并
- **WHEN` 6 source files each have ~5000 records
- **THEN** the index SHALL cover all sources (not just the last 5000)
- **OR` clearly report per-source coverage

### Requirement: _status_payload 须用数值排序时间戳
The system SHALL sort jobs by numeric `updated_at`, not `str(updated_at)` which breaks lexicographic ordering ("9.0" > "10.0").

#### Scenario: 查询最新 job
- **WHEN` `/api/jobs/status` returns the latest job
- **THEN` it SHALL be the one with max numeric `updated_at`

### Requirement: trends 写入须并发安全与校验
The system SHALL protect `record_trend` with a lock and SHALL go through `_validated_post_route`; `get_trends` SHALL tolerate non-numeric `ts` without crashing.

#### Scenario: 并发 trends 写入
- **WHEN` multiple panels refresh simultaneously
- **THEN` JSONL lines SHALL not interleave
- **AND` a string `ts` in history SHALL not crash `get_trends`

### Requirement: _read_json 须校验 Content-Length 并返回 4xx
The system SHALL validate `Content-Length >= 0` and return 400/413 (not 500) for malformed or oversized bodies.

#### Scenario: 负 Content-Length
- **WHEN` a request has `Content-Length: -1`
- **THEN` the server SHALL return 400
- **AND NOT` 500 with possible stack leak

### Requirement: JobStore update 须处理显式 None updated_at
The system SHALL treat `updated_at=None` as missing (set to `time.time()`), not leave it as None which causes watchdog to misjudge the job as 56-years-stale.

#### Scenario: 异常路径传 None
- **WHEN` a handler passes `updated_at=None`
- **THEN` `setdefault` SHALL still set it to now
- **AND` watchdog SHALL not immediately mark the job failed

### Requirement: JobStore 读操作不得有 watchdog 副作用
The system SHALL NOT trigger watchdog side-effects on pure read operations (`get`, `latest_active`); reads SHALL return the state at call time.

#### Scenario: 读取超时 job
- **WHEN` a read is performed on a job that has exceeded watchdog timeout
- **THEN` the read SHALL return current state without mutating it
- **AND` watchdog actions SHALL be explicit, not side-effects of reads

### Requirement: evaluate_release_score 须正确区分 settings 与 metrics
The system SHALL NOT use `metrics` as `settings` when `settings is None`; delay lookup SHALL use actual settings.

#### Scenario: settings 为 None
- **WHEN` `evaluate_release_score` is called without settings
- **THEN` delay SHALL default to a safe value (not be looked up in metrics)
- **AND` release gate delay-based checks SHALL be correct

### Requirement: 提交异常须走 redact_error_message
The system SHALL use `redact_error_message(exc)` for submit error `status_message`, not `str(exc)[:100]` which may leak Authorization/Cookie.

#### Scenario: 提交失败
- **WHEN` `_run_submit_alpha_job` catches an exception
- **THEN` `status_message` SHALL be redacted
- **AND` no credentials SHALL reach the frontend or audit log

### Requirement: fetch_official_thresholds 须用正确签名调用 _request
The system SHALL NOT pass a `timeout` kwarg to `_request` (which lacks that parameter); dynamic thresholds SHALL actually be fetched.

#### Scenario: 动态阈值拉取
- **WHEN` `fetch_official_thresholds` calls `_request`
- **THEN` the call SHALL succeed (no TypeError)
- **AND` dynamic thresholds SHALL be used when available

### Requirement: 浏览器 check_alpha 须解析真实 PASS/FAIL
The system SHALL parse real PASS/FAIL from the check page, not return `ok=True` with truncated `inner_text`.

#### Scenario: 检查失败
- **WHEN` the BRAIN check page shows a failed check
- **THEN` `check_alpha` SHALL return `ok=False`
- **AND` the failing check SHALL be in the result

### Requirement: A-Share 缓存损坏须自愈
The system SHALL delete a corrupted Parquet cache file and fall back to JSON (or re-fetch), not return None forever.

#### Scenario: Parquet 损坏
- **WHEN` Parquet read fails
- **THEN` the corrupted file SHALL be removed
- **AND` the next get SHALL fall back to JSON or re-fetch

### Requirement: Loader 须记录加载失败而非静默 return
The system SHALL log at ERROR level when `_load_fields/_load_operators/_load_datasets` fail, not silently return empty.

#### Scenario: 官方元数据损坏
- **WHEN` `official_fields.json` is corrupted
- **THEN` an ERROR log SHALL be emitted
- **AND` the pipeline SHALL fail fast (not silently reject all alphas)

## ADDED Requirements (第三轮：安全 / Agent / MCP / LLM / 架构)

### Requirement: Docker 容器不得以 root 运行
The system SHALL run the Docker container as a non-root user and SHALL NOT chmod 777 evidence directories.

#### Scenario: 容器启动
- **WHEN** the Docker container starts
- **THEN** the process SHALL run as a non-root user (e.g., `appuser`)
- **AND** evidence directories SHALL NOT be world-writable
- **AND** docker-compose SHALL bind to `127.0.0.1` only, with `cap_drop: [ALL]` and `no-new-privileges`

### Requirement: 证据归档须脱敏
The system SHALL redact credentials (Authorization headers, Cookies, tokens) from HAR files, screenshots metadata, network logs, and console logs before persisting to the evidence directory.

#### Scenario: 归档 browser session 证据
- **WHEN** `archive_session` copies screenshots / DOM / HAR / logs
- **THEN** HAR files SHALL have Authorization/Set-Cookie/Cookie headers redacted
- **AND** network_logs / console_logs SHALL be passed through `redact_text`
- **AND** evidence directory permissions SHALL be restricted (not 777)

### Requirement: REAL_SUBMIT 旁路须基于进程内可信判定
The system SHALL NOT trust the `PYTEST_CURRENT_TEST` environment variable as a test-environment signal for real-submit override, since it can be set externally.

#### Scenario: 生产环境设置 PYTEST_CURRENT_TEST
- **WHEN** `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` + `PYTEST_CURRENT_TEST=1` are all set in a production container
- **THEN** real submission SHALL remain disabled
- **AND** the override SHALL require a verifiable in-process pytest signal (e.g., `sys.modules` check) or be removed entirely

### Requirement: 生产 pipeline 须接入 execution_backend
The system SHALL integrate `execution_backend` into the production pipeline path, and SHALL NOT let `DEFAULT_BACKEND="browser"` be a dead default.

#### Scenario: 生产 pipeline 启动
- **WHEN** `runner.run_pipeline_from_config` or Web `_handle_pipeline_start` constructs `AlphaResearchPipeline`
- **THEN** it SHALL pass `execution_backend` (browser mode for production)
- **AND** `backend_registration.register_all_backends()` SHALL be invoked at startup
- **AND** `register_backend` SHALL detect duplicate registration

### Requirement: MCP stdio 不得被长轮询工具阻塞
The system SHALL NOT let a single long-running tool call block the entire MCP stdio server.

#### Scenario: 长轮询 simulation 调用
- **WHEN** a `run_simulation` call polls for up to 600s
- **THEN** other tool calls (e.g., `list_context`, `get_job_status`) SHALL still be servicable
- **AND** `notifications/cancelled` SHALL be consumable
- **OR** long-running tools SHALL be dispatched to a worker and return progress notifications

### Requirement: LLM 配额账本须实际生效
The system SHALL actually invoke the `LLMCallLedger` (record/wait_for_quota/budget_exhausted) so that the 200K token/run budget and rate limiting take effect.

#### Scenario: LLM 调用
- **WHEN** `_call_review_provider` or `_call_guidance_provider` calls the provider
- **THEN** token usage SHALL be recorded in the ledger
- **AND** the ledger SHALL be checked before the call (wait_for_quota)
- **AND** budget exhaustion SHALL halt further LLM calls

### Requirement: Browser 提交幂等键须持久化或不淘汰
The system SHALL NOT evict idempotency keys such that a real submission can be replayed.

#### Scenario: 长生命周期 adapter 或重启
- **WHEN** the adapter exceeds `_MAX_IDEMPOTENCY_KEYS=1000` OR restarts
- **THEN** idempotency keys SHALL persist to disk (or a larger store)
- **AND** a replayed submission SHALL be rejected
- **AND NOT** evict the oldest key allowing replay

### Requirement: Browser 登录判定须可靠
The system SHALL NOT use the generic `nav` selector as a login-success signal.

#### Scenario: 错误凭证
- **WHEN** login fails and the page stays on the login page
- **THEN** `is_logged_in` SHALL be False
- **AND** the check SHALL use login-page-specific negative signals (e.g., presence of password field, login error message)
- **AND NOT** count `nav` elements which exist on both login and dashboard pages

### Requirement: web_security allow_remote 须防 DNS rebinding
The system SHALL NOT trust the attacker-controlled `Host` header as the trust anchor when `allow_remote=True`.

#### Scenario: DNS rebinding attack
- **WHEN** `allow_remote=True` and an attacker sends `Host: evil.com` + `Origin: http://evil.com`
- **THEN** the request SHALL be rejected
- **AND** the trust anchor SHALL be a configured allowlist (not the Host header)

### Requirement: 日志脱敏须覆盖纯字母 token
The system SHALL redact tokens that do not contain digits, not only those matching `\d`.

#### Scenario: 纯字母 token
- **WHEN** a log line contains `token-abc-def-xyz` or `session-cookie-abcd`
- **THEN** the redaction filter SHALL redact it
- **AND NOT** require a digit in the secret fragment

### Requirement: CI 须真正检查依赖 CVE
The system SHALL NOT use `continue-on-error` for npm critical CVE audit and SHALL add `pip-audit` for Python dependencies.

#### Scenario: npm critical CVE
- **WHEN** `npm audit --audit-level=critical` finds a critical CVE
- **THEN** the CI gate SHALL fail
- **AND NOT` continue-on-error`
- **AND** Python dependencies SHALL be scanned by `pip-audit`

### Requirement: strategy profile_id 须包含 delay
The system SHALL include `delay` in the strategy profile_id hash to avoid collisions between same-name profiles with different delays.

#### Scenario: 同名不同 delay 的 profile
- **WHEN** two profiles share index/name/region/universe/neutralization but differ in delay
- **THEN** their profile_ids SHALL be distinct
- **AND** rewards/lineage/retired SHALL NOT cross-contaminate

### Requirement: 参数审计须覆盖 official_api 全部参数
The system SHALL include all `official_api` config parameters (cache_dir, context_cache_ttl_seconds, timeout_seconds, rate_limit_retry_attempts, etc.) in the parameter audit trace.

#### Scenario: timeout_seconds 被篡改
- **WHEN** `timeout_seconds` deviates from canonical
- **THEN** the audit SHALL produce a finding
- **AND** `api_paths_aligned` SHALL be False

### Requirement: lifecycle_records 须有上限
The system SHALL cap `lifecycle_records` growth (like `backtest_records` is capped at 200) to prevent OOM in `run_forever` mode.

#### Scenario: 长跑流水线
- **WHEN** `run_forever` mode runs for an extended period
- **THEN** `lifecycle_records` SHALL be capped (e.g., last 500)
- **AND** dedup window SHALL scale accordingly

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
