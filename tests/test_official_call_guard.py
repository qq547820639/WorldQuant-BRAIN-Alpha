from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.official_call_guard import OfficialCallGuard


def _candidate(alpha_id: str = "alpha_1", expression: str = "rank(ts_delta(close, 20))") -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="Momentum",
        hypothesis="price momentum",
        scorecard={"total_score": 91.25},
    )


def test_official_call_guard_blocks_duplicate_expression_and_updates_snapshot():
    guard = OfficialCallGuard()
    candidate = _candidate()
    guidance = {
        "active": True,
        "top_duplicate_expressions": ["rank(ts_delta(close,20))"],
        "top_duplicate_fingerprints": [],
    }

    result = guard.block(
        candidate,
        phase="official_validation",
        guidance=guidance,
        blocked_at=123.0,
    )
    snapshot = guard.snapshot()

    assert result is not None
    assert result["blocked"] is True
    assert result["expression_canonical"] == "rank(ts_delta(close,20))"
    assert candidate.lifecycle_status == "observability_duplicate_blocked"
    assert candidate.gate["status"] == "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED"
    assert candidate.submission["observability_duplicate_blocked_phase"] == "official_validation"
    assert snapshot["blocked_count"] == 1
    assert snapshot["validation_blocked_count"] == 1
    assert snapshot["simulation_blocked_count"] == 0
    assert snapshot["last_blocked_alpha_id"] == "alpha_1"
    assert snapshot["last_blocked_at"] == 123.0
    assert snapshot["blocked_candidates"][0]["score"] == 91.25


def test_official_call_guard_ignores_inactive_or_unmatched_guidance():
    guard = OfficialCallGuard()
    candidate = _candidate()
    original_status = candidate.lifecycle_status

    assert guard.block(candidate, phase="official_validation", guidance={"active": False}) is None
    assert (
        guard.block(
            candidate,
            phase="official_simulation",
            guidance={"active": True, "top_duplicate_expressions": ["rank(open)"]},
        )
        is None
    )
    assert candidate.lifecycle_status == original_status
    assert guard.snapshot()["blocked_count"] == 0


def test_official_call_guard_keeps_recent_blocked_candidates_bounded():
    guard = OfficialCallGuard()
    guidance = {"active": True, "top_duplicate_expressions": ["rank(close)"]}

    for index in range(12):
        guard.block(
            _candidate(alpha_id=f"alpha_{index}", expression="rank(close)"),
            phase="official_simulation",
            guidance=guidance,
            blocked_at=float(index),
        )
    snapshot = guard.snapshot()

    assert snapshot["blocked_count"] == 12
    assert snapshot["simulation_blocked_count"] == 12
    assert len(snapshot["blocked_candidates"]) == 10
    assert snapshot["blocked_candidates"][0]["alpha_id"] == "alpha_2"
    assert snapshot["blocked_candidates"][-1]["alpha_id"] == "alpha_11"
