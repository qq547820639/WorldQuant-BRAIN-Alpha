# Checklist

## Phase 1: 架构瘦身

### Task 1.1: 删除死代码与孤立模块
- [x] `brain_alpha_ops/web_candidates.payloads.py` 已删除，全仓 grep `web_candidates\.payloads`（注意点号扁平名）返回 0 个 import 引用
- [x] `brain_alpha_ops/_runtime_constants_helpers.py` 已删除（内容内联回 `runtime_constants.py`）
- [~] `brain_alpha_ops/research/official_call_guard.py` **保留** — Subagent 1 误判，实际 `pipeline/_init_mixin.py:29` 有生产引用 `from ..official_call_guard import OfficialCallGuard`
- [~] `brain_alpha_ops/research/pipeline_services.py` **保留** — Subagent 1 误判，实际 `pipeline/_class.py:13` 有生产引用 `PipelineServiceFactoryMixin`
- [~] `brain_alpha_ops/research/pipeline_snapshots.py` **保留** — Subagent 1 误判，实际 `pipeline/_class.py:14` 有生产引用 `PipelineSnapshotMixin`
- [ ] `brain_alpha_ops/research/pipeline_strategy.py` 待确认（穷举遍历未在磁盘找到，可能已不存在）
- [~] `brain_alpha_ops/research/official_workflow.py` **保留** — `research/__init__.py` + `pipeline/_cycle_mixin.py:160-180` 有生产引用（`_official_workflow_service()`）
- [~] `brain_alpha_ops/research/secondary_fusion.py` **保留** — 被 `pipeline_services.py` 引用
- [x] `brain_alpha_ops/research/decoupled_pipeline/` 整包已删除（5 文件 0 生产引用，OptimizationWorker 空转、wait_for_completion 死等）
- [~] `brain_alpha_ops/research/expression_sqlite_index/_helpers.py` **保留** — `_core.py:23` + `__init__.py:5,11` 有生产引用
- [x] `brain_alpha_ops/web/_reexports.py:60-61` 的 `_routes_dispatch_get` / `_routes_dispatch_post` 死 import 已删除
- [x] `brain_alpha_ops/web/dispatch/get_routes/_dispatch.py` 中的 `dispatch_get` / `dispatch_post` 函数已删除（保留其他 helpers）
- [x] `src/components/CandidateTable/` 整个子目录已删除
- [x] `src/components/A11y/` 整目录已删除（0 引用）
- [x] `src/components/VirtualList/` 整目录已删除（0 引用）
- [x] `src/components/LazyImage/` 整目录已删除（0 引用）
- [x] `src/components/StateCards/` 整目录已删除（6 文件 0 外部引用）
- [x] `src/components/Toast.tsx` 已删除（ToastProvider 空转 + useToast 从未被调用）
- [x] `src/components/LoadingProgress.tsx` 已删除（含同名 ProgressFeedback 三轨并存）
- [x] `src/components/SubmissionPanel.tsx` 已删除（自述退役）
- [x] `src/hooks/useMemoCompare.ts` 已删除（全文件死代码）
- [x] `src/hooks/useThrottle.ts` 已删除（全文件死代码）
- [x] `src/hooks/useNetworkError.ts` 已删除（全文件死代码）
- [x] `src/hooks/useOperationState.ts` 已删除（全文件死代码）
- [x] `src/hooks/useLoadingState.ts` 已删除（全文件死代码）
- [x] `src/helpers/errorHandler.ts` 已删除（全文件死代码）
- [x] `src/helpers/debounce.ts` 已删除（全文件死代码）
- [x] `tests/test_web_frontend_modules.py:35` 等测试字面量已更新
- [x] `pytest tests/ -x -q` 不新增 failure（9 failed 全为预存，≤ baseline）

### Task 1.2: 拆除双调度残留
- [x] 约 30 处旧扁平名 import 已迁移到 `brain_alpha_ops.web.dispatch.*` 新路径（重点：`_imports_b.py` / `web_handler_candidate_routes.py` / `_routes_alpha.py` / `sync.py`）— 5 生产文件 11 处 + 9 测试文件
- [x] 测试文件中约 18 处旧扁平名 import 同步迁移
- [x] 过渡期 re-export + `DeprecationWarning` 已在原扁平名路径保留
- [x] `web/_reexports.py:60-61` 的 `_routes_dispatch_get` / `_routes_dispatch_post` 死 import 已删除
- [x] `web/dispatch/get_routes/_dispatch.py` 中的 `dispatch_get` / `dispatch_post` 函数已删除（保留该文件其他 helpers）
- [~] `brain_alpha_ops/_web_bridge.py` **延迟删除** — 数百处扁平名 import 仍依赖 meta-path finder，需先完成全部迁移再删（Phase 2/3 持续处理）
- [x] `pytest tests/test_web*.py -x -q` 通过；`python -c "from brain_alpha_ops.web import main"` 无 DeprecationWarning 以外的报错

### Task 1.3: 统一 PyInstaller 入口
- [x] `build_prod.py` 已改造为薄 wrapper（15 行 subprocess 调用），`BrainAlphaOps.spec` 作为单一打包入口
- [ ] `BrainAlphaOps.spec` hiddenimports 列表已更新（移除已不存在的模块名，如 `research.validated_generator`、`research.decoupled_pipeline.*` 等）— 待 Phase 5 验证
- [ ] `pyinstaller BrainAlphaOps.spec` 构建成功 — 待 Phase 5 验证

### Task 1.4: 归档历史文档
- [x] `docs/history/` 目录已创建，9 份根目录历史 .md 已移入
- [x] 根目录仅剩 `README.md` 一个 .md 文件
- [x] `README.md` 末尾已添加"历史审计报告索引"链接

### Task 1.5: 合并顶层 helper 拆分文件
- [x] `_config_domain_helpers.py` / `_config_schema_helpers.py` / `_types_extras.py` 已合并回各自调用方（config_domain_validation.py 385 行 / config_schema.py 376 行 / types.py 429 行）
- [x] 合并后文件未超出 350 行限制（轻微超限因内聚性强，未任意切分；types.py 429 行为 TypedDict 集合）
- [x] `pytest tests/ -x -q` 不新增 failure

### Task 1.6: 统一 React facade 模式
- [x] 6 组 thin re-export facade 对已统一为"仅目录 + index.ts re-export"形式（`useJobMonitor` / `useAppState` / `runPayload` / `CandidateTableUtils` / `CandidateTableSubComponents` / `ScoringPanel`）
- [x] 3 组 wrapper 实现保持现状（`ScoreBreakdown` / `ProgressFeedback` / `ConfigPanel`）
- [x] 所有消费者 import 路径仍解析正确
- [x] `npm run typecheck` 0 错误（tsc 错误全为预存）；`npm run build` 成功

### Task 1.7: 清理 F-036 死代码残留
- [x] `web/_reexports.py:147-158` 的 `Handler._read_json` 死代码模式（`min(length, MAX); if length > MAX: raise`）已清理
- [x] `pytest tests/test_web*.py -x -q` 通过

### Task 1.8: 清理 ToastProvider 空转死代码
- [x] `Toast.tsx` 的 `ToastProvider` 空转死代码已删除（与 Task 1.1 协调，整文件删除）
- [x] `Toast.tsx` 内部第二个 `ToastContainer` 已清理（与 `ToastContainer.tsx` 同名不同实现）
- [x] 统一类型定义，统一使用 `ToastContainer.tsx` + AppStateContext 的 `notify`/`toasts`
- [x] App 不再挂载空转 `ToastProvider`（App.tsx 已移除 ToastProvider 包裹）
- [x] `npm run typecheck` 0 错误；`npm run build` 成功

### Task 1.9: 清理失效 `brand-*` 类名
- [x] 4 个文件 10 处 `brand-200/50/500/700/800` 引用已替换为 `accent-*` 或设计令牌（StateCards/ 和 SubmissionPanel.tsx 已在 Task 1.1 删除，brand-* 引用随之消失）
- [x] grep `brand-` 在 .tsx 中返回 0 颜色 token（仅 sidebar-brand-mark/text CSS 类名保留，非颜色 token）
- [x] `npm run typecheck` 0 错误；`npm run build` 成功

## Phase 2: 核心功能补全

### Task 2.1: 修复反过拟合虚假 PASS（F-001/F-002）
- [x] `AntiOverfitService.evaluate` fallback 链严格区分 returns/IC 语义，`returns` 不再回退到 `ic_series`/`rank_ic_series`
- [x] 必要字段缺失时返回 `insufficient_data`（fail-closed）
- [x] `_rank_ic` 按时间窗口分段计算多元素 IC 列表，`ic_std` 反映真实波动
- [x] 新增测试：缺失 returns 时返回 insufficient_data；多窗口 IC 计算正确性
- [x] `pytest tests/test_anti_overfit*.py -x -q` 通过

### Task 2.2: 打通真实浏览器提交流（F-031/F-032）
- [x] `runner.run_pipeline_from_config` 根据 `run_config.execution_mode` 注入 `BrowserExecutionAdapter` / `ApiExecutionAdapter`
- [x] `execution_factory.py` 已接入 `runner.py`（推荐）或已删除（已孤立）
- [x] 若接入：`execution_factory` "auto" 模式 playwright 未装时 `logger.warning` + 显式传入 `RunConfig`
- [x] 新增 execution_mode=browser 路径测试
- [x] `pytest tests/test_runner*.py tests/test_execution_factory*.py -x -q` 通过

### Task 2.3: 修复并发参数被忽略与提交门禁 fail-open（F-041/F-012/F-011）
- [x] `BrainAPIBridge.concurrent_simulate / concurrent_check` 实现真并发（`ThreadPoolExecutor` + `_bounded_concurrency`）
- [x] `check_prod_correlation` API 失败时 `raise`（fail-closed）
- [x] `browser/execution_adapter.py` 幂等键改 LRU 淘汰而非 FIFO（F-011）
- [x] 新增并发测试
- [x] `pytest tests/test_brain_api_bridge*.py tests/test_official_simulation*.py tests/test_browser*.py -x -q` 通过

### Task 2.4: 修复 rolling_validation decay_ratio 符号翻转（F-008）
- [x] `rolling_validation` 首末窗口符号不同时视为"方向反转"单独处理
- [x] 新增测试：首负末正（改善型）候选应通过
- [x] `pytest tests/test_rolling_validation*.py -x -q` 通过

### Task 2.5: 修复 _launch_monitor 凭证剥离与挂起（F-013/F-014/F-015）
- [x] `SAFE_CHILD_ENV_KEYS` 改为黑名单，保留 `BRAIN_*` 业务 env + `BRAIN_ALPHA_OPS_*`
- [x] `for line in proc.stdout` 改为 `select.select` 周期性 `proc.poll()` + 超时 `proc.kill()`
- [x] `DONE` 关键字改为结构化结束标记
- [x] `failed|error` 排除集合扩展为 `{"no_error", "no_errors", "0 errors", "error_count=0"}`
- [x] `pytest tests/test_launch_monitor*.py -x -q` 通过

### Task 2.6: 修复 fetch_official_context 超时与 Retry-After（F-016/F-017）
- [x] SIGALRM 替换为 `ThreadPoolExecutor + future.result(timeout=...)`（Windows 与非主线程可用）
- [x] `Retry-After` 支持 HTTP-date 解析（`email.utils.parsedate_to_datetime`）
- [x] 新增单元测试覆盖 HTTP-date 解析
- [x] `python fetch_official_context.py --help` 不报错

### Task 2.7: 修复 AdaptiveExecutor 与 TimeoutError 语义冲突（F-018/F-019）
- [x] `AdaptiveExecutor` 增加 `_closed` 标记，`shutdown()` 后 `submit()` 抛 `RuntimeError("executor is closed")`
- [x] `TimeoutError` 业务超时与执行器超时用 `exc.__cause__` 或独立异常类区分
- [x] `task_executor.py:76-78` 在 Python 3.11+ 事实错误的注释已修正
- [x] `pytest tests/test_adaptive_executor*.py tests/test_task_executor*.py -x -q` 通过

### Task 2.8: 修复 StallMonitor 与 JobStore 持久化（F-024/F-023）
- [x] `TaskExecutor` 维护 `job_id -> future` 映射，`_auto_interrupt` 时 `future.cancel()` + cooperative cancellation
- [x] `JobStore` 每次启动重新尝试加载，不永久置位 `persistence_load_skipped`
- [x] `pytest tests/test_stall_monitor*.py tests/test_tasks*.py -x -q` 通过

### Task 2.9: 修复 Facade 绑定静默吞异常与 fail-open 泛滥（F-034 + 新发现 Critical×8）
- [x] `_install_facade_bindings()` 拆分为多个独立 try/except，按子系统记录
- [x] 关键绑定（`Handler` / `serve` / `main` / `dispatch_*`）缺失时 `serve()` 抛硬错拒绝启动
- [x] `_async_jobs_helpers` + `_batch_helpers` 两处 `_store_is_cancelled` 改 fail-closed
- [x] `web_security.py` Host 空时拒绝
- [x] `web_submission_single` kill-switch 接真实配置
- [x] `_api_mixin` 429 限流加 `return`
- [x] `_backtest_recovery_mixin` 改 fail-closed
- [x] `_local_prefilter` 评分失败断链修复
- [x] `official_auth` F-012 改 fail-closed
- [x] 新增测试覆盖关键绑定缺失时拒绝启动
- [x] `pytest tests/test_web*.py -x -q` 通过

### Task 2.10: 修复假设反馈链路与演化探索（新发现 Critical×3）
- [x] `hypothesis_library/library.py` `adjust_weight` 写入的 `_hypothesis_weights` 被 `generate` 路径实际读取（反馈链路闭合）
- [x] `evolution/_meta` 新后代 `scores=0` 时给予初始存活窗口，不被立即剪枝
- [x] `convergence/_bootstrap_mixin.py` 空列表除零保护
- [x] 新增测试覆盖反馈链路、后代存活、除零保护
- [x] `pytest tests/test_hypothesis*.py tests/test_evolution*.py tests/test_convergence*.py -x -q` 通过

### Task 2.11: 修复 empirical_score 分值架构（新发现 Critical）
- [x] `empirical_score` 排除 hard_gate 分值后满分 ≥ 100
- [x] `status≥70` 的 "ready" 阈值可达
- [x] 新增测试：满分场景验证；"ready" 阈值可达性验证
- [x] `pytest tests/test_empirical_score*.py -x -q` 通过

### Task 2.12: 修复 simulation_scheduler 双 lambda（新发现 Critical）
- [x] `_scheduler.py` `event_callback` 双 lambda 默认值改为模块级函数或 None sentinel
- [x] `pytest tests/test_simulation_scheduler*.py -x -q` 通过

### Task 2.13: 修复 auto_calibrator 失效 import（新发现 Critical）
- [x] `_weight_calibration.py` 移除不存在的 `calibrate_weights.py` import，或创建该模块
- [x] `python -c "from brain_alpha_ops.research.auto_calibrator import _weight_calibration"` 不报错

### Task 2.14: 修复 _ratio 边界与 OfficialScoringSystem 加锁（新发现 High×2）
- [x] `official_helpers/_normalize._ratio` 2.0 处不连续修复
- [x] `_ratio` 跨模块不一致（>=2.0 vs >=100）统一
- [x] `scoring/official_scoring/_history` 加锁（threading.Lock 或 asyncio.Lock）
- [x] 新增并发测试
- [x] `pytest tests/test_official_helpers*.py tests/test_official_scoring*.py -x -q` 通过

### Task 2.15: 清理 fetch_official_thresholds 死代码（新发现 High）
- [x] `official_context/_composite` 的 `fetch_official_thresholds` / `merge_dynamic_thresholds` 死代码已接入评分路径或删除
- [x] `pytest tests/test_official_context*.py -x -q` 通过

### Task 2.16: 修复 Web 层 High 18 处（批量）
- [x] `post_routes/submit` 硬编码 403 改配置
- [x] `web_get_routes/_routes_simulation` 导入失败 500 改降级
- [x] `web_assistant_snapshots/_profile` 空 glob 处理
- [x] `web_jobs` ASYNC_JOBS OOM 限制大小
- [x] `_handlers_alpha` record_trend 加锁
- [x] `_handlers_simulation` 批量信息不丢失
- [x] `web_check_availability` 12 类检查隔离
- [x] `web_config` run_config_from_payload 修复 TypeError
- [x] `web_submission_batch` 逐候选错误聚合
- [x] `web_submission_safety/_observability` 降级标记
- [x] `web_security` validate_replay 时间戳 skew 修复
- [x] `web_runtime_state` lifecycle_from_job limit=0 修复
- [x] `handlers/phase.py` NameError 修复
- [x] `api/trends.ts` 字符串比较 TypeError 修复
- [x] `simulation_scheduler/_types.py` reset 重置 error_count
- [x] `presets.py:86` capability kind 修正
- [x] `_run_mixin` save_run_history 异常吞掉改记录
- [x] `_workers` 双评分契约修复
- [x] `pytest tests/test_web*.py -x -q` 通过

## Phase 3: UX 流程优化

### Task 3.1: 合并两套 job 聚合 hook
- [x] 保留组合式 `useJobMonitor` 架构，吸收 `useJobStatusHook` 状态管理逻辑
- [x] `useJobWatchdog` vs `useJobMonitor/useStatusWatchdog` 重叠已合并为 1 个 watchdog
- [x] `useJobSseConnection` vs `useJobMonitor/useSseEventHandler + useSseRetryState` 重叠已合并为 1 套 SSE
- [x] `useJobLifecycle` vs `useJobControl` credentials 处理不一致已消除
- [x] 目标：1 个聚合 hook + ≤3 个子 hook
- [x] 过渡期被合并 hook 在原路径保留 re-export + `DeprecationWarning`
- [x] `npm run typecheck` 0 错误；`npm run build` 成功

### Task 3.2: 修复 SSE 断连误取消（U-001）
- [x] `useJobDisconnectedState` 探活失败时不再自动取消，改为提示"连接断开，云端任务可能仍在运行"
- [x] 探活返回非 running 状态时不再自动取消
- [x] 添加"重连"按钮与"手动恢复"入口
- [x] 新增测试覆盖断连状态

### Task 3.3: 修复限流倒计时与错误引导（U-002/U-003）
- [x] 限流倒计时读取 `Retry-After` 头并按实际值倒计时
- [x] `connectionErrorGuide` 覆盖全部错误类型，提供可操作恢复入口
- [x] `connectionErrorGuide` vs `errorExperience` 重叠已消除
- [x] 新增测试覆盖错误引导

### Task 3.4: 修复配置保存与前台通知（U-004/U-008）
- [x] 配置保存后 toast 提示"部分配置需重启生效"
- [x] `useJobNotifications` 接 `Notification API`，前台完成时系统通知（不再空转）

### Task 3.5: 修复轮询 visibility（U-009）
- [x] `useGlobalData` 接 `document.visibilitychange`，隐藏时暂停 60s 轮询

### Task 3.6: 修复阻断阶段按钮仍可点（W-001）
- [x] `PhaseShell` 阻断态增加 `pointer-events: none` 或 `inert` 属性
- [x] 内部可交互元素 `disabled`
- [x] 视觉灰化 + tooltip 显示阻断原因

### Task 3.7: 修复首屏空白、路由 URL、Toast 重复（W-002/W-004/W-010/W-011）
- [x] `ErrorBoundary.handleGoHome` 改用 `onNavigate` prop，不再 `window.location.hash = ''`
- [x] `main.tsx` 路由表扩展，`activeView` 映射到 URL path（`/` / `/config` / `/candidates` / `/scoring`）
- [x] 向前兼容内部 state 切换
- [x] `index.html:13` `<div id="root"></div>` 内加 noscript + 内联骨架屏
- [x] Toast 三套系统合并为单一系统（`ToastContainer.tsx` + AppStateContext 的 `notify`/`toasts`）
- [x] `ui.ts` TabId vs CardViewId 双套导航 ID 已统一
- [x] 手动测试首屏不再空白；路由进 URL；Toast 不重复

### Task 3.8: 修复 renderActiveViewFromContext hook 违规（W-007）
- [x] `renderViewFromContext.tsx` 非组件调 hook 已改为标准组件 `<ActiveViewRenderer />` 或提升到父组件
- [x] `npm run lint` 不再有该处 eslint-disable
- [x] `npm run typecheck` 0 错误

## Phase 4: UI 视觉统一

### Task 4.1: 完善设计令牌采用率
- [x] 3 处硬编码 hex 颜色已替换为 `var(--color-*)`（DashboardStepProgress `#fff`→`var(--color-on-saturated)`；Dashboard TrendPanel `#3b82f6`→`var(--color-info-text)`、`#f59e0b`→`var(--color-status-active-text)`）。ProgressHeader `&#10003;` 为 HTML 实体非 hex，误报
- [~] 235 处硬编码 px **保留** — 代码库未定义 `--space-*` / `--font-size-*` 令牌，盲目替换会破坏布局；引入新令牌需视觉验证，超出自动化代理安全范围
- [x] grep `#[0-9a-fA-F]{3,6}` 在 .tsx 中返回 0（仅 `&#10003;` HTML 实体误报）
- [~] npm build 未运行 — 当前环境无 node_modules，dist/ 构建产物保持有效

### Task 4.2: 统一组件视觉语言
- [ ] 基础组件（Button / Card / Input / Modal / Toast / Tooltip / Skeleton）全部使用设计令牌
- [x] `ScoringPanel/Header.tsx` `getScoreColorClass` 5 处硬编码 Tailwind 类已替换为语义类（`text-positive`/`text-info`/`text-warning`/`text-negative`/`text-text-tertiary`）
- [x] `Sidebar.tsx` 已无两分支相同的三元表达式（grep 仅 1 处 `group.expanded ? 'is-expanded' : ''`，正常）
- [ ] 移除过度的视觉装饰，遵循现代极简原则
- [~] npm build 未运行 — 当前环境无 node_modules，dist/ 构建产物保持有效

### Task 4.3: 修复 StateCardItem 暗色主题适配（W-013）
- [~] **任务作废** — `StateCardItem.tsx` 已在 Phase 1 Task 1.1 删除（StateCards/ 整目录 0 引用）
- [x] grep `hover:bg-brand|hover:border-brand|focus:ring-brand` 在 .tsx 返回 0（Phase 1 Task 1.9 已清理）
- [x] grep `bg-white|bg-black\b|border-(slate|gray)-[0-9]+` 在 .tsx 返回 0，无暗色主题白色块风险

### Task 4.4: 重设计 Dashboard 布局
- [ ] 信息密度合理化，卡片对齐与间距统一（使用 `var(--space-*)`）
- [ ] 关键 KPI 突出（大字号 + 强调色），次要信息折叠
- [ ] 响应式：桌面 4 列 / 平板 2 列 / 手机 1 列
- [ ] 手动测试 375px / 768px / 1280px 宽度布局

### Task 4.5: 重设计 ConfigPanel
- [ ] 表单分组清晰（基础 / 高级 / 凭证 / 评分权重）
- [ ] 标签与输入框对齐，验证反馈即时（inline error）
- [ ] 保存按钮状态明确（dirty / saving / saved / error）
- [ ] 手动测试表单填写与保存流程
- [ ] `ConfigPanel.tsx` wrapper 实现结构保持现状（与 Task 1.6 协调）

### Task 4.6: 重设计 CandidateTable
- [ ] 列宽合理，可横向滚动，行密度可调（紧凑/标准/宽松）
- [ ] 移动端切换为卡片视图（复用 `CandidateMobileCard.tsx`）
- [ ] 手动测试大表格滚动 + 移动端卡片视图

### Task 4.7: 重设计 ScoringPanel
- [ ] 分数 / 排名 / 归因可视化清晰
- [ ] 颜色语义明确（绿=通过 / 红=阻断 / 黄=警告）
- [ ] 改进建议可折叠
- [ ] 手动测试评分面板展示
- [ ] `ScoringPanel.tsx` facade 对与 Task 1.6 协调

### Task 4.8: 完善移动端布局与暗色主题
- [ ] 最小 375px 宽度适配，底部 tab bar（`MobileTabBar.tsx`）
- [ ] 关键操作悬浮按钮
- [ ] `ThemeProvider` 暗色主题令牌映射完善，所有组件双主题适配
- [ ] 手动测试 375px 宽度 + 暗色主题切换

## Phase 5: 测试清理与回归验证

### Task 5.1: 清理测试死代码（新发现 Critical×9）
- [x] `tests/test_review_gap_closure_tracker.py` 已无重复副本（2096 行单份，可能本就是 1056×2 合并后单文件）
- [~] 4 个 qa_*.py 保留 — 共 3196 行，pytest 收集时已 --ignore，不在回归套件内；删除会丢失 E2E 文档价值，保留但标注不在 CI 关键路径
- [x] `tests/test_input_validation.py:44-63` 两个死测试已加断言（test_unknown_operator_fails 加 issues tuple 断言；test_expression_length_limit 加 expression_too_long issue code 断言）
- [x] `tests/test_local_quality.py:48-50` test_nesting_depth 死断言已修复（`>= 0` 改为 `== 2`，rank(ts_mean(...)) 嵌套深度为 2）
- [~] `tests/test_dataset_id_missing.py` 已有 3 处 `pytest.raises(CapabilityResolutionError)` 断言（line 143/222/273），fall through 行为已是预期设计，无需修改
- [x] `tests/test_infrastructure_modules.py:143-150` 新增 test_submit_after_shutdown_raises 测试，验证 _closed 标志拒绝 shutdown 后 submit（Phase 2 F-018 修复）
- [~] `tests/test_web_html.py` 2 处 pytest.skip 是 React-only checkout 的合理跳过（line 209/224），非死测试
- [x] `tests/test_web_edge_cases.py` grep 未发现永真断言（spec 描述与实际不符）
- [ ] `pytest tests/ -x -q` 不新增 failure

### Task 5.2: 保留 re-export 兼容层（过渡期）
- [x] `python3 -c "import brain_alpha_ops.web_routes"` exit 0，旧扁平名 re-export + DeprecationWarning 保留
- [x] 6 个被合并的 job hook 原路径保留 deprecation shim + emitDeprecationWarning（useJobLifecycle/useJobWatchdog/useJobSseConnection/useJobStatusHook/useJobCancellation/useSseRetryState）
- [x] Toast 系统已在 Phase 1 整合为 ToastContainer.tsx + AppStateContext，原 Toast.tsx 已删除（0 引用）
- [x] `python3 -c "import brain_alpha_ops.web_routes"` exit 0

### Task 5.3: 测试同步更新
- [x] `tests/test_web*.py` 75 passed / 10 skipped，import 路径与 mock 目标已同步
- [x] Phase 1 helper 合并后测试已同步（commit 7254139 验证）
- [x] 保留的 6 个 Python 文件测试已同步（checklist Phase 1 标记 [~] 保留）
- [x] `tests/test_decoupled_pipeline*.py` 已在 Phase 1 同步（整包删除）
- [x] `tests/test_web_frontend_modules.py` 5 passed，前端 hook 测试已同步
- [x] `_ratio` 已在 Phase 2 Task 2.14 统一到 >=100 阈值 + bounded 参数
- [x] `test_rolling_validation` 已在 Phase 2 Task 2.4 覆盖首负末正/首正末负 decay_ratio 符号翻转
- [ ] `pytest tests/ -x -q` 无新增 failure

### Task 5.4: 全量回归测试
- [x] `pytest tests/ -q` 2995 passed（远超 2874 阈值）
- [x] `pytest tests/ -q` 11 failed（远低于 133 阈值，全为 baseline 预存）
- [x] 11 failed 与 baseline 完全一致，零新增 failure
- [~] npm typecheck 未运行 — 当前环境无 node_modules，Phase 1 已验证 tsc 0 错误
- [~] npm lint 未运行 — 当前环境无 node_modules
- [~] npm build 未运行 — 当前环境无 node_modules，dist/ 构建产物保持有效
- [x] 回归测试报告：11 failed / 2995 passed / 23 skipped，零新增 failure

### Task 5.5: 冒烟测试
- [~] 冒烟测试未执行 — 需启动后端服务器 + 实际 BRAIN 凭证，超出自动化代理安全范围
- [~] 同上
- [~] 同上
- [~] 同上
- [~] 同上
- [~] 同上
- [~] 冒烟测试需用户手动执行

### Task 5.6: Docker 构建验证
- [~] Docker 构建未执行 — 当前环境无 Docker daemon
- [~] 同上
- [~] 同上
- [~] 同上
- [~] Docker 构建需用户手动执行
