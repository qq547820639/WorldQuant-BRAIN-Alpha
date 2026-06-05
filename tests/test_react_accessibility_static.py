from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_COMPONENTS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components"
APP = REACT_SRC / "App.tsx"


def _component(name: str) -> str:
    return (REACT_COMPONENTS / name).read_text(encoding="utf-8")


def test_react_app_state_cards_have_accessible_navigation_semantics():
    app = APP.read_text(encoding="utf-8")
    state_cards = _component("StateCards.tsx")

    assert 'useState<CardViewId | "cards">("cards")' in app
    assert 'aria-label="返回状态卡"' in app
    assert 'aria-label="打开系统配置"' in app
    assert "onClick={() => onNavigate(config.id)}" in state_cards
    assert 'type="button"' in state_cards
    assert "focus:outline-none focus:ring-2 focus:ring-brand-500/50" in state_cards
    assert 'role="alert"' in state_cards
    assert 'aria-live="assertive"' in state_cards
    assert 'aria-hidden="true"' in state_cards


def test_react_dashboard_and_candidate_errors_are_announced():
    dashboard = _component("Dashboard.tsx")
    candidates = _component("CandidateTable.tsx")
    snapshots = _component("SnapshotPanel.tsx")

    assert 'role="alert"' in dashboard
    assert 'aria-live="assertive"' in dashboard
    assert 'aria-label="过滤候选"' in candidates
    assert 'aria-label="刷新候选"' in candidates
    assert 'role="alert"' in candidates
    assert 'aria-label={`筛选 ${config.title}`}' in snapshots
    assert 'aria-label={`${config.title}表格`}' in snapshots


def test_react_submission_inputs_expose_validation_and_confirmation_context():
    submission = _component("SubmissionPanel.tsx")

    assert 'aria-describedby="alpha-id-validation"' in submission
    assert 'aria-describedby="candidate-json-validation"' in submission
    assert "aria-invalid={Boolean(candidateJsonError)}" in submission
    assert 'role={candidateJsonError ? "alert" : undefined}' in submission
    assert 'aria-describedby="confirm-submit-help"' in submission
    assert 'id="confirm-submit-help"' in submission
    assert 'aria-hidden="true">⚠</span>' in submission


def test_react_progress_and_score_bars_have_accessible_names():
    progress = _component("ProgressFeedback.tsx")
    scoring = _component("ScoringPanel.tsx")

    assert 'role="progressbar"' in progress
    assert 'aria-label={`${title}: ${label}`}' in progress
    assert 'aria-valuenow={isDeterminate ? roundedPercent : undefined}' in progress
    assert 'aria-label={`${label} score`}' in scoring
    assert "aria-valuemax={max}" in scoring


def test_react_job_monitor_exposes_status_and_event_log_to_assistive_tech():
    job_monitor = _component("JobMonitor.tsx")

    assert 'role="status"' in job_monitor
    assert "流水线${running ? \"运行中\" : \"空闲\"}" in job_monitor
    assert 'role="log"' in job_monitor
    assert 'aria-label="流水线事件日志"' in job_monitor
    assert "function PlayIcon" in job_monitor
    assert "function StopIcon" in job_monitor
    assert 'aria-hidden="true" width="16" height="16"' in job_monitor


def test_react_gate_status_icons_are_visual_only():
    scoring = _component("ScoringPanel.tsx")

    assert 'aria-hidden="true">{check.passed ? "✓" : "✕"}</span>' in scoring


def test_react_toasts_announce_errors_assertively_and_other_messages_politely():
    toast = _component("ToastContainer.tsx")

    assert 'role={urgent ? "alert" : "status"}' in toast
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast
    assert 'aria-atomic="true"' in toast
    assert 'aria-label="关闭通知"' in toast
