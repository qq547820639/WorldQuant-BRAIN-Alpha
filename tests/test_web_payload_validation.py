"""Tests for web payload validation, server lifecycle, and sync-status payload helpers."""

import threading

import pytest

from brain_alpha_ops.web.misc import web_payload_validation as wv


# ═══════════════════════ Payload validation helpers ═══════════════════════

def test_validate_json_object_payload():
    assert wv.validate_json_object_payload({"a": 1}) == ""
    assert wv.validate_json_object_payload(None) == "request body must be a JSON object"
    assert wv.validate_json_object_payload([1]) == "request body must be a JSON object"


def test_validate_generate_candidates_payload_ok():
    assert wv.validate_generate_candidates_payload({"count": 5}) == ""
    assert wv.validate_generate_candidates_payload({"candidates": 3}) == ""
    assert wv.validate_generate_candidates_payload({}) == ""
    assert wv.validate_generate_candidates_payload(None) == "request body must be a JSON object"


def test_validate_generate_candidates_payload_bounds():
    assert wv.validate_generate_candidates_payload({"count": 0}) == "count must be between 1 and 100"
    assert wv.validate_generate_candidates_payload({"count": 101}) == "count must be between 1 and 100"
    assert wv.validate_generate_candidates_payload({"candidates": "abc"}) == (
        "candidates must be an integer between 1 and 100"
    )
    # empty/None values are treated as absent
    assert wv.validate_generate_candidates_payload({"count": ""}) == ""
    assert wv.validate_generate_candidates_payload({"count": None}) == ""


def test_validate_generate_candidates_payload_maintain_pool():
    payload = {
        "automation_mode": "maintain_candidate_pool",
        "target_pool_size": 10,
        "pool_deficit": 2,
    }
    assert wv.validate_generate_candidates_payload(payload) == ""
    bad = {"automation_mode": "maintain_candidate_pool", "target_pool_size": 0}
    assert "target_pool_size must be between" in wv.validate_generate_candidates_payload(bad)
    bad2 = {"automationMode": "maintain_candidate_pool", "existing_pool_size": "x"}
    assert "existing_pool_size must be an integer" in wv.validate_generate_candidates_payload(bad2)


def test_validate_submit_batch_payload():
    assert wv.validate_submit_batch_payload({"alpha_ids": ["A1"]}) == ""
    assert wv.validate_submit_batch_payload(None) == "request body must be a JSON object"
    assert wv.validate_submit_batch_payload({}) == "alpha_ids must be a non-empty list of Alpha IDs"
    assert wv.validate_submit_batch_payload({"alpha_ids": []}) == "alpha_ids must be a non-empty list of Alpha IDs"
    assert wv.validate_submit_batch_payload({"alpha_ids": "A1"}) == "alpha_ids must be a non-empty list of Alpha IDs"
    many = {"alpha_ids": [str(i) for i in range(200)]}
    assert wv.validate_submit_batch_payload(many) == "alpha_ids must contain at most 100 items"
    bad_id = {"alpha_ids": ["bad id with space"]}
    assert "may only contain" in wv.validate_submit_batch_payload(bad_id)
    non_list = {"alpha_ids": ["A1"], "submit_candidates": "nope"}
    assert wv.validate_submit_batch_payload(non_list) == "submit_candidates must be a list when provided"


def test_validate_check_batch_payload():
    assert wv.validate_check_batch_payload(None) == ""
    assert wv.validate_check_batch_payload({}) == ""
    assert wv.validate_check_batch_payload({"candidate_ids": ["A1"]}) == ""
    assert wv.validate_check_batch_payload({"candidate_ids": "A1"}) == "candidate_ids must be a list of Alpha IDs"
    assert wv.validate_check_batch_payload({"mode": "quick"}) == ""
    assert wv.validate_check_batch_payload({"mode": "bogus"}) == "mode must be quick or all"
    assert wv.validate_check_batch_payload({"check_candidates": "x"}) == "check_candidates must be a list when provided"


def test_validate_simulation_payload():
    assert wv.validate_simulation_payload({}) == ""
    assert wv.validate_simulation_payload({"candidate_ids": ["A1"]}) == ""
    assert wv.validate_simulation_payload(None) == "request body must be a JSON object"
    assert wv.validate_simulation_payload({"candidate_ids": "A1"}) == "candidate_ids must be a list of Alpha IDs"
    assert wv.validate_simulation_payload({"workflow_plan": "x"}) == "workflow_plan must be an object when provided"
    assert wv.validate_simulation_payload({"workflow_plan": {"validator": "x"}}) == (
        "workflow_plan.validator must be an object when provided"
    )
    assert wv.validate_simulation_payload({"workflow_plan": {"validator": {"next_candidate_ids": "A1"}}}) == (
        "workflow_plan.validator.next_candidate_ids must be a list of Alpha IDs"
    )
    assert wv.validate_simulation_payload({"min_score": -1}) == "min_score must be a finite number between 0 and 100"
    assert wv.validate_simulation_payload({"min_score": 50}) == ""
    assert wv.validate_simulation_payload({"max_simulations": 1.5}) == (
        "max_simulations must be a finite integer between 0 and 100"
    )
    assert wv.validate_simulation_payload({"poll_timeout": "abc"}) == (
        "poll_timeout must be a finite number between 0 and 3600"
    )
    assert wv.validate_simulation_payload({"stall_timeout": 4000}) == (
        "stall_timeout must be a finite number between 0 and 3600"
    )


def test_validate_candidate_rows():
    assert wv.validate_candidate_rows(None, "field") == ""
    assert wv.validate_candidate_rows("x", "field") == "field must be a list when provided"
    assert wv.validate_candidate_rows(list(range(101)), "field") == "field must contain at most 100 items"
    assert wv.validate_candidate_rows([{"alpha_id": "A1"}], "field") == ""
    assert wv.validate_candidate_rows([42], "field") == "field[] must be an object"
    assert wv.validate_candidate_rows([{"alpha_id": "bad id"}], "field") == (
        "field[].alpha_id may only contain letters, numbers, underscore, dash, dot, or colon"
    )
    # empty/missing ids are skipped
    assert wv.validate_candidate_rows([{"alpha_id": ""}, {"official_alpha_id": None}], "field") == ""


def test_validate_job_cancel_payload():
    assert wv.validate_job_cancel_payload({"job_id": "job-1"}) == ""
    assert wv.validate_job_cancel_payload(None) == "request body must be a JSON object"
    assert wv.validate_job_cancel_payload({}) == "job_id must be a non-empty string"
    assert wv.validate_job_cancel_payload({"job_id": 5}) == "job_id must be a non-empty string"
    assert wv.validate_job_cancel_payload({"job_id": ""}) == "job_id must be a non-empty string"
    assert wv.validate_job_cancel_payload({"job_id": "x" * 200}) == (
        "job_id must be 128 characters or fewer"
    )
    assert wv.validate_job_cancel_payload({"job_id": "bad id"}) == (
        "job_id may only contain letters, numbers, underscore, dash, dot, or colon"
    )
    # custom field name
    assert wv.validate_job_cancel_payload({"task_id": "t1"}, field="task_id") == ""


def test_validate_assistant_text_payload():
    assert wv.validate_assistant_text_payload({"raw_output": "hi"}) == ""
    assert wv.validate_assistant_text_payload({"text": "hi"}) == ""
    assert wv.validate_assistant_text_payload(None) == "request body must be a JSON object"
    assert wv.validate_assistant_text_payload({}) == "raw_output or text must be a non-empty string"
    assert wv.validate_assistant_text_payload({"raw_output": ""}) == "raw_output or text must be a non-empty string"
    assert wv.validate_assistant_text_payload({"raw_output": "x" * 200001}) == (
        "raw_output or text must be 200000 characters or fewer"
    )


def test_validate_assistant_guidance_save_payload():
    assert wv.validate_assistant_guidance_save_payload({"assistant_guidance": {"a": 1}}) == ""
    assert wv.validate_assistant_guidance_save_payload({"assistant_response": "hi"}) == ""
    assert wv.validate_assistant_guidance_save_payload({"raw_output": "hi"}) == ""
    assert wv.validate_assistant_guidance_save_payload({"text": "hi"}) == ""
    assert wv.validate_assistant_guidance_save_payload(None) == "request body must be a JSON object"
    assert wv.validate_assistant_guidance_save_payload({"assistant_guidance": "x"}) == (
        "assistant_guidance must be an object"
    )
    assert wv.validate_assistant_guidance_save_payload({"assistant_guidance": {}}) == (
        "assistant_guidance must not be empty"
    )
    assert wv.validate_assistant_guidance_save_payload({}) == (
        "assistant_response, raw_output, text, or assistant_guidance is required"
    )
    assert wv.validate_assistant_guidance_save_payload({"text": "x" * 200001}) == (
        "assistant_response, raw_output, or text must be 200000 characters or fewer"
    )


def test_validate_assistant_cross_review_payload():
    assert wv.validate_assistant_cross_review_payload({"request_pack": {}, "primary_response": "r"}) == ""
    assert wv.validate_assistant_cross_review_payload({"request": {}, "primary": "r"}) == ""
    assert wv.validate_assistant_cross_review_payload(None) == "request body must be a JSON object"
    assert wv.validate_assistant_cross_review_payload({}) == "request_pack must be an object"
    assert wv.validate_assistant_cross_review_payload({"request_pack": {}}) == "primary_response is required"


def test_validate_alpha_action_payload():
    assert wv.validate_alpha_action_payload({"alpha_id": "A1"}) == ""
    assert wv.validate_alpha_action_payload({"candidate": {"alpha_id": "A1"}}) == ""
    assert wv.validate_alpha_action_payload({"simulation_id": "S1"}) == ""
    # official_alpha_id with empty value is skipped
    assert wv.validate_alpha_action_payload({"official_alpha_id": ""}) == "candidate or alpha_id is required"
    assert wv.validate_alpha_action_payload(None) == "request body must be a JSON object"
    assert wv.validate_alpha_action_payload({"candidate": "x"}) == "candidate must be an object when provided"
    assert wv.validate_alpha_action_payload({"alpha_id": "bad id"}) == (
        "alpha_id may only contain letters, numbers, underscore, dash, dot, or colon"
    )
    assert wv.validate_alpha_action_payload({"candidate": {"official_alpha_id": "bad id"}}) == (
        "candidate.official_alpha_id may only contain letters, numbers, underscore, dash, dot, or colon"
    )
    assert wv.validate_alpha_action_payload({}) == "candidate or alpha_id is required"


def test_validate_sync_alphas_payload():
    assert wv.validate_sync_alphas_payload({}) == ""
    assert wv.validate_sync_alphas_payload({"syncRange": "3d"}) == ""
    assert wv.validate_sync_alphas_payload({"range": "7d"}) == ""
    assert wv.validate_sync_alphas_payload({"syncRange": ""}) == ""
    assert wv.validate_sync_alphas_payload({"syncRange": "bogus"}) == "syncRange must be one of 3d, 7d, recent, 6months, all"
    assert wv.validate_sync_alphas_payload(None) == "request body must be a JSON object"


def test_validate_alpha_id_value():
    assert wv.validate_alpha_id_value("A1", "f") == ""
    assert wv.validate_alpha_id_value("a.b:c_d-e", "f") == ""
    assert wv.validate_alpha_id_value(42, "f") == "f must be a string Alpha ID"
    assert wv.validate_alpha_id_value("", "f") == "f must be a non-empty Alpha ID"
    assert wv.validate_alpha_id_value("   ", "f") == "f must be a non-empty Alpha ID"
    assert wv.validate_alpha_id_value("x" * 200, "f") == "f must be 128 characters or fewer"
    assert wv.validate_alpha_id_value("bad id", "f") == (
        "f may only contain letters, numbers, underscore, dash, dot, or colon"
    )


def test_validate_numeric_field_helpers():
    # bool value rejected
    assert wv._validate_numeric_field({"f": True}, "f", minimum=0, maximum=10, integer=True) == (
        "f must be a finite integer between 0 and 10"
    )
    assert wv._validate_numeric_field({"f": True}, "f", minimum=0, maximum=10, integer=False) == (
        "f must be a finite number between 0 and 10"
    )
    # absent / empty / None treated as fine
    assert wv._validate_numeric_field({}, "f", minimum=0, maximum=10, integer=True) == ""
    assert wv._validate_numeric_field({"f": ""}, "f", minimum=0, maximum=10, integer=True) == ""
    # non-finite
    assert "finite" in wv._validate_numeric_field({"f": float("inf")}, "f", minimum=0, maximum=10, integer=False)
    assert "finite" in wv._validate_numeric_field({"f": float("nan")}, "f", minimum=0, maximum=10, integer=False)
    # out of range
    assert wv._validate_numeric_field({"f": 99}, "f", minimum=0, maximum=10, integer=True) == (
        "f must be a finite integer between 0 and 10"
    )
    # valid
    assert wv._validate_numeric_field({"f": 5}, "f", minimum=0, maximum=10, integer=True) == ""


# ═══════════════════════ Server lifecycle helpers ═══════════════════════

def test_find_free_port_finds_free_port():
    _port = wv.find_free_port(18000, host="127.0.0.1")
    assert isinstance(_port, int) and _port > 0


def test_display_host_for_bind():
    assert wv.display_host_for_bind("0.0.0.0") == "127.0.0.1"
    assert wv.display_host_for_bind("::") == "127.0.0.1"
    assert wv.display_host_for_bind("localhost") == "localhost"


def test__server_port():
    class FakeServer:
        server_port = 8080
        server_address = ("127.0.0.1", 8080)

    class NoAttr:
        pass

    assert wv._server_port(FakeServer(), 9999) == 8080
    # server_port missing -> fall back to server_address
    obj = type("S", (), {"server_address": ("127.0.0.1", 7000)})()
    assert wv._server_port(obj, 9999) == 7000
    # invalid address -> fallback
    obj2 = type("S", (), {"server_address": ("127.0.0.1", "x")})()
    assert wv._server_port(obj2, 1234) == 1234
    assert wv._server_port(NoAttr(), 9999) == 9999


def test_shutdown_server():
    class FakeServer:
        def __init__(self):
            self.shutdown_called = False
            self.close_called = False

        def shutdown(self):
            self.shutdown_called = True

        def server_close(self):
            self.close_called = True

    evt = threading.Event()
    srv = FakeServer()
    wv.shutdown_server(srv, evt)
    assert evt.is_set()
    assert srv.shutdown_called and srv.close_called
    # None server is safe
    evt2 = threading.Event()
    wv.shutdown_server(None, evt2)
    assert evt2.is_set()


def test_serve_loopback_no_allow_remote_raises():
    evt = threading.Event()
    with pytest.raises(ValueError, match="remote web bind requires web.allow_remote=true"):
        wv.serve(
            port=1,
            open_browser=False,
            host="0.0.0.0",
            default_port=9000,
            handler_class=object,
            stop_event=evt,
            configure_session_policy=lambda *a, **k: None,
            normalize_host=lambda h: h or "127.0.0.1",
            loopback_bind_hosts={"127.0.0.1"},
            allow_remote=False,
        )


def test_serve_with_fake_factory():
    events = []

    class FakeServer:
        def __init__(self, addr, handler):
            self.server_address = addr
            self.daemon = False
            self.target = None

        def serve_forever(self):
            events.append("serving")

    evt = threading.Event()
    url, server = wv.serve(
        port=12345,
        open_browser=False,
        host="127.0.0.1",
        default_port=9000,
        handler_class=object,
        stop_event=evt,
        configure_session_policy=lambda *a, **k: events.append("policy"),
        normalize_host=lambda h: h or "127.0.0.1",
        loopback_bind_hosts={"127.0.0.1"},
        allow_remote=False,
        server_factory=lambda addr, handler: FakeServer(addr, handler),
        thread_factory=lambda **kw: (events.append("thread"), type("T", (), {"start": lambda self: events.append("start"), "daemon": True})())[1],
    )
    assert url.startswith("http://127.0.0.1:12345/")
    assert "policy" in events


def test_serve_with_open_browser_calls_browser_open():
    opened = []
    evt = threading.Event()

    class FakeServer:
        def __init__(self, addr, handler):
            self.server_address = addr

        def serve_forever(self):
            pass

    wv.serve(
        port=12346,
        open_browser=True,
        host="127.0.0.1",
        default_port=9000,
        handler_class=object,
        stop_event=evt,
        configure_session_policy=lambda *a, **k: None,
        normalize_host=lambda h: h or "127.0.0.1",
        loopback_bind_hosts={"127.0.0.1"},
        allow_remote=False,
        server_factory=lambda addr, handler: FakeServer(addr, handler),
        browser_open=opened.append,
        thread_factory=lambda **kw: type("T", (), {"start": lambda self: None, "daemon": True})(),
    )
    assert opened and "http://127.0.0.1:12346/" in opened[0]


# ═══════════════════════ Sync status payload helpers ═══════════════════════

def test_with_sync_history_limit_zero():
    assert wv.with_sync_history({"a": 1}, None, limit=0) == {"a": 1, "sync_history": []}


class _FakeCtx:
    def __init__(self, rows=None, progress=None, counts=None, raise_error=False):
        self._rows = rows or []
        self._progress = progress or {}
        self._counts = counts or {}
        self._raise_error = raise_error
        self.sync_jobs = _Rows(self._rows, self._raise_error)

    def enrich_progress(self, d):
        return self._progress if self._progress else d

    def official_context_file_counts(self):
        if self._raise_error:
            raise RuntimeError("boom")
        return self._counts


class _Rows:
    def __init__(self, rows, raise_error):
        self._rows = rows
        self._raise_error = raise_error

    def all(self, limit=None):
        if self._raise_error:
            raise RuntimeError("boom")
        return self._rows


def test_with_sync_history_returns_items():
    ctx = _FakeCtx(
        rows=[("job1", {"status": "running", "progress": {"phase": "scan", "scanned": 5, "total": 10}})]
    )
    out = wv.with_sync_history({"a": 1}, ctx, limit=10)
    assert out["a"] == 1
    assert len(out["sync_history"]) == 1
    item = out["sync_history"][0]
    assert item["job_id"] == "job1"
    assert item["status"] == "running"
    assert item["phase"] == "scan"
    assert item["scanned"] == 5
    assert item["total"] == 10


def test_with_sync_history_error_redacts():
    ctx = _FakeCtx(rows=[], raise_error=True)
    out = wv.with_sync_history({"a": 1}, ctx, limit=10)
    assert out["sync_history"] == []
    assert "sync_history_error" in out


def test_with_sync_history_filters_non_dict_rows():
    ctx = _FakeCtx(rows=[("job1", "not-a-dict")])
    out = wv.with_sync_history({}, ctx, limit=10)
    assert out["sync_history"] == []


def test_sync_history_item_field_mapping():
    ctx = _FakeCtx(progress={})
    row = {"progress": {"updated_at_ms": 1234, "status": "done", "phase": "complete", "scanned": 3, "total_count": 8}, "result": {"added": 2}, "error": "boom"}
    item = wv.sync_history_item("j1", row, ctx)
    assert item["task_id"] == "j1"
    assert item["status"] == "done"
    assert item["phase"] == "complete"
    assert item["updated_at_ms"] == 1234
    assert item["added"] == 2
    assert item["status_message"] == "boom"
    assert item["context_only"] is False


def test_sync_history_item_updated_at_ms_from_updated_at():
    ctx = _FakeCtx(progress={})
    item = wv.sync_history_item("j1", {"updated_at": 1.5, "status": "x"}, ctx)
    assert item["updated_at_ms"] == 1500


def test_with_official_context_cache():
    ctx = _FakeCtx(counts={"fields_count": 3, "operators_count": 2, "datasets_count": 1})
    out = wv.with_official_context_cache({"a": 1}, ctx)
    cache = out["official_context_cache"]
    assert cache["ok"] is True
    assert cache["fields_count"] == 3
    assert cache["operators_count"] == 2
    assert cache["datasets_count"] == 1


def test_with_official_context_cache_manifest():
    counts = {
        "fields_count": 1,
        "context_cache_manifest": {
            "complete": False,
            "is_stale": True,
            "missing_files": ["a"],
            "expired_files": ["b"],
            "invalid_files": ["c"],
            "record_counts": {"x": 5},
        },
    }
    out = wv.with_official_context_cache({"a": 1}, _FakeCtx(counts=counts))
    cache = out["official_context_cache"]
    assert cache["manifest"]["complete"] is False
    assert cache["manifest"]["is_stale"] is True
    assert cache["manifest"]["missing_files"] == ["a"]
    assert cache["manifest"]["stale_files"] == ["b"]
    assert cache["manifest"]["record_counts"] == {"x": 5}


def test_with_official_context_cache_error():
    out = wv.with_official_context_cache({"a": 1}, _FakeCtx(raise_error=True))
    assert out["official_context_cache"]["ok"] is False
    assert "error" in out["official_context_cache"]


def test__first_int_and_value_helpers():
    assert wv._first_int({"a": 5}, {}, "a") == 5
    assert wv._first_int({"a": 0}, {"a": 7}, "a") == 7
    assert wv._first_int({}, {}, "a", "b") == 0
    assert wv._first_int("not-dict", {}, "a") == 0
    assert wv._int_value("12") == 12
    assert wv._int_value("abc") == 0
    assert wv._int_value(-3) == 0
    assert wv._float_value("2.5") == 2.5
    assert wv._float_value("abc") == 0.0
    assert wv._float_value(-1) == 0.0


# ═══════════════════════ SQLite index web helpers ═══════════════════════

def test_sqlite_index_snapshot_error_uses_web_error():
    def load_config():
        raise RuntimeError("config boom")

    out = wv.sqlite_index_snapshot(load_config=load_config)
    assert out["ok"] is False
    assert out["error_code"] == "SQLITE_INDEX_SNAPSHOT_ERROR"


def test_sqlite_expression_lookup_payload_error():
    def load_config():
        raise RuntimeError("lookup boom")

    out = wv.sqlite_expression_lookup_payload(expression="x", load_config=load_config)
    assert out["error_code"] == "SQLITE_EXPRESSION_LOOKUP_ERROR"


def test_sqlite_record_lookup_payload_error():
    def load_config():
        raise RuntimeError("rec boom")

    out = wv.sqlite_record_lookup_payload(alpha_id="A1", load_config=load_config)
    assert out["error_code"] == "SQLITE_RECORD_LOOKUP_ERROR"