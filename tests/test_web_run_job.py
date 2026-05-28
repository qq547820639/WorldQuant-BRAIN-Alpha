from __future__ import annotations

import logging
from types import SimpleNamespace

from brain_alpha_ops.models import PipelineResult
from brain_alpha_ops.web_run_job import run_guided_job_service, run_job_service


class _Store:
    def __init__(self, *, cancelled=False):
        self.cancelled = cancelled
        self.rows = {"job_1": {"progress": {}}}
        self.updates = []

    def update(self, job_id, **fields):
        self.rows.setdefault(job_id, {}).update(fields)
        self.updates.append((job_id, fields))

    def get(self, job_id):
        return self.rows.get(job_id)

    def is_cancelled(self, job_id):
        return self.cancelled


class _Result:
    def to_dict(self):
        return {
            "summary": {
                "produced_count": 2,
                "backtest_slots": [{"status": "RUNNING"}],
            },
            "candidates": [{"alpha_id": "a1"}],
        }


def _config(*, run_forever=False):
    return SimpleNamespace(ops=SimpleNamespace(budget=SimpleNamespace(run_forever=run_forever)))


def test_run_job_service_marks_completed_with_summary_stats():
    store = _Store()

    def run_pipeline(config, *, progress_callback, stop_callback):
        progress_callback({"phase": "official_simulation", "data": {"ready_results_count": 1}})
        assert stop_callback() is False
        return _Result()

    run_job_service(
        "job_1",
        {"env": "mock"},
        job_store=store,
        run_config_from_payload=lambda payload: _config(run_forever=True),
        run_pipeline_from_config=run_pipeline,
        compute_run_stats=lambda data, config: {"produced_count": data["produced_count"]},
        safe_error_message=str,
        log=logging.getLogger("tests.web_run_job"),
    )

    row = store.get("job_1")
    assert row["status"] == "completed"
    assert row["progress"]["phase"] == "completed"
    assert row["progress"]["continuous"] is True
    assert row["progress"]["data"]["candidates"] == [{"alpha_id": "a1"}]
    assert row["progress"]["data"]["backtests"] == [{"status": "RUNNING"}]
    assert row["progress"]["data"]["stats"] == {"produced_count": 2}


def test_run_job_service_records_redacted_failure_context():
    store = _Store()

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret-token-123 failed")

    run_job_service(
        "job_1",
        {},
        job_store=store,
        run_config_from_payload=lambda payload: _config(),
        run_pipeline_from_config=boom,
        compute_run_stats=lambda data, config: {},
        safe_error_message=lambda exc: "redacted failure",
        log=logging.getLogger("tests.web_run_job"),
    )

    row = store.get("job_1")
    assert row["status"] == "failed"
    assert row["error"] == "redacted failure"
    assert row["progress"]["error_context"]["error_code"] == "RUN_JOB_FAILED"
    assert row["progress"]["error_context"]["job_id"] == "job_1"


def test_run_guided_job_service_registers_phase_progress(monkeypatch):
    store = _Store()

    class FakeGuidedPipeline:
        def __init__(self, _config, *, stop_callback=None):
            self.phases = {"init": object(), "redline": object(), "finalize": object()}
            self.callback = None
            self.stop_callback = stop_callback

        def on_progress(self, callback):
            self.callback = callback
            return self

        def run(self):
            assert self.callback is not None
            assert self.stop_callback is not None
            assert self.stop_callback() is False
            self.callback("redline", "running", {"message": "checking red lines", "percent": 33, "alpha_id": "a1"})
            return PipelineResult(run_id="run_guided", candidates=[], events=[], summary={"candidates": [{"alpha_id": "a1"}]})

        def resume(self):
            return self.run()

    monkeypatch.setattr("brain_alpha_ops.ux.guided_pipeline.GuidedPipeline", FakeGuidedPipeline)

    run_guided_job_service(
        "job_1",
        {"guided": True},
        job_store=store,
        run_config_from_payload=lambda payload: _config(),
        compute_run_stats=lambda data, config: {"candidate_count": len(data.get("candidates", []))},
        safe_error_message=str,
        log=logging.getLogger("tests.web_run_job"),
    )

    assert any(
        update.get("progress", {}).get("phase") == "redline"
        and update.get("progress", {}).get("status") == "running"
        and update.get("progress", {}).get("percent") == 33
        for _job_id, update in store.updates
    )
    row = store.get("job_1")
    assert row["status"] == "completed"
    assert row["progress"]["data"]["stats"] == {"candidate_count": 1}
