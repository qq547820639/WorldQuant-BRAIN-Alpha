from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.backtest_polling import BacktestPollingService


def _candidate(simulation_id: str = "sim_1") -> Candidate:
    candidate = Candidate(
        alpha_id="alpha_poll",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
    )
    candidate.simulation_id = simulation_id
    candidate.submission["simulation_status"] = "SUBMITTED"
    return candidate


def _service(api, *, halted=None, events=None):
    halted = halted if halted is not None else []
    events = events if events is not None else []
    return BacktestPollingService(
        api=api,
        halt_official_calls=lambda reason, retry=None: halted.append((reason, retry)),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    )


class RunningAPI(MockBrainAPI):
    def poll_simulation(self, simulation_id: str) -> str:
        return "RUNNING"


class CompletedAPI(MockBrainAPI):
    def poll_simulation(self, simulation_id: str) -> str:
        return "COMPLETED"

    def fetch_result(self, simulation_id: str) -> dict:
        return {"alpha_id": "official_1", "metrics": {"sharpe": 1.7, "fitness": 1.2}}


class FailedAPI(MockBrainAPI):
    def poll_simulation(self, simulation_id: str) -> str:
        return "FAILED"


class PollRateLimitedAPI(MockBrainAPI):
    def poll_simulation(self, simulation_id: str) -> str:
        raise BrainAPIError("HTTP 429 poll", status_code=429, retry_after=7)


class PollFailingAPI(MockBrainAPI):
    def poll_simulation(self, simulation_id: str) -> str:
        raise BrainAPIError("HTTP 500 poll failed", status_code=500)


class ResultRateLimitedAPI(CompletedAPI):
    def fetch_result(self, simulation_id: str) -> dict:
        raise BrainAPIError("HTTP 429 result", status_code=429, retry_after=9)


class ResultFailingAPI(CompletedAPI):
    def fetch_result(self, simulation_id: str) -> dict:
        raise BrainAPIError("HTTP 500 result failed", status_code=500)


def test_backtest_polling_service_marks_running_and_schedules_next_poll():
    candidate = _candidate()
    outcome = _service(RunningAPI()).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "running"
    assert outcome.finalize is False
    assert candidate.lifecycle_status == "simulation_running"
    assert candidate.submission["simulation_status"] == "RUNNING"
    assert candidate.submission["next_poll_at"] == 12.5
    assert [record.action for record in outcome.records] == ["polled", "running"]


def test_backtest_polling_service_fetches_completed_result():
    candidate = _candidate()
    outcome = _service(CompletedAPI()).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "completed"
    assert outcome.finalize is True
    assert outcome.release_slot is True
    assert outcome.official_result is True
    assert outcome.official_result_increment == 1
    assert outcome.official_simulated_increment == 1
    assert candidate.lifecycle_status == "official_simulated"
    assert candidate.official_alpha_id == "official_1"
    assert candidate.official_metrics["sharpe"] == 1.7
    assert [record.action for record in outcome.records] == ["polled", "completed"]


def test_backtest_polling_service_marks_failed_status_for_finalize():
    candidate = _candidate()
    outcome = _service(FailedAPI()).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "failed"
    assert outcome.finalize is True
    assert outcome.release_slot is True
    assert outcome.official_result_increment == 1
    assert candidate.lifecycle_status == "simulation_failed"
    assert candidate.gate["status"] == "SIMULATION_FAILED"


def test_backtest_polling_service_defers_on_poll_rate_limit():
    halted = []
    events = []
    candidate = _candidate()
    outcome = _service(PollRateLimitedAPI(), halted=halted, events=events).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "poll_deferred"
    assert outcome.halted is True
    assert candidate.lifecycle_status == "simulation_poll_deferred_rate_limit"
    assert candidate.submission["next_poll_at"] == 17.0
    assert halted and "polling rate limit" in halted[0][0]
    assert events and events[0][0][0] == "official_simulation_poll_deferred"
    assert outcome.records[0].error_code == "SIMULATION_POLL_RATE_LIMIT"


def test_backtest_polling_service_marks_poll_failure_for_finalize():
    candidate = _candidate()
    outcome = _service(PollFailingAPI()).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "poll_failed"
    assert outcome.finalize is True
    assert outcome.release_slot is True
    assert candidate.lifecycle_status == "simulation_poll_failed"
    assert candidate.gate["status"] == "SIMULATION_POLL_FAILED"
    assert outcome.records[0].error_code == "SIMULATION_POLL_ERROR"


def test_backtest_polling_service_defers_on_result_rate_limit():
    halted = []
    events = []
    candidate = _candidate()
    outcome = _service(ResultRateLimitedAPI(), halted=halted, events=events).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "result_deferred"
    assert outcome.halted is True
    assert candidate.lifecycle_status == "simulation_result_deferred_rate_limit"
    assert candidate.submission["next_poll_at"] == 19.0
    assert halted and "result rate limit" in halted[0][0]
    assert events and events[0][0][0] == "official_simulation_result_deferred"
    assert [record.action for record in outcome.records] == ["polled", "result_deferred"]


def test_backtest_polling_service_marks_result_failure_for_finalize():
    candidate = _candidate()
    outcome = _service(ResultFailingAPI()).poll(candidate, now=10.0, interval=2.5)

    assert outcome.action == "result_failed"
    assert outcome.finalize is True
    assert outcome.release_slot is True
    assert candidate.lifecycle_status == "simulation_result_failed"
    assert candidate.gate["status"] == "SIMULATION_RESULT_FAILED"
    assert outcome.records[-1].error_code == "SIMULATION_RESULT_ERROR"
