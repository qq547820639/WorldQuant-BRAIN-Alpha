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
    submission = _source("components/SubmissionPanel.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    progress = _source("components/ProgressFeedback.tsx")
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
        progress + use_api + use_sse + csrf_utils,
        [
            'role="progressbar"',
            "normalizedPercent(progress, state)",
            'credentials: "same-origin"',
            'headers["X-Brain-Alpha-CSRF"] = csrf',
            '"X-Brain-Alpha-Request-ID"',
            "new EventSource(withStreamToken(streamUrl), { withCredentials: true })",
            "onExhaustedRef.current?.();",
            "stream_token=${encodeURIComponent(token)}",
        ],
    )


def test_browser_react_smoke_requires_official_and_alpha_flow_assertions():
    smoke = (ROOT / "scripts" / "browser_react_artifact_smoke.mjs").read_text(encoding="utf-8")

    _assert_snippets(
        smoke,
        [
            "const officialOperations = interactions.officialOperations || {};",
            "official operations card did not expose the button-driven Web flow",
            "official operations did not show readiness blockers and check results",
            "official operations did not auto-interrupt unclear refresh state",
            "official operations still exposes command-line wording",
            "const alphaFlow = interactions.alphaFlow || {};",
            "candidate generation flow was not exercised through the Web UI",
            "candidate generation did not request backend cancellation after ambiguous SSE state",
            "scoring flow did not request backend cancellation after ambiguous SSE state",
            '"/api/sync_alphas"',
            '"/api/sync_cancel"',
            '"/api/generate_candidates"',
            '"/api/scoring/evaluate"',
            '"/api/scoring/attribution"',
            '"/api/cancel"',
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
