from __future__ import annotations

from types import SimpleNamespace

import brain_alpha_ops.web as web


def test_legacy_run_endpoint_forces_non_submit_and_keeps_credentials_out_of_job_metadata(monkeypatch):
    created_rows: list[dict] = []
    validated_payloads: list[dict] = []
    started: list[tuple[object, tuple[object, ...]]] = []

    class Jobs:
        def latest_active(self):
            return None

        def create(self, initial):
            created_rows.append(dict(initial))
            return "job_safe"

    monkeypatch.setattr(web, "JOB_REGISTRY", SimpleNamespace(jobs=Jobs()), raising=False)
    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: validated_payloads.append(dict(payload)) or object(), raising=False)
    monkeypatch.setattr(web, "run_job", object(), raising=False)
    monkeypatch.setattr(web, "_submit_background_job", lambda target, *args: started.append((target, args)), raising=False)

    result = web._real_run({
        "autoSubmit": True,
        "auto_submit": True,
        "username": "tester@example.com",
        "password": "session-password",
    })

    assert result["ok"] is True
    assert result["job_id"] == "job_safe"
    assert result["auto_submit"] is False
    assert result["submitted"] is False
    assert validated_payloads[0]["autoSubmit"] is False
    assert validated_payloads[0]["auto_submit"] is False
    assert started and started[0][1] == ("job_safe", validated_payloads[0])
    assert created_rows
    assert "username" not in created_rows[0]
    assert "password" not in created_rows[0]
    assert created_rows[0]["result"]["summary"] == {
        "submitted_this_run": 0,
        "auto_submitted": 0,
    }
