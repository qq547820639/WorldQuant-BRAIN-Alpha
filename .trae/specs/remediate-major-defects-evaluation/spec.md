# 重大缺陷修复与体验改进 Spec

## Why

在完整阅读 brain_alpha_ops 全量源码后，识别出 **38 项实质性重大问题**，覆盖三大维度：

- **功能缺陷**：12 项（3 Critical / 6 High / 3 Medium）— 含状态机不变量被绕过、真实提交后审计失败导致重复提交、Web 控制台整体不可用的静默失败等
- **用户体验**：13 项（2 Critical / 6 High / 5 Medium）— 含 Web 端永久无法真实提交却强制走完整 HIL、SSE 断连后误取消但云端任务仍在运行、错误引导仅覆盖 4/11 类等
- **WebUI**：13 项（3 Critical / 5 High / 5 Medium）— 含阻断阶段按钮仍可点、默认 inline HTML 不存在导致首屏空白、路由不进 URL 等

这些问题已对生产稳定性、账户安全（重复提交风险）、用户信任（终点被阻断无前置提示）和可用性（首屏空白、刷新循环）造成实质性影响。本规格聚焦修复 Critical 与 High 级问题，并给出 Medium 级的改进方向。

## What Changes

### Critical 修复（8 项，必做）
- 修复 `_install_facade_bindings` 静默吞异常导致 `JOB_REGISTRY=None` 后整站 AttributeError，改为安装失败 fail-fast 暴露根因
- 修复真实提交成功后审计写入失败冒泡为 400 → 用户误重试 → 重复提交：审计写入与提交响应解耦，提交成功后审计失败仅记录告警不阻断响应
- **BREAKING**：移除 `candidate_lifecycle.transition()` 中非法转换回退 `force_transition` 的生产路径，生产环境非法转换必须抛 `IllegalTransitionError`，仅测试用例显式 opt-in `force=True`
- 修复 PhaseShell 阻断阶段仅视觉淡化（opacity/grayscale）但按钮仍可点击：阻断/未就绪阶段对关键操作区加 `inert` 或 `pointer-events:none`
- 修复默认 `inline` 前端模板文件不存在导致未构建 React 时首屏仅显示 `<h1>Template not found</h1>`：fallback 链修正为 `react_app/dist` → 内置引导 HTML（含诊断信息），并修正 `safe_selected_frontend` 默认回退
- 修复路由仅注册 `/` 导致面板切换不进 URL、刷新丢视图、后退退出站点：核心面板接入路由（`/dashboard` `/candidates` `/backtest` `/scoring` `/quality` `/submission` `/config` `/history`）
- 修复 Web 端 `REAL_SUBMIT_DISABLED_WEB_FLOW` 永久 True 却让用户走完整 HIL 才在终点 403：在提交流程入口（候选进入提交队列前）显式提示「Web 端不可真实提交，需跳转 BRAIN 平台」，提供外链，避免用户投入时间后发现无法闭环
- 修复 SSE 断连 5 分钟后前端自动取消任务跟踪但 BRAIN 云端回测仍在运行导致槽位重复占用：断连取消时必须给出「云端可能仍在运行，请先去 BRAIN 平台确认」的明确提示与槽位查询入口

### High 修复（15 项，应做）
- 后端：StallMonitor 超限后静默放弃 → 超限必须 `_on_interrupt` 中断作业并升级告警
- 后端：BRAIN 认证仅 basic 单方法、401 无刷新重试 → 增加 token 刷新与备选认证回退
- 后端：`concurrent_simulate`/`concurrent_check` 超时 `future.cancel()` 无法中断线程 → 改用可中断执行或显式标记槽位释放
- 后端：并行回测 `future.result()` 无 timeout → 加批次级超时熔断，单作业卡死不阻塞全批
- 后端：心跳线程异常退出不重启 → 加入有限次重启，避免长作业失联被 watchdog 误判
- 后端：WebSocket publish 不清理死亡订阅者 → 失败 sender 移出 `_subscribers`，防止延迟累积
- WebUI：`useCandidateTableData` 中 `loadCandidates` deps 含 `globalCandidatesData` 形成刷新循环 → 拆分依赖或用 ref 锁
- WebUI：`OfficialBacktestSlots` 每 5s 全量 `refreshAll` → 改为仅轮询 `/api/backtest_slots`
- WebUI：JobMonitor SSE 随 Dashboard 卸载断连 → SSE 连接提升到 App 层（context/provider）独立于视图生命周期
- WebUI：所有 Modal 无焦点陷阱，已有 FocusTrap 组件却无人使用 → ConfirmDialog / KeyboardShortcutsHelp / 提交确认等接入 FocusTrap
- WebUI：双重 Toast 系统（ToastProvider 死代码 + 真实 Toast 走 useBaseState）→ 移除死代码 ToastProvider，统一到单一实现
- UX：批量提交无 dry-run 预览、无撤销、无原子性 → 批量提交前显示候选清单预览，部分失败时给出已提交/未提交明细
- UX：配置保存仅提示「已保存」无「需重启生效」说明 → 涉及 Final 常量的配置项保存后明确提示生效条件
- UX：限流倒计时固定 30s 不读后端 `retry_after` → 前端读取并展示后端返回的精确 retry_after
- UX：任务完成通知仅在 `document.hidden` 时发送，前台无任何提示 → 前台完成时补充 toast/徽标提示

### Medium 改进方向（15 项，记录为后续）
- 后端：生命周期审计写入异常被 debug 级静默吞 → 提升日志级别并加指标
- 后端：LocalBacktestEngine LRU 实为 FIFO → 命中时移到末尾
- 后端：phase stalled 判定硬编码 10s 阈值 → 可配置
- UX：首次启动无引导、launch_web.py 无端口/URL 输出
- UX：首次 8599 字段下载无总体 ETA
- UX：历史文件 >10MB 静默跳过加载无提示
- UX：JobStore 持久化 >50MB 跳过加载、中断任务无法续跑
- UX：watchdog 失败消息英文外泄、仅 scan 阶段检测停滞
- UX：live_submit_readiness 累计 15+ 英文 reasons 无中文映射
- WebUI：ErrorBoundary 返回首页用 hash 与 BrowserRouter 冲突
- WebUI：移动端 statusbar 被 mobile-tab-bar 遮挡
- WebUI：候选导出下拉无 click-outside 关闭
- WebUI：GlobalData 30s 轮询不看 visibility
- WebUI：`renderActiveViewFromContext` 在 render 期调 hook
- UX：错误引导仅覆盖 4 类连接错误，其余 7+ 类业务错误无恢复入口

## Impact

- **Affected specs**：`overhaul-alpha-production-quality`、`complete-brain-alpha-ops`、`upgrade-to-public-product`、`improve-frontend-ux`
- **Affected code**：
  - `brain_alpha_ops/web/__init__.py`、`brain_alpha_ops/web/ws.py`、`brain_alpha_ops/web/handlers/phase.py`
  - `brain_alpha_ops/web/submissions/web_submission_single.py`、`web_submission_batch.py`
  - `brain_alpha_ops/candidate_lifecycle.py`
  - `brain_alpha_ops/brain_api/official_auth.py`、`official_simulation/_mixin.py`
  - `brain_alpha_ops/research/parallel_backtest/_executor.py`、`research/local_backtest/engine.py`
  - `brain_alpha_ops/stall_monitor.py`、`brain_alpha_ops/web/business/web_run_job.py`、`web_job_registry.py`
  - `brain_alpha_ops/web/misc/web_html.py`、`web_rate_limit.py`
  - `brain_alpha_ops/runtime_constants.py`
  - `brain_alpha_ops/web/react_app/src/main.tsx`、`App.tsx`、`components/PhaseShell.tsx`、`components/views/renderView.tsx`
  - `brain_alpha_ops/web/react_app/src/hooks/useCandidateTableData.ts`、`useGlobalData.ts`、`useJobMonitor/`、`useJobWatchdog.ts`、`useSSE.ts`、`useJobDisconnectedState.ts`、`useConfigForm.ts`
  - `brain_alpha_ops/web/react_app/src/components/Toast.tsx`、`ConfirmDialog.tsx`、`KeyboardShortcutsHelp.tsx`、`OfficialBacktestSlots.tsx`、`SubmissionConfirmPanel.tsx`、`ErrorBoundary.tsx`
  - `brain_alpha_ops/web/react_app/src/helpers/connectionErrorGuide.ts`
  - `brain_alpha_ops/ux/history.py`、`brain_alpha_ops/i18n/messages.py`
  - `brain_alpha_ops/tasks/_store.py`、`_watchdog.py`、`_constants.py`
  - `brain_alpha_ops/live_submit_readiness_assessment.py`、`error_catalog.py`、`error_payloads.py`
  - `launch_web.py`

## ADDED Requirements

### Requirement: Facade 绑定安装失败必须 fail-fast
The system SHALL surface facade binding installation failures with root cause instead of silently degrading to `JOB_REGISTRY=None` and later `AttributeError`.

#### Scenario: 绑定安装异常
- **WHEN** `_install_facade_bindings()` 抛出任意异常
- **THEN** 异常向上传播导致服务启动失败，日志记录原始异常堆栈
- **AND NOT** 模块级 `JOB_REGISTRY` 保持 `None` 后在请求期才暴露无关 `AttributeError`

### Requirement: 真实提交成功后审计失败不得阻断响应
The system SHALL decouple lifecycle audit writing from the submit response so that a successful BRAIN submission is never reported as failure due to audit write failure.

#### Scenario: 提交成功但审计写失败
- **WHEN** `api.submit_alpha()` 已成功返回 result
- **AND** 后续 `save_lifecycle_record()` 抛出异常
- **THEN** 响应仍返回提交成功
- **AND** 审计失败记录到 ERROR 级日志与监控指标
- **AND NOT** 异常冒泡为 400 响应导致用户误重试

### Requirement: 候选生命周期非法转换必须显式失败
The system SHALL raise `IllegalTransitionError` on illegal lifecycle transitions in production paths, and SHALL NOT silently fall back to `force_transition`.

#### Scenario: 生产路径非法转换
- **WHEN** 生产代码调用 `transition(target)` 且 `lc.transition(target)` 返回 `False`
- **THEN** 抛出 `IllegalTransitionError` 包含当前状态与目标状态
- **AND** 仅当调用方显式传 `force=True` 时才允许 `force_transition`（仅测试用例）

### Requirement: 阻断阶段必须禁用关键交互
The system SHALL prevent user interaction with action controls in blocked / not-ready phases, not merely visually fade them.

#### Scenario: 阶段未就绪或已阻断
- **WHEN** `statusTone` 为 `pending` 或 `blocked`
- **THEN** 关键操作区应用 `inert` 属性或 `pointer-events: none`
- **AND** 可聚焦元素不可被 Tab 到达
- **AND NOT** 仅靠 `opacity` / `filter` 视觉淡化而按钮仍可点击

### Requirement: 默认前端首屏必须有可用引导
The system SHALL provide a usable first screen even when the React build is absent, instead of showing only `<h1>Template not found</h1>`.

#### Scenario: React 未构建且 inline 模板缺失
- **WHEN** `react_app/dist/index.html` 不存在
- **AND** inline 模板不存在
- **THEN** 返回内置引导 HTML，包含：当前 frontend 选取结果、缺失原因、修复指引（如何 `npm run build`）、后端端口信息
- **AND NOT** 返回空白英文 `Template not found`

### Requirement: 核心面板切换必须反映到 URL
The system SHALL synchronize active panel with the URL so that refresh, back/forward, and sharing work as expected.

#### Scenario: 切换面板后刷新
- **WHEN** 用户从 Dashboard 切换到 Scoring 面板
- **THEN** URL 变为 `/scoring`
- **AND** 刷新页面后仍停留在 Scoring 面板
- **AND** 浏览器后退可回到 Dashboard

### Requirement: Web 端不可真实提交须前置提示
The system SHALL inform the user before they invest time in the full HIL flow that Web-side real submission is permanently disabled, and provide a clear path to the BRAIN platform.

#### Scenario: 候选进入提交队列
- **WHEN** 候选首次进入提交队列或用户打开提交面板
- **THEN** 明确展示「Web 端不可真实提交，最终提交需在 BRAIN 平台完成」
- **AND** 提供 BRAIN 平台外链
- **AND NOT** 让用户走完硬门禁 + confirm + observability 后才在终点收到 403

### Requirement: SSE 断连取消须警示云端可能仍在运行
The system SHALL warn the user that cloud-side backtests may still be running before auto-cancelling local task tracking on SSE disconnect.

#### Scenario: SSE 断连超时自动取消
- **WHEN** SSE 断连超过重连上限触发本地任务取消
- **THEN** 展示明确警示「BRAIN 云端回测可能仍在运行，请先到 BRAIN 平台确认槽位」
- **AND** 提供槽位查询入口
- **AND NOT** 静默取消让用户误以为可安全重启

### Requirement: 阻断阶段按钮、Modal 焦点陷阱、单一 Toast 系统
（由上述 Critical/High 修复覆盖，详见 tasks.md）

### Requirement: 批量提交须提供预览与部分失败明细
The system SHALL present a dry-run preview of candidates to be submitted and SHALL report per-candidate submitted/failed breakdown after batch submission.

#### Scenario: 批量提交部分失败
- **WHEN** 批量提交中部分候选成功部分失败
- **THEN** 响应包含 `submitted` 与 `failed` 两个明细列表
- **AND** 前端展示每个候选的提交结果
- **AND NOT** 仅返回累计 `submitted_set` 让用户反推

### Requirement: 配置生效条件须明确告知
The system SHALL inform the user when a saved config requires a process restart to take effect.

#### Scenario: 修改涉及 Final 常量的配置
- **WHEN** 用户保存涉及 `runtime_constants` 中 Final 常量的配置项
- **THEN** 保存成功提示包含「需重启服务生效」
- **AND** 标注受影响的具体配置项

### Requirement: 限流倒计时须读取后端 retry_after
The system SHALL display the backend-provided `retry_after` value in the rate-limit countdown, not a hardcoded 30s.

#### Scenario: 触发限流
- **WHEN** 后端返回 `rate_limit` 错误携带 `retry_after`
- **THEN** 前端倒计时使用该 `retry_after` 值
- **AND NOT** 固定 30s

### Requirement: 前台任务完成须有可见提示
The system SHALL notify the user of long-running task completion even when the page is in the foreground.

#### Scenario: 前台运行时长任务完成
- **WHEN** 长耗时回测/同步任务在前台完成
- **THEN** 显示 toast 或徽标提示
- **AND NOT** 仅在 `document.hidden` 时通知

## MODIFIED Requirements

### Requirement: StallMonitor 超限处理
**Modified**: 超过 `max_retry_count` 后必须调用 `_on_interrupt` 中断作业并升级告警，而非静默 `return`。

### Requirement: BRAIN 认证容错
**Modified**: `authenticate()` 遇 401 须尝试 token 刷新与备选认证方法，并在指数退避后重试，而非单 basic 方法直接终止。

### Requirement: 并发模拟/检查超时处理
**Modified**: `concurrent_simulate`/`concurrent_check` 超时后须显式释放槽位并标记作业可中断，而非依赖无效的 `future.cancel()`。

### Requirement: 并行回测批次超时
**Modified**: `ParallelBacktestExecutor.execute` 须对 `as_completed` 与 `future.result()` 设置批次级 timeout，单作业卡死不阻塞全批。

### Requirement: 心跳线程容错
**Modified**: `_heartbeat_loop` 异常退出前须有限次重启，避免长作业因一次瞬时异常永久失联。

### Requirement: WebSocket 死连接清理
**Modified**: `publish` 失败的 sender 须从 `_subscribers` 移除，防止延迟累积。

### Requirement: 候选表数据加载
**Modified**: `useCandidateTableData` 须消除 `loadCandidates` 对 `globalCandidatesData` 的依赖循环。

### Requirement: 回测槽位轮询
**Modified**: `OfficialBacktestSlots` 须仅轮询 `/api/backtest_slots`，不得每 5s 全量 `refreshAll`。

### Requirement: 任务 SSE 生命周期
**Modified**: 任务 SSE 连接须独立于 Dashboard 视图生命周期，提升到 App 层 context。

### Requirement: Modal 焦点陷阱
**Modified**: 所有 Modal 须接入 `FocusTrap` 组件实现焦点隔离。

### Requirement: Toast 系统统一
**Modified**: 移除死代码 `ToastProvider`，统一到 `useBaseState` 的 Toast 实现。

## REMOVED Requirements

### Requirement: 候选生命周期非法转换静默回退
**Reason**: 生产路径中 `transition()` 非法转换回退 `force_transition` 破坏状态机不变量，使合规审计、HIL 闸门、提交就绪检查失效。
**Migration**: 生产调用方须处理 `IllegalTransitionError`；仅测试用例显式传 `force=True` 调用 `force_transition`。
