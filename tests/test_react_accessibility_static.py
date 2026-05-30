from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_COMPONENTS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components"
APP = REACT_SRC / "App.tsx"


def _component(name: str) -> str:
    return (REACT_COMPONENTS / name).read_text(encoding="utf-8")


def test_react_app_tabs_have_accessible_semantics_and_keyboard_navigation():
    source = APP.read_text(encoding="utf-8")

    assert 'role="tablist"' in source
    assert 'aria-label="Primary sections"' in source
    assert 'role="tab"' in source
    assert "aria-selected={activeTab === tab.id}" in source
    assert "aria-controls={tabPanelId(tab.id)}" in source
    assert "tabIndex={activeTab === tab.id ? 0 : -1}" in source
    assert "onKeyDown={(event) => handleTabKeyDown(event, index)}" in source
    assert 'role="tabpanel"' in source
    assert "aria-labelledby={tabButtonId(activeTab)}" in source
    assert "activateTabByIndex(index + 1)" in source
    assert "activateTabByIndex(index - 1)" in source
    assert 'event.key === "Home"' in source
    assert 'event.key === "End"' in source
    assert 'aria-hidden="true">{tab.icon}</span>' in source


def test_react_dashboard_and_candidate_errors_are_announced():
    dashboard = _component("Dashboard.tsx")
    candidates = _component("CandidateTable.tsx")
    snapshots = _component("SnapshotPanel.tsx")

    assert 'role="alert"' in dashboard
    assert 'aria-live="assertive"' in dashboard
    assert 'aria-label="Filter candidates"' in candidates
    assert 'aria-label="Refresh candidates"' in candidates
    assert 'role="alert"' in candidates
    assert 'aria-label={`Filter ${config.title}`}' in snapshots
    assert 'aria-label={`${config.title} rows`}' in snapshots


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
    assert "Pipeline is ${running ? \"running\" : \"idle\"}" in job_monitor
    assert 'role="log"' in job_monitor
    assert 'aria-label="Pipeline event log"' in job_monitor
    assert 'aria-hidden="true">▶' in job_monitor
    assert 'aria-hidden="true">⏹' in job_monitor


def test_react_gate_status_icons_are_visual_only():
    scoring = _component("ScoringPanel.tsx")

    assert 'aria-hidden="true">{check.passed ? "✓" : "✕"}</span>' in scoring


def test_react_toasts_announce_errors_assertively_and_other_messages_politely():
    toast = _component("ToastContainer.tsx")

    assert 'role={urgent ? "alert" : "status"}' in toast
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast
    assert 'aria-atomic="true"' in toast
    assert 'aria-label="Dismiss notification"' in toast
