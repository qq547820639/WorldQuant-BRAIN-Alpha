from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.backtest_slots import BacktestSlotManager
from brain_alpha_ops.research.backtest_submission import BacktestSubmissionService


def _candidate() -> Candidate:
    return Candidate(
        alpha_id="alpha_submit",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
    )


def _service(api, *, halted=None, events=None, slots=None):
    halted = halted if halted is not None else []
    events = events if events is not None else []
    return BacktestSubmissionService(
        api=api,
        slots=slots or BacktestSlotManager(),
        settings_provider=lambda: {"region": "USA"},
        poll_interval=lambda: 0.25,
        halt_official_calls=lambda reason, retry=None: halted.append((reason, retry)),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    )


def test_backtest_submission_service_assigns_slot_on_success():
    slots = BacktestSlotManager()
    service = _service(MockBrainAPI(), slots=slots)
    candidate = _candidate()

    outcome = service.submit_slot(2, candidate)

    assert outcome.submitted is True
    assert outcome.simulation_id
    assert candidate.simulation_id == outcome.simulation_id
    assert candidate.lifecycle_status == "simulation_submitted"
    assert candidate.submission["simulation_status"] == "SUBMITTED"
    assert candidate.submission["backtest_slot"] == 2
    assert candidate.submission["poll_count"] == 0
    assert candidate.submission["next_poll_at"] > 0
    assert slots.get(2) is candidate


class ConcurrencyLimitedAPI(MockBrainAPI):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError(
            "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
        )


class RateLimitedAPI(MockBrainAPI):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError("HTTP 429", status_code=429, retry_after=7)


class FailingAPI(MockBrainAPI):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError("HTTP 500: upstream failed", status_code=500)


def test_backtest_submission_service_defers_on_concurrency_limit():
    halted = []
    service = _service(ConcurrencyLimitedAPI(), halted=halted)
    candidate = _candidate()

    outcome = service.submit_slot(1, candidate)

    assert outcome.submitted is False
    assert outcome.halted is True
    assert candidate.lifecycle_status == "simulation_deferred_concurrency_limit"
    assert candidate.gate["status"] == "SIMULATION_DEFERRED_CONCURRENCY_LIMIT"
    assert halted and halted[0][1] is None


def test_backtest_submission_service_defers_on_rate_limit():
    halted = []
    service = _service(RateLimitedAPI(), halted=halted)
    candidate = _candidate()

    outcome = service.submit_slot(1, candidate)

    assert outcome.submitted is False
    assert outcome.halted is True
    assert candidate.lifecycle_status == "simulation_deferred_rate_limit"
    assert candidate.gate["status"] == "SIMULATION_DEFERRED_RATE_LIMIT"
    assert halted[0][1] == 7


def test_backtest_submission_service_records_request_failure_event():
    events = []
    service = _service(FailingAPI(), events=events)
    candidate = _candidate()

    outcome = service.submit_slot(1, candidate)

    assert outcome.submitted is False
    assert outcome.halted is False
    assert candidate.lifecycle_status == "simulation_request_failed"
    assert candidate.gate["status"] == "SIMULATION_REQUEST_FAILED"
    assert events and events[0][0][0] == "official_simulation_failed"
