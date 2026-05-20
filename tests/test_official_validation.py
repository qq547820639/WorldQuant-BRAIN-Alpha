from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.official_validation import OfficialValidationService


def _candidate(alpha_id: str, expression: str = "rank(close)") -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="test",
        hypothesis="official validation service",
        scorecard={"total_score": 80},
    )


class ValidationRateLimitedAPI(MockBrainAPI):
    def validate_expression(self, expression: str, settings: dict) -> dict:
        raise BrainAPIError("HTTP 429: too many requests", status_code=429)


def test_official_validation_service_records_pass_and_failure():
    events = []
    progress = []
    lifecycle = []

    service = OfficialValidationService(
        api=MockBrainAPI(),
        settings_payload={},
        progress=lambda *args: progress.append(args),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
        record_lifecycle=lambda candidate, stage, status: lifecycle.append((candidate.alpha_id, stage, status)),
        halt_official_calls=lambda reason: None,
    )
    passing = _candidate("passing", "rank(close)")
    failing = _candidate("failing", "rank(close")

    outcome = service.validate([passing, failing])

    assert outcome.attempted == 2
    assert outcome.passed == 1
    assert outcome.valid == [passing]
    assert passing.lifecycle_status == "official_validation_passed"
    assert failing.lifecycle_status == "official_validation_failed"
    assert failing.gate["status"] == "OFFICIAL_VALIDATION_FAILED"
    assert len(progress) == 4
    assert lifecycle == [("passing", "official_validation", "PASS"), ("failing", "official_validation", "FAIL")]
    assert events and events[0][0][0] == "official_validation_failed"


def test_official_validation_service_halts_on_rate_limit():
    halted = []
    service = OfficialValidationService(
        api=ValidationRateLimitedAPI(),
        settings_payload={},
        progress=lambda *args: None,
        event=lambda *args, **kwargs: None,
        record_lifecycle=lambda candidate, stage, status: None,
        halt_official_calls=lambda reason: halted.append(reason),
    )
    candidate = _candidate("rate_limited")

    outcome = service.validate([candidate])

    assert outcome.halted is True
    assert outcome.attempted == 0
    assert halted and "official validation rate limit reached" in halted[0]
    assert candidate.lifecycle_status == "official_validation_deferred_rate_limit"
    assert candidate.gate["status"] == "OFFICIAL_VALIDATION_DEFERRED_RATE_LIMIT"
