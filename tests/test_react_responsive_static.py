from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
COMPONENTS = REACT_SRC / "components"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_shell_uses_mobile_safe_spacing_and_horizontal_tab_scroll():
    source = _source(REACT_SRC / "App.tsx")

    assert 'className="min-h-screen min-w-0 flex flex-col"' in source
    assert "px-4 py-3 sm:px-6 flex flex-wrap items-center justify-between gap-3" in source
    assert 'className="flex min-w-0 items-center gap-3"' in source
    assert 'className="truncate text-xs text-muted"' in source
    assert "px-4 sm:px-6 flex gap-1 shrink-0 overflow-x-auto" in source
    assert "shrink-0 px-3 py-2.5 sm:px-4" in source
    assert 'className="flex-1 min-w-0 p-4 sm:p-6 overflow-auto"' in source


def test_candidate_toolbar_wraps_and_keeps_filter_input_shrinkable():
    source = _source(COMPONENTS / "CandidateTable.tsx")

    assert 'className="min-w-0 space-y-4"' in source
    assert 'className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center"' in source
    assert "w-full min-w-0 bg-gray-800" in source
    assert "sm:flex-1" in source
    assert 'className="card min-w-0 overflow-hidden p-0"' in source
    assert 'className="max-w-full overflow-auto"' in source
    assert 'className="min-w-[760px] w-full text-sm"' in source


def test_config_actions_and_toasts_fit_narrow_viewports():
    config = _source(COMPONENTS / "ConfigPanel.tsx")
    toast = _source(COMPONENTS / "ToastContainer.tsx")

    assert 'className="w-full max-w-4xl min-w-0 space-y-6 animate-fade-in"' in config
    assert 'className="flex w-full flex-wrap justify-end gap-2 sm:w-auto"' in config
    assert 'className="card min-w-0"' in config
    assert "grid grid-cols-1 gap-x-5 gap-y-3 mt-2 md:grid-cols-2" in config
    assert "w-full min-w-0 bg-gray-800" in config
    assert "fixed bottom-4 left-4 right-4" in toast
    assert "sm:left-auto sm:max-w-sm" in toast


def test_operational_panels_wrap_on_narrow_viewports():
    submission = _source(COMPONENTS / "SubmissionPanel.tsx")
    scoring = _source(COMPONENTS / "ScoringPanel.tsx")
    job_monitor = _source(COMPONENTS / "JobMonitor.tsx")
    snapshot = _source(COMPONENTS / "SnapshotPanel.tsx")

    assert 'className="w-full max-w-3xl min-w-0 space-y-6 animate-fade-in"' in submission
    assert 'className="min-w-0 outline-none focus:ring-2 focus:ring-brand-500/50"' in submission
    assert 'className="min-w-0 space-y-6 animate-fade-in"' in scoring
    assert "flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-muted" in scoring
    assert "flex min-w-0 justify-between items-center gap-3" in scoring
    assert "min-w-0 truncate font-mono" in scoring
    assert 'className="card min-w-0 space-y-4"' in job_monitor
    assert "grid grid-cols-1 gap-3 text-xs text-muted sm:grid-cols-2" in job_monitor
    assert 'className="flex flex-wrap gap-2"' in job_monitor
    assert 'className="min-w-0 space-y-4 animate-fade-in"' in snapshot
    assert 'className="grid grid-cols-2 gap-3 lg:grid-cols-4"' in snapshot
    assert 'className="card min-w-0 overflow-hidden p-0"' in snapshot
