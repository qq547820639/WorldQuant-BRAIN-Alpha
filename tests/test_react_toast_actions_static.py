from __future__ import annotations

from pathlib import Path

from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"


def _source(path: str) -> str:
    return resolve_react_source(REACT_SRC / path)


def test_app_notify_forwards_toast_actions():
    source = _source("hooks/useAppState/useBaseState.ts")

    assert 'action?: { label: string; onClick: () => void }' in source
    assert 'addToast(type, msg, 5000, action' in source


def test_toast_action_button_is_accessible_and_dismisses_after_action():
    source = _source("components/ToastContainer.tsx")

    assert "role={urgent ? 'alert' : 'status'}" in source
    assert "aria-live={urgent ? 'assertive' : 'polite'}" in source
    assert "MAX_VISIBLE = 3" in source
    assert "toasts.slice(-MAX_VISIBLE)" in source
    assert 'className="toast-container"' in source
    assert "toast.action_label && toast.on_action" in source
    assert 'aria-label={`${toast.action_label}: ${toast.message}`}' in source
    assert "toast.on_action?.();" in source
    assert "onDismiss(toast.id);" in source
