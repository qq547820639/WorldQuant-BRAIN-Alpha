# Tasks

本任务清单按"先架构瘦身（清场地）→ 再功能补全（修核心）→ 再 UX 优化（顺流程）→ 再 UI 重设计（统一视觉）→ 最后测试清理与回归验证"顺序组织。每个阶段内部任务尽量并行化，跨阶段存在依赖。

**与初版的关键修正**（基于 2026-06-30 穷举遍历 10 个子智能体覆盖全部 1,310 文件 / 219,909 行）：
- Task 1.1 从"删除 8 个孤立模块 + 1 个死目录"扩展为"删除 8 个孤立 Python 模块 + 整包死代码 `decoupled_pipeline/`（5 文件）+ `expression_sqlite_index/_helpers.py` + 5 个前端整目录死代码 + 3 个前端整文件死代码 + 7 个全文件死代码 hook/util"
- 新增 Task 1.9（双轨并存 Critical 修复，新发现）
- 新增 Task 2.10/2.11/2.12/2.13/2.14/2.15（新发现 Critical/High 修复）
- Task 2.16 从原 Web 层 High 单列为批量修复任务
- 新增 Phase 5 Task 5.1（测试死代码清理，新发现）

## Phase 1: 架构瘦身（Architectural Simplification）

- [ ] Task 1.1: 删除死代码与孤立模块（穷举确认死代码清单）
  - **Python 后端**：
    - 删除 `brain_alpha_ops/web_candidates.payloads.py`（点号扁平名，40 行重复 import，0 引用，损坏文件）
    - 删除 `brain_alpha_ops/_runtime_constants_helpers.py`（自承 deprecated，仅 `runtime_constants.py:20` 1 处引用）；内容内联回 `runtime_constants.py` 或删除引用
    - 删除 `brain_alpha_ops/research/official_call_guard.py`（仅测试引用，生产 0 引用）
    - 删除 `brain_alpha_ops/research/pipeline_services.py`（孤立）
    - 删除 `brain_alpha_ops/research/pipeline_snapshots.py`（孤立）
    - 删除 `brain_alpha_ops/research/pipeline_strategy.py`（孤立）
    - 删除 `brain_alpha_ops/research/official_workflow.py`（仅被孤立的 `pipeline_services.py` 导入，传递性孤立）
    - 删除 `brain_alpha_ops/research/secondary_fusion.py`（同上，传递性孤立）
    - **删除整包死代码 `brain_alpha_ops/research/decoupled_pipeline/`（5 文件 0 生产引用，OptimizationWorker 空转、wait_for_completion 死等）**
    - 删除 `brain_alpha_ops/research/expression_sqlite_index/_helpers.py`（整文件复制 `expression_index`，合并回 `expression_index` 或删除）
    - 删除 `brain_alpha_ops/web/_reexports.py:60-61` 的 `_routes_dispatch_get` / `_routes_dispatch_post` 死 import
    - 删除 `brain_alpha_ops/web/dispatch/get_routes/_dispatch.py` 中的 `dispatch_get` / `dispatch_post` 函数（保留该文件其他 helpers）
  - **前端**：
    - 删除 `src/components/CandidateTable/` 整个子目录（`CandidateTable.tsx` + `useCandidateTableSse.ts` + `detailPanelProps.ts` + `TaskSuccessBanner.tsx` 全部死代码）
    - **删除整目录死代码**：`src/components/A11y/`（0 引用）、`src/components/VirtualList/`（0 引用）、`src/components/LazyImage/`（0 引用）、`src/components/StateCards/`（6 文件 0 外部引用）
    - **删除整文件死代码**：`src/components/Toast.tsx`（ToastProvider 空转 + useToast 从未被调用）、`src/components/LoadingProgress.tsx`（含同名 ProgressFeedback 三轨并存）、`src/components/SubmissionPanel.tsx`（自述退役）
    - **删除 7 个全文件死代码 hook/util**：`src/hooks/useMemoCompare.ts`、`src/hooks/useThrottle.ts`、`src/hooks/useNetworkError.ts`、`src/hooks/useOperationState.ts`、`src/hooks/useLoadingState.ts`、`src/helpers/errorHandler.ts`、`src/helpers/debounce.ts`
  - 同步更新 `tests/test_web_frontend_modules.py:35` 等测试字面量引用
  - 验证：`pytest tests/ -x -q` 不新增 failure；grep 确认无残留引用
  - 产出：删除 11 个 Python 模块/文件 + 1 个 Python 整包（5 文件）+ 5 个前端整目录 + 3 个前端整文件 + 7 个前端 hook/util，更新测试字面量

- [ ] Task 1.2: 拆除双调度残留（迁移约 30 处旧扁平名 import）
  - 范围：迁移约 30 处旧扁平名 import（`brain_alpha_ops.web_routes` / `web_handler_dispatch` / `web_post_handlers` / `web_get_handlers` 等）到 `brain_alpha_ops.web.dispatch.*` 新路径
  - 重点迁移文件（穷举定位）：
    - `web/misc/web_service_namespace/_imports_b.py`（3+ 处）
    - `web/dispatch/web_handler_candidate_routes.py`（3 处）
    - `web/dispatch/web_get_routes/_routes_alpha.py`（2 处）
    - `web/handlers/sync.py`（1 处）
    - 测试文件中约 18 处旧扁平名 import 同步迁移
  - 步骤：
    1. 用 Grep 全仓扫描 `from brain_alpha_ops.web_routes import` / `from brain_alpha_ops.web_handler_dispatch import` / `from brain_alpha_ops.web_post_handlers import` 等旧扁平名
    2. 逐个迁移到新路径
    3. 在原扁平名路径保留 re-export + `DeprecationWarning`（过渡期 1 个版本）
    4. 删除 `web/_reexports.py:60-61` 的死 import（对应 F-036 关联死代码）
    5. 删除 `web/dispatch/get_routes/_dispatch.py` 中的 `dispatch_get` / `dispatch_post` 函数（保留该文件其他 helpers，仍被生产路径间接复用）
    6. 验证全部迁移完成后，删除 `brain_alpha_ops/_web_bridge.py` + 移除 `brain_alpha_ops/__init__.py` / `web/__init__.py` / `web/_reexports.py` 中的 `install_web_bridge()` 调用
  - 验证：`pytest tests/test_web*.py -x -q` 通过；`python -c "from brain_alpha_ops.web import main"` 无 DeprecationWarning 以外的报错
  - 产出：迁移约 30 处 import，删除 `_web_bridge.py`，删除 `dispatch_get/dispatch_post` 函数 + 死 import

- [ ] Task 1.3: 统一 PyInstaller 入口
  - 保留 `BrainAlphaOps.spec` 作为单一打包入口
  - `build_prod.py` 改造为薄 wrapper（仅调用 `pyinstaller BrainAlphaOps.spec`）或删除
  - 验证 `BrainAlphaOps.spec` 的 hiddenimports 列表与当前模块结构一致（移除已不存在的模块名，如 `research.validated_generator`、`research.decoupled_pipeline.*` 等）
  - 验证：`pyinstaller BrainAlphaOps.spec` 构建成功
  - 产出：1 个薄 wrapper 或删除 `build_prod.py`，更新 `BrainAlphaOps.spec` hiddenimports

- [ ] Task 1.4: 归档历史文档
  - 创建 `docs/history/` 目录
  - 移动 9 份根目录历史 .md 到 `docs/history/`：`REFACTORING_PLAN.md` / `CODE_DIAGNOSTIC_REPORT_20260618.md` / `BRAINALPHA_AUDIT_V3_20260619.md` / `PHASE33_DELIVERY_REPORT_20260619.md` / `BRAINALPHA_FULLSTACK_AUDIT_20260622.md` / `IMPLEMENTATION_PLAN_20260622.md` / `DELIVERY_REPORT_20260622.md` / `DELIVERY_REPORT_OVERHAUL.md` / `DEFECT_TRACKING.md`
  - `README.md` 末尾添加"历史审计报告索引"链接到 `docs/history/`
  - 验证：根目录仅剩 `README.md` 一个 .md 文件
  - 产出：`docs/history/` 含 9 份归档，`README.md` 更新索引

- [ ] Task 1.5: 合并顶层 helper 拆分文件
  - 将 `_config_domain_helpers.py`（70 行）合并回 `config_domain_validation.py`（唯一调用方）
  - 将 `_config_schema_helpers.py`（112 行）合并回 `config_schema.py`（唯一调用方）
  - 将 `_types_extras.py`（42 行）合并回 `types.py`（唯一调用方）
  - 合并后若超出 350 行限制，按语义内聚拆分为子模块（而非任意行数切分）
  - 验证：`pytest tests/ -x -q` 不新增 failure
  - 产出：删除 3 个 helper shim，合并到 3 个调用方

- [ ] Task 1.6: 统一 React "文件+同名目录" facade 模式（区分 thin re-export 与 wrapper）
  - **6 组 thin re-export facade 对**（统一为"仅目录 + index.ts re-export"形式，删除根目录 thin re-export 文件）：
    - `useJobMonitor.ts` → `useJobMonitor/index.ts`
    - `useAppState.ts` → `useAppState/index.ts`
    - `runPayload.ts` → `runPayload/index.ts`
    - `CandidateTableUtils.ts` → `CandidateTableUtils/index.ts`
    - `CandidateTableSubComponents.tsx` → `CandidateTableSubComponents/index.ts`
    - `ScoringPanel.tsx` → `ScoringPanel/index.ts`
  - **3 组 wrapper 实现**（保持现状，非纯 facade，是真实组合入口）：
    - `ScoreBreakdown.tsx` + `ScoreBreakdown/`（保持）
    - `ProgressFeedback.tsx` + `ProgressFeedback/`（保持）
    - `ConfigPanel.tsx` + `ConfigPanel/`（保持）
  - 验证：`npm run typecheck` 0 错误；`npm run build` 成功；所有消费者 import 路径仍解析正确
  - 产出：6 个 thin re-export 文件删除，import 路径统一为目录形式

- [ ] Task 1.7: 清理 F-036 死代码残留
  - `brain_alpha_ops/web/_reexports.py:147-158`：`Handler._read_json` 含 `min(length, MAX); if length > MAX: raise` 死代码模式
  - 此 `Handler` 类已被 facade 版本覆盖，生产中不实例化，但死代码仍残留
  - 清理为正确版本（仅 `if length > MAX: raise`）或随 facade 重构一并删除该类
  - 验证：`pytest tests/test_web*.py -x -q` 通过
  - 产出：1 个文件清理

- [ ] Task 1.8: 清理 ToastProvider 空转死代码（W-010 关联）
  - `src/components/Toast.tsx:289-376`：`ToastProvider` 被 App 挂载但 `useToast()` 从未被调用，内部 toasts 永远为空（与 Task 1.1 协调，Toast.tsx 整文件删除）
  - 同时清理 `Toast.tsx` 内部第二个 `ToastContainer`（与 `ToastContainer.tsx` 同名不同实现）
  - 统一类型定义，统一使用 `ToastContainer.tsx` + AppStateContext 的 `notify`/`toasts`
  - App 不再挂载空转 `ToastProvider`
  - 验证：`npm run typecheck` 0 错误；`npm run build` 成功
  - 产出：`Toast.tsx` 删除，Toast 系统统一为单一系统

- [ ] Task 1.9: 清理失效 `brand-*` 类名（W-013 关联）
  - `tailwind.config.js:60` 已用 `accent` 替换 `brand`，但 4 个文件 10 处仍引用 `brand-200/50/500/700/800`，类名解析为空，hover/focus 样式完全不生效
  - 扫描定位 4 个文件 10 处 `brand-*` 引用
  - 替换为 `accent-*` 或迁移到设计令牌（`var(--color-accent-*)`）
  - 重点文件：`StateCards/StateCardItem.tsx` / `StateCards/cardConfigs.ts` / `StateCards/StateCards.tsx` / `SubmissionPanel.tsx`（注意：StateCards/ 和 SubmissionPanel.tsx 在 Task 1.1 中删除，brand-* 引用随之消失，仅需处理 StateCardItem 等保留组件）
  - 验证：`npm run typecheck` 0 错误；`npm run build` 成功；grep `brand-` 在 .tsx 中返回 0
  - 产出：剩余保留组件的 `brand-*` 类名替换为 `accent-*` 或设计令牌

## Phase 2: 核心功能补全（Core Feature Completion）

- [ ] Task 2.1: 修复反过拟合虚假 PASS（Critical F-001/F-002）
  - `brain_alpha_ops/scoring/anti_overfit/service.py:30-56`：`AntiOverfitService.evaluate` fallback 链严格区分 returns/IC 语义，`returns` 不再回退到 `ic_series`/`rank_ic_series`，必要字段缺失时返回 `insufficient_data`（fail-closed）
  - `brain_alpha_ops/scoring/anti_overfit/utils.py:63-69`：`_rank_ic` 按时间窗口（月度/周度）分段计算多元素 IC 列表，使 `ic_std` 反映真实波动
  - 添加单元测试：缺失 returns 时返回 insufficient_data；多窗口 IC 计算正确性
  - 验证：`pytest tests/test_anti_overfit*.py -x -q` 通过
  - 产出：2 个文件修复 + 新增/更新测试

- [ ] Task 2.2: 打通真实浏览器提交流（F-031/F-032）
  - `brain_alpha_ops/runner.py:18-28`：`run_pipeline_from_config` 根据 `run_config.execution_mode` 注入 `BrowserExecutionAdapter` / `ApiExecutionAdapter`
  - 决策 `brain_alpha_ops/execution_factory.py`（已孤立，全项目无 import）：推荐**接入** `runner.py`（已实现 browser/api 切换逻辑），而非删除
  - 若接入：`execution_factory.py:40-44, 65-69` "auto" 模式 playwright 未装时 `logger.warning("playwright unavailable, falling back to API backend")` + 显式传入 `RunConfig`
  - 验证：`pytest tests/test_runner*.py tests/test_execution_factory*.py -x -q` 通过；新增 execution_mode=browser 路径测试
  - 产出：2 个文件修复 + 新增测试

- [ ] Task 2.3: 修复并发参数被忽略与提交门禁 fail-open（F-041/F-012/F-011）
  - `brain_alpha_ops/brain_api/brain_api_bridge.py:84-118`：`concurrent_simulate` / `concurrent_check` 用 `ThreadPoolExecutor` + `_bounded_concurrency` 实现真并发
  - `brain_alpha_ops/brain_api/official_simulation/_mixin.py:299-327`：`check_prod_correlation` API 失败时直接 `raise`（fail-closed）
  - `brain_alpha_ops/browser/execution_adapter.py`：幂等键改 LRU 淘汰而非 FIFO（F-011）
  - 验证：`pytest tests/test_brain_api_bridge*.py tests/test_official_simulation*.py tests/test_browser*.py -x -q` 通过
  - 产出：3 个文件修复 + 新增并发测试

- [ ] Task 2.4: 修复 rolling_validation decay_ratio 符号翻转（F-008）
  - `brain_alpha_ops/research/rolling_validation.py:36-41`：首末窗口符号不同时视为"方向反转"单独处理，不进入 `decay_ratio` 计算
  - 添加测试：首负末正（改善型）候选应通过
  - 验证：`pytest tests/test_rolling_validation*.py -x -q` 通过
  - 产出：1 个文件修复 + 新增测试

- [ ] Task 2.5: 修复 _launch_monitor 凭证剥离与挂起（F-013/F-014/F-015）
  - `_launch_monitor.py:17-44, 76`：`SAFE_CHILD_ENV_KEYS` 改为黑名单（保留 `BRAIN_*` 业务 env + `BRAIN_ALPHA_OPS_*`）
  - `_launch_monitor.py:91, 114`：`for line in proc.stdout` 改为 `select.select` 周期性 `proc.poll()` + 超时 `proc.kill()`
  - `_launch_monitor.py:101, 106-108`：`DONE` 关键字改为结构化结束标记（如 JSON 行带 `event` 字段）；`failed|error` 排除集合扩展为 `{"no_error", "no_errors", "0 errors", "error_count=0"}`
  - 验证：`pytest tests/test_launch_monitor*.py -x -q` 通过（若无可新增）
  - 产出：1 个文件修复

- [ ] Task 2.6: 修复 fetch_official_context 超时与 Retry-After（F-016/F-017）
  - `fetch_official_context.py:365-367`：用 `ThreadPoolExecutor + future.result(timeout=...)` 替代 SIGALRM（Windows 与非主线程可用）
  - `fetch_official_context.py:249-261`：`Retry-After` 用 `email.utils.parsedate_to_datetime` 解析 HTTP-date
  - 新增单元测试覆盖 HTTP-date 解析
  - 验证：手动运行 `python fetch_official_context.py --help` 不报错
  - 产出：1 个文件修复 + 新增测试

- [ ] Task 2.7: 修复 AdaptiveExecutor 与 TimeoutError 语义冲突（F-018/F-019）
  - `brain_alpha_ops/adaptive_executor.py:130-149`：增加 `_closed` 标记，`shutdown()` 置 True，`submit()` 检测到 True 时抛 `RuntimeError("executor is closed")`
  - `brain_alpha_ops/adaptive_executor.py:18-23, 322-336` + `brain_alpha_ops/task_executor.py:8-13, 75-90`：业务超时与执行器超时用 `exc.__cause__` 或独立异常类区分
  - 修正 `task_executor.py:76-78` 在 Python 3.11+ 事实错误的注释（`concurrent.futures.TimeoutError` 已是 `builtins.TimeoutError` 别名）
  - 验证：`pytest tests/test_adaptive_executor*.py tests/test_task_executor*.py -x -q` 通过
  - 产出：2 个文件修复 + 新增测试

- [ ] Task 2.8: 修复 StallMonitor 与 JobStore 持久化（F-024/F-023）
  - `brain_alpha_ops/stall_monitor.py:206-218, 275-282`：`TaskExecutor` 维护 `job_id -> future` 映射，`_auto_interrupt` 时 `future.cancel()` + cooperative cancellation
  - `brain_alpha_ops/tasks/_store.py:56, 241-255, 317-336`：每次启动重新尝试加载，不永久置位 `persistence_load_skipped`，用 try/except 记录失败
  - 验证：`pytest tests/test_stall_monitor*.py tests/test_tasks*.py -x -q` 通过
  - 产出：2 个文件修复 + 新增测试

- [ ] Task 2.9: 修复 Facade 绑定静默吞异常与 fail-open 泛滥（F-034 + 新发现 Critical×8）
  - `brain_alpha_ops/web/__init__.py:153-219`：`_install_facade_bindings()` 拆分为多个独立 try/except，按子系统记录
  - 关键绑定（`Handler` / `serve` / `main` / `dispatch_*`）缺失时 `serve()` 抛硬错拒绝启动，避免"半残"状态（legacy Handler 无 dispatch 绑定）
  - `web/misc/_async_jobs_helpers.py` + `web/misc/_batch_helpers.py`：两处 `_store_is_cancelled` 改 fail-closed
  - `brain_alpha_ops/web/web_security.py`：Host 空时拒绝（不绕过）
  - `brain_alpha_ops/web/handlers/web_submission_single.py`：kill-switch 接真实配置（不永久 True）
  - `brain_alpha_ops/research/pipeline/_api_mixin.py`：429 限流加 `return`（不再继续请求）
  - `brain_alpha_ops/research/pipeline/_backtest_recovery_mixin.py`：改 fail-closed
  - `brain_alpha_ops/research/pipeline/_local_prefilter.py`：评分失败断链修复
  - `brain_alpha_ops/brain_api/official_auth.py`：F-012 改 fail-closed
  - 验证：`pytest tests/test_web*.py -x -q` 通过；新增测试覆盖关键绑定缺失时拒绝启动
  - 产出：9 个文件修复 + 新增测试

- [ ] Task 2.10: 修复假设反馈链路与演化探索（新发现 Critical×3）
  - `brain_alpha_ops/research/hypothesis_library/library.py`：让 `adjust_weight` 写入的 `_hypothesis_weights` 被 `generate` 路径实际读取（接入假设权重到生成逻辑，闭合反馈链路）
  - `brain_alpha_ops/research/evolution/_meta.py`：新后代 `scores=0` 时给予初始存活窗口（如 N 代内不剪枝），不被立即剪枝
  - `brain_alpha_ops/research/convergence/_bootstrap_mixin.py`：空列表除零保护（`if not data: return 0.0`）
  - 验证：`pytest tests/test_hypothesis*.py tests/test_evolution*.py tests/test_convergence*.py -x -q` 通过
  - 产出：3 个文件修复 + 新增测试

- [ ] Task 2.11: 修复 empirical_score 分值架构（新发现 Critical）
  - `brain_alpha_ops/scoring/empirical_score.py`（或相关文件）：排除 hard_gate 分值后满分仅 51 分，`status≥70` 的 "ready" 不可达
  - 重新校准分值权重，使满分 ≥ 100，"ready" 阈值可达
  - 添加测试：满分场景验证；"ready" 阈值可达性验证
  - 验证：`pytest tests/test_empirical_score*.py -x -q` 通过
  - 产出：1-2 个文件修复 + 新增测试

- [ ] Task 2.12: 修复 simulation_scheduler 双 lambda（新发现 Critical）
  - `brain_alpha_ops/research/simulation_scheduler/_scheduler.py`：`event_callback` 双 lambda 默认值改为模块级函数或 None sentinel（避免可变默认参数共享状态）
  - 验证：`pytest tests/test_simulation_scheduler*.py -x -q` 通过
  - 产出：1 个文件修复

- [ ] Task 2.13: 修复 auto_calibrator 失效 import（新发现 Critical）
  - `brain_alpha_ops/research/auto_calibrator/_weight_calibration.py`：移除不存在的 `calibrate_weights.py` import，或创建该模块
  - 验证：`python -c "from brain_alpha_ops.research.auto_calibrator import _weight_calibration"` 不报错
  - 产出：1 个文件修复

- [ ] Task 2.14: 修复 _ratio 边界与 OfficialScoringSystem 加锁（新发现 High×2）
  - `brain_alpha_ops/brain_api/official_helpers/_normalize.py`：`_ratio` 2.0 处不连续修复（统一跨模块 >=2.0 vs >=100 不一致）
  - `brain_alpha_ops/scoring/official_scoring/_history.py`：加锁（threading.Lock 或 asyncio.Lock）防止并发变异
  - 验证：`pytest tests/test_official_helpers*.py tests/test_official_scoring*.py -x -q` 通过
  - 产出：2 个文件修复 + 新增并发测试

- [ ] Task 2.15: 清理 fetch_official_thresholds 死代码（新发现 High）
  - `brain_alpha_ops/brain_api/official_context/_composite.py`：`fetch_official_thresholds` / `merge_dynamic_thresholds` 死代码（W-08 从未接入）—— 接入到评分路径或删除
  - 验证：`pytest tests/test_official_context*.py -x -q` 通过
  - 产出：1 个文件修复（接入或删除）

- [ ] Task 2.16: 修复 Web 层 High 18 处（批量）
  - `web/handlers/post_routes/submit*.py`：硬编码 403 改配置
  - `web/dispatch/web_get_routes/_routes_simulation.py`：导入失败 500 改降级
  - `web/misc/web_assistant_snapshots/_profile.py`：空 glob 处理
  - `web/misc/web_jobs.py`：ASYNC_JOBS OOM 限制大小
  - `web/handlers/_handlers_alpha.py`：record_trend 加锁
  - `web/handlers/_handlers_simulation.py`：批量信息不丢失
  - `web/misc/web_check_availability.py`：12 类检查隔离
  - `web/misc/web_config.py`：run_config_from_payload 修复 TypeError
  - `web/handlers/web_submission_batch.py`：逐候选错误聚合
  - `web/handlers/web_submission_safety/_observability.py`：降级标记
  - `web/web_security.py`：validate_replay 时间戳 skew 修复
  - `web/misc/web_runtime_state.py`：lifecycle_from_job limit=0 修复
  - `web/handlers/phase.py`：NameError 修复
  - `src/api/trends.ts`：字符串比较 TypeError 修复
  - `brain_alpha_ops/research/simulation_scheduler/_types.py`：reset 重置 error_count
  - `brain_alpha_ops/research/presets.py:86`：capability kind 修正
  - `brain_alpha_ops/research/pipeline/_run_mixin.py`：save_run_history 异常吞掉改记录
  - `brain_alpha_ops/research/pipeline/_workers.py`：双评分契约修复
  - 验证：`pytest tests/test_web*.py -x -q` 通过
  - 产出：18 个文件批量修复

## Phase 3: UX 流程优化（UX Flow Optimization）

- [ ] Task 3.1: 合并两套 job 聚合 hook（关键新发现）
  - 现状：两套 hook 真的并行存在且都在生产路径
    - `useJobStatusHook.ts`（385 行，单体式）→ `useJobState` → `useAppState` → 全局 App state
    - `useJobMonitor/index.ts`（153 行，组合式，5 子 hook）→ `JobMonitor.tsx` → dashboard 视图
  - 合并策略：**保留组合式 `useJobMonitor` 架构**（更现代），吸收 `useJobStatusHook` 的状态管理逻辑
  - 消除 `useJobWatchdog` vs `useJobMonitor/useStatusWatchdog` 重叠（合并为 1 个 watchdog）
  - 消除 `useJobSseConnection` vs `useJobMonitor/useSseEventHandler + useSseRetryState` 重叠（合并为 1 套 SSE）
  - 消除 `useJobLifecycle` vs `useJobControl` credentials 处理不一致
  - 目标：1 个聚合 hook + ≤3 个子 hook
  - 过渡期：被合并 hook 在原路径保留 re-export + `DeprecationWarning`
  - 验证：`npm run typecheck` 0 错误；`npm run build` 成功；相关组件测试通过
  - 产出：合并 2 套 hook 为 1 套聚合 hook，删除 5+ 个重叠子 hook 文件

- [ ] Task 3.2: 修复 SSE 断连误取消（U-001，部分缓解后剩余问题）
  - `src/hooks/useJobDisconnectedState.ts:97-128`：已加 status 探活（探活成功且 running 时重连）
  - 剩余问题：探活失败（catch 分支）时仍自动取消；探活返回非 running 状态时仍取消
  - 改为：探活失败时提示"连接断开，云端任务可能仍在运行" + 手动恢复入口，不自动取消
  - 添加"重连"按钮与"手动恢复"入口
  - 验证：手动断网测试，任务不被自动取消；新增测试覆盖断连状态
  - 产出：1 个 hook 修改 + 新增测试

- [ ] Task 3.3: 修复限流倒计时与错误引导（U-002/U-003）
  - 限流倒计时读取 `Retry-After` 头并按实际值倒计时（不再固定 30s）
  - `src/helpers/connectionErrorGuide.ts` 扩展覆盖全部错误类型，提供可操作恢复入口
  - 消除 `connectionErrorGuide` vs `errorExperience` 重叠
  - 验证：手动触发 429 测试倒计时；新增测试覆盖错误引导
  - 产出：2 个文件修改 + 新增测试

- [ ] Task 3.4: 修复配置保存与前台通知（U-004/U-008）
  - 配置保存后 toast 提示"部分配置需重启生效"
  - `useJobNotifications` 接 `Notification API`，前台完成时系统通知（当前空转，需接入实际逻辑）
  - 验证：手动测试配置保存 toast；手动测试前台完成通知
  - 产出：2 个文件修改

- [ ] Task 3.5: 修复轮询 visibility（U-009，间隔已改 60s 但仍不看 visibility）
  - `src/hooks/useGlobalData.ts:98-103`：接 `document.visibilitychange`，隐藏时暂停 60s 轮询
  - 验证：手动切 tab 测试轮询暂停
  - 产出：1 个文件修改

- [ ] Task 3.6: 修复阻断阶段按钮仍可点（W-001）
  - `src/components/PhaseShell.tsx:102-107`：阻断态增加 `pointer-events: none` 或 `inert` 属性
  - 内部可交互元素 `disabled`
  - 视觉灰化 + tooltip 显示阻断原因
  - 验证：手动测试阻断阶段按钮不可点
  - 产出：1 个文件修改

- [ ] Task 3.7: 修复首屏空白、路由 URL、Toast 重复（W-002/W-004/W-010/W-011）
  - `src/components/ErrorBoundary.tsx:57-61`：`handleGoHome` 改用 `onNavigate` prop（已存在），不再 `window.location.hash = ''`
  - `src/main.tsx`：扩展路由表，将 `activeView` 映射到 URL path（如 `/` / `/config` / `/candidates` / `/scoring`），向前兼容内部 state 切换
  - `brain_alpha_ops/web/react_app/index.html:13`：`<div id="root"></div>` 内加 noscript + 内联骨架屏
  - Toast 三套系统合并为单一系统：删除 `Toast.tsx`（与 Task 1.8 协调）；统一使用 `ToastContainer.tsx` + AppStateContext 的 `notify`/`toasts`
  - 消除 `ui.ts` TabId vs CardViewId 双套导航 ID
  - 验证：手动测试首屏不再空白；手动测试路由进 URL；手动测试 Toast 不重复
  - 产出：4 个文件修改/合并

- [ ] Task 3.8: 修复 renderActiveViewFromContext hook 违规（W-007）
  - `src/views/renderViewFromContext.tsx:26-28`：非组件调 hook（用 eslint-disable 压告警）
  - 改为标准组件 `<ActiveViewRenderer />` 或将 hook 提升到父组件
  - 验证：`npm run lint` 不再有该处 eslint-disable；`npm run typecheck` 0 错误
  - 产出：1 个文件重构

## Phase 4: UI 视觉统一（UI Visual Unification）

**注**：设计令牌系统已存在且采用率高（`src/styles/theme-tokens.css` 完整定义 + `tailwind.config.js` oklch 体系，362 处 `var(--` 引用）。本阶段主要是统一采用率 + 修复失效类名 + 修复硬编码值 + 完善暗色主题适配，**不创建新的 tokens.css**。

- [ ] Task 4.1: 完善设计令牌采用率
  - 替换 4 处硬编码 hex 颜色为 `var(--color-*)`（ProgressHeader / DashboardStepProgress / Dashboard）
  - 替换 251 处硬编码 px 间距/字号为 `var(--space-*)` / `var(--font-size-*)`（动态计算除外）
  - 验证：`npm run build` 成功；grep `#[0-9a-fA-F]{3,6}` 在 .tsx 中返回 ≤ 0（动态计算除外）
  - 产出：基础组件硬编码值全部替换为设计令牌

- [ ] Task 4.2: 统一组件视觉语言
  - 审查基础组件（`Button` / `Card` / `Input` / `Modal` / `Toast` / `Tooltip` / `Skeleton` 等），全部使用设计令牌
  - 移除过度的视觉装饰，遵循现代极简原则
  - 修复 `ScoringPanel/Header.tsx` 硬编码 `text-gray-*` / `text-green-*` 等
  - 修复 `Sidebar` 三元表达式两分支相同
  - 验证：`npm run build` 成功；视觉回归测试
  - 产出：基础组件视觉语言统一

- [ ] Task 4.3: 修复 StateCardItem 暗色主题适配（W-013）
  - `StateCardItem.tsx` 硬编码 `border-slate-200` / `bg-white` / `text-slate-950` / `text-slate-600` 已替换为设计令牌
  - `hover:border-brand-200` / `hover:bg-brand-50/40` / `focus:ring-brand-500/50` 等失效类名已修复为 `accent-*`（与 Task 1.9 协调）
  - 手动测试暗色主题切换无白色块
  - 产出：暗色主题适配完成

- [ ] Task 4.4: 重设计 Dashboard 布局
  - 信息密度合理化，卡片对齐与间距统一（使用 `var(--space-*)`）
  - 关键 KPI 突出（大字号 + 强调色），次要信息折叠
  - 响应式：桌面 4 列 / 平板 2 列 / 手机 1 列
  - 手动测试 375px / 768px / 1280px 宽度布局
  - 产出：Dashboard 布局重设计完成

- [ ] Task 4.5: 重设计 ConfigPanel
  - 表单分组清晰（基础 / 高级 / 凭证 / 评分权重）
  - 标签与输入框对齐，验证反馈即时（inline error）
  - 保存按钮状态明确（dirty / saving / saved / error）
  - 手动测试表单填写与保存流程
  - `ConfigPanel.tsx` wrapper 实现结构保持现状（与 Task 1.6 协调）
  - 产出：ConfigPanel 重设计完成

- [ ] Task 4.6: 重设计 CandidateTable
  - 列宽合理，可横向滚动，行密度可调（紧凑/标准/宽松）
  - 移动端切换为卡片视图（复用 `CandidateMobileCard.tsx`）
  - 手动测试大表格滚动 + 移动端卡片视图
  - 产出：CandidateTable 重设计完成

- [ ] Task 4.7: 重设计 ScoringPanel
  - 分数 / 排名 / 归因可视化清晰
  - 颜色语义明确（绿=通过 / 红=阻断 / 黄=警告）
  - 改进建议可折叠
  - 手动测试评分面板展示
  - `ScoringPanel.tsx` facade 对与 Task 1.6 协调
  - 产出：ScoringPanel 重设计完成

- [ ] Task 4.8: 完善移动端布局与暗色主题
  - 最小 375px 宽度适配，底部 tab bar（`MobileTabBar.tsx`）
  - 关键操作悬浮按钮
  - `ThemeProvider` 暗色主题令牌映射完善，所有组件双主题适配
  - 手动测试 375px 宽度 + 暗色主题切换
  - 产出：移动端布局与暗色主题完善

## Phase 5: 测试清理与回归验证（Test Cleanup & Regression）

- [ ] Task 5.1: 清理测试死代码（新发现 Critical×9）
  - 删除 `tests/test_review_gap_closure_tracker.py` 重复副本（1056 行 ×2 → 1 份）
  - 4 个 qa_*.py 永久 skip（~3200 行）：`qa_e2e_new_user_walkthrough.py` / `qa_full_chain_backend.py` / `qa_full_chain_frontend.py` / `qa_hypothesis_system.py` —— 评估能否修复并启用，或删除
  - 修复 `tests/test_input_validation.py:44-60` 两个死测试（加断言）
  - 修复 `tests/test_local_quality.py:48-49` test_nesting_depth 死断言（仅断言 >=0）
  - 修复 `tests/test_dataset_id_missing.py` CapabilityResolutionError fall through
  - 修复 `tests/test_infrastructure_modules.py` AdaptiveExecutor shutdown 重建盲区
  - 修复 `tests/test_web_html.py` 4 个 Dead Test
  - 修复 `tests/test_web_edge_cases.py` 永真断言
  - 验证：`pytest tests/ -x -q` 不新增 failure
  - 产出：清理 ~4200 行死测试/永久 skip 测试，修复薄弱断言

- [ ] Task 5.2: 保留 re-export 兼容层（过渡期）
  - 旧扁平名 import 路径保留 re-export + `DeprecationWarning`
  - 被合并的 job 聚合 hook 原路径保留 re-export + `DeprecationWarning`
  - Toast 系统原路径保留 re-export
  - 验证：`python -c "import brain_alpha_ops.web_routes"` 触发 DeprecationWarning 但不报错
  - 产出：re-export 兼容层就位

- [ ] Task 5.3: 测试同步更新
  - `tests/test_web*.py` import 路径与 mock 目标已同步（双调度迁移、`dispatch_get/dispatch_post` 删除）
  - `tests/test_runtime_constants.py` 等已同步（helper 合并）
  - `tests/test_official_workflow*.py` / `tests/test_pipeline_services*.py` 等已同步（孤立模块删除）
  - `tests/test_decoupled_pipeline*.py` 已同步（整包死代码删除）
  - 前端 hook 测试已同步（useJob 聚合 hook 合并）
  - `_ratio` 跨模块不一致（>=2.0 vs >=100）统一
  - `test_rolling_validation` 覆盖 decay_ratio 符号翻转
  - 验证：`pytest tests/ -x -q` 无新增 failure
  - 产出：测试与生产代码同步

- [ ] Task 5.4: 全量回归测试
  - `pytest tests/ -x -q` passed ≥ 2874
  - `pytest tests/ -x -q` failed ≤ 133
  - 无新增 failure（与 baseline 失败集合一致或更少）
  - `npm run typecheck` exit code 0
  - `npm run lint` warnings 数 ≤ baseline
  - `npm run build` 成功
  - 回归测试报告已记录
  - 产出：回归测试通过

- [ ] Task 5.5: 冒烟测试
  - `/api/health` 返回 200
  - 关键 GET 端点冒烟通过（`/api/jobs` / `/api/candidates` / `/api/config` / `/api/trends`）
  - 前端路由冒烟通过（`/` / `/config` / `/candidates` / `/scoring`，验证路由进 URL）
  - SSE 连接 `/api/jobs/sse` 可连接
  - 配置保存 POST `/api/config` 成功
  - 候选生成流程 POST `/api/jobs` 可触发
  - 冒烟测试报告已记录
  - 产出：冒烟测试通过

- [ ] Task 5.6: Docker 构建验证
  - `docker build -t brain-alpha-ops:refactor .` 成功
  - Docker 镜像大小 ≤ baseline + 10%
  - 多阶段构建保持有效（runtime 阶段不含 node_modules / tests / .pyc）
  - `docker run` 启动验证成功
  - Docker 构建报告已记录
  - 产出：Docker 构建验证通过
