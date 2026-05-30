from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"


def _source(path: str) -> str:
    return (REACT_SRC / path).read_text(encoding="utf-8")


def test_app_notify_forwards_toast_actions():
    source = _source("App.tsx")

    assert 'action?: { label: string; onClick: () => void }' in source
    assert "addToast(type, msg, 5000, action)" in source


def test_submission_success_toasts_offer_actionable_receipts():
    source = _source("components/SubmissionPanel.tsx")

    assert "submissionReceiptRef" in source
    assert "focusSubmissionReceipt" in source
    assert 'label: "View receipt"' in source
    assert "Latest submission receipt" in source
    assert 'role="status"' in source
    assert 'aria-live="polite"' in source
    assert "batchSubmissionStatusRef" in source
    assert "focusBatchSubmissionStatus" in source
    assert 'label: "View status"' in source


def test_toast_action_button_is_accessible_and_dismisses_after_action():
    source = _source("components/ToastContainer.tsx")

    assert 'role={urgent ? "alert" : "status"}' in source
    assert 'aria-live={urgent ? "assertive" : "polite"}' in source
    assert "toast.action_label && toast.on_action" in source
    assert 'aria-label={`${toast.action_label}: ${toast.message}`}' in source
    assert "toast.on_action?.();" in source
    assert "onDismiss(toast.id);" in source
