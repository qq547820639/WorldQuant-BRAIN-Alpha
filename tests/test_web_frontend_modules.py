from __future__ import annotations

from pathlib import Path

import brain_alpha_ops.build_inline as build_inline


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"

REACT_CONTRACT_COVERAGE = {
    "App.tsx": "app shell router, sidebar navigation, credential quick-start, and detail view selection",
    "api/jobCancel.ts": "shared browser job cancellation helper using cross-store job cancel",
    "main.tsx": "React root bootstrap",
    "components/CandidateTable.tsx": "candidate generation, filters, queue views, and SSE completion",
    "components/ConfigPanel.tsx": "session credentials, config hydration, schema options, validation, import/export, and save",
    "components/Dashboard.tsx": "dashboard snapshots and landing metrics",
    "components/JobMonitor.tsx": "production job start/stop/status and SSE progress",
    "components/KpiCard.tsx": "compact KPI presentation",
    "components/OfficialBacktestSlots.tsx": "official backtest slot polling and conflict guidance",
    "components/OfficialOperationsPanel.tsx": "button-driven official context refresh, blocker review, and operation events",
    "components/ProgressFeedback.tsx": "accessible progress, spinner, ETA, retry, and indeterminate states",
    "components/QualityCheckPanel.tsx": "quality gate summary and readiness blockers",
    "components/ScoringPanel.tsx": "score evaluation, attribution, and result presentation",
    "components/Sidebar.tsx": "persistent left sidebar navigation with badges (Terminal Precision v2.0)",
    "components/SnapshotPanel.tsx": "cloud/checkpoint/research/history snapshots",
    "components/StateCards.tsx": "card-first navigation and startup status loading (superseded by Sidebar)",
    "components/SubmissionConfirmPanel.tsx": "read-only pre-submit blocker review",
    "components/SubmissionPanel.tsx": "retired submit compatibility wrapper for read-only readiness review",
    "components/ToastContainer.tsx": "toast roles, actions, and dismissal",
    "helpers/errorExperience.ts": "backend user-error payload to user-facing message mapping",
    "helpers/readinessLabels.ts": "official readiness and blocker reason labels shared across review panels",
    "helpers/runPayload.ts": "prod validation run payload builder (Terminal Precision v2.0)",
    "hooks/useApi.ts": "CSRF, replay headers, same-origin credentials, and error mapping",
    "hooks/useJobState.ts": "job state lifecycle management (Terminal Precision v2.0)",
    "hooks/useSSE.ts": "stream token, credentials, reconnect, and close semantics",
    "hooks/useToast.ts": "toast lifecycle state",
    "types/index.ts": "shared API, progress, candidate, and card view contracts",
    "utils/backtestSlots.ts": "official backtest slot status and count helpers",
    "utils/csrf.ts": "CSRF token, stream token, and request-ID generation helpers",
    "utils/reportIgnoredError.ts": "development-only diagnostics for intentionally ignored browser errors",
    "components/PhaseShell.tsx": "phase wrapper with header, step guide, and unlock condition (UI Design System v3.0)",
    "components/StepGuide.tsx": "horizontal step progress bar with complete/active/pending states (v3.0)",
    "components/MobileTabBar.tsx": "bottom tab navigation for mobile with 4 phase tabs (v3.0)",
    "components/EmptyState.tsx": "centered empty state with icon, title, description, CTA, and hint (v3.0)",
    "hooks/usePhaseState.ts": "phase navigation state management with phase determination and step computation (v3.0)",
    "components/StatusFlowDiagram.tsx": "submission readiness flow visualization showing checklist to submit flow (v3.0)",
    "__tests__/components_v3.test.tsx": "unit tests for PhaseShell, StepGuide, MobileTabBar, EmptyState components (v3.0)",
    "__tests__/usePhaseState.test.ts": "unit tests for usePhaseState hook — phase transitions and step computation (v3.0)",
}


def _source(relative: str) -> str:
    return (REACT_SRC / relative).read_text(encoding="utf-8")


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
    official = _source("components/OfficialOperationsPanel.tsx")
    submission = _source("components/SubmissionPanel.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    quality = _source("components/QualityCheckPanel.tsx")
    slots = _source("components/OfficialBacktestSlots.tsx")
    progress = _source("components/ProgressFeedback.tsx")
    scoring = _source("components/ScoringPanel.tsx")
    job_monitor = _source("components/JobMonitor.tsx")
    use_job_state = _source("hooks/useJobState.ts")
    run_payload = _source("helpers/runPayload.ts")
    readiness_labels = _source("helpers/readinessLabels.ts")
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")
    csrf_utils = _source("utils/csrf.ts")

    _assert_snippets(
        candidate,
        [
            "const PAGE_SIZE = 20;",
            "candidateMatchesQueueView(candidate, viewMode, checkResults)",
            "sanitizeTextInput(value, MAX_FILTER_LENGTH)",
            "const rows = result?.candidates || [];",
            "result.partial",
            'useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}` : null',
            'aria-label="过滤候选"',
            'aria-label="候选结果"',
            'scope="col"',
            "没有匹配的候选",
        ],
    )
    _assert_snippets(
        submission,
        [
            "Retired submit surface kept as a compatibility alias",
            "SubmissionConfirmPanel notify={notify}",
            "旧提交面板已退役",
            "Web 页面不执行真实提交",
            "任何真实提交需另走人工审批",
            'role="status"',
        ],
    )
    assert "/api/submit" not in submission
    assert "/api/submit_batch" not in submission
    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in confirm
    _assert_snippets(
        official,
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
        official + confirm + quality + slots + readiness_labels,
        [
            "readinessReasonLabel(",
            "readinessProductionGapLabel(",
            "存在未分类生产缺口",
            'missing_scientific_audit: "缺少科学审计证据"',
            'scientific_audit_submit_boundary_breached: "科学审计提交边界异常"',
            'latest_candidate_scientific_audit_test_feedback_used: "最新候选科学审计含测试反馈"',
            'incomplete_scientific_audit: "科学审计证据不完整"',
        ],
    )
    _assert_snippets(
        progress + use_api + use_sse + csrf_utils,
        [
            'role="progressbar"',
            "normalizedPercent(progress, progressState)",
            'credentials: "same-origin"',
            'headers["X-Brain-Alpha-CSRF"] = csrf',
            '"X-Brain-Alpha-Request-ID"',
            "new EventSource(withStreamToken(streamUrl), { withCredentials: true })",
            "onExhaustedRef.current?.();",
            "stream_token=${encodeURIComponent(token)}",
        ],
    )
    _assert_snippets(
        run_payload + candidate + scoring + job_monitor + use_job_state,
        [
            "export function resolveJobEventState(",
            'import { resolveJobEventState } from "@/helpers/runPayload";',
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
    state_cards = _source("components/StateCards.tsx")
    job_monitor = _source("components/JobMonitor.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")

    _assert_snippets(
        app + state_cards + job_monitor,
        [
            'useState<CardViewId>("dashboard")',
            "Sidebar",
            "setActiveView(view)",
            'aria-label="切换导航菜单"',
            'import Sidebar from "@/components/Sidebar"',
            "BRAIN Alpha Ops",
            "凭证与连接",
            "未填写页面凭证",
            "非提交生产验证",
            "页面凭证为空",
            'key="checkpoint_status"',
            "selectedCandidate",
            "grid w-full max-w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5",
            "onClick={() => onNavigate(config.id)}",
            'role="alert"',
            'aria-live="assertive"',
            "ProgressFeedback",
            'phase: "state_cards_load"',
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
        assert f'id: "{view_id}"' in state_cards
        assert f'case "{view_id}":' in app

    _assert_snippets(
        confirm,
        [
            'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")',
            "ready_to_submit",
            "official_api_called",
            "production_gaps",
            "required_next_steps",
            "暂无通过预提交检查的 Alpha",
        ],
    )
    assert '"/api/submit"' not in confirm


def test_ux_styles_cover_interaction_feedback_and_responsive_layout():
    css = _source("index.css")
    app = _source("App.tsx")
    candidate = _source("components/CandidateTable.tsx")
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
        css + app + candidate + config + toast,
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
