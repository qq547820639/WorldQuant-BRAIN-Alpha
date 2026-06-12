import json

from brain_alpha_ops.web_get_handlers import (
    active_job_payload,
    health_payload,
    job_status_payload,
    lifecycle_payload,
    presets_payload,
    profile_payload,
)
from brain_alpha_ops.runtime_constants import CloudDefaults


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


def test_job_status_payload_redacts_sensitive_job_rows_before_response():
    store = Store()
    store.rows["job_secret"] = {
        "status": "failed",
        "username": "operator@example.test",
        "password": "plain-password",
        "progress": {
            "phase": "failed",
            "message": "token=secret-token-123",
            "headers": {
                "X-CSRF-Token": "csrf-secret-123",
                "X-Brain-Alpha-Admin-Token": "admin-secret-123",
            },
        },
        "result": {
            "sessionId": "session-secret-123",
            "refreshToken": "refresh-secret-123",
        },
    }

    payload, status = job_status_payload(store, "job_secret", _enrich)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert status == 200
    assert payload["username"] == "<redacted>"
    assert payload["password"] == "<redacted>"
    assert payload["progress"]["headers"]["X-CSRF-Token"] == "<redacted>"
    assert payload["progress"]["headers"]["X-Brain-Alpha-Admin-Token"] == "<redacted>"
    assert payload["result"]["sessionId"] == "<redacted>"
    assert payload["result"]["refreshToken"] == "<redacted>"
    assert "operator@example.test" not in encoded
    assert "plain-password" not in encoded
    assert "secret-token-123" not in encoded
    assert "csrf-secret-123" not in encoded
    assert "admin-secret-123" not in encoded
    assert "session-secret-123" not in encoded
    assert "refresh-secret-123" not in encoded


def test_active_lifecycle_profile_presets_and_health_payloads():
    store = Store()
    store.active = ("job_active", {"status": "running", "progress": {"phase": "scan"}})
    store.rows["job_active"] = {"progress": {"records": [{"stage": "x"}]}}

    active = active_job_payload(store, _enrich)
    lifecycle = lifecycle_payload(store, "job_active", lambda job: job["progress"]["records"])

    assert active["job_id"] == "job_active"
    assert active["progress"]["enriched"] is True
    assert lifecycle["records"] == [{"stage": "x"}]
    assert lifecycle["items"] == [{"stage": "x"}]
    assert lifecycle["returned_count"] == 1
    assert lifecycle["total_count"] == 1
    assert lifecycle["complete"] is True
    assert lifecycle["display_limit"] is None
    assert health_payload() == {
        "ok": True,
        "status": "ready",
        "cloud_sync_stale_seconds": CloudDefaults.CLOUD_SYNC_STALE_SECONDS,
    }
    assert profile_payload(lambda: {"tier": "mock"})["profile"]["tier"] == "mock"
    assert presets_payload(lambda: {"default": {}})["presets"] == {"default": {}}


def test_lifecycle_and_profile_payloads_redact_sensitive_values():
    store = Store()
    store.rows["job_secret"] = {
        "progress": {
            "records": [
                {
                    "stage": "sync",
                    "note": "token=secret-token-123",
                    "sessionId": "session-secret-123",
                }
            ]
        }
    }

    lifecycle = lifecycle_payload(store, "job_secret", lambda job: job["progress"]["records"])
    profile = profile_payload(
        lambda: {
            "tier": "ADVANCED",
            "username": "operator@example.test",
            "phone": "+123456789",
            "headers": {"X-Brain-Alpha-Admin-Token": "admin-secret-123"},
        }
    )
    encoded = json.dumps({"lifecycle": lifecycle, "profile": profile}, ensure_ascii=False)

    assert lifecycle["records"][0]["stage"] == "sync"
    assert lifecycle["records"][0]["sessionId"] == "<redacted>"
    assert lifecycle["items"] == lifecycle["records"]
    assert profile["profile"]["tier"] == "ADVANCED"
    assert profile["profile"]["username"] == "<redacted>"
    assert profile["profile"]["phone"] == "<redacted>"
    assert profile["profile"]["headers"]["X-Brain-Alpha-Admin-Token"] == "<redacted>"
    assert "secret-token-123" not in encoded
    assert "session-secret-123" not in encoded
    assert "operator@example.test" not in encoded
    assert "+123456789" not in encoded
    assert "admin-secret-123" not in encoded
