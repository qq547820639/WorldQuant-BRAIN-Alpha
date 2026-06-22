from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_COMPONENTS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components"
APP = REACT_SRC / "App.tsx"


def _component(name: str) -> str:
    return (REACT_COMPONENTS / name).read_text(encoding="utf-8")


def _components(names: list[str]) -> str:
    return "\n".join(_component(name) for name in names)


def test_react_app_state_cards_have_accessible_navigation_semantics():
    app = APP.read_text(encoding="utf-8")
    state_cards = _component("StateCards.tsx")

    assert 'useState<CardViewId>("dashboard")' in app
    assert 'aria-label="切换导航菜单"' in app
    assert 'import Sidebar from "@/components/Sidebar"' in app
    assert "onClick={() => onNavigate(config.id)}" in state_cards
    assert 'type="button"' in state_cards
    assert "focus:outline-none focus:ring-2 focus:ring-brand-500/50" in state_cards
    assert 'role="alert"' in state_cards
    assert 'aria-live="assertive"' in state_cards
    assert 'aria-hidden="true"' in state_cards


def test_react_dashboard_and_candidate_errors_are_announced():
    dashboard = _component("Dashboard.tsx")
    candidates = _components([
        "CandidateTable.tsx",
        "CandidateTableToolbar.tsx",
        "CandidateTableSubComponents.tsx",
        "CandidateDetailPanel.tsx",
    ])
    snapshots = _component("SnapshotPanel.tsx")

    assert 'role="alert"' in dashboard
    assert '重试</button>' in dashboard
    assert 'aria-label="过滤候选"' in candidates
    assert '"刷新"' in candidates
    assert 'role="alert"' in candidates
    assert 'aria-label={`筛选 ${config.title}`}' in snapshots
    assert 'aria-label={`${config.title}表格`}' in snapshots


def test_react_submission_inputs_expose_validation_and_confirmation_context():
    submission = _component("SubmissionPanel.tsx")
    confirm = _component("SubmissionConfirmPanel.tsx")

    assert 'role="status"' in submission
    assert 'aria-live="polite"' in submission
    assert "SubmissionConfirmPanel notify={notify}" in submission
    assert 'role="alert"' in confirm


def test_react_progress_and_score_bars_have_accessible_names():
    progress = _component("ProgressFeedback.tsx")
    scoring = _component("ScoringPanel.tsx")

    assert 'role="progressbar"' in progress
    assert 'aria-label={`${title}: ${label}`}' in progress
    assert 'aria-valuenow={isDeterminate ? roundedPercent : undefined}' in progress
    assert 'aria-label={`${label} score`}' in scoring
    assert "aria-valuemax={max}" in scoring


def test_react_job_monitor_exposes_status_and_run_records_to_assistive_tech():
    job_monitor = _component("JobMonitor.tsx")

    assert 'ProgressFeedback' in job_monitor
    assert '"运行中" : "空闲"' in job_monitor
    assert "events.length > 0" in job_monitor
    assert "function PlayIcon" in job_monitor
    assert "function StopIcon" in job_monitor
    assert 'aria-hidden="true" width="14" height="14"' in job_monitor


def test_react_gate_status_icons_are_visual_only():
    scoring = _component("ScoringPanel.tsx")

    assert '{check.passed ? "\\u2713" : "\\u2715"}</span>' in scoring


def test_react_toasts_announce_errors_assertively_and_other_messages_politely():
    toast = _component("ToastContainer.tsx")

    assert 'role={urgent ? "alert" : "status"}' in toast
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast
    assert 'aria-atomic="true"' in toast
    assert 'aria-label="关闭通知"' in toast
