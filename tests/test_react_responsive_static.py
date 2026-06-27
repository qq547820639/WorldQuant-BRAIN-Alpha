from __future__ import annotations

from pathlib import Path

from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
COMPONENTS = REACT_SRC / "components"


def _source(path: Path) -> str:
    return resolve_react_source(path)


def _joined(paths: list[Path]) -> str:
    return "\n".join(resolve_react_source(path) for path in paths)


def test_app_shell_uses_mobile_safe_spacing_and_horizontal_tab_scroll():
    source = _source(REACT_SRC / "App.tsx")

    # Terminal Precision v2.0: App shell uses CSS Grid layout classes
    assert 'className="app-shell"' in source
    assert 'className="app-topbar"' in source
    assert 'className="app-main"' in source
    assert 'className="app-statusbar"' in source
    # Mobile-responsive sidebar with burger menu
    assert "lg:hidden" in source
    assert 'aria-label="切换导航菜单"' in source
    # Header content (v3.0 redesigned topbar)
    assert "BRAIN Alpha Ops" in source or "topbar-phase" in source
    assert "PRODUCTION" in source
    # Skip-link and content anchors for accessibility
    assert 'id="main-content"' in source


def test_readability_compat_layer_keeps_primary_buttons_high_contrast():
    css = _joined([
        REACT_SRC / "index.css",
        REACT_SRC / "styles" / "components-ui.css",
    ])

    assert ".btn-primary" in css
    assert "text-text-inverse" in css


def test_candidate_toolbar_wraps_and_keeps_filter_input_shrinkable():
    source = _joined([
        COMPONENTS / "CandidateTable.tsx",
        COMPONENTS / "CandidateTableToolbar.tsx",
        COMPONENTS / "CandidateTableSubComponents.tsx",
        COMPONENTS / "CandidateRow.tsx",
        COMPONENTS / "CandidateTableToolbarProductionControls.tsx",
        COMPONENTS / "CandidateTableToolbarFilterToolbar.tsx",
        COMPONENTS / "CandidateTableDesktop.tsx",
    ])

    assert 'className="animate-fade-in"' in source
    assert 'className="flex flex-wrap items-center gap-3 mb-4"' in source
    assert 'className="form-input flex-1"' in source
    assert "flex-1" in source
    assert 'className="panel"' in source
    assert 'aria-label="候选结果"' in source
    assert 'className="hidden md:block overflow-auto"' in source
    assert "minWidth: 980" in source
    assert "break-words" in source


def test_config_actions_and_toasts_fit_narrow_viewports():
    config = _joined([
        COMPONENTS / "ConfigPanel.tsx",
        COMPONENTS / "ConfigPanel" / "ConfigFormFields.tsx",
        COMPONENTS / "ConfigPanel" / "CredentialsSection.tsx",
    ])
    toast = _source(COMPONENTS / "ToastContainer.tsx")

    assert 'className="w-full max-w-5xl min-w-0 space-y-5 animate-fade-in"' in config
    assert 'className="flex w-full flex-wrap justify-end gap-2 sm:w-auto"' in config
    assert 'className="panel min-w-0"' in config
    assert "mt-4 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2" in config
    assert "连接与生产参数" in config
    assert "账户邮箱" in config
    assert "type=\"password\"" in config
    assert "const inputClass = 'form-input';" in config
    assert ".form-input" in _source(REACT_SRC / "styles" / "components-ui.css")
    # Toast: migrated from inline Tailwind classes to toast-container CSS component
    assert 'className="toast-container"' in toast
    assert "TOAST_CLASS" in toast
    assert 'aria-label="关闭通知"' in toast
    assert "flex-1" in toast


def test_operational_panels_wrap_on_narrow_viewports():
    submission = _source(COMPONENTS / "SubmissionPanel.tsx")
    scoring = _joined([
        COMPONENTS / "ScoringPanel.tsx",
        COMPONENTS / "ScoringPanel" / "Header.tsx",
    ])
    job_monitor = _joined([
        COMPONENTS / "JobMonitor.tsx",
        COMPONENTS / "JobMonitor" / "JobStatusCard.tsx",
        COMPONENTS / "JobMonitor" / "JobProgressBar.tsx",
        COMPONENTS / "JobMonitor" / "JobActions.tsx",
    ])
    snapshot = _joined([
        COMPONENTS / "SnapshotPanel.tsx",
        COMPONENTS / "SnapshotPanel" / "utils.ts",
        COMPONENTS / "SnapshotPanel" / "SnapshotPanelCloud.tsx",
        COMPONENTS / "SnapshotPanel" / "SnapshotPanelLocal.tsx",
        COMPONENTS / "SnapshotPanel" / "SnapshotPanelCompare.tsx",
        COMPONENTS / "SnapshotPanel" / "SnapshotDesktopTable.tsx",
    ])

    assert 'className="w-full max-w-3xl min-w-0 space-y-6 animate-fade-in"' in submission
    assert "min-w-0 outline-none focus:ring-2 focus:ring-brand-500/50" in submission
    assert 'className="animate-fade-in"' in scoring
    assert "flexWrap: 'wrap'" in scoring
    assert "grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4" in scoring
    assert "font-mono-value" in scoring
    assert 'className="panel mb-4"' in job_monitor
    assert 'className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4"' in job_monitor
    assert 'className="flex flex-wrap gap-2"' in job_monitor
    assert "页面凭证为空" in job_monitor
    assert 'className="min-w-0 space-y-4 animate-fade-in"' in snapshot
    assert 'className="grid grid-cols-2 gap-3 lg:grid-cols-4"' in snapshot
    assert 'className="panel overflow-hidden p-0"' in snapshot
    assert 'aria-label={`${title}移动列表`}' in snapshot
    assert 'className="hidden max-w-full overflow-auto md:block"' in snapshot
