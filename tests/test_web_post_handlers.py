from brain_alpha_ops.web_post_handlers import (
    assistant_response_guidance_post_payload,
    assistant_response_parse_post_payload,
    background_job_start_payload,
    connection_test_post_payload,
    save_assistant_guidance_post_payload,
    session_end_payload,
    stop_job_payload,
)


class Store:
    def __init__(self):
        self.active = None
        self.cancelled = []
        self.created = []

    def latest_active(self):
        return self.active

    def create(self):
        job_id = f"job_{len(self.created) + 1}"
        self.created.append(job_id)
        return job_id

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return job_id == "job_1"


def test_background_job_start_payload_handles_conflict_and_starts_job():
    store = Store()
    store.active = ("job_active", {"status": "running"})
    started = []

    conflict, conflict_status = background_job_start_payload(
        store,
        {"alpha": 1},
        lambda job_id, payload: started.append((job_id, payload)),
        conflict_error="already running",
    )

    store.active = None
    payload, status = background_job_start_payload(
        store,
        {"alpha": 2},
        lambda job_id, body: started.append((job_id, body)),
        conflict_error="already running",
    )

    assert conflict_status == 409
    assert conflict["error_code"] == "CONFLICT_RUNNING"
    assert conflict["job_id"] == "job_active"
    assert status == 200
    assert payload == {"ok": True, "job_id": "job_1"}
    assert started == [("job_1", {"alpha": 2})]


def test_stop_job_payload_normalizes_job_id():
    store = Store()

    assert stop_job_payload(store, {"job_id": "job_1"}) == {"ok": True}
    assert stop_job_payload(store, {}) == {"ok": False}
    assert store.cancelled == ["job_1", ""]


def test_post_payload_adapters_delegate_to_domain_handlers():
    seen = []

    def handler(payload):
        seen.append(payload)
        return {"ok": True, "value": payload["value"]}

    assert connection_test_post_payload({"value": 1}, handler)["value"] == 1
    assert assistant_response_parse_post_payload({"value": 2}, handler)["value"] == 2
    assert assistant_response_guidance_post_payload({"value": 3}, handler)["value"] == 3
    assert save_assistant_guidance_post_payload({"value": 4}, handler)["value"] == 4
    assert seen == [{"value": 1}, {"value": 2}, {"value": 3}, {"value": 4}]


def test_session_end_payload_expires_session_and_cookie():
    expired = []

    payload, headers = session_end_payload(
        "session_1",
        lambda session_id: expired.append(session_id),
        lambda: "brain_alpha_ops_session=; Max-Age=0",
    )

    assert payload == {"ok": True}
    assert headers == [("Set-Cookie", "brain_alpha_ops_session=; Max-Age=0")]
    assert expired == ["session_1"]
