"""Tests for the structured scoring interpreter web handlers and helpers."""

import json
from pathlib import Path

import pytest

from brain_alpha_ops.web.misc import web_scoring_interpreter as wsi


# ═══════════════════════ Shared helper functions ═════════════════════════

def test_first_value():
    assert wsi._first_value({"a": "x"}, "a") == "x"
    assert wsi._first_value({"a": ["x", "y"]}, "a") == "x"
    assert wsi._first_value({"a": []}, "a") == ""
    assert wsi._first_value({}, "a") == ""
    assert wsi._first_value({"a": None}, "a") == ""
    assert wsi._first_value({"a": 5}, "a") == "5"


def test_bounded_int():
    assert wsi._bounded_int("10", lower=1, upper=100) == 10
    assert wsi._bounded_int("abc", lower=1, upper=100) == 1
    assert wsi._bounded_int(0, lower=1, upper=100) == 1
    assert wsi._bounded_int(500, lower=1, upper=100) == 100
    assert wsi._bounded_int(None, lower=5, upper=50) == 5


def test_query_truthy():
    assert wsi._query_truthy("true") is True
    assert wsi._query_truthy("1") is True
    assert wsi._query_truthy("yes") is True
    assert wsi._query_truthy("on") is True
    assert wsi._query_truthy(["true"]) is True
    assert wsi._query_truthy("false") is False
    assert wsi._query_truthy("") is False
    assert wsi._query_truthy([]) is False


def test_extract_filters():
    assert wsi._extract_filters({}) == {}
    assert wsi._extract_filters({"event_type": "gate_decision"}) == {"event_type": "gate_decision"}
    assert wsi._extract_filters({"passed": "true"}) == {"passed": True}
    assert wsi._extract_filters({"passed": "FALSE"}) == {"passed": False}
    assert wsi._extract_filters({"passed": "maybe"}) == {}
    assert wsi._extract_filters({"gate_name": "quality"}) == {"gate_name": "quality"}


def test_candidate_payload():
    assert wsi._candidate_payload({"candidate": {"alpha_id": "A1"}}) == {"alpha_id": "A1"}
    assert wsi._candidate_payload({"alpha_id": "A1"}) == {"alpha_id": "A1"}


def test_matches_candidate_id():
    assert wsi._matches_candidate_id({"alpha_id": "A1"}, "A1") is True
    assert wsi._matches_candidate_id({"candidate": {"official_alpha_id": "B2"}}, "B2") is True
    assert wsi._matches_candidate_id({"simulation_id": "S1"}, "S1") is True
    assert wsi._matches_candidate_id({"alpha_id": "A1"}, "ZZZ") is False


def test_candidate_rows_from_snapshot():
    payload = {
        "result": {"summary": {"candidates": [{"alpha_id": "A1"}]}},
        "passed_candidates": [{"alpha_id": "B2"}],
    }
    rows = wsi._candidate_rows_from_snapshot(payload)
    assert len(rows) == 2
    assert wsi._candidate_rows_from_snapshot({}) == []


def test_candidate_snapshot():
    class FakeCandidate:
        alpha_id = "A1"
        lifecycle_status = "submission_ready"
        scorecard = {"total_score": 12.5, "decision_band": "A"}
        official_metrics = {"sharpe": 1.5}
        gate = {"submission_ready": True, "hard_gate_blocked": False}

    snap = wsi._candidate_snapshot(FakeCandidate())
    assert snap["alpha_id"] == "A1"
    assert snap["total_score"] == 12.5
    assert snap["decision_band"] == "A"
    assert snap["has_official_metrics"] is True
    assert snap["gate_submission_ready"] is True
    assert snap["gate_hard_blocked"] is False


def test_candidate_snapshot_no_scorecard():
    class FakeCandidate:
        alpha_id = ""
        lifecycle_status = ""
        scorecard = None
        official_metrics = {}
        gate = {}

    snap = wsi._candidate_snapshot(FakeCandidate())
    assert snap["total_score"] == 0.0
    assert snap["decision_band"] == ""


def test_coerce_candidates():
    out = wsi._coerce_candidates([{"alpha_id": "A1"}, "not-dict", {"alpha_id": "B2"}])
    # dicts are kept (coerced to Candidate when possible, else raw dict);
    # non-dict items are skipped
    assert len(out) == 2
    assert out[0]["alpha_id"] == "A1"


def test_find_candidate_row_from_candidates_jsonl(tmp_path):
    row = {"alpha_id": "A1", "official_metrics": {"sharpe": 1.0}}
    (tmp_path / "candidates.jsonl").write_text(json.dumps(row) + "\n")
    found = wsi._find_candidate_row(str(tmp_path), "A1", limit=100)
    assert found is not None
    assert found["alpha_id"] == "A1"
    assert wsi._find_candidate_row(str(tmp_path), "NOPE", limit=100) is None


def test_find_candidate_row_from_run_history(tmp_path):
    row = {"candidate": {"alpha_id": "A1"}}
    history = tmp_path / "run_history"
    history.mkdir()
    (history / "latest.json").write_text(json.dumps({"result": {"summary": {"candidates": [row]}}}))
    found = wsi._find_candidate_row(str(tmp_path), "A1", limit=100)
    assert found is not None
    assert found["alpha_id"] == "A1"


def test_find_candidate_row_skips_corrupt_json(tmp_path):
    history = tmp_path / "run_history"
    history.mkdir()
    (history / "latest.json").write_text("{bad json")
    assert wsi._find_candidate_row(str(tmp_path), "A1", limit=100) is None


def test_candidate_from_request_invalid_candidate():
    out = wsi._candidate_from_request({"candidate": {}}, "/tmp/nonexistent")
    assert out[0] is None
    assert out[1]["error_code"] == "SCORING_INVALID_CANDIDATE"


def test_candidate_from_request_missing_id():
    out = wsi._candidate_from_request({}, "/tmp/nonexistent")
    assert out[0] is None
    assert out[1]["error_code"] == "SCORING_CANDIDATE_REQUIRED"


def test_candidate_from_request_not_found(tmp_path):
    out = wsi._candidate_from_request({"alpha_id": "A1"}, str(tmp_path))
    assert out[0] is None
    assert out[1]["error_code"] == "SCORING_CANDIDATE_NOT_FOUND"


# ═══════════════════════ Handlers (error paths only, no real submission) ═══

def test_handle_scoring_multi_attribution_invalid():
    out = wsi.handle_scoring_multi_attribution({"scorecards": "not-a-list"})
    assert out["ok"] is False
    assert out["error_code"] == "MULTI_ATTR_INVALID_SCORECARDS"


def test_handle_scoring_multi_attribution_no_scorecards():
    out = wsi.handle_scoring_multi_attribution({"scorecards": []})
    assert out["ok"] is False
    assert out["error_code"] == "MULTI_ATTR_NO_SCORECARDS"


def test_handle_scoring_evaluate_missing_candidate():
    out = wsi.handle_scoring_evaluate({})
    assert out["ok"] is False
    assert out["error_code"] == "SCORING_CANDIDATE_REQUIRED"


def test_handle_scoring_gate_decision_missing_candidate():
    out = wsi.handle_scoring_gate_decision({})
    assert out["ok"] is False
    assert out["error_code"] == "SCORING_CANDIDATE_REQUIRED"


def test_handle_scoring_attribution_missing_candidate():
    out = wsi.handle_scoring_attribution({})
    assert out["ok"] is False


def test_handle_audit_export_invalid_dir(tmp_path):
    out = wsi.handle_audit_export({"audit_dir": str(tmp_path / "missing")})
    # export on missing dir should succeed with 0 entries or fail closed
    assert out["ok"] is True or out["error_code"] == "AUDIT_EXPORT_FAILED"


def test_handle_audit_export_ok(tmp_path):
    out = wsi.handle_audit_export({"audit_dir": str(tmp_path), "limit": "50"})
    assert out["schema_version"] == "audit_export_route.v1"
    assert "entries" in out