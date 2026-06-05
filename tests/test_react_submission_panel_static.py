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

    assert "const MAX_BATCH_ALPHA_IDS = 100;" in source
    assert "if (rows.length > MAX_BATCH_ALPHA_IDS)" in source
    assert "候选JSON最多包含 ${MAX_BATCH_ALPHA_IDS} 行。" in source
    assert "setCandidateJsonError(validateCandidateJsonRows(rows));" in source
    assert "function validateCandidateJsonRows(candidates: Candidate[])" in source
    assert 'for (const field of ["alpha_id", "official_alpha_id", "simulation_id"] as const)' in source
    assert "候选行 ${index + 1} 的 ${field} 必须为字符串。" in source
    assert "候选行 ${index + 1} 的 ${field}: ${error}" in source


def test_submission_panel_blocks_batch_submit_without_valid_alpha_ids():
    source = _source()

    assert "const batchSubmitError = submitCandidates.length ? validateBatchSubmitCandidates(submitCandidates) : \"\";" in source
    assert "const validationError = candidateJsonError || validateBatchSubmitCandidates(submitCandidates);" in source
    assert 'notify("warning", validationError);' in source
    assert "alpha_ids: submitCandidates.map(candidateAlphaId).filter(Boolean)" in source
    assert "function validateBatchSubmitCandidates(candidates: Candidate[])" in source
    assert "批量提交最多支持 ${MAX_BATCH_ALPHA_IDS} 个候选。" in source
    assert "批量提交前，至少一个候选行必须包含 alpha_id 或 official_alpha_id。" in source
    assert "disabled={!submitCandidates.length || Boolean(candidateJsonError) || Boolean(batchSubmitError) || batchSubmitApi.loading}" in source
    assert 'id="batch-submit-validation"' in source


def test_submission_panel_retry_paths_revalidate_candidate_json_before_requests():
    source = _source()

    assert "const validationError = candidateJsonError || validateCandidateJsonRows(submitCandidates);" in source
    assert "const validationError = candidateJsonError || validateBatchSubmitCandidates(submitCandidates);" in source
    assert "if (validationError) {" in source
    assert 'notify("warning", validationError);' in source
    assert "[batchCheckApi, candidateJsonError, notify, submitCandidates]" in source
    assert "[batchSubmitApi, candidateJsonError, notify, submitCandidates]" in source


def test_react_candidate_contract_includes_simulation_id():
    assert "simulation_id?: string;" in TYPES.read_text(encoding="utf-8")
