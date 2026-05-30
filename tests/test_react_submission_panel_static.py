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
    assert "Candidate JSON must contain at most ${MAX_BATCH_ALPHA_IDS} rows." in source
    assert "setCandidateJsonError(validateCandidateJsonRows(rows));" in source
    assert "function validateCandidateJsonRows(candidates: Candidate[])" in source
    assert 'for (const field of ["alpha_id", "official_alpha_id", "simulation_id"] as const)' in source
    assert "Candidate row ${index + 1} ${field} must be a string." in source
    assert "Candidate row ${index + 1} ${field}: ${error}" in source


def test_submission_panel_blocks_batch_submit_without_valid_alpha_ids():
    source = _source()

    assert "const batchSubmitError = submitCandidates.length ? validateBatchSubmitCandidates(submitCandidates) : \"\";" in source
    assert "const validationError = candidateJsonError || validateBatchSubmitCandidates(submitCandidates);" in source
    assert 'notify("warning", validationError);' in source
    assert "alpha_ids: submitCandidates.map(candidateAlphaId).filter(Boolean)" in source
    assert "function validateBatchSubmitCandidates(candidates: Candidate[])" in source
    assert "Batch submit supports at most ${MAX_BATCH_ALPHA_IDS} candidates." in source
    assert "At least one candidate row must include alpha_id or official_alpha_id before batch submit." in source
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
