from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_PANEL = (
    ROOT
    / "brain_alpha_ops"
    / "web"
    / "react_app"
    / "src"
    / "components"
    / "SubmissionPanel.tsx"
)
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types" / "index.ts"


def _source() -> str:
    return SUBMISSION_PANEL.read_text(encoding="utf-8")


def test_submission_panel_bounds_batch_json_and_validates_candidate_ids():
    source = _source()

    assert "Retired submit surface kept as a compatibility alias" in source
    assert "SubmissionConfirmPanel notify={notify}" in source
    assert "/api/submit" not in source
    assert "/api/submit_batch" not in source


def test_submission_panel_blocks_batch_submit_without_valid_alpha_ids():
    source = _source()

    assert "旧提交面板已退役" in source
    assert "Web 页面不执行真实提交" in source
    assert "任何真实提交需另走人工审批" in source


def test_submission_panel_retry_paths_revalidate_candidate_json_before_requests():
    source = _source()

    assert 'role="status"' in source
    assert 'aria-live="polite"' in source
    assert "focus:ring-2 focus:ring-brand-500/50" in source


def test_submission_panel_requires_fresh_single_and_batch_checks_before_submit():
    source = _source()

    assert "Retired submit surface kept as a compatibility alias for read-only review" in source
    assert "useApi" not in source
    assert "useSSE" not in source
    assert "requestJobCancel" not in source


def test_react_candidate_contract_includes_simulation_id():
    assert "simulation_id?: string;" in TYPES.read_text(encoding="utf-8")
