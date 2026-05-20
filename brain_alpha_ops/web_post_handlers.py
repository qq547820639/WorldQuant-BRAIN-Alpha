"""Pure POST payload handlers for the local web console."""

from __future__ import annotations

from typing import Any, Callable, Protocol


Payload = dict[str, Any]
StatusPayload = tuple[Payload, int]
HeaderList = list[tuple[str, str]]


class CancellableJobStore(Protocol):
    def cancel(self, job_id: str) -> bool:
        ...


class BackgroundJobStore(Protocol):
    def latest_active(self) -> tuple[str, dict] | None:
        ...

    def create(self) -> str:
        ...


def stop_job_payload(store: CancellableJobStore, payload: Payload | None) -> Payload:
    job_id = str((payload or {}).get("job_id", ""))
    return {"ok": store.cancel(job_id)}


def background_job_start_payload(
    store: BackgroundJobStore,
    payload: Payload,
    start_job: Callable[[str, Payload], None],
    *,
    conflict_error: str,
    conflict_error_code: str = "CONFLICT_RUNNING",
) -> StatusPayload:
    active = store.latest_active()
    if active:
        active_job_id, _job = active
        response: Payload = {"ok": False, "error": conflict_error, "job_id": active_job_id}
        if conflict_error_code:
            response["error_code"] = conflict_error_code
        return response, 409
    job_id = store.create()
    start_job(job_id, payload)
    return {"ok": True, "job_id": job_id}, 200


def connection_test_post_payload(payload: Payload, test_connection: Callable[[Payload], Payload]) -> Payload:
    return test_connection(payload)


def assistant_response_parse_post_payload(payload: Payload, parse_payload: Callable[[Payload], Payload]) -> Payload:
    return parse_payload(payload)


def assistant_response_guidance_post_payload(payload: Payload, guidance_payload: Callable[[Payload], Payload]) -> Payload:
    return guidance_payload(payload)


def save_assistant_guidance_post_payload(payload: Payload, save_payload: Callable[[Payload], Payload]) -> Payload:
    return save_payload(payload)


def session_end_payload(
    session_id: str,
    expire_session: Callable[[str], None],
    expired_session_cookie_header: Callable[[], str],
) -> tuple[Payload, HeaderList]:
    expire_session(session_id)
    return {"ok": True}, [("Set-Cookie", expired_session_cookie_header())]
