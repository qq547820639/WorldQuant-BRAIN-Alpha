"""Tests for assistant / snapshot facade / run-history payload builders."""

import json
from pathlib import Path

import pytest

from brain_alpha_ops.web.misc import web_assistant_snapshots as was


def test__bounded_float():
    assert was._bounded_float(5, 0, 10) == 5.0
    assert was._bounded_float(-1, 0, 10) == 0.0
    assert was._bounded_float(99, 0, 10) == 10.0
    assert was._bounded_float("abc", 2, 10) == 2.0
    assert was._bounded_float(None, 3, 10) == 3.0


def test__payload_truthy():
    assert was._payload_truthy(True) is True
    assert was._payload_truthy("yes") is True
    assert was._payload_truthy(1) is True
    assert was._payload_truthy(False) is False
    assert was._payload_truthy("false") is False
    assert was._payload_truthy("False") is False
    assert was._payload_truthy("0") is False
    assert was._payload_truthy(0) is False
    assert was._payload_truthy(None) is False


def test_prompt_run_ledger_snapshot_public_row():
    row = {
        "schema_version": "v1",
        "timestamp": "t",
        "prompt_digest": "p",
        "model": "m",
        "secret": "should-not-leak",
    }
    out = was._prompt_run_public_row(row)
    assert out["schema_version"] == "v1"
    assert "secret" not in out


def test_prompt_run_ledger_snapshot_ok(tmp_path):
    def load_config():
        return _FakeConfig(tmp_path)

    def read_jsonl_tail(path, limit=None):
        return [
            {"schema_version": "v1", "timestamp": "t1", "model": "m"},
            {"schema_version": "v1", "timestamp": "t2", "model": "m2"},
        ]

    out = was.prompt_run_ledger_snapshot(
        load_config=load_config,
        read_jsonl_tail_func=read_jsonl_tail,
    )
    assert out["ok"] is True
    assert out["source"] == "prompt_runs_jsonl"
    assert out["count"] == 2
    assert out["items"][0]["timestamp"] == "t2"


def test_prompt_run_ledger_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.prompt_run_ledger_snapshot(load_config=load_config)
    assert out["ok"] is False
    assert out["error_code"] == "PROMPT_RUN_LEDGER_ERROR"


def test_research_memory_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.research_memory_snapshot(load_config=load_config)
    assert out["error_code"] == "RESEARCH_MEMORY_ERROR"


def test_research_knowledge_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.research_knowledge_snapshot(load_config=load_config)
    assert out["error_code"] == "RESEARCH_KNOWLEDGE_ERROR"


def test_research_observability_snapshot_uses_builder():
    captured = {}

    def load_config():
        return _FakeConfig(Path("/tmp/x"))

    def observability_builder(storage_dir, **kwargs):
        captured["storage_dir"] = storage_dir
        captured["kwargs"] = kwargs
        return {"ok": True, "built": True}

    out = was.research_observability_snapshot(
        limit=10,
        top_n=3,
        include_cloud=False,
        load_config=load_config,
        durable_job_rows=lambda limit=1000: [{"source": "s", "job_id": "j"}],
        observability_builder=observability_builder,
    )
    assert out["ok"] is True
    assert captured["kwargs"]["limit"] == 10
    assert captured["kwargs"]["top_n"] == 3
    assert captured["kwargs"]["include_cloud"] is False


def test_research_observability_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.research_observability_snapshot(load_config=load_config)
    assert out["error_code"] == "RESEARCH_OBSERVABILITY_ERROR"


def test_durable_job_rows():
    class Store:
        def all(self, limit=None):
            return [("j1", {"status": "ok"}), ("j2", {"status": "done"})]

    class BadStore:
        pass

    class RaisingStore:
        def all(self, limit=None):
            raise RuntimeError("nope")

    rows = was.durable_job_rows(
        stores=[("a", Store()), ("b", BadStore()), ("c", RaisingStore())],
        limit=10,
    )
    assert len(rows) == 2
    assert rows[0]["source"] == "a"
    assert rows[0]["job_id"] == "j1"


def test_latest_run_history_path_no_files(tmp_path):
    def load_config():
        return _FakeConfig(tmp_path)

    assert was.latest_run_history_path(load_config=load_config) is None


def test_latest_run_history_path_picks_latest(tmp_path):
    history = tmp_path / "run_history"
    history.mkdir(parents=True)
    (history / "old.json").write_text("{}")
    (history / "new.json").write_text("{}")

    def load_config():
        return _FakeConfig(tmp_path)

    result = was.latest_run_history_path(load_config=load_config)
    assert result is not None
    assert result.name == "new.json"


def test_user_profile_snapshot_offline_no_file(tmp_path):
    class JobStore:
        def latest_active(self):
            return None

    out = was.user_profile_snapshot(
        job_store=JobStore(),
        storage_jsonl_path=lambda name: tmp_path / name,
    )
    assert out["tier"] == "offline"
    assert out["username"] == ""


def test_user_profile_snapshot_offline_reads_file(tmp_path):
    p = tmp_path / "user_profile.json"
    p.write_text(json.dumps({"tier": "free", "username": "alice"}))

    class JobStore:
        def latest_active(self):
            return None

    out = was.user_profile_snapshot(
        job_store=JobStore(),
        storage_jsonl_path=lambda name: tmp_path / name,
    )
    assert out["username"] == "alice"


def test_user_profile_snapshot_offline_corrupt_file(tmp_path):
    p = tmp_path / "user_profile.json"
    p.write_text("{not json")

    class JobStore:
        def latest_active(self):
            return None

    out = was.user_profile_snapshot(
        job_store=JobStore(),
        storage_jsonl_path=lambda name: tmp_path / name,
    )
    assert out["tier"] == "offline"


def test_user_profile_snapshot_active_job():
    class JobStore:
        def latest_active(self):
            return ("job1", {"progress": {"data": {"user_profile": {"tier": "pro", "level": 3}}}})

    out = was.user_profile_snapshot(
        job_store=JobStore(),
        storage_jsonl_path=lambda name: Path(name),
    )
    assert out["tier"] == "pro"


def test_user_profile_snapshot_active_job_from_summary():
    class JobStore:
        def latest_active(self):
            return ("job1", {"result": {"summary": {"user_profile": {"tier": "loading"}}}})

    out = was.user_profile_snapshot(
        job_store=JobStore(),
        storage_jsonl_path=lambda name: Path(name),
    )
    assert out["tier"] == "loading"


def test_latest_result_snapshot_from_job_store():
    class JobStore:
        def latest_any(self):
            return ("jobX", {"status": "running", "progress": {"phase": "go"}})

    out = was.latest_result_snapshot(
        job_store=JobStore(),
        latest_run_history_path=lambda: None,
        enrich_progress=lambda d: {**d, "enriched": True},
    )
    assert out["ok"] is True
    assert out["source"] == "job_store"
    assert out["job_id"] == "jobX"
    assert out["progress"]["enriched"] is True


def test_latest_result_snapshot_empty():
    class JobStore:
        def latest_any(self):
            return None

    out = was.latest_result_snapshot(
        job_store=JobStore(),
        latest_run_history_path=lambda: None,
        enrich_progress=lambda d: d,
    )
    assert out["source"] == "empty"
    assert out["status"] == "idle"


def test_latest_result_snapshot_run_history(tmp_path):
    p = tmp_path / "run_1.json"
    p.write_text(json.dumps({"status": "completed", "run_id": "r1", "summary": {"candidates": [{"alpha_id": "A1"}]}}))

    class JobStore:
        def latest_any(self):
            return None

    out = was.latest_result_snapshot(
        job_store=JobStore(),
        latest_run_history_path=lambda: p,
        enrich_progress=lambda d: d,
    )
    assert out["source"] == "run_history"
    assert out["job_id"] == "r1"
    assert out["status"] == "completed"
    assert out["result"]["candidates"][0]["alpha_id"] == "A1"


def test_latest_result_snapshot_run_history_read_error(tmp_path):
    p = tmp_path / "run_1.json"
    p.write_text("{bad")

    class JobStore:
        def latest_any(self):
            return None

    out = was.latest_result_snapshot(
        job_store=JobStore(),
        latest_run_history_path=lambda: p,
        enrich_progress=lambda d: d,
    )
    assert out["source"] == "run_history"
    assert out["ok"] is False


def test_run_history_replay_audit_basic():
    path = Path("x.json")
    candidates = [{"alpha_id": "A1", "production_decision": {"action": "archive", "reason_codes": ["risk"]}}]
    payload = {"candidates": candidates, "pool_summary": {"decision_action_counts": {"archive": 1}}}
    audit = was._run_history_replay_audit(
        payload=payload,
        payload_rows=[{"alpha_id": "A1"}],
        lifecycle_rows=[],
        raw_candidate_count=1,
        total_candidate_count=1,
        path=path,
    )
    assert audit["schema_version"] == "run-history-replay-audit-v1"
    assert audit["official_api_called"] is False
    assert audit["real_submit_performed"] is False
    assert audit["submit_allowed"] is False
    assert audit["production_decision_counts"] == {"archive": 1}
    assert audit["readiness_blocker_counts"] == {"risk": 1}


def test_run_history_replay_audit_fallback_counts():
    candidates = [
        {"alpha_id": "A1", "production_decision": {"action": "keep", "reason_codes": ["ok", "ok"]}},
    ]
    audit = was._run_history_replay_audit(
        payload={"candidates": candidates},
        payload_rows=[],
        lifecycle_rows=[],
        raw_candidate_count=1,
        total_candidate_count=1,
        path=Path("x"),
    )
    assert audit["production_decision_counts"] == {"keep": 1}
    assert audit["readiness_blocker_counts"] == {"ok": 2}


def test_run_history_workflow_queue_counts():
    workflow = {
        "producer": {"candidate_count": 5},
        "validator": {"candidate_count": 2},
        "rework": {},
        "review": {"candidate_count": "bad"},
        "archive": {"candidate_count": 1},
    }
    counts = was._run_history_workflow_queue_counts(workflow)
    assert counts["producer"] == 5
    assert counts["validator"] == 2
    assert counts["rework"] == 0
    assert counts["review"] == 0
    assert counts["archive"] == 1


def test_run_history_workflow_queue_counts_producer_deficit():
    counts = was._run_history_workflow_queue_counts({"producer": {"deficit": 3}})
    assert counts["producer"] == 3


def test_run_history_candidate_keys_and_digest():
    row = {"alpha_id": "A1", "expression": "Rank(Close) "}
    keys = was._run_history_candidate_keys(row)
    assert "A1" in keys
    assert any(k.startswith("expression:") for k in keys)
    assert any(k.startswith("expr_") for k in keys)
    assert was._run_history_expression_digest("close") == "expr_" + __import__("hashlib").sha256(b"close").hexdigest()[:12]
    assert was._run_history_expression_digest("") == ""


def test_run_history_matching_lifecycle_count():
    candidates = [{"alpha_id": "A1"}]
    lifecycle = [{"alpha_id": "A1"}, {"alpha_id": "B2"}]
    assert was._run_history_matching_lifecycle_count(candidates, lifecycle) == 1
    assert was._run_history_matching_lifecycle_count([{}], lifecycle) == 0


def test_assistant_guidance_history_basic():
    rows = [
        {
            "guidance": {
                "confidence": 0.9,
                "ok": True,
                "usable": True,
                "top_fields": ["close"],
                "summary": "s",
            },
            "timestamp": "t1",
        },
        {"guidance": {"confidence": 0.2, "usable": False}, "timestamp": "t2"},
    ]
    items = was.assistant_guidance_history(rows, min_confidence=0.5)
    assert len(items) == 2
    assert items[1]["history_index"] == 0
    assert items[1]["usable"] is True
    assert items[1]["meets_min_confidence"] is True
    assert items[1]["has_generator_bias"] is True
    assert items[0]["usable"] is False


def test_assistant_guidance_history_skips_non_dict():
    assert was.assistant_guidance_history([42, "x"], min_confidence=0.5) == []


def test_assistant_guidance_history_digest_from_row():
    rows = [{"guidance_digest": "abc", "guidance": {"confidence": 1.0}}]
    items = was.assistant_guidance_history(rows, min_confidence=0.0)
    assert items[0]["guidance_digest"] == "abc"


def test_assistant_response_parse_payload_empty():
    with pytest.raises(Exception, match="assistant response is empty"):
        was.assistant_response_parse_payload({})
    with pytest.raises(Exception, match="assistant response is empty"):
        was.assistant_response_parse_payload(None)


def test_assistant_response_guidance_payload_empty():
    with pytest.raises(Exception, match="assistant response is empty"):
        was.assistant_response_guidance_payload({})


def test_assistant_guidance_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.assistant_guidance_snapshot(load_config=load_config)
    assert out["error_code"] == "ASSISTANT_GUIDANCE_ERROR"


def test_assistant_context_snapshot_error():
    def load_config():
        raise RuntimeError("boom")

    out = was.assistant_context_snapshot(
        load_config=load_config,
        latest_result_snapshot=lambda: {},
        cloud_alpha_snapshot=lambda: {},
    )
    assert out["error_code"] == "ASSISTANT_CONTEXT_ERROR"


def test_assistant_request_snapshot_error():
    def assistant_context_snapshot(**kwargs):
        raise RuntimeError("boom")

    out = was.assistant_request_snapshot(assistant_context_snapshot=assistant_context_snapshot)
    assert out["error_code"] == "ASSISTANT_REQUEST_ERROR"


def test_assistant_request_snapshot_returns_error_context():
    def assistant_context_snapshot(**kwargs):
        return {"ok": False, "error_code": "X"}

    out = was.assistant_request_snapshot(assistant_context_snapshot=assistant_context_snapshot)
    assert out["ok"] is False


def test_default_web_error():
    out = was._default_web_error(ValueError("leak secret value"), "CODE")
    assert out["ok"] is False
    assert out["error_code"] == "CODE"


class _FakeBudget:
    assistant_guidance_min_confidence = 0.6
    use_assistant_guidance = True


class _FakeOps:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.budget = _FakeBudget()
        self.scoring = {}


class _FakeConfig:
    def __init__(self, storage_dir):
        self.ops = _FakeOps(storage_dir)