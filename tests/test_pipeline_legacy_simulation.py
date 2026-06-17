from __future__ import annotations

from types import SimpleNamespace

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_legacy_simulation import PipelineLegacySimulationMixin


def _candidate(alpha_id: str = "alpha_1") -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
    )


class _Settings:
    def to_platform_dict(self) -> dict:
        return {"settings": {"region": "USA", "universe": "TOP3000"}}


class _Api:
    def __init__(
        self,
        *,
        submit_errors: list[BrainAPIError] | None = None,
        poll_statuses: dict[str, list[str | BrainAPIError]] | None = None,
        fetch_results: dict[str, dict | BrainAPIError] | None = None,
        attempts: int = 2,
    ):
        self.config = SimpleNamespace(poll_attempts=attempts, poll_interval_seconds=0)
        self.submit_errors = list(submit_errors or [])
        self.poll_statuses = {key: list(value) for key, value in (poll_statuses or {}).items()}
        self.fetch_results = dict(fetch_results or {})
        self.submissions: list[tuple[str, dict]] = []

    def submit_simulation(self, expression: str, settings: dict) -> str:
        if self.submit_errors:
            raise self.submit_errors.pop(0)
        sim_id = f"sim_{len(self.submissions) + 1}"
        self.submissions.append((expression, dict(settings)))
        return sim_id

    def poll_simulation(self, sim_id: str) -> str:
        sequence = self.poll_statuses.get(sim_id, ["COMPLETED"])
        value = sequence.pop(0) if sequence else "COMPLETED"
        if isinstance(value, BrainAPIError):
            raise value
        return value

    def fetch_result(self, sim_id: str) -> dict:
        value = self.fetch_results.get(sim_id, {"alpha_id": f"official_{sim_id}", "metrics": {"sharpe": 1.4}})
        if isinstance(value, BrainAPIError):
            raise value
        return value


class _Harness(PipelineLegacySimulationMixin):
    def __init__(self, api: _Api):
        self.api = api
        self.config = SimpleNamespace(settings=_Settings())
        self.backtests_submitted = 0
        self.officially_simulated_count = 0
        self.official_halt_reason = ""
        self.progress_calls: list[tuple] = []
        self.events: list[tuple] = []
        self.halts: list[str] = []
        self.sleep_calls: list[float] = []

    def _progress(self, *args, **kwargs) -> None:
        self.progress_calls.append((args, kwargs))

    def _event(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))

    def _halt_official_calls(self, reason: str) -> None:
        self.official_halt_reason = reason
        self.halts.append(reason)

    def _sleep_with_stop(self, interval: float) -> bool:
        self.sleep_calls.append(interval)
        return True

    def _backtest_snapshot(self, candidates: list[Candidate]) -> list[dict]:
        return [{"alpha_id": candidate.alpha_id, "status": candidate.lifecycle_status} for candidate in candidates]


def test_simulate_batch_handles_empty_candidate_pool():
    harness = _Harness(_Api())

    assert harness._simulate_batch([]) == []

    assert harness.progress_calls[0][0][:4] == (
        "official_simulation",
        0,
        1,
        "候选池中暂时没有满足回测门槛的 Alpha。",
    )
    assert harness.api.submissions == []


def test_simulate_batch_submits_and_fetches_completed_results():
    harness = _Harness(_Api(fetch_results={"sim_1": {"metrics": {"official_alpha_id": "brain_1", "fitness": 1.1}}}))
    first = _candidate("alpha_a")
    second = _candidate("alpha_b")

    submitted = harness._simulate_batch([first, second])

    assert submitted == [first, second]
    assert harness.backtests_submitted == 2
    assert harness.officially_simulated_count == 2
    assert first.official_alpha_id == "brain_1"
    assert first.official_metrics["fitness"] == 1.1
    assert second.official_alpha_id == "official_sim_2"
    assert first.lifecycle_status == "official_simulated"
    assert second.submission["settings"]["region"] == "USA"
    assert second.submission["backtest_batch_rank"] == 2


def test_submit_error_defers_candidate_batch_on_concurrency_limit():
    exc = BrainAPIError(
        "HTTP 400: CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        status_code=400,
        payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
    )
    harness = _Harness(_Api(submit_errors=[exc]))
    first = _candidate("alpha_a")
    second = _candidate("alpha_b")

    submitted = harness._simulate_batch([first, second])

    assert submitted == [first, second]
    assert harness.halts
    assert first.lifecycle_status == "simulation_deferred_concurrency_limit"
    assert second.gate["status"] == "SIMULATION_DEFERRED_CONCURRENCY_LIMIT"
    assert harness.events[-1][0][0] == "official_simulation_halted"
    assert harness.progress_calls[-1][0][0] == "official_deferred"


def test_submit_error_defers_on_rate_limit_and_records_other_failures():
    rate_limited = BrainAPIError("HTTP 429", status_code=429, retry_after=11)
    harness = _Harness(_Api(submit_errors=[rate_limited]))
    candidate = _candidate("alpha_rate")

    assert harness._simulate_batch([candidate]) == [candidate]
    assert candidate.gate["status"] == "SIMULATION_DEFERRED_RATE_LIMIT"
    assert "retry_after=11" in candidate.gate["failed_reasons"][0]

    failing = _candidate("alpha_fail")
    other = _Harness(_Api())
    other._handle_simulation_submit_error(
        BrainAPIError("HTTP 500: upstream failed", status_code=500),
        failing,
        [],
        [],
    )
    assert failing.lifecycle_status == "simulation_request_failed"
    assert failing.gate["status"] == "SIMULATION_REQUEST_FAILED"
    assert other.events[-1][0][0] == "official_simulation_failed"


def test_wait_for_simulation_batch_handles_poll_and_result_rate_limits():
    poll_limited = BrainAPIError("HTTP 429 poll", status_code=429)
    first = _candidate("alpha_poll")
    first.simulation_id = "sim_poll"
    harness = _Harness(_Api(poll_statuses={"sim_poll": [poll_limited]}))

    harness._wait_for_simulation_batch([first])

    assert first.lifecycle_status == "simulation_poll_deferred_rate_limit"
    assert first.gate["status"] == "SIMULATION_POLL_DEFERRED_RATE_LIMIT"
    assert harness.events[-1][0][0] == "official_simulation_poll_deferred"

    result_limited = BrainAPIError("HTTP 429 result", status_code=429)
    second = _candidate("alpha_result")
    second.simulation_id = "sim_result"
    result_harness = _Harness(_Api(fetch_results={"sim_result": result_limited}))

    result_harness._wait_for_simulation_batch([second])

    assert second.lifecycle_status == "simulation_result_deferred_rate_limit"
    assert second.gate["status"] == "SIMULATION_RESULT_DEFERRED_RATE_LIMIT"
    assert result_harness.events[-1][0][0] == "official_simulation_result_deferred"


def test_wait_for_simulation_batch_records_failures_and_timeout():
    poll_failed = _candidate("alpha_poll_failed")
    poll_failed.simulation_id = "sim_poll_failed"
    result_failed = _candidate("alpha_result_failed")
    result_failed.simulation_id = "sim_result_failed"
    failed = _candidate("alpha_failed")
    failed.simulation_id = "sim_failed"
    timeout = _candidate("alpha_timeout")
    timeout.simulation_id = "sim_timeout"
    api = _Api(
        poll_statuses={
            "sim_poll_failed": [BrainAPIError("HTTP 500 poll", status_code=500)],
            "sim_result_failed": ["COMPLETED"],
            "sim_failed": ["FAILED"],
            "sim_timeout": ["RUNNING"],
        },
        fetch_results={"sim_result_failed": BrainAPIError("HTTP 500 result", status_code=500)},
        attempts=1,
    )
    harness = _Harness(api)

    harness._wait_for_simulation_batch([poll_failed, result_failed, failed, timeout])

    assert poll_failed.gate["status"] == "SIMULATION_POLL_FAILED"
    assert result_failed.gate["status"] == "SIMULATION_RESULT_FAILED"
    assert failed.gate["status"] == "SIMULATION_FAILED"
    assert timeout.lifecycle_status == "simulation_timeout"
    assert timeout.gate["status"] == "SIMULATION_TIMEOUT"


def test_should_remove_after_official_result_classifies_candidate_states():
    harness = _Harness(_Api())

    failed = _candidate("alpha_failed")
    failed.lifecycle_status = "simulation_failed"
    assert harness._should_remove_after_official_result(failed) is True

    ready = _candidate("alpha_ready")
    ready.official_metrics = {"sharpe": 1.5}
    ready.gate = {"submission_ready": True}
    assert harness._should_remove_after_official_result(ready) is False
    assert ready.lifecycle_status == "submission_ready"

    rejected = _candidate("alpha_rejected")
    rejected.official_metrics = {"sharpe": 0.4}
    assert harness._should_remove_after_official_result(rejected) is True
    assert rejected.lifecycle_status == "official_standard_rejected"
    assert rejected.gate["status"] == "OFFICIAL_STANDARD_REJECTED"
