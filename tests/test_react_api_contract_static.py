from __future__ import annotations

import re
from pathlib import Path

import brain_alpha_ops.web  # noqa: F401  install meta-path bridge for web_* modules
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for

from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_INDEX = ROOT / "brain_alpha_ops" / "web" / "react_app" / "index.html"
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"
README = ROOT / "README.md"
SYSTEM_EVALUATION_DOC = ROOT / "docs" / "COMPREHENSIVE_SYSTEM_EVALUATION_20260514.md"
SMOKE_SCRIPT = ROOT / "scripts" / "browser_react_artifact_smoke.mjs"
QA_E2E_WALKTHROUGH = ROOT / "tests" / "qa_e2e_new_user_walkthrough.py"


def _source(path: str) -> str:
    return resolve_react_source(REACT_SRC / path)


def _sources(paths: list[str]) -> str:
    return "\n".join(_source(path) for path in paths)


def _app_shell_source() -> str:
    return _sources([
        "App.tsx",
        "components/views/renderView.tsx",
        "components/views/renderViewFromContext.tsx",
        "components/views/helpers.ts",
        "hooks/useGlobalData.ts",
        "hooks/useAppState/index.ts",
    ])


def _candidate_source() -> str:
    return _sources([
        "components/CandidateTable.tsx",
        "components/CandidateTableToolbar.tsx",
        "components/CandidateTableSubComponents.tsx",
        "components/CandidateTableUtils.ts",
        "components/CandidateRow.tsx",
        "components/CandidateTablePagination.tsx",
        "components/CandidateDetailPanel.tsx",
        "components/useCandidateColumns.tsx",
        "hooks/useCandidateActions.ts",
        "hooks/useCandidatePipeline.ts",
        "hooks/useSseManager.ts",
        "hooks/useCandidateTableData.ts",
        "hooks/useCandidateGeneration.ts",
        "hooks/useCandidateSimulation.ts",
        "hooks/useCandidateCheck.ts",
        "hooks/useCandidateTableSse.ts",
    ])


def _config_source() -> str:
    return _sources([
        "components/ConfigPanel.tsx",
        "components/ConfigPanel/utils.ts",
        "components/ConfigPanel/ConfigFormFields.tsx",
        "components/ConfigPanel/ScoringWeightModal.tsx",
        "components/ConfigPanel/CredentialsSection.tsx",
        "hooks/useConfigForm.ts",
    ])


def _official_operations_source() -> str:
    return "\n".join(
        resolve_react_source(path)
        for path in [
            REACT_SRC / "components" / "OfficialOperationsPanel.tsx",
            *sorted((REACT_SRC / "components" / "OfficialOperations").glob("*.tsx")),
            *sorted((REACT_SRC / "components" / "OfficialOperations").glob("*.ts")),
        ]
    )


def _snapshot_source() -> str:
    return _sources([
        "components/SnapshotPanel.tsx",
        "components/SnapshotPanel/utils.ts",
        "components/SnapshotPanel/SnapshotPanelCloud.tsx",
        "components/SnapshotPanel/SnapshotPanelLocal.tsx",
        "components/SnapshotPanel/SnapshotPanelCompare.tsx",
        "components/SnapshotPanel/snapshotViews.ts",
    ])


def _react_source_files() -> list[Path]:
    return sorted(path for path in REACT_SRC.rglob("*") if path.suffix in {".ts", ".tsx"})


def _dist_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in REACT_DIST.rglob("*")
        if path.suffix in {".html", ".js", ".css"}
    )


def _normalize_route(url: str) -> str:
    path = url.split("?", 1)[0].split("${", 1)[0]
    return path.rstrip("/")


def test_react_api_paths_are_registered_in_backend_routes():
    backend_paths = set(GET_ROUTES) | set(POST_ROUTES)
    backend_paths.add("/api/trends")
    frontend_paths: set[str] = set()

    for path in _react_source_files():
        source = resolve_react_source(path)
        for match in re.finditer(r'["`](/(?:api|sse)[^"`]*)["`]', source):
            frontend_paths.add(_normalize_route(match.group(1)))

    assert frontend_paths
    assert frontend_paths <= backend_paths


def test_react_dashboard_contract_uses_snapshot_aliases_backed_by_get_routes():
    source = _sources([
        "components/Dashboard/Dashboard.tsx",
        "hooks/useDashboard.ts",
        "hooks/useGlobalData.ts",
    ])

    assert "statusApi.call('/api/production-validation/status')" in source
    assert "cloudApi.call('/api/snapshot/cloud')" in source
    assert "memoryApi.call('/api/snapshot/memory?limit=100&top_n=5')" in source
    assert route_for("GET", "/api/production-validation/status") is not None
    assert route_for("GET", "/api/snapshot/cloud").handler == "cloud_alphas"
    assert route_for("GET", "/api/snapshot/memory").handler == "research_memory"


def test_react_app_cloud_badge_reads_complete_snapshot_summary():
    source = _app_shell_source()

    assert "cloudBadgeTotal(globalData.cloud.data)" in source
    assert "summary.count ?? summary.total ?? summary.total_count" in source
    assert "summary.returned_count" not in source


def test_browser_walkthrough_verifies_complete_cloud_snapshot_without_limit():
    source = QA_E2E_WALKTHROUGH.read_text(encoding="utf-8")
    cloud_paths = ('"/api/' + 'cloud_alphas"', '"/api/' + 'snapshot/cloud"')

    assert '"/api/snapshot/cloud"' in source
    for path in cloud_paths:
        assert f'{path}, params={{"limit"' not in source
        assert f'{path}?limit=' not in source


def test_react_candidate_and_scoring_contracts_match_backend_routes():
    app = _app_shell_source()
    candidates = _candidate_source()
    scoring = _source("components/ScoringPanel")

    assert "candidatesApi.call('/api/candidates')" in app
    assert "CANDIDATE_FETCH_LIMIT" not in candidates
    assert "result?.candidates_preview ||" not in candidates
    assert "callCheckResultsApi<{ items?: CandidateCheckResult[] }>('/api/check_results')" in candidates
    assert "callSingleCheckApi<CandidateCheckResult>('/api/check'" in candidates
    assert "type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string }" in candidates
    assert "callApi<AsyncJobStart>('/api/generate_candidates'" in candidates
    assert "callApi<{ job_id: string; task_id?: string }>" in candidates
    assert "'/api/candidates/simulate'" in candidates
    assert "callBatchCheckApi<AsyncJobStart>('/api/check_batch'" in candidates
    assert "sseManager.connect('task', `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`" in candidates
    assert "callScoreApi('/api/scoring/evaluate'" in scoring
    assert "callAttributionApi('/api/scoring/attribution'" in scoring
    assert "useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}`" in scoring
    assert "nonEmpty(scoring?.hard_gates) || nonEmpty(attributionData?.hard_gates)" in scoring
    assert "页面会自动完成官方评分、归因分析和门禁复核" not in scoring
    assert "归因分析" in scoring
    assert "官方门禁检查" in scoring
    assert "点击评分以通过 /api/scoring/evaluate" not in scoring

    assert route_for("GET", "/api/candidates") is not None
    assert route_for("GET", "/api/check_results") is not None
    assert route_for("POST", "/api/check") is not None
    assert route_for("POST", "/api/generate_candidates") is not None
    assert route_for("POST", "/api/candidates/simulate") is not None
    assert route_for("POST", "/api/check_batch") is not None
    assert route_for("GET", "/sse") is not None
    assert route_for("POST", "/api/scoring/evaluate") is not None
    assert route_for("POST", "/api/scoring/attribution") is not None


def test_react_status_summaries_do_not_cap_reason_lists():
    official_ops = _official_operations_source()
    confirm = _sources(["components/SubmissionConfirmPanel.tsx", "components/SubmissionGates.tsx", "components/SubmissionChecklist.tsx"])
    quality = _source("components/QualityCheckPanel.tsx")
    slots = _source("components/OfficialBacktestSlots.tsx")

    for source in (official_ops, confirm, quality, slots):
        assert ".slice(0, 3)" not in source
        assert ".slice(0, 4)" not in source
        assert "前 ${shown}" not in source
        assert "前 " not in source
    assert "countTitle(" in official_ops
    assert "formatCount(" in confirm
    assert "truncate text-xs text-text-tertiary" not in slots


def test_official_sync_copy_does_not_call_filter_window_count_a_total():
    banned_terms = (
        "官方总量",
        "接口总量",
        "动态总量",
        "等待总量",
        "全局总量",
        "固定总量",
        "云端真实总量",
        "官方报告总量",
        "真实总量",
        "云端库存",
        "真实库存",
        "10000 上限",
        "10,000 上限",
        "固定 10000",
        "固定 10,000",
        "true cloud Alpha inventory",
        "API total",
        "data total",
        "scan totals",
    )
    required_clarifying_terms = (
        "接口分页参考数",
        "不是云端 Alpha 总量",
        "分页边界判断",
    )
    checked_files = [
        REACT_SRC / "App.tsx",
        REACT_SRC / "components" / "Dashboard" / "Dashboard.tsx",
        REACT_SRC / "components" / "OfficialOperationsPanel.tsx",
        REACT_SRC / "components" / "ProgressFeedback.tsx",
        REACT_SRC / "components" / "SnapshotPanel.tsx",
        REACT_SRC / "components" / "StateCards.tsx",
        REACT_SRC / "hooks" / "useApi.ts",
        REACT_SRC / "types" / "index.ts",
        REACT_DIST / "index.html",
        ROOT / "brain_alpha_ops" / "web" / "misc" / "web_progress.py",
        ROOT / "brain_alpha_ops" / "web" / "dispatch" / "web_handler_dispatch.py",
        ROOT / "brain_alpha_ops" / "research" / "pipeline_context_sync.py",
        ROOT / "brain_alpha_ops" / "web" / "handlers" / "sync.py",
        ROOT / "tests" / "test_web_handler_dispatch.py",
        ROOT / "brain_alpha_ops" / "web" / "react_app" / "tests" / "components.test.tsx",
        ROOT / "brain_alpha_ops" / "web" / "react_app" / "tests" / "ui-components.test.tsx",
        README,
    ]

    for path in checked_files:
        source = resolve_react_source(path)
        for term in banned_terms:
            assert term not in source, f"{path.relative_to(ROOT)} must not describe API filter-window count as {term}"
    dist_source = _dist_text()
    for term in banned_terms:
        assert term not in dist_source, f"react dist assets must not describe API filter-window count as {term}"
    official_ops = _official_operations_source()
    for term in required_clarifying_terms:
        assert term in official_ops, f"OfficialOperationsPanel should clarify API filter-window count with {term}"


def test_official_sync_scan_window_count_is_not_unified_total():
    source = _official_operations_source()

    assert "total: stage.kind === 'scan' || terminalFailure || stage.total <= 0 ? undefined : stage.total" in source
    assert "api_reported_total: numberField(syncStatus?.progress, 'api_reported_total') || undefined" in source


def test_phase_shell_keeps_blocked_content_interactive_for_recovery_controls():
    phase_shell = _source("components/PhaseShell.tsx")

    assert 'className="phase-shell-body"' in phase_shell
    assert "pointerEvents" not in phase_shell
    assert "filter: 'grayscale(0.3)'" in phase_shell


def test_react_submission_config_and_job_contracts_match_backend_routes():
    submission = _source("components/SubmissionPanel.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    app = _app_shell_source()
    config = _config_source()
    monitor = _sources([
        "components/JobMonitor.tsx",
        "components/JobMonitor",
        "hooks/useJobMonitor/index.ts",
        "hooks/useJobMonitor",
    ])

    assert "SubmissionConfirmPanel notify={notify}" in submission
    assert "/api/submit" not in submission
    assert "/api/submit_batch" not in submission
    assert "callReadiness<SubmitReadinessResponse>('/api/submit_readiness')" in confirm
    assert route_for("GET", "/api/submit_readiness") is not None
    for endpoint in ("/api/config", "/api/config_schema"):
        assert f"'{endpoint}'" in config
        assert route_for("GET", endpoint) is not None
    assert "connectionApi.call('/api/test_connection'" in config
    assert 'label="Token"' in config
    assert 'autoComplete="off"' in config
    assert "maxLength={512}" in config
    assert route_for("POST", "/api/config") is not None
    assert route_for("POST", "/api/test_connection") is not None
    assert "lazy(() => import('@/components/ConfigPanel'))" in app
    assert "import SubmissionPanel" not in app
    assert "import CredentialQuickStart" in app
    assert "JobMonitor notify={notify} credentials={credentials} jobState={jobState}" in app
    assert "case 'config':" in app
    assert "credentials={credentials}" in app
    assert "onCredentialsChange: appState.setCredentials" in app
    assert "onCredentialsChange={onCredentialsChange}" in app
    assert "api.call<{ job_id: string }>('/api/run'" in monitor
    assert "api.call<{ ok?: boolean; error?: string; error_code?: string }>" in monitor
    assert "'/api/production-validation/stop'" in monitor
    assert "body: JSON.stringify({ job_id: stoppedJobId })" in monitor
    assert "const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;" in monitor
    assert "body: JSON.stringify(buildRunPayload(resume, credentials))" in monitor
    assert "autoSubmit: false" not in monitor
    assert "auto_submit: false" not in monitor
    assert "auto_submitted" in monitor
    assert "页面凭证为空" in monitor
    assert "填写凭证" in monitor
    assert "if (!running || !jobId) return;" in monitor
    assert "api.call<JobStatus>(" in monitor
    assert "`/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`" in monitor
    assert "运行证明" not in monitor
    assert "submittedThisRun" in monitor
    assert "autoSubmitted" in monitor
    assert route_for("POST", "/api/run") is not None
    assert route_for("POST", "/api/production-validation/stop") is not None
    assert route_for("GET", "/api/production-validation/status") is not None


def test_react_cancel_helper_uses_cross_store_cancel_route():
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in _react_source_files())
    cancel = _source("api/jobCancel.ts")

    assert "'/api/cancel'" in cancel
    assert "'/api/production-validation/stop'" not in cancel
    assert '"/api/stop"' not in source_text
    assert route_for("POST", "/api/cancel") is not None


def test_default_react_app_and_dist_do_not_expose_raw_submit_surface():
    app = _app_shell_source()
    state_cards = _source("components/StateCards.tsx")
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in _react_source_files())
    dist_text = _dist_text()
    raw_submit_pattern = re.compile(r"/api/(?:submit|submit_batch)(?:$|[?#'\"`])")

    assert "import SubmissionPanel" not in app
    assert "SubmissionPanel notify={notify}" not in app
    assert "<SubmissionConfirmPanel notify={notify}" in app
    assert 'title: "手动提交"' not in state_cards
    assert "进入提交" not in state_cards
    assert raw_submit_pattern.search(source_text) is None
    assert raw_submit_pattern.search(dist_text) is None
    assert "手动提交" not in dist_text


def test_react_dist_preserves_browser_safe_credentials_and_sync_recovery_contracts():
    dist_text = _dist_text()

    assert 'autoComplete:"username"' not in dist_text
    assert 'autocomplete:"username"' not in dist_text
    assert 'autoComplete:"current-password"' not in dist_text
    assert 'autocomplete:"current-password"' not in dist_text
    assert "brain_alpha_active_sync_job_id" in dist_text
    assert "/api/sync_status?compact=1" in dist_text
    assert "/api/sync_status?job_id=" in dist_text
    assert "Request failed" in dist_text
    assert "HTTP ${" in dist_text
    assert "ok:!1" in dist_text
    assert "/api/sync_alphas" in dist_text
    assert "已有官方上下文刷新正在运行，已接管当前任务状态。" in dist_text
    assert "已接管正在运行的官方上下文刷新" in dist_text


def test_react_html_shell_uses_local_resources_only_for_credential_flow():
    html_text = REACT_INDEX.read_text(encoding="utf-8")
    dist_html = (REACT_DIST / "index.html").read_text(encoding="utf-8")

    for page in (html_text, dist_html):
        assert "fonts.googleapis.com" not in page
        assert "fonts.gstatic.com" not in page
        assert 'rel="preconnect"' not in page


def test_react_official_operations_is_web_operator_console_not_cli_surface():
    app = _app_shell_source()
    state_cards = _source("components/StateCards")
    operations = _official_operations_source()
    types = _source("types/ui.ts")

    assert "'official_operations'" in types
    assert '"visual_terminal"' not in types
    assert "official_operations: '官方操作'" in app
    assert "case 'official_operations':" in app
    assert "<OfficialOperationsPanel" in app
    assert "notify={notify}" in app
    assert "credentials={credentials}" in app
    assert "VisualTerminalPanel" not in app
    assert "visual_terminal" not in app
    assert "title: '官方操作'" in state_cards
    assert "description: '按钮驱动的官方上下文、合规与阻断复核'" in state_cards
    assert "visual_terminal" not in state_cards
    assert "/api/sync_alphas" in operations
    assert "/api/sync_status" in operations
    assert "/api/sync_cancel" in operations
    assert "/api/submit_readiness" in operations
    assert "/api/check_results" in operations
    assert "...credentialsPayload(credentials)" in operations
    assert "if (password) payload.password = password;" in operations
    assert route_for("POST", "/api/sync_alphas") is not None
    assert route_for("GET", "/api/sync_status") is not None
    assert route_for("POST", "/api/sync_cancel") is not None
    assert route_for("GET", "/api/submit_readiness") is not None
    assert route_for("GET", "/api/check_results") is not None
    assert re.search(r"['\"`]\/api\/submit(?:[?/'\"`]|$)", operations) is None
    assert re.search(r"['\"`]\/api\/submit_batch(?:[?/'\"`]|$)", operations) is None
    assert "不展示命令或路径" in operations
    assert "用户只需留在浏览器里查看进度和结果" in operations
    assert "官方操作入口" in operations
    assert "同一个页面" in operations
    assert "Web 控制台内" not in operations
    assert "Web 操作台" not in operations
    assert "可视化终端" not in operations
    assert "任务页" not in operations
    assert "visual_terminal" not in operations
    assert "TerminalMode" not in operations
    assert "TerminalLogEntry" not in operations
    assert "用户打开命令行" not in operations
    assert "shell 命令" not in operations
    assert "终端界面" not in operations
    assert "终端进度" not in operations


def test_react_components_do_not_display_raw_api_error_fields_directly():
    offenders: list[str] = []
    banned_patterns = (
        re.compile(r"notify\([^;\n]*(?:result|Result)\??\.error\b"),
        re.compile(r"set[A-Za-z]+Error\([^;\n]*(?:result|Result)\??\.error\b"),
        re.compile(r"(?:result|Result)\??\.error\s*\|\|"),
        re.compile(r"(?:result|Result)\??\.error_code\s*\|\|"),
        re.compile(r"`[^`]*\$\{(?:connectionApi|logoutApi)\.error\}[^`]*`"),
        re.compile(r">\s*\{(?:connectionApi|logoutApi)\.error\}\s*<"),
    )
    checked_files = [
        REACT_SRC / "App.tsx",
        *(REACT_SRC / "components").glob("*.tsx"),
    ]

    for path in checked_files:
        source = resolve_react_source(path)
        for pattern in banned_patterns:
            for match in pattern.finditer(source):
                offenders.append(f"{path.relative_to(ROOT)}:{match.group(0)}")

    assert not offenders, "raw API errors must pass through apiErrorMessage/jobStatusMessage: " + "; ".join(offenders)

    for relative in (
        "components/views/_renderViewHelpers.tsx",
        "hooks/useCandidateTableData.ts",
        "hooks/useConfigForm.ts",
        "components/QualityCheckPanel.tsx",
        "components/ScoringPanel.tsx",
        "components/SnapshotPanel.tsx",
        "components/SubmissionConfirmPanel.tsx",
    ):
        assert "apiErrorMessage(" in _source(relative), f"{relative} should use shared API error copy"

    for relative in (
        "App.tsx",
        "components/ConfigPanel.tsx",
        "hooks/useDashboard.ts",
        "components/StateCards",
    ):
        assert "safeDisplayErrorMessage(" in _source(relative), f"{relative} shell display errors should fail closed"


def test_react_api_error_helpers_keep_af018_metadata_contract():
    error_experience = _source("helpers/errorExperience.ts")
    use_api = _source("hooks/useApi.ts")

    for snippet in (
        "user_error?:",
        "user_error_kind?: string;",
        "user_message?: string;",
        "next_action?: string;",
        "recoverable?: boolean;",
        "retryable?: boolean;",
    ):
        assert snippet in error_experience
        assert snippet in use_api

    assert "payload?.user_message" in error_experience
    assert "return fallback;" in error_experience
    assert "networkErrorMessage(err)" in use_api


def test_browser_react_smoke_fails_when_non_submit_state_experience_is_not_exercised():
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "report.productionValidation = {" in smoke
    assert "home shell does not expose local non-submit validation state" in smoke
    assert "home shell does not expose non-submit proof metrics" in smoke
    assert "production validation monitor did not render non-submit proof surface" in smoke
    assert "production validation interrupted state did not show safe user-facing copy" in smoke
    assert "production validation interrupted state did not return controls to retry-safe state" in smoke
    assert "production validation run request did not preserve non-submit/no-credential payload" in smoke
    assert "report.submissionConfirm = {" in smoke
    assert "submission confirm panel did not render final non-submit blocker review" in smoke
    assert "submission confirm panel did not show scientific-audit blockers" in smoke
    assert "submission confirm panel exposed raw readiness/check/status text" in smoke
    assert "submission confirm panel attempted a submit endpoint" in smoke
    assert "report.candidateOperations = {" in smoke
    assert "candidate operations panel did not render target-pool recovery controls" in smoke
    assert "candidate operations auto-advance control was not clickable" in smoke
    assert "candidate operations official validation queue did not run visible mocked simulation" in smoke
    assert "candidate operations official validation queue did not continue into quality gate check" in smoke
    assert "simulate_queue_zero_smoke" in smoke
    assert "negativeOfficialSimulationFailed" in smoke
    assert "candidate operations zero-success official validation queue did not fail closed before quality gate check" in smoke
    assert "candidate operations zero-success official validation queue called check_batch before a successful simulation" in smoke
    assert "candidate operations did not navigate from a candidate row into scoring" in smoke
    assert "candidate operations auto-advance request did not preserve local non-submit/no-credential payload" in smoke
    assert "candidate operations official validation simulation request did not preserve safe Top3 no-credential payload" in smoke
    assert "candidate operations batch quality check request did not preserve safe simulated-candidate no-credential payload" in smoke
    assert "report.scoringPanel = {" in smoke
    assert "scoring panel did not render clicked-candidate scoring attribution and gate evidence" in smoke
    assert "score_failed_smoke" in smoke
    assert "raw backend scoring failure password=secret" in smoke
    assert "raw backend family password=secret" in smoke
    assert "REPORT_RAW_BACKEND_TEXT_PATTERN" in smoke
    assert "RAW_BACKEND_SCORE_STATUS" in smoke
    assert "评分失败，请重新评估候选后再继续。" in smoke
    assert "failureRefreshClicked" in smoke
    assert "failureUserCopy" in smoke
    assert "failureRetryVisible" in smoke
    assert "failureNotComplete" in smoke
    assert "failureRawBackendHidden" in smoke
    assert "recoveredAfterRetry" in smoke
    assert "scoringFailureRetryInteractionExpression" in smoke
    assert "validateScoringFailureRetryInteractions" in smoke
    assert "scoring_failure_retry" in smoke
    assert "scoring failure retry slice did not navigate from candidate row into scoring" in smoke
    assert "scoring failure retry slice did not render initial clicked-candidate scoring success" in smoke
    assert "scoring failure retry slice did not stay retry-safe and non-complete after refresh failure" in smoke
    assert "scoring failure retry slice did not recover after retry success" in smoke
    assert "scoring failure retry slice exposed raw backend/session text" in smoke
    assert "scoring failure retry slice did not exercise initial success, refresh failure, and retry success" in smoke
    assert "scoring failure retry request ${endpoint} did not preserve no-credential candidate payload" in smoke
    assert "scoring failure retry slice attempted a submit endpoint" in smoke
    assert "scoring failure retry slice request carried credential-like fields" in smoke
    assert "scoring panel failure state did not stay retry-safe and non-complete" in smoke
    assert "scoring panel retry did not recover after a failed scoring event" in smoke
    assert "scoring panel failure state exposed raw backend/session text" in smoke
    assert "scoring request ${endpoint} did not preserve no-credential candidate payload" in smoke
    assert "clickedScoreAlphaId" in smoke
    assert "clickedAlphaId: clickedScoreAlphaId" in smoke
    assert "body.alpha_id !== scoringPanel.clickedAlphaId" in smoke
    assert "body.candidate.alpha_id !== scoringPanel.clickedAlphaId" in smoke
    assert "report.backtestSlots = {" in smoke
    assert "official backtest slots panel did not render slot capacity summary" in smoke
    assert "official backtest slots panel did not render running, empty, and completed slot states" in smoke
    assert "report.qualityCheck = {" in smoke
    assert "quality check panel did not render local and official evidence summary" in smoke
    assert "quality check panel did not show non-submit blocker evidence and next action" in smoke
    assert "raw backend action password=secret" in smoke
    assert "等待候选和门禁数据" in smoke
    assert "report.configPanel = {" in smoke
    assert "config panel did not render safe cache/session configuration copy" in smoke
    assert "config panel connection test ran during browser smoke" in smoke
    assert "report.snapshotPanel = {" in smoke
    assert "snapshot panel did not render checkpoint evidence rows" in smoke
    assert "snapshot panel exposed raw checkpoint status, visible fields, or backend detail text" in smoke
    assert "report.robustnessReplay = {" in smoke
    assert "replayAuditInteractionExpression" in smoke
    assert "validateReplayAuditInteractions" in smoke
    assert 'argValue("--slice", "full")' in smoke
    assert "VALID_SLICES" in smoke
    assert "--slice must be one of: ${VALID_SLICES.join" in smoke
    assert 'slice === "replay_audit"' in smoke
    assert 'slice === "scoring_failure_retry"' in smoke
    assert "30000" in smoke
    assert "45000" in smoke
    assert "runSmokeStep(" in smoke
    assert "diagnosticMessage(" in smoke
    assert "last_mock_endpoint=" in smoke
    assert "viewport=${viewport}" in smoke
    assert "step=${step}" in smoke
    assert "elapsed_ms=${elapsedMs}" in smoke
    assert "robustness replay audit slice did not navigate to the robustness evidence panel" in smoke
    assert "robustness replay audit panel did not render local latest_result replay metrics" in smoke
    assert "robustness replay audit panel did not expose stop-rule, non-submit, and scientific-audit evidence" in smoke
    assert "robustness replay audit panel exposed local path or raw backend text" in smoke
    assert "/api/latest_result" in smoke
    assert "expected mocked GET /api/latest_result" in smoke
    assert "unexpected browser-smoke mutating request ${request.method} ${request.path}" in smoke
    assert "replay_audit" in smoke
    assert "本地回放审计" in smoke
    assert "非提交边界" in smoke
    assert "停机规则:check_live_submit_readiness\\.py" in smoke
    assert "raw backend-only checkpoint failure" in smoke
    assert "raw backend title password=secret" in smoke
    assert "raw backend metric api_key=secret" in smoke
    assert "raw backend metric csrf_token=secret" in smoke
    assert "raw backend delta password=secret" in smoke
    assert "RAW_BACKEND_RISK password=secret" in smoke
    assert "RAW_BACKEND_CHECK_STATUS" in smoke
    assert "详情待确认" in smoke
    assert "记录待确认" in smoke
    assert "指标待确认" in smoke
    assert "时间待确认" in smoke
    assert "趋势待确认" in smoke
    assert "对比项待确认" in smoke
    assert "raw backend-only submission gap" in smoke
    assert "raw backend-only submit action" in smoke
    assert "raw backend-only check reason" in smoke
    assert "状态待确认" in smoke
    assert "提交前阻断复核" in smoke
    assert "report.lifecycleReplay = {" in smoke
    assert "lifecycle replay panel did not render local read-only non-submit state" in smoke
    assert "lifecycle replay panel did not expose replay summary metrics" in smoke
    assert "lifecycle replay recovered trace did not prioritize latest passed state" in smoke
    assert "lifecycle replay blocked trace did not show review next action" in smoke
    assert "lifecycle replay panel exposed secret-like labels or values" in smoke
    assert 'document.querySelector(\'section[aria-label="生命周期回放"]\')' in smoke
    assert "report.officialOperations = {" in smoke
    assert 'document.querySelector(\'section[aria-label="官方同步数据总览"]\')' in smoke
    assert 'Array.from(document.querySelectorAll("h2"))' in smoke
    assert 'officialHeading?.closest(".animate-fade-in")' in smoke
    assert "officialPanel?.innerText || \"\"" in smoke
    assert "official operations panel did not render the non-submit sync entry and overview" in smoke
    assert "official operations session-invalid recovery state did not show safe reconnect guidance" in smoke
    assert "official operations open-ended sync scan did not stay indeterminate and non-complete" in smoke
    assert "official operations stopped/cancelled sync state did not stay retry-safe and non-complete" in smoke
    assert "official operations intermediate state-error snapshots overflow horizontally" in smoke
    assert "official operations sync warning state did not expose safe partial-success guidance" in smoke
    assert "official operations readiness review did not stay visibly blocked and non-submit" in smoke
    assert "official operations readiness review did not show scientific-audit blockers" in smoke
    assert "official operations check-results review did not load visible quality evidence" in smoke
    assert "official operations panel exposed raw backend/session or secret-like text" in smoke
    assert "official operations sync request did not preserve safe local visual-smoke payload" in smoke
    assert "official operations sync cancel request did not preserve safe local visual-smoke payload" in smoke
    assert "sync_open_ended_scan" in smoke
    assert "sync_cancelled_terminal" in smoke
    assert "scientificAuditBlocked" in smoke
    assert "missing_scientific_audit" in smoke
    assert "scientific_audit_submit_boundary_breached" in smoke
    assert "latest_candidate_scientific_audit_test_feedback_used" in smoke
    assert "incomplete_scientific_audit" in smoke
    assert "缺少科学审计证据" in smoke
    assert "科学审计提交边界异常" in smoke
    assert "最新候选科学审计含测试反馈" in smoke
    assert "科学审计证据不完整" in smoke
    assert "后台确认状态为已停止" in smoke
    assert "后台确认状态为已取消" in smoke
    assert "reconnectClicked && reconnectNavigated" in smoke
    assert "stateOverflowFree" in smoke
    assert "!/width:\\s*100%/i.test(scanProgressFillStyle)" in smoke
    assert 'document.querySelector(\'[role="progressbar"][aria-label*="扫描云端"]\')' in smoke
    assert "completed_with_warnings" in smoke
    assert "COMPLETED_WITH_WARNINGS" in smoke
    assert 'context_status: "failed"' in smoke
    assert 'userFacingOperation !== "official_operations_context_refresh"' in smoke
    assert "REPORT_FORBIDDEN_TEXT_PATTERN" in smoke
    assert "SENSITIVE_KEY_PATTERN" in smoke
    assert "isSensitiveKey(" in smoke
    assert "user[_-]?name" in smoke
    assert "|user|" not in smoke
    assert "searchHasCredentialFields(" in smoke
    assert "hasCredentialSearch: searchHasCredentialFields(url.search)" in smoke
    assert 'userFacingOperation !== "official_operations_context_refresh"' in smoke
    assert "redactText(" in smoke
    assert "redactUrl(" in smoke
    assert "redactReportValue(result)" in smoke
    assert "assertReportRedacted(serializedResult)" in smoke
    assert "SECRET_TEXT_PATTERN" in smoke
    assert "forbiddenLifecycleSecretsVisible" in smoke
    assert 'textSample: "<omitted>"' in smoke
    assert 'sample: "<omitted>"' in smoke
    assert "password|passwd|pwd|hunter2" in smoke
    assert "client[_-]?secret" in smoke
    assert "api[_-]?key" in smoke
    assert "set[_-]?cookie" in smoke
    assert "hasCredentialFields: requestHasCredentialFields(request.postData || \"\")" in smoke
    assert "Boolean(request.hasCredentialSearch)" in smoke
    assert "Boolean(request.hasCredentialFields)" in smoke
    assert "redactRequestBody(request.postData || \"\")" in smoke
    assert "redactSearchParams(url.search)" in smoke
    assert "csrfPresent: Boolean" in smoke
    assert "streamPresent: Boolean" in smoke
    assert "metrics.meta.csrfPresent" in smoke
    assert "UNMOCKED_BROWSER_SMOKE_API" in smoke
    assert "NON_LOCAL_BROWSER_SMOKE_REQUEST_BLOCKED" in smoke
    assert "LOOPBACK_HOSTS" in smoke
    assert "requireLoopbackHttpUrl(rawUrl, \"--url\")" in smoke
    assert 'requireLoopbackHttpUrl(argValue("--devtools-url"' in smoke
    assert "isLocalBrowserUrl(rawUrl)" in smoke
    assert "browser attempted to load a non-local resource" in smoke
    assert 'urlPattern: "*", requestStage: "Request"' in smoke
    assert '"Fetch.continueRequest"' in smoke
    assert "networkRequests: [...session.networkRequests]" in smoke
    assert "blockedNonLocalRequests: [...session.blockedNonLocalRequests]" in smoke
    assert "production validation interrupted state overflows horizontally" in smoke
    assert "/session_invalid/i" in smoke or "session_invalid|invalid local session/i" in smoke

    for endpoint in (
        "/api/phase_state",
        "/api/production-validation/status",
        "/api/candidates",
        "/api/alpha_lifecycle",
        "/api/backtest_slots",
        "/api/config",
        "/api/checkpoint_status",
        "/api/snapshot/cloud",
        "/api/snapshot/memory",
        "/api/sync_status",
        "/api/submit_readiness",
        "/api/check_results",
        "/api/run",
        "/api/sync_alphas",
        "/api/sync_cancel",
        "/api/generate_candidates",
        "/api/scoring/evaluate",
        "/api/scoring/attribution",
    ):
        assert f'"{endpoint}"' in smoke
    assert 'pathname === "/api/alpha_lifecycle"' in smoke
    assert "/(?:\\?|&)limit=250(?:&|$)/.test(request.search)" in smoke
    assert 'requested("POST", endpoint)' in smoke
    assert "`expected mocked POST ${endpoint}`" in smoke
    assert 'body.refreshOfficialContext !== true' in smoke
    assert 'body.automation_mode !== "maintain_candidate_pool"' in smoke
    assert 'body.auto_simulate_after_generation !== false' in smoke
    assert 'body.auto_check_after_simulation !== false' in smoke
    assert "body.candidate" in smoke
    assert 'match(/ALPHA_[A-Z0-9_]+/)' in smoke
    assert "body.alpha_id !== scoringPanel.clickedAlphaId" in smoke
    assert 'Boolean(request.hasCredentialFields)' in smoke
    assert 'Boolean(request.hasCredentialSearch)' in smoke
    assert "MUTATING_METHODS" in smoke
    assert "ALLOWED_MUTATING_REQUESTS" in smoke
    assert '"POST /api/run"' in smoke
    assert '"POST /api/sync_alphas"' in smoke
    assert '"POST /api/sync_cancel"' in smoke
    assert '"POST /api/generate_candidates"' in smoke
    assert '"POST /api/candidates/simulate"' in smoke
    assert '"POST /api/check_batch"' in smoke
    assert "checkBatchBeforeSimulationSuccessCount" in smoke
    assert "candidate operations mock server observed check_batch before official simulation success" in smoke
    assert '"POST /api/scoring/evaluate"' in smoke
    assert '"POST /api/scoring/attribution"' in smoke
    assert "isAllowedMutatingRequest(request.method, request.path)" in smoke
    assert "unexpected browser-smoke mutating request" in smoke
    assert 'requestCount("POST", endpoint) !== 0' in smoke
    assert "`unexpected browser-smoke API request ${endpoint}`" in smoke
    assert "`unmocked browser-smoke API request ${request.method} ${request.path}`" in smoke

    assert 'pathname === "/api/submit" || pathname === "/api/submit_batch"' in smoke
    assert "WEB_ONLY_SUBMIT_REQUIRED" in smoke
    for endpoint in (
        "/api/candidate/submit",
        "/api/check",
        "/api/sync_context_only",
        "/api/test_connection",
        "/api/config",
        "/api/candidates/optimize",
    ):
        assert f'"{endpoint}"' in smoke


def test_readme_keeps_operator_path_in_official_operations_area():
    readme = README.read_text(encoding="utf-8")

    # 允许 emoji 前缀 (例如 "## 🔄 核心操作流程", "## 👥 开发与贡献")
    assert re.search(r"^##\s+\S*\s*核心操作流程", readme, re.MULTILINE) is not None, (
        "README must contain a '## 核心操作流程' section heading"
    )
    assert re.search(r"^##\s+\S*\s*开发与贡献", readme, re.MULTILINE) is not None, (
        "README must contain a '## 开发与贡献' section heading"
    )
    assert "Web 控制台" in readme
    assert "独立审批路径" in readme
    assert "### 🔒 预提交审查" in readme
    assert "不会" in readme and "直接执行提交" in readme
    assert "独立审批路径执行前，所有阻断项已被识别和处理" in readme
    assert "official-operations" not in readme
    assert "大多数量化研究者偏好 CLI" not in readme
    assert "CLI 已满足基本需求" not in readme


def test_system_evaluation_keeps_cli_as_internal_automation_only():
    report = SYSTEM_EVALUATION_DOC.read_text(encoding="utf-8")

    assert "### 5.2 内部自动化接口" in report
    assert "不能作为最终用户操作路径" in report
    assert "最终用户只通过 Web 控制台与官方操作区操作" in report
    assert "不维护面向最终用户的 CLI 产品面" in report
    assert "脚本只能作为内部自动化、CI、维护者诊断接口" in report
    assert "不能作为最终用户操作路径" in report
    assert "### 5.2 CLI 交互" not in report
    assert "大多数量化研究者偏好 CLI" not in report
    assert "CLI 已满足基本需求" not in report


def test_react_snapshot_panel_contracts_match_backend_routes():
    snapshot = _snapshot_source()

    for endpoint in (
        "/api/snapshot/cloud",
        "/api/checkpoint_status",
        "/api/lifecycle",
        "/api/research_memory",
        "/api/research_knowledge",
        "/api/research_observability",
        "/api/prompt_runs",
        "/api/sqlite_indexes",
        "/api/latest_result",
    ):
        assert f"'{endpoint}" in snapshot
        assert route_for("GET", endpoint) is not None
    assert "normalizeSnapshotRow" in snapshot
    assert "snapshotStatusLabel" in snapshot
    assert "safeSnapshotDetail" in snapshot
    assert "safeSnapshotDisplayText" in snapshot
    assert "状态待确认" in snapshot
    assert "详情待确认" in snapshot
    assert "记录待确认" in snapshot
    assert "指标待确认" in snapshot
    assert "时间待确认" in snapshot
    assert "趋势待确认" in snapshot
    assert "对比项待确认" in snapshot
    assert "类型待确认" in snapshot
    assert "RAW_SNAPSHOT_TEXT_PATTERN" in snapshot
    assert "replay_audit" in snapshot
    assert "回放审计" in snapshot
    assert "本地回放审计" in snapshot
    assert "check_live_submit_readiness.py" in snapshot
    assert "非提交边界" in snapshot
    assert "replayStopRule" in snapshot


def test_react_state_cards_include_checkpoint_history_entry():
    app = _app_shell_source()
    sidebar = _source("components/Sidebar.tsx")
    state_cards = _source("components/StateCards")
    types = _source("types/ui.ts")

    assert "'checkpoint_status'" in types
    assert "checkpoint_status: '续跑记录'" in app
    assert "'robustness'" in types
    assert "robustness: '稳健性证据'" in app
    assert "case 'checkpoint_status':" in app
    assert 'viewMode="checkpoint_status"' in app
    assert "case 'robustness':" in app
    assert 'viewMode="robustness"' in app
    assert "id: 'robustness'" in sidebar
    assert "label: '稳健性证据'" in sidebar
    assert "checkpointApi.call('/api/checkpoint_status')" in state_cards
    assert "title: '续跑记录'" in state_cards
    assert "description: '上次进度与运行历史回溯'" in state_cards


def test_react_fetch_helpers_keep_session_csrf_replay_and_sse_credentials():
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")
    csrf_utils = _source("utils/csrf.ts")

    assert "credentials: 'same-origin'" in use_api
    assert "headers['X-Brain-Alpha-CSRF'] = csrf" in use_api
    assert "'X-Brain-Alpha-Request-ID'" in csrf_utils
    assert "'X-Brain-Alpha-Request-Timestamp'" in csrf_utils
    assert "headers['Content-Type'] = 'application/json';" in use_api
    assert "DEFAULT_REQUEST_TIMEOUT_MS = 600000" in use_api
    assert 'signal: options?.signal ?? controller?.signal' in use_api
    error_experience = _source("helpers/errorExperience.ts")
    assert "'网络请求未在预期时间内返回，请刷新状态或稍后重试。'" in error_experience
    assert "networkErrorMessage(err)" in use_api
    assert "new EventSource(withStreamToken(streamUrl), { withCredentials: true })" in use_sse
    assert "onExhaustedRef.current?.();" in use_sse
    assert "return { connected, exhausted, reconnectAttempts, lastEvent, close };" in use_sse
    assert 'meta[name="brain-alpha-stream"]' in csrf_utils
    assert "stream_token=${encodeURIComponent(token)}" in use_sse
    assert "const namedEvents: NamedSSEEvent[] = [" in use_sse
    assert "'stream_timeout'" in use_sse
    assert "es.addEventListener(eventName" in use_sse


def test_react_build_template_exposes_backend_token_placeholders():
    html = REACT_INDEX.read_text(encoding="utf-8")
    csrf_utils = _source("utils/csrf.ts")

    assert 'name="brain-alpha-csrf" content="__BRAIN_ALPHA_OPS_CSRF_TOKEN__"' in html
    assert 'name="brain-alpha-stream" content="__BRAIN_ALPHA_OPS_STREAM_TOKEN__"' in html
    assert 'meta[name="brain-alpha-csrf"]' in csrf_utils
