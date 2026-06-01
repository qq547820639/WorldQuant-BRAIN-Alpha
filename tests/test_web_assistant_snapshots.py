from __future__ import annotations

import json
import logging
from pathlib import Path

from brain_alpha_ops.web_assistant_snapshots import (
    assistant_response_guidance_payload,
    durable_job_rows,
    latest_result_snapshot,
    latest_run_history_path,
    prompt_run_ledger_snapshot,
    research_knowledge_snapshot,
)


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def all(self, *, limit):
        return self.rows[-limit:]


class _FailingStore:
    def all(self, *, limit):
        raise RuntimeError("store unavailable")


class _EmptyJobStore:
    def latest_any(self):
        return None


def test_durable_job_rows_merges_available_stores_and_warns_on_failures(caplog):
    with caplog.at_level(logging.WARNING):
        rows = durable_job_rows(
            stores=[
                ("production_job", _Store([("job_1", {"status": "completed"})])),
                ("sync_job", _FailingStore()),
                ("check_job", _Store([("job_2", {"status": "running"})])),
            ],
            limit=10,
        )

    assert rows == [
        {"source": "production_job", "job_id": "job_1", "status": "completed"},
        {"source": "check_job", "job_id": "job_2", "status": "running"},
    ]
    assert "durable job rows unavailable for source=sync_job" in caplog.text


def test_latest_result_snapshot_restores_run_history(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {"candidates": [{"alpha_id": "a1"}], "produced_count": 1},
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    assert snapshot["source"] == "run_history"
    assert snapshot["job_id"] == "run_1"
    assert snapshot["progress"]["phase_label"] == "最近结果"
    assert snapshot["result"]["candidates"] == [{"alpha_id": "a1"}]


def test_latest_run_history_path_warns_when_history_dir_unreadable(monkeypatch, tmp_path, caplog):
    storage = tmp_path / "data"
    history_dir = storage / "run_history"
    config = type("Config", (), {"ops": type("Ops", (), {"storage_dir": str(storage)})()})()
    original_glob = Path.glob

    def fail_glob(self, pattern):
        if self == history_dir:
            raise OSError("permission denied")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fail_glob)

    with caplog.at_level(logging.WARNING):
        result = latest_run_history_path(load_config=lambda: config)

    assert result is None
    assert "failed to list run history files from" in caplog.text


def test_assistant_response_guidance_payload_uses_bounded_min_confidence():
    payload = assistant_response_guidance_payload(
        {
            "text": (
                '{"summary":"Favor price momentum.",'
                '"candidate_adjustments":[{"target":"fields","value":["close"]}],'
                '"confidence":0.7}'
            ),
            "min_confidence": 0.8,
        }
    )

    assert payload["ok"] is True
    assert payload["usable"] is False
    assert payload["top_fields"] == ["close"]


def test_research_knowledge_snapshot_reads_summary(tmp_path):
    storage = tmp_path / "data"
    config = type("Config", (), {"ops": type("Ops", (), {"storage_dir": str(storage)})()})()
    result = research_knowledge_snapshot(
        limit=5,
        min_confidence=0.6,
        load_config=lambda: config,
    )
    assert result["ok"] is True
    assert result["schema_version"] == "research_knowledge_summary.v1"
    assert result["count"] == 0


def test_prompt_run_ledger_snapshot_redacts_raw_prompt_and_response(tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    (storage / "prompt_runs.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "prompt_run_ledger.v1",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "prompt_digest": "prompt_1",
                        "context_digest": "context_1",
                        "model": "reviewer",
                        "temperature": 0.1,
                        "response_digest": "response_1",
                        "parse_status": "ok",
                        "prompt": "raw prompt must not leak",
                        "response_text": "raw response must not leak",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    config = type("Config", (), {"ops": type("Ops", (), {"storage_dir": str(storage)})()})()

    snapshot = prompt_run_ledger_snapshot(limit=10, load_config=lambda: config)

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "prompt_run_ledger_snapshot.v1"
    assert snapshot["count"] == 1
    assert snapshot["items"][0]["prompt_digest"] == "prompt_1"
    assert snapshot["items"][0]["response_digest"] == "response_1"
    assert "prompt" not in snapshot["items"][0]
    assert "response_text" not in snapshot["items"][0]
