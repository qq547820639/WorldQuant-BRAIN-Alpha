"""Production submission gate tests.

These tests keep the production safety guard explicit: candidates with
non-production source markers must never reach the official submit endpoint,
while clean production-looking identifiers remain allowed by local screening.
"""

from __future__ import annotations

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI, _looks_non_production_alpha_id
from brain_alpha_ops.config import OfficialAPIConfig, SubmissionPolicy
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.safety import (
    NON_PRODUCTION_SOURCE_VALUES,
    SubmissionLedger,
    looks_non_production_identifier,
    non_production_source_reasons,
)


def _candidate(
    alpha_id: str = "alpha_a1b2c3d4",
    official_alpha_id: str = "abc123xyz",
    simulation_id: str = "sim_789real",
    source_tags: list[str] | None = None,
    **extra_fields,
) -> Candidate:
    candidate = Candidate(
        alpha_id=alpha_id,
        expression="rank(close)",
        family="Momentum",
        hypothesis="Price strength continues.",
        data_fields=["close"],
        operators=["rank"],
        source_tags=source_tags if source_tags is not None else ["experience"],
    )
    candidate.official_alpha_id = official_alpha_id
    candidate.simulation_id = simulation_id
    candidate.official_metrics = {
        "sharpe": 1.5,
        "fitness": 1.1,
        "turnover": 0.25,
        "correlation": 0.30,
        "weight_concentration": 0.05,
        "official_alpha_id": official_alpha_id,
    }
    candidate.gate = {"submission_ready": True, "failed_reasons": []}
    for key, value in extra_fields.items():
        setattr(candidate, key, value)
    return candidate


def _stub_official_api() -> tuple[OfficialBrainAPI, list[tuple]]:
    request_calls: list[tuple] = []
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example-stub.invalid", min_request_interval_seconds=0),
        token="stub-token",
    )

    def raise_if_called(*args, **kwargs):
        request_calls.append((args, kwargs))
        raise AssertionError("_request must not be called")

    api._request = raise_if_called
    return api, request_calls


@pytest.mark.parametrize(
    "value",
    [
        "mock",
        "mock_alpha_001",
        "demo-alpha-xyz",
        "test_something",
        "testing",
        "dry_run_001",
        "dryrun_abc",
        "fake_alpha",
        "sample-alpha",
    ],
)
def test_non_production_identifiers_are_detected(value: str):
    assert looks_non_production_identifier(value) is True
    assert _looks_non_production_alpha_id(value) is True


@pytest.mark.parametrize("value", ["", None, "abc123xyz", "alpha_a1b2c3d4", "alpha_contest_123"])
def test_clean_identifiers_are_not_falsely_flagged(value: str | None):
    assert looks_non_production_identifier(value) is False
    assert _looks_non_production_alpha_id(value) is False


def test_non_production_candidate_ids_return_submission_reasons():
    candidate = _candidate(
        alpha_id="mock_alpha_001",
        official_alpha_id="test_official_001",
        simulation_id="dry_run_sim_001",
    )

    reasons = non_production_source_reasons(candidate)

    assert reasons
    assert any("alpha_id" in reason for reason in reasons)
    assert any("official_alpha_id" in reason for reason in reasons)
    assert any("simulation_id" in reason for reason in reasons)
    assert all("non-production" in reason for reason in reasons)


def test_non_production_source_fields_return_submission_reasons():
    for marker in sorted(NON_PRODUCTION_SOURCE_VALUES):
        candidate = _candidate(source_tags=[marker])
        assert non_production_source_reasons(candidate), marker

    for field_name, field_value in (
        ("source", "demo"),
        ("environment", "paper"),
        ("mode", "dry-run"),
    ):
        candidate = _candidate()
        setattr(candidate, field_name, field_value)
        assert non_production_source_reasons(candidate), field_name


def test_clean_production_candidate_has_no_local_source_reasons():
    candidate = _candidate(
        alpha_id="alpha_a1b2c3d4",
        official_alpha_id="abc123xyz",
        simulation_id="sim_789real",
        source_tags=["experience"],
    )

    assert non_production_source_reasons(candidate) == []


def test_submission_ledger_blocks_missing_official_alpha_id(tmp_path):
    ledger = SubmissionLedger(str(tmp_path))
    candidate = _candidate(official_alpha_id="")
    candidate.official_metrics = {}

    result = ledger.assess(
        candidate,
        SubmissionPolicy(min_minutes_between_auto_submissions=0),
        mode="manual",
    )

    assert result["allowed"] is False
    assert any("official" in reason.lower() for reason in result["failed_reasons"])


def test_official_api_blocks_non_production_alpha_id_before_network_call():
    api, request_calls = _stub_official_api()

    with pytest.raises(BrainAPIError, match="non-production alpha_id"):
        api.submit_alpha("mock_alpha_001", "rank(close)", {})

    assert request_calls == []


def test_official_pre_submit_error_is_distinct_from_local_source_guard():
    local_error_text = "; ".join(non_production_source_reasons(_candidate(alpha_id="mock_alpha_999")))
    api, _ = _stub_official_api()

    with pytest.raises(BrainAPIError) as exc_info:
        api.submit_alpha("mock_alpha_999", "rank(close)", {})

    official_guard_text = str(exc_info.value)
    official_check_fail_text = "official pre-submit check failed"
    assert "non-production" in local_error_text
    assert "non-production" in official_guard_text
    assert len({local_error_text, official_guard_text, official_check_fail_text}) == 3
