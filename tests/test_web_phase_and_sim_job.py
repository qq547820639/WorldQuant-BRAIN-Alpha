from __future__ import annotations

from datetime import datetime, timezone

from brain_alpha_ops.web.handlers.phase import phase_state_payload
from brain_alpha_ops.web_jobs import job_delete
from brain_alpha_ops.web_simulation_job import create_sim_job_store


class _SyncJobs:
    def __init__(self, *, active=None, rows=None, fail_active=False, fail_list=False):
        self.active = active
        self.rows = rows or []
        self.fail_active = fail_active
        self.fail_list = fail_list

    def latest_active(self):
        if self.fail_active:
            raise RuntimeError("active failed")
        return self.active

    def list_all(self):
        if self.fail_list:
            raise RuntimeError("list failed")
        return self.rows


class _CandidateRepo:
    def __init__(self, count_value=0, scored_value=0, fail=False):
        self.count_value = count_value
        self.scored_value = scored_value
        self.fail = fail

    def count(self):
        if self.fail:
            raise ValueError("count failed")
        return self.count_value

    def scored_count(self):
        if self.fail:
            raise TypeError("scored failed")
        return self.scored_value


class _Connection:
    def __init__(self, connected=True, *, status="connected", page=True, fail=False):
        self.status = status
        self.last_tested_at = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)
        self.uses_page_credentials = page
        self.fail = fail
        self.connected = connected

    def is_connected(self):
        if self.fail:
            raise ValueError("connection failed")
        return self.connected


class _Readiness:
    def __init__(self, payload=None, fail=False):
        self.payload = payload or {"ready_to_submit": False, "eligible_count": 0}
        self.fail = fail

    def get_readiness(self):
        if self.fail:
            raise RuntimeError("readiness failed")
        return self.payload


def test_phase_state_payload_reports_stalled_evaluate_phase():
    payload = phase_state_payload(
        sync_jobs=_SyncJobs(
            active=("sync_1", {"progress": {"scanned": 0, "total": 40, "elapsed_seconds": 12, "phase": "scan"}}),
            rows=[("sync_0", {"status": "completed"})],
        ),
        candidate_repo=_CandidateRepo(count_value=3, scored_value=2),
        connection_tracker=_Connection(),
        readiness_service=_Readiness({"ready_to_submit": False, "eligible_count": 0}),
    )

    assert payload["ok"] is True
    assert payload["current_phase"] == "evaluate"
    assert payload["context_fresh"] is True
    assert payload["sync"]["in_progress"] is True
    assert payload["sync"]["stalled"] is True
    assert payload["sync"]["total"] == 40
    assert payload["connection"]["credential_source"] == "page"
    assert payload["connection"]["last_tested_at"] == "2026-06-09T10:00:00+00:00"


def test_phase_state_payload_uses_server_session_connection_status():
    payload = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[("sync_0", {"status": "completed"})]),
        candidate_repo=_CandidateRepo(count_value=2, scored_value=1),
        connection_tracker=None,
        readiness_service=_Readiness({"ready_to_submit": False, "eligible_count": 0}),
        session_status={
            "authenticated": True,
            "connected": True,
            "brain_connection_verified": True,
            "credential_source": "managed",
            "last_verified_at": "2026-06-10T02:00:00+00:00",
        },
    )

    assert payload["connected"] is True
    assert payload["current_phase"] == "evaluate"
    assert payload["connection"] == {
        "status": "connected",
        "last_tested_at": "2026-06-10T02:00:00+00:00",
        "credential_source": "managed",
    }


def test_phase_state_authenticated_disconnected_session_overrides_tracker():
    payload = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[("sync_0", {"status": "completed"})]),
        candidate_repo=_CandidateRepo(count_value=2),
        connection_tracker=_Connection(connected=True, status="connected", page=True),
        readiness_service=_Readiness({"ready_to_submit": False, "eligible_count": 0}),
        session_status={
            "authenticated": True,
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
        },
    )

    assert payload["connected"] is False
    assert payload["current_phase"] == "connect"
    assert payload["connection"]["status"] == "disconnected"
    assert payload["connection"]["credential_source"] == "none"


def test_phase_state_uses_fresh_local_snapshot_when_sync_job_history_is_unavailable():
    payload = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[]),
        candidate_repo=_CandidateRepo(count_value=4, scored_value=1),
        connection_tracker=_Connection(),
        readiness_service=_Readiness({"ready_to_submit": False, "eligible_count": 0}),
        cloud_alpha_snapshot=lambda limit=1: {
            "alphas": [{"id": "prod_alpha"}],
            "summary": {"count": 40852, "is_stale": False},
        },
        official_context_file_counts=lambda: {
            "fields_count": 8599,
            "operators_count": 67,
            "datasets_count": 20,
            "context_cache_manifest": {"complete": True, "is_stale": False},
            "context_cache_metadata": {
                "official_fields.json": {"is_stale": False, "is_expired": False},
                "official_operators.json": {"is_stale": False, "is_expired": False},
                "official_datasets.json": {"is_stale": False, "is_expired": False},
            },
        },
    )

    assert payload["context_fresh"] is True
    assert payload["context_fresh_source"] == "local_cache"
    assert payload["current_phase"] == "evaluate"


def test_phase_state_accepts_stale_local_snapshot_for_cache_first_login():
    payload = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[]),
        candidate_repo=_CandidateRepo(count_value=4, scored_value=1),
        connection_tracker=_Connection(),
        readiness_service=_Readiness({"ready_to_submit": False, "eligible_count": 0}),
        cloud_alpha_snapshot=lambda limit=1: {
            "alphas": [{"id": "prod_alpha"}],
            "summary": {"count": 40852, "is_stale": True},
        },
        official_context_file_counts=lambda: {
            "fields_count": 8599,
            "operators_count": 67,
            "datasets_count": 20,
            "context_cache_manifest": {"complete": True, "is_stale": False},
        },
    )

    assert payload["context_fresh"] is True
    assert payload["context_fresh_source"] == "local_cache"
    assert payload["current_phase"] == "evaluate"


def test_phase_state_payload_phase_selection_and_safe_defaults():
    disconnected = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[("sync_0", {"status": "completed"})]),
        candidate_repo=_CandidateRepo(count_value=9),
        connection_tracker=_Connection(connected=False, status="disconnected", page=False),
        readiness_service=_Readiness({"ready_to_submit": True, "eligible_count": 2}),
    )
    assert disconnected["current_phase"] == "connect"
    assert disconnected["connection"]["credential_source"] == "managed"

    discover = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[("sync_0", {"status": "completed_with_warnings"})]),
        candidate_repo=_CandidateRepo(count_value=0),
        connection_tracker=_Connection(),
        readiness_service=_Readiness(),
    )
    assert discover["current_phase"] == "discover"

    ready = phase_state_payload(
        sync_jobs=_SyncJobs(rows=[("sync_0", {"status": "completed"})]),
        candidate_repo=_CandidateRepo(count_value=5, scored_value=5),
        connection_tracker=_Connection(),
        readiness_service=_Readiness({"ready_to_submit": True, "eligible_count": 1}),
    )
    assert ready["current_phase"] == "ready"
    assert ready["readiness"]["eligible_count"] == 1

    fallback = phase_state_payload(
        sync_jobs=_SyncJobs(fail_active=True, fail_list=True),
        candidate_repo=_CandidateRepo(count_value=3, scored_value=2, fail=True),
        connection_tracker=_Connection(fail=True),
        readiness_service=_Readiness(fail=True),
    )
    assert fallback["current_phase"] == "connect"
    assert fallback["candidates_count"] == 0
    assert fallback["scored_count"] == 0
    assert fallback["sync"]["in_progress"] is False
    assert fallback["readiness"]["ready"] is False


class _Store:
    def __init__(self):
        self.rows = {}

    def update(self, jid: str, **kwargs):
        self.rows.setdefault(jid, {}).update(kwargs)

    def get(self, jid: str):
        return self.rows.get(jid)

    def is_cancelled(self, jid: str) -> bool:
        return bool(self.rows.get(jid, {}).get("cancel"))


def test_create_sim_job_store_adapts_injected_and_module_stores():
    store = _Store()
    adapter = create_sim_job_store(store)
    adapter.update("job_1", status="running")
    assert store.rows["job_1"]["status"] == "running"
    assert adapter.is_cancelled("job_1") is False

    store.rows["job_1"]["status"] = "stopped"
    assert adapter.is_cancelled("job_1") is True

    store.rows["job_1"]["status"] = "running"
    store.rows["job_1"]["cancel"] = True
    assert adapter.is_cancelled("job_1") is True

    module_adapter = create_sim_job_store()
    job_id = "sim_job_store_adapter_test"
    try:
        module_adapter.update(job_id, status="running")
        assert module_adapter.is_cancelled(job_id) is False
        module_adapter.update(job_id, status="cancelled")
        assert module_adapter.is_cancelled(job_id) is True
    finally:
        job_delete(job_id)
