from brain_alpha_ops.web_get_handlers import (
    active_job_payload,
    health_payload,
    job_status_payload,
    lifecycle_payload,
    presets_payload,
    profile_payload,
)


class Store:
    def __init__(self):
        self.rows = {}
        self.active = None

    def get(self, job_id):
        return self.rows.get(job_id)

    def latest_active(self):
        return self.active


def _enrich(progress):
    progress["enriched"] = True
    return progress


def test_job_status_payload_enriches_progress_and_reports_missing():
    store = Store()
    store.rows["job_1"] = {"status": "running", "progress": {"phase": "run"}}

    payload, status = job_status_payload(store, "job_1", _enrich)
    missing, missing_status = job_status_payload(store, "missing", _enrich, error="missing job")

    assert status == 200
    assert payload["ok"] is True
    assert payload["progress"]["enriched"] is True
    assert missing_status == 404
    assert missing["error"] == "missing job"


def test_active_lifecycle_profile_presets_and_health_payloads():
    store = Store()
    store.active = ("job_active", {"status": "running", "progress": {"phase": "scan"}})
    store.rows["job_active"] = {"progress": {"records": [{"stage": "x"}]}}

    active = active_job_payload(store, _enrich)
    lifecycle = lifecycle_payload(store, "job_active", lambda job: job["progress"]["records"])

    assert active["job_id"] == "job_active"
    assert active["progress"]["enriched"] is True
    assert lifecycle["records"] == [{"stage": "x"}]
    assert health_payload() == {"ok": True, "status": "ready"}
    assert profile_payload(lambda: {"tier": "mock"})["profile"]["tier"] == "mock"
    assert presets_payload(lambda: {"default": {}})["presets"] == {"default": {}}
