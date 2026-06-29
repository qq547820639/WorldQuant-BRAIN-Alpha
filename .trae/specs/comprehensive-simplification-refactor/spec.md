# 全面重构与简化 Spec

## Why

本项目（BRAIN Alpha Ops）经过 14 个阶段的"深挖优化"后，文件行数已全面合规（≤350 行/Python、≤400 行/前端），但**架构层面仍存在严重臃肿与失真**。

**调研方法**：2026-06-30 启动 10 个并行子智能体，**穷举遍历全部 1,310 文件 / 219,909 行代码**（766 Python + 296 前端 + 248 测试）。覆盖完整无盲区，以下发现均基于当前磁盘代码真实状态。

### 一、架构冗余

**Python 后端死代码与双轨系统**：
- `_web_bridge.py` meta-path finder 维持 60 条别名映射（load-bearing，需先迁移再删）
- `web/_reexports.py:60-61` 的 `_routes_dispatch_get` / `_routes_dispatch_post` 纯死 import（全仓 0 引用）
- `web/dispatch/get_routes/_dispatch.py` 的 `dispatch_get` / `dispatch_post` 函数是 dead code（保留其他 helpers）
- `web_candidates.payloads.py`（点号扁平名，40 行重复 import 20 次，0 引用）—— 代码生成器 bug 残留
- `_runtime_constants_helpers.py`（自承 deprecated，仅 1 处引用）
- 6 个真正孤立模块：`research/official_call_guard.py` / `research/pipeline_services.py` / `research/pipeline_snapshots.py` / `research/pipeline_strategy.py` / `execution_factory.py` / `web/dispatch/get_routes/_dispatch.py`
- 2 个传递性孤立模块：`research/official_workflow.py` / `research/secondary_fusion.py`
- **整包死代码 `decoupled_pipeline/`**（5 文件 0 生产引用，OptimizationWorker 空转、wait_for_completion 死等）
- **双轨并存 ×2**（Critical）：
  - `candidate_pool_service_` vs `pipeline_candidates` —— P0-5 修复仅落 mixin 轨道，service 轨道（生产路径）未同步 `previous_official_metrics`
  - `backtest_flow_service` vs `pipeline_backtest_flow` —— P1-1 修复未同步
- `expression_sqlite_index/_helpers.py` 整文件复制 `expression_index`
- `tasks/_store.py` 持久化永久失效（F-023）
- `auto_calibrator/_weight_calibration.py` 失效 import（`calibrate_weights.py` 不存在）

**前端死代码（穷举确认）**：
- 整目录死代码：`src/components/A11y/`（0 引用）、`VirtualList/`（0 引用）、`LazyImage/`（0 引用）、`StateCards/`（6 文件 0 外部引用）、`CandidateTable/`（仅本地互引）
- 整文件死代码：`Toast.tsx`（ToastProvider 空转 + useToast 从未被调用）、`LoadingProgress.tsx`（含同名 ProgressFeedback 三轨并存）、`SubmissionPanel.tsx`（自述退役）
- 7 个全文件死代码 hook/util：`useMemoCompare.ts` / `useThrottle.ts` / `useNetworkError.ts` / `useOperationState.ts` / `useLoadingState.ts` / `errorHandler.ts` / `debounce.ts`
- 双轨系统：Toast（`Toast.tsx` vs `ToastContainer.tsx` 接口不兼容）、ScoreHistory、useJobMonitor vs useJobStatusHook
- 6 组 thin re-export facade 对 + 3 组 wrapper 实现
- 2 套并存的 PyInstaller 打包入口（`build_prod.py` + `BrainAlphaOps.spec`）
- 9 份根目录历史 .md 评分离散且互相矛盾（7.0 / 8.0 / 8.5 / 不合格）

### 二、核心功能缺失/失效

**反过拟合链路**：
- F-001/F-002（Critical）：`AntiOverfitService.evaluate` fallback 链仍把 `ic_series` 当 returns 回退填充；`_rank_ic` 仍返回单元素列表致 `ic_std` 恒为 0，反过拟合第一层 IC Stability 完全失效
- `empirical_score` 排除 hard_gate 分值后满分仅 51 分，`status≥70` 的 "ready" 不可达（**新发现 Critical**）
- `evolution/_meta` 新后代因 `scores=0` 被剪枝无法存活（**新发现 Critical**，演化探索失效）
- `hypothesis_library/library.py` `adjust_weight` 写入 `_hypothesis_weights` 但从不被读取（**新发现 Critical**，假设反馈链路断裂）

**提交流与并发**：
- F-031/F-032（High）：`runner.run_pipeline_from_config` 仍未注入 `execution_backend`；`execution_factory.py` 已孤立
- F-041（High）：`BrainAPIBridge.concurrent_simulate / concurrent_check` 仍是串行 for 循环
- F-012（High）：`check_prod_correlation` API 失败时仍返回 warning（fail-open）
- F-011（High）：`browser/execution_adapter` 幂等键 FIFO 淘汰

**评分与校准**：
- `official_helpers/_normalize._ratio` 2.0 处不连续（**新发现 High**）
- `scoring/official_scoring/_history` 无锁变异（**新发现 High**）
- `official_context/_composite` `fetch_official_thresholds` / `merge_dynamic_thresholds` 死代码（W-08 从未接入，**新发现 High**）
- F-008（High）：`rolling_validation.decay_ratio` 符号翻转，改善型候选被错误判定失败
- `convergence/_bootstrap_mixin.py` 空列表除零（**新发现 Critical**）

**调度与执行器**：
- F-018/F-019/F-023/F-024：AdaptiveExecutor shutdown 后重建池、TimeoutError 语义冲突、JobStore 持久化永久失效、StallMonitor 不真正中断 future
- `simulation_scheduler/_scheduler.py` event_callback 双 lambda 默认值（**新发现 Critical**）
- `simulation_scheduler/_types.py` reset 不重置 error_count
- `presets.py:86` 错误 capability kind

**Web 层 fail-open 泛滥（新发现 Critical×5）**：
- `_install_facade_bindings` fail-open 半残启动（F-034，影响面比原报告更严重）
- `_async_jobs_helpers` + `_batch_helpers` 两处 `_store_is_cancelled` fail-open
- `web_security.py` Host 空绕过
- `web_submission_single` kill-switch 永久 True
- `_api_mixin` 429 限流不 return
- `_backtest_recovery_mixin` fail-open
- `_local_prefilter` 评分失败断链
- `official_auth` F-012 fail-open

**Web 层 High 18 处**：`_web_bridge` 60 条别名债务、`post_routes/submit` 硬编码 403、`web_get_routes/_routes_simulation` 导入失败 500、`web_assistant_snapshots/_profile` 空 glob、`web_facade_bindings/_builder` 重叠、`web_runtime_facade/_server` stub、`web_jobs` ASYNC_JOBS OOM、`_handlers_misc` 截断 token、`_handlers_alpha` record_trend 无锁、`_handlers_simulation` 批量信息丢失、`web_check_availability` 12 类检查未隔离、`web_config` run_config_from_payload TypeError、`web_submission_batch` 逐候选重复错误、`web_submission_safety/_observability` 降级未标记、`web_security` validate_replay 时间戳 skew、`web_runtime_state` lifecycle_from_job limit=0、`handlers/phase.py` NameError、`api/trends.ts` 字符串比较 TypeError

### 三、WebUI/UX 阻断级痛点

- W-001：`PhaseShell` 阻断态未设 `pointer-events:none`，按钮仍可点
- W-002：`ErrorBoundary.handleGoHome` 仍 `window.location.hash = ''`，与 BrowserRouter 脱节
- W-004：`main.tsx` 仅 `/` + `*`，路由不进 URL
- W-007：`renderActiveViewFromContext` 非组件却在 render 期调 hook（eslint-disable 压告警）
- W-010：Toast 系统**三套并存**，`Toast.tsx` ToastProvider 空转死代码
- W-011：`index.html` 第 13 行 `<div id="root"></div>` 空白，首屏白屏
- W-013：`StateCardItem` 引用**已失效的 `brand-*` 类名**（4 文件 10 处，hover/focus 完全不生效）
- U-001：SSE 断连误取消（探活失败时仍自动取消）
- U-009：`useGlobalData` 轮询不看 `document.visibilityState`
- 新发现：`useJobDisconnectedState` 误取消、`useGlobalData` visibilitychange 全仓 0 引用、`useJobLifecycle` vs `useJobControl` credentials 处理不一致、`useSSE` vs `useSseRetryState` 重试策略不一致

### 四、UI 视觉现状

- 设计令牌系统**已存在且采用率高**（`theme-tokens.css` 完整 + `tailwind.config.js` oklch 体系，362 处 `var(--` 引用）
- 但仍有 4 处硬编码 hex 颜色 + 251 处硬编码 px 间距/字号
- 暗色主题完整但 StateCardItem 等组件未适配
- 路由级 code splitting 已实现（7 lazy + Suspense），但首屏空白仍存在

### 五、测试死代码与盲区（新发现）

**Critical 死测试/盲区 9 处**：
- `test_review_gap_closure_tracker.py` 整文件重复（1056 行 ×2）
- 4 个 qa_*.py 永久 skip（~3200 行）：`qa_e2e_new_user_walkthrough.py` / `qa_full_chain_backend.py` / `qa_full_chain_frontend.py` / `qa_hypothesis_system.py`
- `test_input_validation.py:44-60` 两个死测试（无断言）
- `test_local_quality.py:48-49` test_nesting_depth 仅断言 >=0
- `test_dataset_id_missing.py` CapabilityResolutionError fall through
- `test_infrastructure_modules.py` AdaptiveExecutor shutdown 重建盲区

**测试亮点**：安全契约验证极其完整（REAL_SUBMIT_DISABLED kill switch、AF-021 fail-closed、session credentials 注入路由、凭证 redaction）

---

用户明确要求：**在降低复杂度的同时，保证核心功能的稳定性和整体用户体验的提升**。本次重构是"瘦身 + 补全 + 优化 + 修复"四位一体的系统性重构，目标是将项目从"可运行但未达生产就绪"推进到"架构精简、功能完整、体验流畅、视觉统一"的可交付状态。

## What Changes

### 阶段一：架构瘦身（Architectural Simplification）

**1.1 删除死代码与孤立模块**：
- 删除 `web_candidates.payloads.py`（点号扁平名，损坏文件）
- 删除 `_runtime_constants_helpers.py`（自承 deprecated）
- 删除 6 个真正孤立模块：`research/official_call_guard.py` / `pipeline_services.py` / `pipeline_snapshots.py` / `pipeline_strategy.py` / `execution_factory.py`（待 Task 2.2 决策）/ `web/dispatch/get_routes/_dispatch.py`
- 删除 2 个传递性孤立模块：`research/official_workflow.py` / `secondary_fusion.py`
- **删除整包死代码 `decoupled_pipeline/`（5 文件 0 生产引用）**
- 删除 `expression_sqlite_index/_helpers.py`（整文件复制 expression_index，合并回 expression_index）
- 删除 `web/_reexports.py:60-61` 的死 import
- 删除 `web/dispatch/get_routes/_dispatch.py` 中的 `dispatch_get` / `dispatch_post` 函数
- 删除 `src/components/CandidateTable/` 整个子目录（4 文件死代码）
- **删除前端整目录死代码**：`A11y/` / `VirtualList/` / `LazyImage/` / `StateCards/`（6 文件）
- **删除前端整文件死代码**：`Toast.tsx`（ToastProvider 空转）/ `LoadingProgress.tsx` / `SubmissionPanel.tsx`（自述退役）
- **删除 7 个全文件死代码 hook/util**：`useMemoCompare.ts` / `useThrottle.ts` / `useNetworkError.ts` / `useOperationState.ts` / `useLoadingState.ts` / `errorHandler.ts` / `debounce.ts`
- 同步更新测试字面量引用

**1.2 拆除双调度残留**：
- 迁移约 30 处旧扁平名 import（`web_routes` / `web_handler_dispatch` / `web_post_handlers` / `web_get_handlers`）到 `web.dispatch.*` 新路径
- 重点迁移：`_imports_b.py`（3+ 处）、`web_handler_candidate_routes.py`（3 处）、`_routes_alpha.py`（2 处）、`sync.py`（1 处）
- 测试文件中约 18 处旧扁平名 import 同步迁移
- 原扁平名路径保留 re-export + `DeprecationWarning`（过渡期 1 版本）
- 迁移完成后删除 `_web_bridge.py` + 移除 `install_web_bridge()` 调用

**1.3 统一 React facade 模式**：
- 6 组 thin re-export facade 对统一为"仅目录 + index.ts re-export"形式（`useJobMonitor` / `useAppState` / `runPayload` / `CandidateTableUtils` / `CandidateTableSubComponents` / `ScoringPanel`）
- 3 组 wrapper 实现保持现状（`ScoreBreakdown` / `ProgressFeedback` / `ConfigPanel`）

**1.4 合并顶层 helper 拆分文件**：
- `_config_domain_helpers.py`（70 行）→ `config_domain_validation.py`
- `_config_schema_helpers.py`（112 行）→ `config_schema.py`
- `_types_extras.py`（42 行）→ `types.py`

**1.5 统一 PyInstaller 入口**：
- 保留 `BrainAlphaOps.spec` 作为单一打包入口
- `build_prod.py` 改造为薄 wrapper 或删除
- 验证 hiddenimports 列表与当前模块结构一致

**1.6 归档历史文档**：
- 创建 `docs/history/` 目录
- 移动 9 份根目录历史 .md 到 `docs/history/`
- `README.md` 末尾添加"历史审计报告索引"链接

**1.7 清理 ToastProvider 空转死代码**：
- 删除 `Toast.tsx` 的 `ToastProvider` 包装（App 不再挂载）
- 统一使用 `ToastContainer.tsx` + AppStateContext 的 `notify`/`toasts`

**1.8 清理失效 `brand-*` 类名**：
- 4 文件 10 处 `brand-200/50/500/700/800` 替换为 `accent-*` 或设计令牌

**1.9 修复双轨并存 Critical（新发现）**：
- `candidate_pool_service_` 同步 P0-5 修复（保留 `previous_official_metrics`）
- `backtest_flow_service` 同步 P1-1 修复
- 长期目标：评估能否合并 service 与 mixin 双轨为单一轨道

### 阶段二：核心功能补全（Core Feature Completion）

**2.1 修复反过拟合虚假 PASS（F-001/F-002 Critical）**：
- `scoring/anti_overfit/service.py:30-56`：fallback 链严格区分 returns/IC 语义，缺失时返回 `insufficient_data`（fail-closed）
- `scoring/anti_overfit/utils.py:63-69`：`_rank_ic` 按时间窗口分段计算多元素 IC 列表

**2.2 打通真实浏览器提交流（F-031/F-032）**：
- `runner.py:21-27`：根据 `run_config.execution_mode` 注入 `BrowserExecutionAdapter` / `ApiExecutionAdapter`
- 接入 `execution_factory.py` 到 `runner.py`（已实现 browser/api 切换逻辑），playwright 未装时 `logger.warning` + 显式传 `RunConfig`

**2.3 修复并发参数与提交门禁（F-041/F-012/F-011）**：
- `brain_api_bridge.py:84-118`：`concurrent_simulate` / `concurrent_check` 用 `ThreadPoolExecutor` + `_bounded_concurrency` 真并发
- `official_simulation/_mixin.py:299-327`：`check_prod_correlation` 失败时 `raise`（fail-closed）
- `browser/execution_adapter.py`：幂等键改 LRU 淘汰而非 FIFO

**2.4 修复 rolling_validation decay_ratio（F-008）**：
- `rolling_validation.py:36-41`：首末窗口符号不同时视为"方向反转"单独处理

**2.5 修复 _launch_monitor（F-013/F-014/F-015）**：
- `SAFE_CHILD_ENV_KEYS` 改为黑名单（保留 `BRAIN_*` + `BRAIN_ALPHA_OPS_*`）
- `for line in proc.stdout` 改为 `select.select` + 周期性 `proc.poll()` + 超时 `proc.kill()`
- `DONE` 关键字改为结构化结束标记；`failed|error` 排除集合扩展

**2.6 修复 fetch_official_context（F-016/F-017）**：
- SIGALRM 替换为 `ThreadPoolExecutor + future.result(timeout=...)`
- `Retry-After` 用 `email.utils.parsedate_to_datetime` 解析 HTTP-date

**2.7 修复 AdaptiveExecutor 与 TimeoutError（F-018/F-019）**：
- 增加 `_closed` 标记，`shutdown()` 后 `submit()` 抛 `RuntimeError`
- 业务超时与执行器超时用 `exc.__cause__` 或独立异常类区分
- 修正 `task_executor.py:76-78` Python 3.11+ 事实错误注释

**2.8 修复 StallMonitor 与 JobStore（F-024/F-023）**：
- `TaskExecutor` 维护 `job_id -> future` 映射，`_auto_interrupt` 时 `future.cancel()`
- `tasks/_store.py` 每次启动重新尝试加载，不永久置位 `persistence_load_skipped`

**2.9 修复 Facade 绑定与 fail-open 泛滥（F-034 + 新发现）**：
- `_install_facade_bindings()` 拆分为多个独立 try/except，关键绑定缺失时 `serve()` 抛硬错
- `_async_jobs_helpers` + `_batch_helpers` 两处 `_store_is_cancelled` 改 fail-closed
- `web_security.py` Host 空时拒绝
- `web_submission_single` kill-switch 接真实配置
- `_api_mixin` 429 限流加 `return`
- `_backtest_recovery_mixin` 改 fail-closed
- `_local_prefilter` 评分失败断链修复
- `official_auth` F-012 改 fail-closed

**2.10 修复假设反馈链路与演化探索（新发现 Critical）**：
- `hypothesis_library/library.py`：让 `adjust_weight` 写入的 `_hypothesis_weights` 被 `generate` 路径实际读取
- `evolution/_meta`：新后代 `scores=0` 时给予初始存活窗口，不被立即剪枝
- `convergence/_bootstrap_mixin.py`：空列表除零保护

**2.11 修复 empirical_score 分值架构（新发现 Critical）**：
- `empirical_score` 排除 hard_gate 分值后满分仅 51 分，`status≥70` 的 "ready" 不可达
- 重新校准分值权重，使满分 ≥ 100，"ready" 阈值可达

**2.12 修复 simulation_scheduler 双 lambda（新发现 Critical）**：
- `_scheduler.py` event_callback 双 lambda 默认值改为模块级函数或 None sentinel

**2.13 修复 auto_calibrator 失效 import（新发现 Critical）**：
- `_weight_calibration.py` 移除不存在的 `calibrate_weights.py` import，或创建该模块

**2.14 修复 _ratio 边界与 OfficialScoringSystem 加锁（新发现 High）**：
- `official_helpers/_normalize._ratio` 2.0 处不连续修复
- `scoring/official_scoring/_history` 加锁

**2.15 清理 fetch_official_thresholds 死代码（新发现 High）**：
- `official_context/_composite` 的 `fetch_official_thresholds` / `merge_dynamic_thresholds` 死代码（W-08 从未接入）—— 接入或删除

**2.16 修复 Web 层 High 18 处（批量）**：
- `post_routes/submit` 硬编码 403 改配置
- `web_get_routes/_routes_simulation` 导入失败 500 改降级
- `web_assistant_snapshots/_profile` 空 glob 处理
- `web_jobs` ASYNC_JOBS OOM 限制大小
- `_handlers_alpha` record_trend 加锁
- `_handlers_simulation` 批量信息不丢失
- `web_check_availability` 12 类检查隔离
- `web_config` run_config_from_payload 修复 TypeError
- `web_submission_batch` 逐候选错误聚合
- `web_submission_safety/_observability` 降级标记
- `web_security` validate_replay 时间戳 skew 修复
- `web_runtime_state` lifecycle_from_job limit=0 修复
- `handlers/phase.py` NameError 修复
- `api/trends.ts` 字符串比较 TypeError 修复
- `simulation_scheduler/_types.py` reset 重置 error_count
- `presets.py:86` capability kind 修正

### 阶段三：UX 流程优化（UX Flow Optimization）

**3.1 合并两套 job 聚合 hook**：
- 保留组合式 `useJobMonitor` 架构，吸收 `useJobStatusHook` 状态管理逻辑
- 消除 `useJobWatchdog` vs `useStatusWatchdog` 重叠（合并为 1 个 watchdog）
- 消除 `useJobSseConnection` vs `useSseEventHandler + useSseRetryState` 重叠（合并为 1 套 SSE）
- 目标：1 个聚合 hook + ≤3 个子 hook
- 过渡期被合并 hook 在原路径保留 re-export + `DeprecationWarning`

**3.2 修复 SSE 断连误取消（U-001）**：
- 探活失败时提示"连接断开，云端任务可能仍在运行" + 手动恢复入口，不自动取消
- 添加"重连"按钮

**3.3 修复限流倒计时与错误引导（U-002/U-003）**：
- 限流倒计时读取 `Retry-After` 头按实际值倒计时
- `helpers/connectionErrorGuide.ts` 扩展覆盖全部错误类型

**3.4 修复配置保存与前台通知（U-004/U-008）**：
- 配置保存后 toast 提示"部分配置需重启生效"
- `useJobNotifications` 接 `Notification API`，前台完成时系统通知

**3.5 修复轮询 visibility（U-009）**：
- `useGlobalData.ts:98-103`：接 `document.visibilitychange`，隐藏时暂停轮询

**3.6 修复阻断阶段按钮仍可点（W-001）**：
- `PhaseShell.tsx:102-107`：阻断态增加 `pointer-events: none` 或 `inert`，内部元素 `disabled`，视觉灰化 + tooltip

**3.7 修复首屏空白、路由 URL、Toast 重复（W-002/W-004/W-010/W-011）**：
- `ErrorBoundary.tsx:57-61`：`handleGoHome` 改用 `onNavigate` prop
- `main.tsx`：扩展路由表，`activeView` 映射到 URL path（`/` / `/config` / `/candidates` / `/scoring`）
- `index.html:13`：加 noscript + 内联骨架屏
- Toast 三套合并为单一系统（`ToastContainer.tsx` + AppStateContext）

**3.8 修复 renderActiveViewFromContext hook 违规（W-007）**：
- `renderViewFromContext.tsx:26-28`：改为标准组件 `<ActiveViewRenderer />` 或提升到父组件

### 阶段四：UI 视觉统一（UI Visual Unification）

**注**：设计令牌系统已存在且采用率高，本阶段主要是统一采用率 + 修复失效类名 + 完善暗色主题，**不创建新的 tokens.css**。

**4.1 完善设计令牌采用率**：
- 4 处硬编码 hex 颜色替换为 `var(--color-*)`
- 251 处硬编码 px 间距/字号替换为 `var(--space-*)` / `var(--font-size-*)`（动态计算除外）

**4.2 统一组件视觉语言**：
- 基础组件（Button / Card / Input / Modal / Toast / Tooltip / Skeleton）全部使用设计令牌
- 移除过度视觉装饰，遵循现代极简原则

**4.3 修复 StateCardItem 暗色主题（W-013）**：
- 硬编码 `border-slate-200` / `bg-white` / `text-slate-950` / `text-slate-600` 替换为设计令牌
- `brand-*` 失效类名修复为 `accent-*`（与 Task 1.8 协调）

**4.4 重设计 Dashboard 布局**：
- 信息密度合理化，卡片对齐与间距统一
- 关键 KPI 突出（大字号 + 强调色），次要信息折叠
- 响应式：桌面 4 列 / 平板 2 列 / 手机 1 列

**4.5 重设计 ConfigPanel**：
- 表单分组清晰（基础 / 高级 / 凭证 / 评分权重）
- 标签与输入框对齐，验证反馈即时（inline error）
- 保存按钮状态明确（dirty / saving / saved / error）

**4.6 重设计 CandidateTable**：
- 列宽合理，可横向滚动，行密度可调（紧凑/标准/宽松）
- 移动端切换为卡片视图

**4.7 重设计 ScoringPanel**：
- 分数 / 排名 / 归因可视化清晰
- 颜色语义明确（绿=通过 / 红=阻断 / 黄=警告）
- 改进建议可折叠

**4.8 完善移动端布局与暗色主题**：
- 最小 375px 宽度适配，底部 tab bar（`MobileTabBar.tsx`）
- 关键操作悬浮按钮
- `ThemeProvider` 暗色主题令牌映射完善

### 阶段五：测试清理与回归验证

**5.1 清理测试死代码（新发现）**：
- 删除 `test_review_gap_closure_tracker.py` 重复副本（1056 行 ×2 → 1 份）
- 4 个 qa_*.py 永久 skip（~3200 行）：评估能否修复并启用，或删除
- 修复 `test_input_validation.py:44-60` 两个死测试（加断言）
- 修复 `test_local_quality.py:48-49` 死断言
- 修复 `test_dataset_id_missing.py` CapabilityResolutionError fall through
- 修复 `test_infrastructure_modules.py` AdaptiveExecutor shutdown 重建盲区

**5.2 保留 re-export 兼容层（过渡期）**：
- 旧扁平名 import 路径保留 re-export + `DeprecationWarning`
- 被合并的 job 聚合 hook 原路径保留 re-export
- Toast 系统原路径保留 re-export

**5.3 测试同步更新**：
- `tests/test_web*.py` import 路径与 mock 目标同步
- `tests/test_official_workflow*.py` / `test_pipeline_services*.py` 同步（孤立模块删除）
- 前端 hook 测试同步（useJob 聚合 hook 合并）
- `_ratio` 跨模块不一致（>=2.0 vs >=100）统一
- `test_rolling_validation` 覆盖 decay_ratio 符号翻转

**5.4 全量回归测试**：
- `pytest tests/ -x -q` passed ≥ 2874，failed ≤ 133，无新增 failure
- `npm run typecheck` exit 0
- `npm run lint` warnings ≤ baseline
- `npm run build` 成功

**5.5 冒烟测试**：
- `/api/health` 返回 200
- 关键 GET 端点冒烟（`/api/jobs` / `/api/candidates` / `/api/config` / `/api/trends`）
- 前端路由冒烟（`/` / `/config` / `/candidates` / `/scoring`）
- SSE 连接 `/api/jobs/sse` 可连接
- 配置保存 POST `/api/config` 成功
- 候选生成 POST `/api/jobs` 可触发

**5.6 Docker 构建验证**：
- `docker build -t brain-alpha-ops:refactor .` 成功
- 镜像大小 ≤ baseline + 10%
- 多阶段构建保持有效

## Impact

- **架构层面**：删除约 30+ 个死代码文件/模块，消除双轨系统，拆除 meta-path finder 60 条别名债务，统一 facade 模式
- **功能层面**：修复反过拟合虚假 PASS、假设反馈链路断裂、演化探索失效、empirical_score 分值不可达、双轨修复未同步、Web 层 fail-open 泛滥
- **体验层面**：消除首屏白屏、路由进 URL、SSE 断连不误取消、阻断态按钮不可点、Toast 不重复
- **视觉层面**：暗色主题完整适配、失效类名修复、硬编码值替换为设计令牌、Dashboard/ConfigPanel/CandidateTable/ScoringPanel 重设计
- **测试层面**：清理 ~4200 行死测试/永久 skip 测试，修复薄弱断言，统一 _ratio 跨模块不一致
- **风险**：双轨合并可能引入回归（需保留 re-export 兼容层 + 充分回归测试）；fail-closed 改造可能影响容错性（需按子系统分级处理）
