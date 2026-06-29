# Tasks

本任务清单严格遵循用户硬约束：**未读完全部代码前，禁止输出任何评估结论**。因此 Phase 1 必须全部完成后才能进入 Phase 2 汇总，Phase 2 完成后才能进入 Phase 3 报告产出。

## Phase 1: 全量源码深读（并行子智能体）

每个子智能体产出一份**纯 findings 备忘录**（不输出报告），仅记录在该子系统中发现的具体问题，含 `file:line` 引用、根因、影响、严重级别、维度归类（Functional / UX / WebUI）。子智能体 SHALL NOT 修改任何代码。

- [ ] Task 1: 深读后端 `research/` 子系统
  - 范围：`brain_alpha_ops/research/` 全部 `.py` 文件（含子包 `alpha_quality/` / `backtest_flow_service/` / `expression_index/` / `generator/` / `hypothesis_expression_support/` / `scoring/` / `validated_generator/` 及顶层散落 90+ 文件如 `pipeline*.py` / `backtest_*.py` / `local_backtest*.py` / `parallel_backtest.py` / `candidate_pool.py` / `fusion*.py` / `evolution_helpers.py` / `hypothesis_*.py` / `rolling_validation.py` / `prod_correlation.py` / `checkpoint.py` / `record_sqlite_index.py` 等）
  - 焦点：逻辑漏洞、异常处理缺失、核心流程阻塞、状态机不一致、并发不安全、数值正确性（Pearson/Spearman/IC/BCa bootstrap/regime/placebo/decay_ratio）、资源泄漏、数据丢失/污染、死代码导致功能失效
  - 产出：findings 备忘录（Functional 为主）

- [ ] Task 2: 深读后端 `scoring/` + `compliance/` + `audit_trail/` 子系统
  - 范围：`brain_alpha_ops/scoring/`（含 `anti_overfit/` / `official_scoring/` / `release_score_gate/`）、`brain_alpha_ops/compliance/`（全部 redline_check_*.py）、`brain_alpha_ops/audit_trail/`（writer.py / quality_gate.py / lifecycle_writer.py / anti_overfit.py / export.py / query.py）
  - 焦点：反过拟合虚假 PASS、Quality Gate 审计失败跳过状态转换、release_score_gate settings/metrics 混淆、redline 检查覆盖率/对齐/阈值/可追溯性、审计 64KB 截断丢失关键字段、placebo seed 固定、ic_stability 上限不对称
  - 产出：findings 备忘录（Functional 为主）

- [ ] Task 3: 深读后端 `brain_api/` + `browser/` + `web_candidates/` + `web_cloud/` 子系统
  - 范围：`brain_alpha_ops/brain_api/`（official/ 全部子包 + api_execution_adapter.py + canonical.py + rate_limit_policy.py + pagination_limits.py + user_alpha_sync.py + user_alpha_transient.py）、`brain_alpha_ops/browser/`（execution_adapter/ + brain_ui_runner.py + monitor.py）、`brain_alpha_ops/web_candidates/`（audit/bindings/decisions/generation/optimization/simulation/simulation_state 全部子包）、`brain_alpha_ops/web_cloud/`（snapshot/ + sync_job/ + context_refresh.py + snapshot.py + sync_payload.py）
  - 焦点：浏览器驱动真实提交流缺失、提交幂等键淘汰可重放、Browser 登录判定误判、ApiExecutionAdapter 公开真实提交入口、并发超限 deferred 被计为 failed、ProdCorrelation 本地回退放行、snapshot 缓存陈旧、sync_job 心跳线程异常退出、backtest_polling 槽位永不释放、MAX_USER_ALPHAS_PAGES 无界、cloud alpha 元数据 freshness
  - 产出：findings 备忘录（Functional 为主）

- [ ] Task 4: 深读后端 `monitoring/` + `production_diagnostics/` + `data/` + `config/` + `agent_tools/` + `agent_tool_registry/` + `shared/` + `tasks/` + `ux/` + `i18n/` + `e2e_report/` + `examples/` 子系统
  - 范围：上述全部子包，含 `data/ashare_adapter/`（如存在）、`data/field_dataset_mapper.py`、`data/cache_metadata.py`、`data/schemas.py`、`config/_loader.py`、`agent_tools/` 全部 mixin、`ux/errors/` + `ux/guided_pipeline/`、`tasks/` 全部、`monitoring/evidence.py` + `production_health.py` + `unified_monitor.py`、`production_diagnostics/_probes.py` + `_snapshot.py` + `_analysis.py`
  - 焦点：ashare load_index_universe 缓存键陈旧、FieldDatasetMapper 并发不安全、redaction 反向排除集漏脱凭证、stall_monitor 不真正中断、error_catalog KeyError 误分类、capability_registry language kind 复用、Evidence cleanup 单点失败中断循环、诊断快照无探针隔离、JobStore 持久化跳过后永久失效、guided_pipeline threading 超时不可取消
  - 产出：findings 备忘录（Functional 为主）

- [ ] Task 5: 深读 web 层非前端代码（`web/` 除 `react_app/`）
  - 范围：`brain_alpha_ops/web/` 全部 `.py`：`api/` / `business/` / `candidates/` / `config/` / `dispatch/`（get_routes/post_routes/web_dispatch_context/web_get_routes/web_http_handler 全部子包）/ `handlers/` / `misc/`（web_assistant_snapshots/web_backtest_slots/web_facade_bindings/web_runtime_facade/web_service_namespace 等全部）/ `security/`（web_session + web_csp + web_security）/ `state/` / `submissions/`（web_submission_safety + 单/批量提交）/ 顶层 `web_*.py` 文件 / `ws.py` / `_reexports.py`
  - 焦点：facade 绑定安装失败静默吞异常、secure_cookies HTTP 下强制 True、web_security 空 Host 绕过 + replay timestamp 单位失效、提交异常 str(exc) 直出绕过脱敏、Content-Length 未校验、JobStore 读操作有 watchdog 副作用、_status_payload 字符串排序错位、trends 写入并发不安全、compute_run_stats 接桩返回零、WebApplicationContext 白名单含安全函数、CSP 配置、CSRF 实现、SSE 兼容性
  - 产出：findings 备忘录（Functional + UX）

- [ ] Task 6: 深读顶层入口 + 桥接 + 配置/构建/CI 文件
  - 范围：`/workspace/launch_web.py` / `_launch_monitor.py` / `build_prod.py` / `fetch_official_context.py` / `brain_alpha_ops/_web_bridge.py` / `_config_domain_helpers.py` / `_runtime_constants_helpers.py` / `_config_schema_helpers.py` / `_types_extras.py` / `backend_registration.py` / `execution_backend.py` / `execution_factory.py` / `adaptive_executor.py` / `task_executor.py` / `runner.py` / `mcp_server.py` / `candidate_lifecycle.py` / `stall_monitor.py` / `runtime_constants.py` / `secure_credentials.py` / `redaction.py` / `errors.py` / `error_catalog.py` / `error_knowledge.py` / `error_payloads.py` / `metrics.py` / `observability.py` / `models.py` / `types.py` / `presets.py` / `code_quality.py` / `parameter_audit.py` / `submission_readiness.py` / `live_submit_readiness_assessment.py` / `registry_validation.py` / `config_*.py` / `dataset_defaults.py` / `expression_normalizer.py` / `jsonl.py` / `job_types.py` / `core_state.py` / `shared_bounds.py` / `agent_*_tools.py` / `agent_tool_errors.py` / `build_inline.py` / `diagnosis_gap_coverage.py` / `official_context_datasets.py` / `payloads.py`（顶层 web_candidates.payloads.py）/ `pyproject.toml` / `Dockerfile` / `docker-compose.yml` / `environment.yml` / `requirements.lock` / `.github/workflows/*.yml`
  - 焦点：_launch_monitor 子进程挂起无限阻塞 + DONE 关键字误判 + failed|error 误报 + sanitized_child_env 剥离凭证、fetch_official_context SIGALRM Windows 失效 + 不支持 HTTP-date Retry-After、adaptive_executor.shutdown 后 submit 重建池、task_executor Python 3.11+ TimeoutError 语义冲突 + submit 失败 job 卡 running、Docker root 运行 + chmod 777、CI continue-on-error、_launch_monitor 无端口/URL 输出、launch_web 首次启动无引导、MCP stdio 单线程阻塞、LLM 配额账本死代码、strategy profile_id 不含 delay 哈希冲突、参数审计遗漏、lifecycle_records 无界增长 OOM、redaction _KEY_VALUE_RE \b 边界漏脱
  - 产出：findings 备忘录（Functional + 部署/安全相关 Functional 影响）

- [ ] Task 7: 深读 React 前端 `components/` 全部组件
  - 范围：`brain_alpha_ops/web/react_app/src/components/` 全部 `.tsx`：A11y/、CandidateTable/、CandidateTableSubComponents/、CandidateTableUtils/、ConfigPanel/、Dashboard/、ErrorState/、JobMonitor/、LazyImage/、LoadingState/、OfficialOperations/、ProgressFeedback/、ScoreBreakdown/、ScoringPanel/、SnapshotPanel/、StateCards/、SubmissionGates/、VirtualList/、views/、以及顶层 `CandidateDetailPanel.tsx` / `CandidateRow.tsx` / `CandidateTable*.tsx` / `ConfigPanel.tsx` / `ConfirmDialog.tsx` / `CredentialQuickStart.tsx` / `Dashboard*.tsx` / `EmptyState.tsx` / `ErrorBoundary.tsx` / `ErrorCard.tsx` / `FlowGuide.tsx` / `JobMonitor.tsx` / `KeyboardShortcutsHelp.tsx` / `KpiCard.tsx` / `LoadingProgress.tsx` / `MobileTabBar.tsx` / `NotFound.tsx` / `OfficialBacktestSlots.tsx` / `OfficialOperationsPanel.tsx` / `PhaseShell.tsx` / `ProgressFeedback.tsx` / `QualityCheckPanel.tsx` / `ResumeWork.tsx` / `ScoreBreakdown.tsx` / `ScoringPanel.tsx` / `Sidebar.tsx` / `Skeleton.tsx` / `SnapshotPanel.tsx` / `StateCards.tsx` / `StatusFlowDiagram.tsx` / `StepGuide.tsx` / `SubmissionChecklist.tsx` / `SubmissionConfirmPanel.tsx` / `SubmissionGuidance.tsx` / `SubmissionPanel.tsx` / `ThemeProvider.tsx` / `Toast.tsx` / `ToastContainer.tsx` / `Tooltip.tsx` / `TrendPanel.tsx` / `useCandidateColumns.tsx`
  - 焦点（WebUI 为主）：PhaseShell 阻断阶段按钮仍可点、首屏空白、路由不进 URL、Modal 无焦点陷阱、Toast 系统重复、移动端 statusbar 遮挡、OfficialBacktestSlots 全量刷新、CandidateTable 刷新循环、JobMonitor SSE 随 Dashboard 卸载断连、ErrorBoundary hash 与 BrowserRouter 冲突、候选导出下拉无 click-outside、渲染缺陷、组件状态异常、布局错乱
  - 产出：findings 备忘录（WebUI + UX）

- [ ] Task 8: 深读 React 前端 `hooks/` + `helpers/` + `utils/` + `types/` + 入口文件
  - 范围：`brain_alpha_ops/web/react_app/src/hooks/` 全部（useAppState/ + useJobMonitor/ + useApi.ts + useCandidateActions.ts + useCandidateCheck.ts + useCandidateGeneration.ts + useCandidateOptimization.ts + useCandidatePipeline.ts + useCandidateSSEHandlers.ts + useCandidateSimulation.ts + useCandidateTableData.ts + useCandidateTableSse.ts + useCandidateTableState.ts + useConfigForm.ts + useConfirm.tsx + useDashboard.ts + useDebounce.ts + useFormValidation.ts + useGlobalData.ts + useIntersectionObserver.ts + useJobDisconnectedState.ts + useJobLifecycle.ts + useJobMonitor.ts + useJobNotifications.ts + useJobRecovery.ts + useJobSseConnection.ts + useJobState.ts + useJobStatusHook.ts + useJobWatchdog.ts + useKeyboardShortcuts.ts + useLoadingState.ts + useMediaQuery.ts + useMemoCompare.ts + useNetworkError.ts + useOperationState.ts + usePagination.ts + usePhaseState.ts + useProgressFeedback.ts + useSSE.ts + useSorting.ts + useSseManager.ts + useTheme.ts + useThrottle.ts + useToast.ts）、`helpers/`（runPayload/ + connectionErrorGuide.ts + errorExperience.ts + readinessLabels.ts + runPayload.ts）、`utils/`（backtestSlots.ts + csrf.ts + debounce.ts + errorHandler.ts + reportIgnoredError.ts + resumeState.ts + starredCandidates.ts）、`types/`（全部 .ts）、`App.tsx` / `main.tsx` / `index.css` / `vite-env.d.ts`、`styles/` 全部 .css
  - 焦点（UX + 状态管理为主）：useCandidateTableData 刷新循环、useGlobalData 30s 轮询不看 visibility、renderActiveViewFromContext 在 render 期调 hook、SSE 断连误取消但云端仍在运行、错误引导仅覆盖 4 类连接错误、限流倒计时固定 30s 不读 retry_after、配置保存无"需重启生效"、批量提交无 dry-run 预览、前台任务完成无提示、错误提示英文外泄、网络错误恢复入口缺失、CSRF 实现、resumeState 状态恢复正确性
  - 产出：findings 备忘录（UX + WebUI 状态管理）

- [ ] Task 9: 通读历史审计/缺陷文档，建立已知问题清单
  - 范围：`/workspace/docs/` 全部 `.md`（ARCHITECTURE / CAPABILITY_MATRIX / CODE_REVIEW_20260521 / COMPREHENSIVE_SYSTEM_EVALUATION_20260514 / DEFECT_ANALYSIS_REPORT_* / STATIC_ANALYSIS_DEFECT_REPORT_20260603 / DELIVERY_COMPLETION_AUDIT_20260528 / ALPHA_PRODUCTION_DIAGNOSIS_20260522 / DATA_RETENTION / INSTALL / SECURITY）+ 根目录 `BRAINALPHA_AUDIT_V3_20260619.md` / `BRAINALPHA_FULLSTACK_AUDIT_20260622.md` / `CODE_DIAGNOSTIC_REPORT_20260618.md` / `DEFECT_TRACKING.md` / `DELIVERY_REPORT_20260622.md` / `DELIVERY_REPORT_OVERHAUL.md` / `IMPLEMENTATION_PLAN_20260622.md` / `PHASE33_DELIVERY_REPORT_20260619.md` / `REFACTORING_PLAN.md` / `README.md`
  - 焦点：提取每份文档中提出的重大问题（Functional / UX / WebUI 三维），形成"历史已知问题清单"，供 Phase 2 与当前代码状态交叉核对
  - 产出：已知问题清单备忘录（含问题简述、来源文档、提出日期）

## Phase 2: 汇总与交叉核对（顺序执行）

- [ ] Task 10: 汇总全部 9 份 findings 备忘录，去重、分类、交叉核对
  - 输入：Task 1-9 的 9 份备忘录
  - 动作：
    - 按维度（Functional / UX / WebUI）归类
    - 按 severity（Critical / High / Medium）分级
    - 去重（同一根因被多个子系统发现合并）
    - 与 Task 9 历史清单交叉核对，标注每个历史问题的当前状态（已修复 / 仍存在 / 部分修复 / 新发现）
    - 验证全量子系统覆盖（无遗漏）
  - 产出：去重后的聚合 findings 清单（含维度、severity、file:line、根因、影响、改进方向、历史状态）

## Phase 3: 报告产出（顺序执行）

- [ ] Task 11: 撰写 `ASSESSMENT_REPORT.md`
  - 输入：Task 10 聚合清单
  - 输出位置：`/workspace/.trae/specs/holistic-codebase-assessment/ASSESSMENT_REPORT.md`
  - 结构：按 spec.md 中 "What Changes" 章节定义的报告结构（报告头 / 总体结论 / 三维度 / 改进路线图 / 附录历史交叉核对表）
  - 语言：中文（代码引用/路径/函数名/变量名保持英文，severity 标签英文）
  - 严格排除：代码风格、命名、注释、类型注解、import 顺序、文件行数、lint、测试覆盖率数字、文档拼写
  - 严格仅含：对项目有实质性影响的严重问题

## Phase 4: 验证（顺序执行）

- [ ] Task 12: 对照 `checklist.md` 逐项验证报告
  - 动作：逐项核查 checklist.md 中每个 checkpoint，确认报告满足
  - 失败处理：若任一 checkpoint 未满足，回到 Task 11 修补报告
  - 产出：所有 checkpoint 打勾的 checklist.md

# Task Dependencies

- Task 1-9 互相独立，可全部并行执行
- Task 10 依赖 Task 1-9 全部完成
- Task 11 依赖 Task 10 完成
- Task 12 依赖 Task 11 完成
