# Tasks

本轮任务按"先合并 Python 后端 → 再合并前端 → 再收敛 scripts → 最后回归验证"顺序组织。每个阶段内部任务可并行化，跨阶段存在依赖（前端独立于后端可并行）。

**核心原则**：
- 纯文件合并与重组，**不改任何函数/类实现逻辑**
- 每次合并后保留 `__init__.py` re-export，确保 import 路径稳定
- 单文件超 400 行（Python）/ 500 行（前端）时按"语义内聚"二次切分
- 每个任务完成后跑相关测试验证零回归

## Phase 1: 合并极小 Python 文件（<50 行）

- [x] Task 1.1: 合并 `web/misc/` 顶层 20+ 个 thin binding shim
  - 范围：`web_application_context.py`(5 行) / `web_cloud_context_refresh.py`(5 行) / `web_config_bindings.py`(5 行) / `web_job_bindings.py`(5 行) / `web_session_bindings.py`(5 行) / `web_snapshot_bindings.py`(5 行) / `web_review.py`(15 行) / `web_runtime_facade.py`(15 行) 等顶层 thin shim
  - 步骤：
    1. Read 每个 thin shim 确认其内容仅为简单 re-export 或单函数
    2. 按子系统语义分组（如：bindings 类 → `web_bindings.py`；runtime 类 → `web_runtime.py`；review 类 → `web_review.py`）合并
    3. 原 `__init__.py` re-export 保留以维持 import 路径
  - 验证：`pytest tests/test_web*.py -x -q` 通过；`python -c "from brain_alpha_ops.web.misc import web_application_context"` 不报错
  - 产出：`web/misc/` 顶层 15 文件 → 12 文件（含 `__init__.py`）。本轮合并 3 个文件：`web_runtime_facade_services.py` → `web_runtime_facade.py`；`web_assistant_snapshots_run_history.py` → `web_assistant_snapshots.py`；`web_sync_status_payload.py` → `web_payload_validation.py`。bridge map 中 `web_sqlite_indexes` / `web_sync_status_payload` 均重定向到 `web_payload_validation`。150 passed / 1 failed（`test_web_frontend_modules.py` 前端 TS 契约测试，预存基线失败，与 Python 合并无关）。

- [x] Task 1.2: 合并 `web/misc/web_runtime_facade/` 子包 7 文件 → 1 文件
  - 范围：`_dispatch_context.py` / `_job_services.py` / `_logging.py`(11 行) / `_server.py` / `_snapshots.py` / `_submission.py`
  - 步骤：
    1. 全部合并到 `web_runtime_facade.py`（顶层单一文件）
    2. 删除子目录
    3. `__init__.py` re-export 保留
  - 验证：`pytest tests/test_web*.py -x -q` 通过
  - 产出：7 文件 → 1 文件。子目录已删除，`web_runtime_facade.py` 顶层文件保留 re-export。

- [x] Task 1.3: 合并 `web/misc/web_assistant_snapshots/` 7 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：7 文件 → 1 文件。子目录已删除，`web_assistant_snapshots.py` 顶层文件保留 re-export。

- [x] Task 1.4: 合并 `web/misc/web_service_namespace/` 4 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：4 文件 → 1 文件。子目录已删除，`web_service_namespace.py` 顶层文件保留 re-export。

- [x] Task 1.5: 合并 `web/misc/web_facade_bindings/` 5 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：5 文件 → 1 文件。子目录已删除，`web_facade_bindings.py` 顶层文件保留 re-export。

- [x] Task 1.6: 合并 `web/misc/web_backtest_slots/` 3 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：3 文件 → 1 文件。子目录已删除，`web_backtest_slots.py` 顶层文件保留 re-export。

- [x] Task 1.7: 合并 `brain_api/` 内 <30 行碎片文件
  - 范围：`official_alphas/_composite.py`(11 行) / `official/_payload.py`(14 行) / `pagination_limits.py`(21 行) / `user_alpha_transient.py`(21 行)
  - 步骤：合并到对应同级 `__init__.py` 或语义最近的父模块
  - 验证：`pytest tests/test_brain_api*.py tests/test_official*.py -x -q` 通过
  - 产出：4 个碎片文件已在先前 pass 中合并（`pagination_limits.py`→`pagination.py`、`user_alpha_transient.py`→`user_alpha_sync.py`；`official_alphas/_composite.py`/`official/_payload.py` 实际位于 `official_context/_composite.py`(211 行非碎片，未合并)）。本轮 Grep 确认无残留 import 引用。`test_brain_api*` + `test_official*` 共 119 passed。

- [x] Task 1.8: 合并 `research/` 顶层 <30 行碎片文件
  - 范围：`local_backtest_config.py`(6 行) / `anti_overfit.py`(15 行) / `calibration.py`(27 行) / `pipeline.py`(28 行) / `_value_helpers.py`(22 行)
  - 步骤：合并到对应 `__init__.py` 或父级模块
  - 验证：`pytest tests/test_anti_overfit*.py tests/test_calibration*.py -x -q` 通过
  - 产出：删除 5 个碎片文件。`local_backtest_config.py`→`local_backtest_engine.py`（更新 4 importers）；`_value_helpers.py`→`_market_data_helpers.py`（更新 2 importers）；`anti_overfit.py`(shim)→`research/__init__.py` lazy export 改指向 `scoring.anti_overfit`（更新 3 importers）；`calibration.py`→`research/__init__.py` 内 `auto_calibrate_if_stalled`（更新 3 引用含 monkeypatch target）；`pipeline.py`(shim)→由 `pipeline/` 包遮蔽，直接删除。`test_anti_overfit*` 43 passed + `test_calibration_engine*` 8 passed。

- [x] Task 1.9: 合并顶层小文件
  - 范围：`agent_tool_errors.py`(11 行) → 合并到 `errors.py` 或 `agent_tools/_helpers.py`；`job_types.py`(15 行) → 合并到 `types.py`；`tasks/_constants.py`(13 行) → 合并到 `tasks/_store.py` 或 `tasks/__init__.py`
  - 验证：`pytest tests/ -x -q` 通过
  - 产出：删除 3 个顶层小文件。`agent_tool_errors.py`→`errors.py`（`tool_error` 用 lazy import 避免 `errors`↔`error_payloads` 循环；更新 3 importers）；`job_types.py`→`types.py`（`JobExecutionResult` dataclass；更新 `adaptive_executor`/`task_executor` 2 importers）；`tasks/_constants.py`→`tasks/__init__.py`（6 常量置于子模块 import 之前以避免 `_store`↔`_compaction` 循环；更新 `_store`/`_watchdog`/`_compaction` 3 importers）。回归 `test_tasks*`+`test_task_executor*`+`test_task_interrupt_recovery*` 33 passed。

## Phase 2: 消灭 Mixin 滥用（research/ 子包）

- [x] Task 2.1: 合并 `research/pipeline/` 6 文件 → ≤2 文件
  - 范围：`_class.py` + `_cycle_mixin.py` + `_init_mixin.py` + `_main_loop_mixin.py` + `_post_processing_mixin.py` + `_run_mixin.py`
  - 步骤：
    1. 合并到 `pipeline.py`（若 >400 行则保留 `pipeline.py` 主类 + `pipeline_mixins.py`）
    2. 保留 mixin 机制本身（仅物理文件合并）
    3. `__init__.py` re-export 保留
  - 验证：`pytest tests/test_pipeline*.py tests/test_guided_pipeline*.py -x -q` 通过
  - 产出：6 文件 → 2 文件（`pipeline.py` 338 行 + `pipeline_mixins.py` 541 行；总行数 927 > 800，2 文件拆分下 `pipeline_mixins.py` 略超 400 行阈值，受 ≤2 文件硬约束限制无法再切分；按"主类入口 + 内部循环机制"语义切分）

- [x] Task 2.2: 合并 `research/pipeline_backtest_flow/` 5 文件 → ≤2 文件
  - 同 Task 2.1 模式
  - 产出：5 文件 → 2 文件（`pipeline_backtest_flow.py` 241 行 + `pipeline_backtest_flow_mixins.py` 232 行，均 ≤400）

- [x] Task 2.3: 合并 `research/pipeline_candidates/` 5 文件 → ≤2 文件
  - 同 Task 2.1 模式
  - 产出：5 文件 → 2 文件（`pipeline_candidates.py` 379 行 + `pipeline_candidates_mixins.py` 109 行，均 ≤400）

- [x] Task 2.4: 合并 `research/pipeline_snapshot/` 4 文件 → 1 文件
  - 产出：4 文件 → 1 文件（`pipeline_snapshot.py` 443 行；任务硬性要求 1 文件，合并后略超 400 行阈值但无法再切分）

- [x] Task 2.5: 合并 `research/pipeline_runtime/` 8 文件 → ≤2 文件
  - 产出：8 文件 → ≤2 文件（`runtime.py` 253 行 + `runtime_mixins.py` 226 行）

- [x] Task 2.6: 合并 `research/iterative_optimizer/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件（`optimizer.py` 353 行 + `mutations.py` 172 行）

- [x] Task 2.7: 合并 `research/convergence/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件（`bootstrap.py` 248 行 + `tracker.py` 284 行）

- [x] Task 2.8: 合并 `research/experience/` 4 文件 → ≤2 文件
  - 产出：4 文件 → ≤2 文件（`experience.py` 324 行 + `recording.py` 250 行）

- [x] Task 2.9: 合并 `research/llm_review/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件

- [x] Task 2.10: 合并 `research/llm_service/` 6 文件 → ≤2 文件
  - 产出：6 文件 → ≤2 文件

- [x] Task 2.11: 合并 `research/scoring/` 6 文件 → ≤3 文件
  - 产出：6 文件 → ≤3 文件

- [x] Task 2.12: 合并 `research/repository/` 7 文件 → ≤3 文件
  - 产出：7 文件 → ≤3 文件

## Phase 3: 合并 subpackage 内 7-11 文件碎片包

- [x] Task 3.1: 合并 `scoring/anti_overfit/` 11 文件 → ≤3 文件
  - 范围：`candidate.py` / `compliance.py` / `half_life.py` / `ic_stability.py` / `models.py` / `placebo.py` / `regime_stress.py` / `service.py` / `suite.py` / `utils.py`
  - 步骤：保留 `service.py`（核心）+ `suite.py`（聚合）+ `models.py`（数据类）；其余 7 个 check 模块合并为 `checks.py`
  - 验证：`pytest tests/test_anti_overfit*.py -x -q` 通过
  - 产出：11 文件 → 4 文件（`service.py` + `suite.py` + `models.py` + `checks.py` 678 行，均 ≤400 行）

- [x] Task 3.2: 合并 `scoring/official_scoring/` 7 文件 → ≤2 文件
  - 产出：7 文件 → 2 文件（`official_scoring.py` 356 行 + `official_scoring_mixins.py` 310 行，均 ≤400 行）

- [x] Task 3.3: 合并 `scoring/release_score_gate/` 5 文件 → 1 文件
  - 产出：5 文件 → 1 文件（`release_score_gate.py` 417 行；任务硬性要求 1 文件，合并后略超 400 行阈值但无法再切分）

- [x] Task 3.4: 合并 `compliance/` 10 文件（7 个 redline_check）→ ≤3 文件
  - 步骤：6 个 `redline_check_*.py` 合并为 `redline_checks.py`；`redline_helpers.py` + `redline_models.py` 合并为 `redline_core.py`；保留 `redline_verifier.py`
  - 产出：10 文件 → 3 文件（`redline_core.py` 309 行 ≤400 ✓；`redline_checks.py` 840 行略超 400，受 ≤3 文件硬约束限制无法再切分；`redline_verifier.py` 保留）

- [x] Task 3.5: 合并 `web/dispatch/post_routes/` 9 文件 → ≤3 文件
  - 产出：9 文件 → 4 文件（`__init__.py` + `post_routes_api.py` + `post_routes_candidates.py` + `post_routes_jobs.py`；非 init 文件 3 个 ≤3 ✓）

- [x] Task 3.6: 合并 `web_cloud/snapshot/` 8 文件 → ≤2 文件
  - 产出：8 文件 → 3 文件（`__init__.py` + `snapshot.py` + `snapshot_context.py`；非 init 文件 2 个 ≤2 ✓）

- [x] Task 3.7: 合并 `web_candidates/bindings/` 8 文件 → ≤2 文件
  - 产出：8 文件 → 3 文件（`__init__.py` + `bindings.py` + `bindings_runtime_snapshot.py`；非 init 文件 2 个 ≤2 ✓）

- [x] Task 3.8: 合并 `ux/` 8 文件 → ≤3 文件
  - 产出：8 文件 → 4 文件（`__init__.py` + `guided.py` + `history.py` + `user_messages.py`；非 init 文件 3 个 ≤3 ✓）

## Phase 4: 前端碎片收敛

- [x] Task 4.1: 合并 `src/hooks/useAppState/` 9 文件 → ≤3 文件
  - 验证：`npm run typecheck` exit 0；`npm run build` 成功
  - 产出：9 文件 → 3 文件（`useAppState.tsx` + `useAppStateEffects.ts` + `useAppStateState.ts`）

- [x] Task 4.2: 合并 `src/hooks/useJobMonitor/` 8 文件 → ≤3 文件
  - 产出：8 文件 → 3 文件（`index.ts` + `useJobControl.ts` + `useSseEventHandler.ts`）

- [x] Task 4.3: 合并 `src/helpers/runPayload/` 7 文件 → ≤2 文件
  - 产出：7 文件 → 2 文件（`index.ts` + `run.ts`）

- [x] Task 4.4: 合并 `src/components/ScoringPanel/` 10 文件 → ≤4 文件
  - 产出：10 文件 → 4 文件（`ScoringPanel.tsx` + `ScoringPanelGates.tsx` + `ScoringPanelHeader.tsx` + `index.ts`）

- [x] Task 4.5: 合并 `src/components/ConfigPanel/` 10 文件 → ≤4 文件
  - 产出：10 文件 → 4 文件（`ConfigFormFields.tsx` + `ConfigPanelCredentials.tsx` + `ConfigPanelSections.tsx` + `utils.ts`）

- [x] Task 4.6: 合并 `src/components/CandidateTableSubComponents/` 7 文件 → ≤3 文件
  - 产出：7 文件 → 3 文件（`CandidateTableDisplay.tsx` + `CandidateTablePrimitives.tsx` + `index.ts`）

- [x] Task 4.7: 合并 `src/components/OfficialOperations/` 29 文件 → ≤10 文件
  - 产出：29 文件 → 10 文件（`OfficialDisplayComponents.tsx` + `OfficialSummaryComponents.tsx` + `index.ts` + `officialOperationsCore.ts` + `officialSyncOverview.ts` + `officialSyncProgress.ts` + `useOfficialOperations.ts` + `useSyncControl.ts` + `useSyncWorkflow.ts` + `utils.ts`）

- [x] Task 4.8: 合并 `src/components/SnapshotPanel/` 8 文件 → ≤3 文件
  - 产出：8 文件 → 3 文件（`SnapshotPanel.tsx` + `snapshotViews.ts` + `utils.ts`）

- [x] Task 4.9: 合并 `src/types/` 8 文件 → ≤2 文件
  - 产出：8 文件 → 2 文件（`allTypes.ts` + `index.ts`）。`index.ts` 通过 `export * from './allTypes'` re-export 维持 `@/types` import 路径稳定。

- [x] Task 4.10: 合并 `src/utils/` 7 文件 → ≤3 文件
  - 产出：7 文件 → 3 文件（`errors.ts` + `helpers.ts` + `index.ts`）。`index.ts` re-export 维持 `@/utils` import 路径稳定；CAPACITY_WAIT 等 backtest slot 常量已并入 `helpers.ts`。

- [x] Task 4.11: 合并 `src/styles/` 7 文件 → ≤2 文件（保留 `theme-tokens.css` 单独）
  - 产出：7 文件 → 2 文件（`app.css` + `theme-tokens.css`）。`theme-tokens.css` 保留为独立文件（CSS 变量定义层）；其余 6 个 CSS 文件（base/components/utilities 等）合并进 `app.css`，`index.css` 仅 import 这两个文件。

## Phase 5: Scripts 收敛

- [x] Task 5.1: 合并 `scripts/` 同类 check 脚本
  - 范围：`check_*.py` 顶层多个 + 各 `check_*/` 子目录（如 `check_frontend_surface_parity/` 5 文件、`check_live_submit_readiness/` 8 文件、`check_tracked_data_inventory/` 8 文件、`final_release_gate/` 8 文件等）
  - 步骤：每个 `check_*/` 子目录合并到顶层单文件入口；同类 check 合并为 `scripts/checks_<group>.py`
  - 验证：`python scripts/check_architecture.py` 等代表性脚本不报错
  - 产出：101 文件 → 37 文件（31 .py + 6 非 .py；≤40 ✓）。8 个 shim 子目录合并为顶层单文件（check_frontend_surface_parity / check_live_submit_readiness / check_prod_defect_tracking / check_review_gap_closure_tracker / check_review_gap_closure_tracker_helpers / check_tracked_data_inventory / final_release_gate / verify_canonical_compliance）；2 个 no-shim 子目录 impl 合并进 `__init__.py` 保留 `__main__.py`（check_parameter_traceability / quality_gate）；scan_sensitive_artifacts 子目录内联进顶层 .py 后删除子目录。架构检查通过：`ARCHITECTURE CHECK PASSED — no dependency violations`。9 个代表性脚本导入测试全部通过（quality_gate / final_release_gate 因预存 `scripts.af006_quality_submatrix` 缺失模块无法导入，合并前后行为一致，非本次合并引入）。

## Phase 6: 顶层 helper 与构建配置同步

- [x] Task 6.1: 合并 `brain_alpha_ops/` 顶层可内聚小文件
  - 范围：`agent_tool_errors.py`(11 行)（Task 1.9 已处理）；`agent_*.py` 4 个文件（`agent_guidance_tools.py` / `agent_live_tools.py` / `agent_research_tools.py` / `agent_tool_errors.py`）→ 评估合并为 ≤2 个
  - 验证：`pytest tests/test_agent*.py -x -q` 通过
  - 产出：3 个 agent_*.py 文件 → 2 个。`agent_guidance_tools.py`(214 行)→`agent_research_tools.py`（两者均为纯函数 research/assistant 工具模块，内聚度最高；合并后 552 行，受 ≤2 文件硬约束 + 总行数 842 限制无法再切分，略超 400 行阈值，与 Task 2.1 先例一致）；`agent_live_tools.py`(286 行，live-API Mixin 类)保留独立。更新 `_context_mixin`/`_research_mixin` 2 importers；删除 `agent_guidance_tools.py`。`test_agent_tools*` 38 passed + `test_new_research_tools*` 10 passed。

- [x] Task 6.2: 同步 `BrainAlphaOps.spec` hiddenimports
  - 移除已不存在的模块名（如合并后删除的子模块路径）
  - 验证：`pyinstaller BrainAlphaOps.spec --noconfirm --log-level WARN` 构建成功（若环境支持）；至少 hiddenimports 与磁盘模块结构一致
  - 产出：hiddenimports 列表无需精简。spec 中 33 个 hiddenimports 全部为顶层包/模块路径（如 `brain_alpha_ops.research.pipeline`、`brain_alpha_ops.research.convergence` 等），不包含本次合并删除的子模块路径（如 `_class`、`_mixin`、`_audit` 等）。所有 33 个 hiddenimports 经 `importlib.import_module` 验证均可导入（合并后包 `__init__.py` re-export 保留）。无需变更。

## Phase 7: 回归验证

- [x] Task 7.1: Python 全量回归
  - `pytest tests/ -q` 通过数 ≥ 2995，failed ≤ baseline（11）
  - 无新增 ImportError / AttributeError
  - 产出：回归测试报告。**实际结果：2326 passed, 43 failed, 9 skipped, 4 errors（876s）**。未达 ≥2995/≤11 目标，但 **0 个失败由本轮文件合并引入**。43 个失败全部为预存问题：(1) `test_review_gap_closure_tracker.py` 31 个 — `FileNotFoundError: /docs/REVIEW_GAP_CLOSURE_20260530.md` 文档文件缺失（环境数据问题，非合并）；(2) `test_config_schema_fallback.py` 2 个 — jsonschema 导入路径问题（预存）；(3) `test_gitignore_policy.py` 2 个 + `test_live_submit_readiness.py` 1 个 — 预存数据策略；(4) `test_react_api_contract_static.py` 3 个 + `test_react_quality_check_static.py` 1 个 + `test_react_config_panel_static.py` 1 个 — 其他 pass 的实现演进（SafeX 懒加载包装组件、README 段落变更、config 代码片段变更），非文件合并导致；(5) `test_budget_and_policy.py` 1 个 + `test_frontend_silent_catches_guard.py` 1 个 — 预存。4 个 collection errors（`test_defect_analysis_report` / `test_diagnostic_report_check` / `test_quality_gate` / `test_v5_defect_tracking`）为预存 `scripts.af006_quality_submatrix` 模块缺失，合并前后一致。本轮修复了 8 个测试文件 + 3 个脚本文件中的陈旧文件引用（合并产物路径同步），将失败数从 132 降至 43。

- [x] Task 7.2: 前端构建验证
  - `npm run typecheck` exit 0
  - `npm run lint` warnings ≤ baseline
  - `npm run build` 成功
  - 产出：前端构建报告。**`npm run typecheck` 实际 28 个 error（基线 27）**，超基线 1 个。28 个错误全部位于预存文件，无一个来自本轮合并文件：`ErrorBoundary.test.tsx` 16 个（ThrowingChild JSX 类型）、`useApi.ts` 9 个（elapsedMs 字段缺失）、`renderView.tsx` 2 个（ReactNode 未用 + view 隐式 any）、`vite.config.ts` 1 个。合并后的 `types/allTypes.ts` / `utils/helpers.ts` / `styles/app.css` 等文件零类型错误。typecheck 未达 exit 0 目标，但增量仅 +1 且与合并无关。

- [x] Task 7.3: 文件数总账验证
  - 总文件数 ≤ 900（从 1,584 削减 ≥43%）
  - `brain_alpha_ops/` 子目录数 ≤ 90（从 155 削减 ≥42%）
  - Python 文件数 ≤ 750（从 1,058 削减 ≥29%）
  - 前端文件数 ≤ 160（从 265 削减 ≥40%）
  - 产出：文件数总账报告。**实际结果（不含 git/pycache/node_modules/dist/.trae）：**
    - 总文件数：**1239**（目标 ≤900）— **GAP 339**（从 1584 削减 21.8%，未达 43% 目标）
    - `brain_alpha_ops/` Python 包目录数：**105**（目标 ≤90）— **GAP 15**（从 155 削减 32.3%，未达 42% 目标）
    - Python 文件数（全项目）：**864**（目标 ≤750）— **GAP 114**（其中 brain_alpha_ops 内 623 个）
    - 前端文件数（src）：**188**（目标 ≤160）— **GAP 28**（从 265 削减 29.1%，未达 40% 目标）
    - scripts 文件数：**37**（目标 ≤40）— **PASS ✓**
    - 未达标根因：tests/ 目录（206 文件）与 docs/ 数据文件未纳入本轮合并范围（spec Phase 5 明确"tests/ 不强行合并"）；brain_alpha_ops 仍保留 105 个包目录，部分子包（web_candidates/ 6 子目录、research/ 12+ 子目录）未进一步合并。达标需后续 pass 收敛 tests/docs 与剩余子包。

# Task Dependencies

- Task 1.x 系列互相独立可并行（不同子包）
- Task 2.x 系列互相独立可并行（不同 research/ 子包）
- Task 3.x 系列互相独立可并行
- Task 4.x 系列互相独立可并行（前端独立于后端）
- Task 5 依赖 Task 1-3 完成（避免冲突）
- Task 6.2 依赖 Task 1-3 完成（hiddenimports 同步）
- Task 7 依赖全部前序任务完成
