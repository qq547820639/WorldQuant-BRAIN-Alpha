from __future__ import annotations

from pathlib import Path

import brain_alpha_ops.build_inline as build_inline
from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"

REACT_CONTRACT_COVERAGE = {
    "App.tsx": "app shell router, sidebar navigation, credential quick-start, and detail view selection",
    "__tests__/CandidatePoolState.test.tsx": "unit test: candidate pool state",
    "__tests__/ConfigPanelCacheMode.test.tsx": "unit test: config panel cache mode",
    "__tests__/ConfigPanelFolding.test.tsx": "unit test: config panel folding",
    "__tests__/MobileInteractionBehavior.test.tsx": "unit test: mobile interaction behavior",
    "__tests__/QualityGateInterception.test.tsx": "unit test: quality gate interception",
    "__tests__/ScoringAttribution.test.tsx": "unit test: scoring attribution",
    "__tests__/ErrorBoundary.test.tsx": "unit test: error boundary fallback and recovery",
    "__tests__/SimulationQueueState.test.tsx": "unit test: simulation queue state",
    "__tests__/components_v3.test.tsx": "unit tests for PhaseShell, StepGuide, MobileTabBar, EmptyState components (v3.0)",
    "__tests__/usePhaseState.test.ts": "unit tests for usePhaseState hook — phase transitions and step computation (v3.0)",
    "api/jobCancel.ts": "shared browser job cancellation helper using cross-store job cancel",
    "components/ActionableError.tsx": "React component: actionable error",
    "components/CandidateDetailPanel.tsx": "React component: candidate detail panel",
    "components/CandidateRow.tsx": "React component: candidate row",
    "components/CandidateTable.tsx": "candidate generation, filters, queue views, and SSE completion",
    "components/CandidateTableDesktop.tsx": "React component: candidate table desktop",
    "components/CandidateTableLoading.tsx": "React component: candidate table loading",
    "components/CandidateTableMobile.tsx": "React component: candidate table mobile",
    "components/CandidateTablePagination.tsx": "React component: candidate table pagination",
    "components/CandidateTableSubComponents/index.ts": "React component (candidate table sub components submodule): index re-export",
    "components/CandidateTableSubComponents/CandidateMobileCard.tsx": "React component (candidate table sub components submodule): candidate mobile card",
    "components/CandidateTableSubComponents/EmptyState.tsx": "React component (candidate table sub components submodule): empty state",
    "components/CandidateTableSubComponents/LifecycleReplayPanel.tsx": "React component (candidate table sub components submodule): lifecycle replay panel",
    "components/CandidateTableSubComponents/QualitySummaryItem.tsx": "React component (candidate table sub components submodule): quality summary item",
    "components/CandidateTableSubComponents/SortHeader.tsx": "React component (candidate table sub components submodule): sort header",
    "components/CandidateTableSubComponents/types.ts": "React component (candidate table sub components submodule): types",
    "components/CandidateTableSuccessBanner.tsx": "React component: candidate table success banner",
    "components/CandidateTableToolbar.tsx": "React component: candidate table toolbar",
    "components/CandidateTableToolbarFilterToolbar.tsx": "React component: candidate table toolbar filter toolbar",
    "components/CandidateTableToolbarProductionControls.tsx": "React component: candidate table toolbar production controls",
    "components/CandidateTableToolbarQualitySummaryBar.tsx": "React component: candidate table toolbar quality summary bar",
    "components/CandidateTableToolbarTitleStats.tsx": "React component: candidate table toolbar title stats",
    "components/CandidateTableUtils/base.ts": "React component (candidate table utils submodule): base",
    "components/CandidateTableUtils/constants.ts": "React component (candidate table utils submodule): constants",
    "components/CandidateTableUtils/formatters.ts": "React component (candidate table utils submodule): formatters",
    "components/CandidateTableUtils/index.ts": "React component (candidate table utils submodule): index",
    "components/CandidateTableUtils/lifecycle.ts": "React component (candidate table utils submodule): lifecycle",
    "components/CandidateTableUtils/pool.ts": "React component (candidate table utils submodule): pool",
    "components/CandidateTableUtils/quality.ts": "React component (candidate table utils submodule): quality",
    "components/CandidateTableUtils/types.ts": "React component (candidate table utils submodule): types",
    "components/ConfigPanel.tsx": "session credentials, config hydration, schema options, validation, import/export, and save",
    "components/ConfigPanel/AdvancedConfigGroup.tsx": "React component (config panel submodule): advanced config group",
    "components/ConfigPanel/BasicConfigGroup.tsx": "React component (config panel submodule): basic config group",
    "components/ConfigPanel/ConfigFormFields.tsx": "React component (config panel submodule): config form fields",
    "components/ConfigPanel/CredentialsSection.tsx": "React component (config panel submodule): credentials section",
    "components/ConfigPanel/LocalCacheConnectionSection.tsx": "React component (config panel submodule): local cache connection section",
    "components/ConfigPanel/RunConfigSection.tsx": "React component (config panel submodule): run config section",
    "components/ConfigPanel/ScoringConfigGroup.tsx": "React component (config panel submodule): scoring config group",
    "components/ConfigPanel/ScoringWeightModal.tsx": "React component (config panel submodule): scoring weight modal",
    "components/ConfigPanel/fieldHelp.tsx": "React component (config panel submodule): field help",
    "components/ConfigPanel/utils.ts": "React component (config panel submodule): utils",
    "components/ConfigPanel/utils/constants.ts": "React component (config panel submodule): constants",
    "components/ConfigPanel/utils/formConverters.ts": "React component (config panel submodule): form converters",
    "components/ConfigPanel/utils/helpers.ts": "React component (config panel submodule): helpers",
    "components/ConfigPanel/utils/index.ts": "React component (config panel submodule): index",
    "components/ConfigPanel/utils/types.ts": "React component (config panel submodule): types",
    "components/ConfigPanel/utils/validation.ts": "React component (config panel submodule): validation",
    "components/ConfirmDialog.tsx": "React component: confirm dialog",
    "components/CredentialQuickStart.tsx": "React component: credential quick start",
    "components/Dashboard/Dashboard.tsx": "dashboard snapshots and landing metrics",
    "components/Dashboard/DashboardGuides.tsx": "React component (dashboard submodule): dashboard guides",
    "components/Dashboard/DashboardNotices.tsx": "React component (dashboard submodule): dashboard notices",
    "components/Dashboard/DashboardPanels.tsx": "React component (dashboard submodule): dashboard panels",
    "components/Dashboard/index.ts": "React component (dashboard submodule): index",
    "components/DashboardCloudSnapshot.tsx": "React component: dashboard cloud snapshot",
    "components/DashboardReportModal.tsx": "React component: dashboard report modal",
    "components/DashboardStepProgress.tsx": "React component: dashboard step progress",
    "components/DashboardTrendData.tsx": "React component: dashboard trend data",
    "components/EmptyState.tsx": "centered empty state with icon, title, description, CTA, and hint (v3.0)",
    "components/ErrorBoundary.tsx": "error boundary wrapper with fallback UI and retry recovery",
    "components/ErrorCard.tsx": "React component: error card",
    "components/ErrorState/ErrorState.tsx": "React component (error state submodule): error state",
    "components/ErrorState/RetryButton.tsx": "React component (error state submodule): retry button",
    "components/ErrorState/index.ts": "React component (error state submodule): index",
    "components/FlowGuide.tsx": "React component: flow guide",
    "components/JobMonitor.tsx": "production job start/stop/status and SSE progress",
    "components/JobMonitor/JobActions.tsx": "React component (job monitor submodule): job actions",
    "components/JobMonitor/JobProgressBar.tsx": "React component (job monitor submodule): job progress bar",
    "components/JobMonitor/JobStatusCard.tsx": "React component (job monitor submodule): job status card",
    "components/JobMonitor/index.ts": "React component (job monitor submodule): index",
    "components/KeyboardShortcutsHelp.tsx": "React component: keyboard shortcuts help",
    "components/KpiCard.tsx": "compact KPI presentation",
    "components/LoadingState/ButtonLoader.tsx": "React component (loading state submodule): button loader",
    "components/LoadingState/PageLoader.tsx": "React component (loading state submodule): page loader",
    "components/LoadingState/Skeleton.tsx": "React component (loading state submodule): skeleton",
    "components/LoadingState/Spinner.tsx": "React component (loading state submodule): spinner",
    "components/LoadingState/index.ts": "React component (loading state submodule): index",
    "components/MobileTabBar.tsx": "bottom tab navigation for mobile with 4 phase tabs (v3.0)",
    "components/NotFound.tsx": "React component: not found fallback route",
    "components/OfficialBacktestSlots.tsx": "official backtest slot polling and conflict guidance",
    "components/OfficialOperations/ActionButtons.tsx": "React component (official operations submodule): action buttons",
    "components/OfficialOperations/ActionPanel.tsx": "React component (official operations submodule): action panel",
    "components/OfficialOperations/BlockerList.tsx": "React component (official operations submodule): blocker list",
    "components/OfficialOperations/MetricsDisplay.tsx": "React component (official operations submodule): metrics display",
    "components/OfficialOperations/OperationLog.tsx": "React component (official operations submodule): operation log",
    "components/OfficialOperations/OperationMetric.tsx": "React component (official operations submodule): operation metric",
    "components/OfficialOperations/OperationsLog.tsx": "React component (official operations submodule): operations log",
    "components/OfficialOperations/OverviewCard.tsx": "React component (official operations submodule): overview card",
    "components/OfficialOperations/SummaryMetric.tsx": "React component (official operations submodule): summary metric",
    "components/OfficialOperations/SummarySections.tsx": "React component (official operations submodule): summary sections",
    "components/OfficialOperations/SyncHistoryList.tsx": "React component (official operations submodule): sync history list",
    "components/OfficialOperations/constants.ts": "React component (official operations submodule): constants",
    "components/OfficialOperations/contextCache.ts": "React component (official operations submodule): context cache",
    "components/OfficialOperations/errorMessages.ts": "React component (official operations submodule): error messages",
    "components/OfficialOperations/formatters.ts": "React component (official operations submodule): formatters",
    "components/OfficialOperations/index.ts": "React component (official operations submodule): index",
    "components/OfficialOperations/operationProgress.ts": "React component (official operations submodule): operation progress",
    "components/OfficialOperations/readiness.ts": "React component (official operations submodule): readiness",
    "components/OfficialOperations/syncOverview.ts": "React component (official operations submodule): sync overview",
    "components/OfficialOperations/syncProgress.ts": "React component (official operations submodule): sync progress",
    "components/OfficialOperations/syncStage.ts": "React component (official operations submodule): sync stage",
    "components/OfficialOperations/useOfficialOperations.ts": "React component (official operations submodule): use official operations",
    "components/OfficialOperations/useOfficialOperationsState.ts": "React component (official operations submodule): use official operations state",
    "components/OfficialOperations/useOperationLog.ts": "React component (official operations submodule): use operation log",
    "components/OfficialOperations/useReadinessChecks.ts": "React component (official operations submodule): use readiness checks",
    "components/OfficialOperations/useSyncOperations.ts": "React component (official operations submodule): use sync operations",
    "components/OfficialOperations/useSyncRecovery.ts": "React component (official operations submodule): use sync recovery",
    "components/OfficialOperations/useSyncStop.ts": "React component (official operations submodule): use sync stop",
    "components/OfficialOperations/utils.ts": "React component (official operations submodule): utils",
    "components/OfficialOperationsPanel.tsx": "button-driven official context refresh, blocker review, and operation events",
    "components/PhaseShell.tsx": "phase wrapper with header, step guide, and unlock condition (UI Design System v3.0)",
    "components/ProgressFeedback.tsx": "accessible progress, spinner, ETA, retry, and indeterminate states",
    "components/ProgressFeedback/ProgressBar.tsx": "React component (progress feedback submodule): progress bar",
    "components/ProgressFeedback/ProgressBody.tsx": "React component (progress feedback submodule): progress body",
    "components/ProgressFeedback/ProgressFooter.tsx": "React component (progress feedback submodule): progress footer",
    "components/ProgressFeedback/ProgressHeader.tsx": "React component (progress feedback submodule): progress header",
    "components/ProgressFeedback/index.ts": "React component (progress feedback submodule): index",
    "components/ProgressFeedback/progressUtils.ts": "React component (progress feedback submodule): progress utils",
    "components/QualityCheckPanel.tsx": "quality gate summary and readiness blockers",
    "components/ResumeWork.tsx": "React component: resume work",
    "components/ScoreBreakdown.tsx": "React component: score breakdown",
    "components/ScoreBreakdown/ScoreBar.tsx": "React component (score breakdown submodule): score bar",
    "components/ScoreBreakdown/ScoreDetails.tsx": "React component (score breakdown submodule): score details",
    "components/ScoreBreakdown/ScoreHistory.tsx": "React component (score breakdown submodule): score history",
    "components/ScoreBreakdown/index.ts": "React component (score breakdown submodule): index",
    "components/ScoringPanel/index.ts": "React component (scoring panel submodule): index re-export",
    "components/ScoringPanel/AttributionTooltip.tsx": "React component (scoring panel submodule): attribution tooltip",
    "components/ScoringPanel/AttributionTree.tsx": "React component (scoring panel submodule): attribution tree",
    "components/ScoringPanel/GateDecisionStrip.tsx": "React component (scoring panel submodule): gate decision strip",
    "components/ScoringPanel/GateResults.tsx": "React component (scoring panel submodule): gate results",
    "components/ScoringPanel/Header.tsx": "React component (scoring panel submodule): header",
    "components/ScoringPanel/ImprovementHints.tsx": "React component (scoring panel submodule): improvement hints",
    "components/ScoringPanel/ScoreHistory.tsx": "React component (scoring panel submodule): score history",
    "components/ScoringPanel/ScoringPanel.tsx": "React component (scoring panel submodule): scoring panel",
    "components/ScoringPanel/utils.ts": "React component (scoring panel submodule): utils",
    "components/Sidebar.tsx": "persistent left sidebar navigation with badges (Terminal Precision v2.0)",
    "components/Skeleton.tsx": "loading skeleton components for better UX (SkeletonText, SkeletonCard, SkeletonTable)",
    "components/SnapshotPanel.tsx": "cloud/checkpoint/research/history snapshots",
    "components/SnapshotPanel/SnapshotDesktopTable.tsx": "React component (snapshot panel submodule): snapshot desktop table",
    "components/SnapshotPanel/SnapshotMobileCard.tsx": "React component (snapshot panel submodule): snapshot mobile card",
    "components/SnapshotPanel/SnapshotPanel.tsx": "React component (snapshot panel submodule): snapshot panel",
    "components/SnapshotPanel/SnapshotPanelCloud.tsx": "React component (snapshot panel submodule): snapshot panel cloud",
    "components/SnapshotPanel/SnapshotPanelCompare.tsx": "React component (snapshot panel submodule): snapshot panel compare",
    "components/SnapshotPanel/SnapshotPanelLocal.tsx": "React component (snapshot panel submodule): snapshot panel local",
    "components/SnapshotPanel/snapshotViews.ts": "React component (snapshot panel submodule): snapshot views",
    "components/SnapshotPanel/utils.ts": "React component (snapshot panel submodule): utils",
    "components/StatusFlowDiagram.tsx": "submission readiness flow visualization showing checklist to submit flow (v3.0)",
    "components/StepGuide.tsx": "horizontal step progress bar with complete/active/pending states (v3.0)",
    "components/SubmissionChecklist.tsx": "React component: submission checklist",
    "components/SubmissionConfirmPanel.tsx": "read-only pre-submit blocker review",
    "components/SubmissionGates/BlockerAction.tsx": "React component (submission gates submodule): blocker action",
    "components/SubmissionGates/SubmissionGates.tsx": "React component (submission gates submodule): submission gates",
    "components/SubmissionGates/SubmissionMetrics.tsx": "React component (submission gates submodule): submission metrics",
    "components/SubmissionGates/constants.ts": "React component (submission gates submodule): constants",
    "components/SubmissionGates/index.ts": "React component (submission gates submodule): index",
    "components/SubmissionGates/utils.ts": "React component (submission gates submodule): utils",
    "components/SubmissionGuidance.tsx": "React component: submission guidance",
    "components/ThemeProvider.tsx": "React component: theme provider",
    "components/ToastContainer.tsx": "toast roles, actions, and dismissal",
    "components/Tooltip.tsx": "React component: tooltip",
    "components/TrendPanel.tsx": "React component: trend panel",
    "components/useCandidateColumns.tsx": "React component: use candidate columns",
    "components/views/_renderViewHelpers.tsx": "React component (views submodule): render view helpers",
    "components/views/helpers.ts": "React component (views submodule): helpers",
    "components/views/renderView.tsx": "React component (views submodule): render view",
    "components/views/renderViewFromContext.tsx": "React component (views submodule): render view from context",
    "helpers/connectionErrorGuide.ts": "helper module: connection error guide",
    "helpers/errorExperience.ts": "backend user-error payload to user-facing message mapping",
    "helpers/readinessLabels.ts": "official readiness and blocker reason labels shared across review panels",
    "helpers/runPayload/classify.ts": "helper (run payload submodule): classify",
    "helpers/runPayload/constants.ts": "helper (run payload submodule): constants",
    "helpers/runPayload/events.ts": "helper (run payload submodule): events",
    "helpers/runPayload/index.ts": "helper (run payload submodule): index",
    "helpers/runPayload/internalHelpers.ts": "helper (run payload submodule): internal helpers",
    "helpers/runPayload/run.ts": "helper (run payload submodule): run",
    "helpers/runPayload/types.ts": "helper (run payload submodule): types",
    "hooks/useApi.ts": "CSRF, replay headers, same-origin credentials, and error mapping",
    "hooks/useAppState/AppStateContext.tsx": "React hook (use app state submodule): app state context",
    "hooks/useAppState/index.ts": "React hook (use app state submodule): index",
    "hooks/useAppState/stateContract.ts": "React hook (use app state submodule): state contract",
    "hooks/useAppState/types.ts": "React hook (use app state submodule): types",
    "hooks/useAppState/useBaseState.ts": "React hook (use app state submodule): use base state",
    "hooks/useAppState/useErrorNotifications.ts": "React hook (use app state submodule): use error notifications",
    "hooks/useAppState/useHandlers.ts": "React hook (use app state submodule): use handlers",
    "hooks/useAppState/usePhaseConnection.ts": "React hook (use app state submodule): use phase connection",
    "hooks/useAppState/usePhaseManagement.ts": "React hook (use app state submodule): use phase management",
    "hooks/useCandidateActions.ts": "React hook: use candidate actions",
    "hooks/useCandidateCheck.ts": "React hook: use candidate check",
    "hooks/useCandidateGeneration.ts": "React hook: use candidate generation",
    "hooks/useCandidateOptimization.ts": "React hook: use candidate optimization",
    "hooks/useCandidatePipeline.ts": "React hook: use candidate pipeline",
    "hooks/useCandidateSSEHandlers.ts": "React hook: use candidate s s e handlers",
    "hooks/useCandidateSimulation.ts": "React hook: use candidate simulation",
    "hooks/useCandidateTableData.ts": "React hook: use candidate table data",
    "hooks/useCandidateTableSse.ts": "React hook: use candidate table sse",
    "hooks/useCandidateTableState.ts": "React hook: use candidate table state",
    "hooks/useConfigForm.ts": "React hook: use config form",
    "hooks/useConfirm.tsx": "React hook: use confirm",
    "hooks/useDashboard.ts": "React hook: use dashboard",
    "hooks/useDebounce.ts": "React hook: use debounce",
    "hooks/useFormValidation.ts": "React hook: use form validation",
    "hooks/useGlobalData.ts": "React hook: use global data",
    "hooks/useIntersectionObserver.ts": "React hook: use intersection observer",
    "hooks/useJobDisconnectedState.ts": "React hook: use job disconnected state",
    "hooks/useJobLifecycle.ts": "React hook: use job lifecycle",
    "hooks/useJobMonitor/constants.ts": "React hook (use job monitor submodule): constants",
    "hooks/useJobMonitor/index.ts": "React hook (use job monitor submodule): index",
    "hooks/useJobMonitor/types.ts": "React hook (use job monitor submodule): types",
    "hooks/useJobMonitor/useJobCancellation.ts": "React hook (use job monitor submodule): use job cancellation",
    "hooks/useJobMonitor/useJobControl.ts": "React hook (use job monitor submodule): use job control",
    "hooks/useJobMonitor/useSseEventHandler.ts": "React hook (use job monitor submodule): use sse event handler",
    "hooks/useJobMonitor/useSseRetryState.ts": "React hook (use job monitor submodule): use sse retry state",
    "hooks/useJobMonitor/useStatusWatchdog.ts": "React hook (use job monitor submodule): use status watchdog",
    "hooks/useJobNotifications.ts": "React hook: use job notifications",
    "hooks/useJobRecovery.ts": "React hook: use job recovery",
    "hooks/useJobSseConnection.ts": "React hook: use job sse connection",
    "hooks/useJobState.ts": "job state lifecycle management (Terminal Precision v2.0)",
    "hooks/useJobStatusHook.ts": "React hook: use job status hook",
    "hooks/useJobWatchdog.ts": "React hook: use job watchdog",
    "hooks/useKeyboardShortcuts.ts": "global keyboard shortcuts and KeyboardShortcutsHelp modal",
    "hooks/useMediaQuery.ts": "React hook: use media query",
    "hooks/usePagination.ts": "React hook: use pagination",
    "hooks/usePhaseState.ts": "phase navigation state management with phase determination and step computation (v3.0)",
    "hooks/useProgressFeedback.ts": "React hook: use progress feedback",
    "hooks/useSSE.ts": "stream token, credentials, reconnect, and close semantics",
    "hooks/useSorting.ts": "React hook: use sorting",
    "hooks/useSseManager.ts": "React hook: use sse manager",
    "hooks/useTheme.ts": "React hook: use theme",
    "hooks/useToast.ts": "toast lifecycle state",
    "main.tsx": "React root bootstrap",
    "types/api.ts": "TypeScript type definitions: api",
    "types/candidate.ts": "TypeScript type definitions: candidate",
    "types/cloud.ts": "TypeScript type definitions: cloud",
    "types/config.ts": "TypeScript type definitions: config",
    "types/errors.ts": "TypeScript type definitions: errors",
    "types/index.ts": "shared API, progress, candidate, and card view contracts",
    "types/scoring.ts": "TypeScript type definitions: scoring",
    "types/ui.ts": "TypeScript type definitions: ui",
    "utils/backtestSlots.ts": "official backtest slot status and count helpers",
    "utils/csrf.ts": "CSRF token, stream token, and request-ID generation helpers",
    "utils/debounce.ts": "utility helper: debounce",
    "utils/errorHandler.ts": "utility helper: error handler",
    "utils/reportIgnoredError.ts": "development-only diagnostics for intentionally ignored browser errors",
    "utils/resumeState.ts": "utility helper: resume state",
    "utils/starredCandidates.ts": "utility helper: starred candidates",
    "vite-env.d.ts": "source module: vite env d",
}


def _source(relative: str) -> str:
    return resolve_react_source(REACT_SRC / relative)


def _assert_snippets(source: str, snippets: list[str]) -> None:
    for snippet in snippets:
        assert snippet in source, f"Missing frontend contract: {snippet}"


def test_every_frontend_module_has_a_contract_test_entry():
    actual_sources = {
        path.relative_to(REACT_SRC).as_posix()
        for path in REACT_SRC.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    }

    assert actual_sources == set(REACT_CONTRACT_COVERAGE)

    dist_check = build_inline.check()
    assert dist_check["ok"] is True
    assert dist_check["frontend"] == "react"
    assert dist_check["asset_refs"]
    for ref in dist_check["asset_refs"]:
        assert (REACT_DIST / ref.removeprefix("/")).is_file()


def test_frontend_runtime_modules_render_state_and_interaction_contracts():
    candidate = _source("components/CandidateTable.tsx")
    candidate_state = _source("hooks/useCandidateTableState.ts")
    candidate_data = _source("hooks/useCandidateTableData.ts")
    candidate_generation = _source("hooks/useCandidateGeneration.ts")
    candidate_sse = _source("hooks/useCandidateTableSse.ts")
    candidate_desktop = _source("components/CandidateTableDesktop.tsx")
    candidate_filter = _source("components/CandidateTableToolbarFilterToolbar.tsx")
    candidate_sort_header = _source("components/CandidateTableSubComponents/SortHeader.tsx")
    candidate_utils = _source("components/CandidateTableUtils")
    official = _source("components/OfficialOperationsPanel.tsx")
    official_subdir = _source("components/OfficialOperations")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    quality = _source("components/QualityCheckPanel.tsx")
    slots = _source("components/OfficialBacktestSlots.tsx")
    progress = _source("components/ProgressFeedback.tsx")
    scoring = _source("components/ScoringPanel/ScoringPanel.tsx")
    job_monitor = _source("components/JobMonitor.tsx")
    use_job_state = _source("hooks/useJobState.ts")
    run_payload = _source("helpers/runPayload/index.ts")
    readiness_labels = _source("helpers/readinessLabels.ts")
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")
    csrf_utils = _source("utils/csrf.ts")

    _assert_snippets(
        candidate
        + candidate_state
        + candidate_data
        + candidate_generation
        + candidate_sse
        + candidate_desktop
        + candidate_filter
        + candidate_sort_header
        + candidate_utils,
        [
            "export const PAGE_SIZE = 20;",
            "candidateMatchesQueueView(c, viewMode, checkResults)",
            "sanitizeTextInput(value, MAX_FILTER_LENGTH)",
            "const rows = result?.candidates || [];",
            "sseManager.connect('task', `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`",
            'aria-label="过滤候选"',
            'aria-label="候选结果"',
            'scope="col"',
            "没有匹配的候选",
        ],
    )
    assert "callReadiness<SubmitReadinessResponse>('/api/submit_readiness')" in confirm
    _assert_snippets(
        official + official_subdir,
        [
            'readinessProductionGapLabel',
            "rows={allReadinessBlockers.map(reasonCountText)}",
            "rows={allFamilyBlockers.map(reasonCountText)}",
            "rows={allProductionGaps.map(findingText)}",
            "rows={allBestCandidateReasons.map((reason) => readinessReasonLabel(reason))}",
            "function reasonCountText(row",
            "function findingText(row",
        ],
    )
    _assert_snippets(
        official + official_subdir + confirm + quality + slots + readiness_labels,
        [
            "readinessReasonLabel(",
            "readinessProductionGapLabel(",
            "存在未分类生产缺口",
            "missing_scientific_audit: '缺少科学审计证据'",
            "scientific_audit_submit_boundary_breached: '科学审计提交边界异常'",
            "latest_candidate_scientific_audit_test_feedback_used: '最新候选科学审计含测试反馈'",
            "incomplete_scientific_audit: '科学审计证据不完整'",
        ],
    )
    _assert_snippets(
        progress
        + _source("components/ProgressFeedback")
        + _source("hooks/useProgressFeedback.ts")
        + use_api
        + use_sse
        + csrf_utils,
        [
            'role="progressbar"',
            "normalizedPercent(progress, progressState)",
            "credentials: 'same-origin'",
            "headers['X-Brain-Alpha-CSRF'] = csrf",
            "'X-Brain-Alpha-Request-ID'",
            "new EventSource(withStreamToken(streamUrl), { withCredentials: true })",
            "onExhaustedRef.current?.();",
            "stream_token=${encodeURIComponent(token)}",
        ],
    )
    _assert_snippets(
        run_payload
        + candidate
        + scoring
        + job_monitor
        + use_job_state
        + _source("hooks/useJobMonitor/useSseEventHandler.ts"),
        [
            "export function resolveJobEventState(",
            "import { resolveJobEventState } from '@/helpers/runPayload';",
            "resolveJobEventState(event, progress",
            "resolveJobEventState(event, event.progress || event.data",
        ],
    )


def test_browser_react_smoke_requires_non_submit_state_error_assertions():
    smoke = (ROOT / "scripts" / "browser_react_artifact_smoke.mjs").read_text(encoding="utf-8")

    _assert_snippets(
        smoke,
        [
            "report.productionValidation = {",
            "home shell does not expose local non-submit validation state",
            "home shell does not expose non-submit proof metrics",
            "production validation monitor did not render non-submit proof surface",
            "production validation interrupted state did not show safe user-facing copy",
            "production validation interrupted state did not return controls to retry-safe state",
            "production validation run request did not preserve non-submit/no-credential payload",
            "report.submissionConfirm = {",
            "submission confirm panel did not render final non-submit blocker review",
            "submission confirm panel did not show scientific-audit blockers",
            "submission confirm panel exposed raw readiness/check/status text",
            "submission confirm panel attempted a submit endpoint",
            "report.candidateOperations = {",
            "candidate operations panel did not render target-pool recovery controls",
            "candidate operations auto-advance control was not clickable",
            "candidate operations official validation queue did not run visible mocked simulation",
            "candidate operations official validation queue did not continue into quality gate check",
            "simulate_queue_zero_smoke",
            "negativeOfficialSimulationFailed",
            "candidate operations zero-success official validation queue did not fail closed before quality gate check",
            "candidate operations zero-success official validation queue called check_batch before a successful simulation",
            "candidate operations did not navigate from a candidate row into scoring",
            "candidate operations auto-advance request did not preserve local non-submit/no-credential payload",
            "candidate operations official validation simulation request did not preserve safe Top3 no-credential payload",
            "candidate operations batch quality check request did not preserve safe simulated-candidate no-credential payload",
            "report.scoringPanel = {",
            "scoring panel did not render clicked-candidate scoring attribution and gate evidence",
            "score_failed_smoke",
            "raw backend scoring failure password=secret",
            "raw backend family password=secret",
            "REPORT_RAW_BACKEND_TEXT_PATTERN",
            "RAW_BACKEND_SCORE_STATUS",
            "评分失败，请重新评估候选后再继续。",
            "failureRefreshClicked",
            "failureUserCopy",
            "failureRetryVisible",
            "failureNotComplete",
            "failureRawBackendHidden",
            "recoveredAfterRetry",
            "scoringFailureRetryInteractionExpression",
            "validateScoringFailureRetryInteractions",
            "scoring_failure_retry",
            "scoring failure retry slice did not navigate from candidate row into scoring",
            "scoring failure retry slice did not render initial clicked-candidate scoring success",
            "scoring failure retry slice did not stay retry-safe and non-complete after refresh failure",
            "scoring failure retry slice did not recover after retry success",
            "scoring failure retry slice exposed raw backend/session text",
            "scoring failure retry slice did not exercise initial success, refresh failure, and retry success",
            "scoring failure retry request ${endpoint} did not preserve no-credential candidate payload",
            "scoring failure retry slice attempted a submit endpoint",
            "scoring failure retry slice request carried credential-like fields",
            "scoring panel failure state did not stay retry-safe and non-complete",
            "scoring panel retry did not recover after a failed scoring event",
            "scoring panel failure state exposed raw backend/session text",
            "scoring request ${endpoint} did not preserve no-credential candidate payload",
            "clickedScoreAlphaId",
            "clickedAlphaId: clickedScoreAlphaId",
            "body.alpha_id !== scoringPanel.clickedAlphaId",
            "body.candidate.alpha_id !== scoringPanel.clickedAlphaId",
            "report.backtestSlots = {",
            "official backtest slots panel did not render slot capacity summary",
            "official backtest slots panel did not render running, empty, and completed slot states",
            "report.qualityCheck = {",
            "quality check panel did not render local and official evidence summary",
            "quality check panel did not show non-submit blocker evidence and next action",
            "raw backend action password=secret",
            "等待候选和门禁数据",
            "report.configPanel = {",
            "config panel did not render safe cache/session configuration copy",
            "config panel connection test ran during browser smoke",
            "report.snapshotPanel = {",
            "snapshot panel did not render checkpoint evidence rows",
            "snapshot panel exposed raw checkpoint status, visible fields, or backend detail text",
            "report.robustnessReplay = {",
            "replayAuditInteractionExpression",
            "validateReplayAuditInteractions",
            'argValue("--slice", "full")',
            "VALID_SLICES",
            "--slice must be one of: ${VALID_SLICES.join",
            'slice === "replay_audit"',
            'slice === "scoring_failure_retry"',
            "30000",
            "45000",
            "runSmokeStep(",
            "diagnosticMessage(",
            "last_mock_endpoint=",
            "viewport=${viewport}",
            "step=${step}",
            "elapsed_ms=${elapsedMs}",
            "robustness replay audit slice did not navigate to the robustness evidence panel",
            "robustness replay audit panel did not render local latest_result replay metrics",
            "robustness replay audit panel did not expose stop-rule, non-submit, and scientific-audit evidence",
            "robustness replay audit panel exposed local path or raw backend text",
            "/api/latest_result",
            "expected mocked GET /api/latest_result",
            "unexpected browser-smoke mutating request ${request.method} ${request.path}",
            "replay_audit",
            "本地回放审计",
            "非提交边界",
            "停机规则:check_live_submit_readiness\\.py",
            "RAW_BACKEND_CHECK_STATUS",
            "raw backend-only checkpoint failure",
            "raw backend title password=secret",
            "raw backend metric api_key=secret",
            "raw backend metric csrf_token=secret",
            "raw backend delta password=secret",
            "RAW_BACKEND_RISK password=secret",
            "raw backend-only submission gap",
            "raw backend-only submit action",
            "raw backend-only check reason",
            "状态待确认",
            "详情待确认",
            "记录待确认",
            "指标待确认",
            "时间待确认",
            "趋势待确认",
            "对比项待确认",
            "提交前阻断复核",
            "report.lifecycleReplay = {",
            "lifecycle replay panel did not render local read-only non-submit state",
            "lifecycle replay panel did not expose replay summary metrics",
            "lifecycle replay recovered trace did not prioritize latest passed state",
            "lifecycle replay blocked trace did not show review next action",
            "lifecycle replay panel exposed secret-like labels or values",
            'document.querySelector(\'section[aria-label="生命周期回放"]\')',
            "report.officialOperations = {",
            'document.querySelector(\'section[aria-label="官方同步数据总览"]\')',
            'Array.from(document.querySelectorAll("h2"))',
            'officialHeading?.closest(".animate-fade-in")',
            "officialPanel?.innerText || \"\"",
            "official operations panel did not render the non-submit sync entry and overview",
            "official operations session-invalid recovery state did not show safe reconnect guidance",
            "official operations open-ended sync scan did not stay indeterminate and non-complete",
            "official operations stopped/cancelled sync state did not stay retry-safe and non-complete",
            "official operations intermediate state-error snapshots overflow horizontally",
            "official operations sync warning state did not expose safe partial-success guidance",
            "official operations readiness review did not stay visibly blocked and non-submit",
            "official operations readiness review did not show scientific-audit blockers",
            "official operations check-results review did not load visible quality evidence",
            "official operations panel exposed raw backend/session or secret-like text",
            "official operations sync request did not preserve safe local visual-smoke payload",
            "official operations sync cancel request did not preserve safe local visual-smoke payload",
            "sync_open_ended_scan",
            "sync_cancelled_terminal",
            "scientificAuditBlocked",
            "missing_scientific_audit",
            "scientific_audit_submit_boundary_breached",
            "latest_candidate_scientific_audit_test_feedback_used",
            "incomplete_scientific_audit",
            "缺少科学审计证据",
            "科学审计提交边界异常",
            "最新候选科学审计含测试反馈",
            "科学审计证据不完整",
            "后台确认状态为已停止",
            "后台确认状态为已取消",
            "reconnectClicked && reconnectNavigated",
            "stateOverflowFree",
            "!/width:\\s*100%/i.test(scanProgressFillStyle)",
            'document.querySelector(\'[role="progressbar"][aria-label*="扫描云端"]\')',
            "completed_with_warnings",
            "COMPLETED_WITH_WARNINGS",
            'context_status: "failed"',
            'userFacingOperation !== "official_operations_context_refresh"',
            "REPORT_FORBIDDEN_TEXT_PATTERN",
            "SENSITIVE_KEY_PATTERN",
            "user[_-]?name",
            "isSensitiveKey(",
            "searchHasCredentialFields(",
            "hasCredentialSearch: searchHasCredentialFields(url.search)",
            "redactText(",
            "redactUrl(",
            "redactReportValue(result)",
            "assertReportRedacted(serializedResult)",
            "SECRET_TEXT_PATTERN",
            "forbiddenLifecycleSecretsVisible",
            'textSample: "<omitted>"',
            'sample: "<omitted>"',
            "password|passwd|pwd|hunter2",
            "client[_-]?secret",
            "api[_-]?key",
            "set[_-]?cookie",
            "hasCredentialFields: requestHasCredentialFields(request.postData || \"\")",
            "Boolean(request.hasCredentialSearch)",
            'body.automation_mode !== "maintain_candidate_pool"',
            'body.auto_simulate_after_generation !== false',
            'body.auto_check_after_simulation !== false',
            "body.candidate",
            'match(/ALPHA_[A-Z0-9_]+/)',
            "body.alpha_id !== scoringPanel.clickedAlphaId",
            "Boolean(request.hasCredentialFields)",
            "Boolean(request.hasCredentialSearch)",
            "redactRequestBody(request.postData || \"\")",
            "redactSearchParams(url.search)",
            "csrfPresent: Boolean",
            "streamPresent: Boolean",
            "metrics.meta.csrfPresent",
            "UNMOCKED_BROWSER_SMOKE_API",
            "NON_LOCAL_BROWSER_SMOKE_REQUEST_BLOCKED",
            "LOOPBACK_HOSTS",
            'requireLoopbackHttpUrl(rawUrl, "--url")',
            'requireLoopbackHttpUrl(argValue("--devtools-url"',
            "isLocalBrowserUrl(rawUrl)",
            "browser attempted to load a non-local resource",
            'urlPattern: "*", requestStage: "Request"',
            '"Fetch.continueRequest"',
            "networkRequests: [...session.networkRequests]",
            "blockedNonLocalRequests: [...session.blockedNonLocalRequests]",
            "production validation interrupted state overflows horizontally",
            "`unexpected browser-smoke API request ${endpoint}`",
            "`unmocked browser-smoke API request ${request.method} ${request.path}`",
            "MUTATING_METHODS",
            "ALLOWED_MUTATING_REQUESTS",
            '"POST /api/run"',
            '"POST /api/sync_alphas"',
            '"POST /api/sync_cancel"',
            '"POST /api/generate_candidates"',
            '"POST /api/candidates/simulate"',
            '"POST /api/check_batch"',
            "checkBatchBeforeSimulationSuccessCount",
            "candidate operations mock server observed check_batch before official simulation success",
            '"POST /api/scoring/evaluate"',
            '"POST /api/scoring/attribution"',
            "isAllowedMutatingRequest(request.method, request.path)",
            "unexpected browser-smoke mutating request",
            '"/api/phase_state"',
            '"/api/production-validation/status"',
            '"/api/candidates"',
            '"/api/alpha_lifecycle"',
            '"/api/backtest_slots"',
            '"/api/config"',
            '"/api/checkpoint_status"',
            '"/api/snapshot/cloud"',
            '"/api/snapshot/memory"',
            '"/api/sync_status"',
            '"/api/submit_readiness"',
            '"/api/check_results"',
            '"/api/run"',
            '"/api/sync_alphas"',
            '"/api/sync_cancel"',
            '"/api/generate_candidates"',
            '"/api/scoring/evaluate"',
            '"/api/scoring/attribution"',
            '"/api/candidates/simulate"',
            '"/api/check"',
            '"/api/sync_context_only"',
            '"/api/test_connection"',
            '"/api/candidates/optimize"',
            "/(?:\\?|&)limit=250(?:&|$)/.test(request.search)",
        ],
    )


def test_app_ux_orchestrator_has_tested_navigation_empty_and_busy_contracts():
    app = _source("App.tsx")
    base_state = _source("hooks/useAppState/useBaseState.ts")
    handlers = _source("hooks/useAppState/useHandlers.ts")
    render_view = _source("components/views/renderView.tsx")
    job_monitor = _source("components/JobMonitor.tsx")
    job_status_card = _source("components/JobMonitor/JobStatusCard.tsx")
    use_job_control = _source("hooks/useJobMonitor/useJobControl.ts")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    submission_gates = _source("components/SubmissionGates")

    _assert_snippets(
        app
        + base_state
        + handlers
        + render_view
        + job_monitor
        + job_status_card
        + use_job_control,
        [
            "useState<CardViewId>(readViewFromHash)",
            "Sidebar",
            "setActiveView(view)",
            'aria-label="切换导航菜单"',
            "import Sidebar from '@/components/Sidebar'",
            "BRAIN Alpha Ops",
            "未填写页面凭证",
            "非提交生产验证",
            "页面凭证为空",
            'viewMode="checkpoint_status"',
            "selectedCandidate",
            'role="alert"',
        ],
    )
    for view_id in (
        "official_operations",
        "dashboard",
        "candidates",
        "official_backtests",
        "scoring",
        "quality_check",
        "submission_confirm",
        "checkpoint_status",
        "config",
        "cloud",
    ):
        assert f"case '{view_id}':" in render_view

    _assert_snippets(
        confirm + submission_gates,
        [
            "callReadiness<SubmitReadinessResponse>('/api/submit_readiness')",
            "ready_to_submit",
            "official_api_called",
            "production_gaps",
            "required_next_steps",
            "暂无通过预提交检查的 Alpha",
        ],
    )
    assert "'/api/submit'" not in confirm


def test_ux_styles_cover_interaction_feedback_and_responsive_layout():
    css = _source("styles")
    app = _source("App.tsx")
    candidate = _source("components/CandidateTable.tsx")
    candidate_toolbar_controls = _source(
        "components/CandidateTableToolbarProductionControls.tsx"
    )
    candidate_toolbar_filter = _source("components/CandidateTableToolbarFilterToolbar.tsx")
    config = _source("components/ConfigPanel.tsx")
    toast = _source("components/ToastContainer.tsx")

    _assert_snippets(
        css,
        [
            ":focus-visible",
            ".btn-primary",
            ".btn-secondary",
            ".btn-danger",
            ".panel",
            ".spinner",
            "@keyframes progress-indeterminate",
            "@keyframes fade-in",
            ".app-shell",
            ".app-main",
            ".toast-container",
        ],
    )
    _assert_snippets(
        css
        + app
        + candidate
        + candidate_toolbar_controls
        + candidate_toolbar_filter
        + config
        + toast,
        [
            "app-shell",
            "app-main",
            "flex flex-wrap items-center gap-3",
            "flex flex-col sm:flex-row gap-3",
            "form-input",
            "data-table",
            "toast-container",
            "flex-1 min-w-0 break-words text-sm",
        ],
    )
