from __future__ import annotations

from pathlib import Path

import brain_alpha_ops.build_inline as build_inline


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"

REACT_CONTRACT_COVERAGE = {
    "App.tsx": "state-card router, shell chrome, and detail view selection",
    "main.tsx": "React root bootstrap",
    "components/CandidateTable.tsx": "candidate generation, filters, queue views, and SSE completion",
    "components/ConfigPanel.tsx": "config hydration, schema options, validation, import/export, and save",
    "components/Dashboard.tsx": "dashboard snapshots and landing metrics",
    "components/JobMonitor.tsx": "production job start/stop/status and SSE progress",
    "components/KpiCard.tsx": "compact KPI presentation",
    "components/OfficialBacktestSlots.tsx": "official backtest slot polling and conflict guidance",
    "components/ProgressFeedback.tsx": "accessible progress, spinner, ETA, retry, and indeterminate states",
    "components/QualityCheckPanel.tsx": "quality gate summary and readiness blockers",
    "components/ScoringPanel.tsx": "score evaluation, attribution, and result presentation",
    "components/SnapshotPanel.tsx": "cloud/checkpoint/research/history snapshots",
    "components/StateCards.tsx": "card-first navigation and startup status loading",
    "components/SubmissionConfirmPanel.tsx": "read-only submit readiness confirmation",
    "components/SubmissionPanel.tsx": "manual checks, guarded submit, batch jobs, and SSE status",
    "components/ToastContainer.tsx": "toast roles, actions, and dismissal",
    "hooks/useApi.ts": "CSRF, replay headers, same-origin credentials, and error mapping",
    "hooks/useSSE.ts": "stream token, credentials, reconnect, and close semantics",
    "hooks/useToast.ts": "toast lifecycle state",
    "types/index.ts": "shared API, progress, candidate, and card view contracts",
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
    progress = _source("components/ProgressFeedback.tsx")
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")

    _assert_snippets(
        candidate,
        [
            "const PAGE_SIZE = 20;",
            "candidateMatchesQueueView(candidate, viewMode, checkResults)",
            "sanitizeTextInput(value, MAX_FILTER_LENGTH)",
            "const rows = result?.candidates || result?.candidates_preview || [];",
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
            "validateAlphaId(alphaId)",
            "validateCandidateJsonRows(rows)",
            "validateBatchSubmitCandidates(submitCandidates)",
            '"/api/check_batch"',
            '"/api/submit_batch"',
            'useSSE(batchCheckTaskId ? `/sse?job_id=${encodeURIComponent(batchCheckTaskId)}` : null',
            'useSSE(submitTaskId ? `/sse?job_id=${encodeURIComponent(submitTaskId)}` : null',
            'aria-describedby="confirm-submit-help"',
        ],
    )
    _assert_snippets(
        progress + use_api + use_sse,
        [
            'role="progressbar"',
            "normalizedPercent(progress)",
            'credentials: "same-origin"',
            'headers["X-Brain-Alpha-CSRF"] = csrf',
            'headers["X-Brain-Alpha-Request-ID"] = createRequestId();',
            "new EventSource(withStreamToken(streamUrl), { withCredentials: true })",
            "stream_token=${encodeURIComponent(token)}",
        ],
    )


def test_app_ux_orchestrator_has_tested_navigation_empty_and_busy_contracts():
    app = _source("App.tsx")
    state_cards = _source("components/StateCards.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")

    _assert_snippets(
        app + state_cards,
        [
            'useState<CardViewId | "cards">("cards")',
            "StateCards onNavigate={handleNavigate} notify={notify}",
            "setActiveView(view)",
            'aria-label="返回状态卡"',
            'aria-label="打开系统配置"',
            "候选生成 → 官方回测 → 质量检查 → 提交确认",
            "grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7",
            "onClick={() => onNavigate(config.id)}",
            'role="alert"',
            'aria-live="assertive"',
            "ProgressFeedback",
            'phase: "state_cards_load"',
        ],
    )
    for view_id in (
        "candidates",
        "official_backtests",
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
    toast = _source("components/ToastContainer.tsx")

    _assert_snippets(
        css,
        [
            ":focus-visible",
            ".btn-primary",
            ".btn-secondary",
            ".btn-danger",
            ".card",
            ".progress-feedback",
            ".progress-spinner",
            "@keyframes progress-indeterminate",
            "@keyframes fade-in",
            ".line-clamp-2",
        ],
    )
    _assert_snippets(
        app + candidate + toast,
        [
            "min-h-[100dvh] min-w-0 flex flex-col",
            "px-4 py-4 sm:px-6 lg:px-8",
            "flex-1 min-w-0 p-4 sm:p-6 lg:p-8 overflow-auto",
            "flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center",
            "w-full min-w-0 bg-gray-800",
            "max-w-full overflow-auto",
            "fixed left-4 right-4 top-4",
            "sm:bottom-4 sm:left-auto sm:top-auto sm:max-w-sm",
        ],
    )
