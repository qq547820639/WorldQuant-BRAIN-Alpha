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


def _run_history_candidate(
    alpha_id: str,
    expression: str,
    score: float,
    *,
    decision_band: str = "optimize_before_submit",
) -> dict:
    return {
        "alpha_id": alpha_id,
        "expression": expression,
        "family": "demo",
        "hypothesis": "latest result recovery test",
        "lifecycle_status": "candidate_pool_retained",
        "scorecard": {
            "total_score": score,
            "decision_band": decision_band,
        },
        "quality_diagnosis": {
            "local_candidate_valid": True,
            "submission_ready": False,
            "blocking_reasons": ["missing_official_metrics"],
            "reasons": [
                {
                    "code": "missing_official_metrics",
                    "category": "official_evidence_missing",
                    "severity": "blocking",
                }
            ],
        },
        "local_quality": {"passed": True},
    }


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
    assert snapshot["result"]["candidates"][0]["alpha_id"] == "a1"
    decision = snapshot["result"]["candidates"][0]["production_decision"]
    assert decision["official_api_called"] is False


def test_latest_result_snapshot_enriches_run_history_candidates_like_candidate_payload(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [_run_history_candidate("opt", "rank(close)", 78)],
                    "produced_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    result = snapshot["result"]
    candidate = result["candidates"][0]
    assert snapshot["source"] == "run_history"
    assert candidate["production_decision"]["action"] == "optimize"
    assert candidate["quality_diagnosis"]["production_decision"] == candidate["production_decision"]
    assert result["pool_summary"]["decision_action_counts"]["optimize"] == 1
    assert result["scientific_audit"]["candidate_count"] == 1
    assert result["workflow_plan"]["official_api_called"] is False
    assert result["workflow_plan"]["submit_allowed"] is False
    assert result["candidate_workflow"] == result["workflow_plan"]


def test_latest_result_snapshot_adds_local_replay_audit_summary(tmp_path):
    audited = _run_history_candidate(
        "queue",
        "rank(close)",
        92,
        decision_band="submit_candidate",
    )
    audited["scientific_audit"] = {
        "schema_version": "candidate-scientific-audit-v1",
        "operation": "candidate_generation",
        "source": "web_candidate_generation",
        "safety_boundary": {
            "local_only": True,
            "official_api_called": False,
            "submit_allowed": False,
            "real_submit_performed": False,
        },
        "anti_overfit": {
            "test_script_outcomes_used": False,
            "test_feedback_allowed": False,
        },
        "evidence": {"feedback_sources": ["local_scorecard"]},
    }
    rework = _run_history_candidate("rework", "rank(open)", 81)
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [audited, rework],
                    "produced_count": 7,
                    "total_candidates": 7,
                },
            }
        ),
        encoding="utf-8",
    )
    lifecycle_rows = [
        {
            "alpha_id": "rework",
            "stage": "official_validation",
            "status": "FAILED",
            "timestamp": "2026-06-12T01:00:00Z",
        },
        {
            "alpha_id": "unrelated",
            "stage": "official_validation",
            "status": "FAILED",
            "timestamp": "2026-06-12T01:00:00Z",
        },
    ]

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
        read_storage_jsonl=(
            lambda filename, **_kwargs: lifecycle_rows
            if filename == "lifecycle.jsonl"
            else []
        ),
    )

    audit = snapshot["result"]["replay_audit"]
    assert audit["schema_version"] == "run-history-replay-audit-v1"
    assert audit["local_only"] is True
    assert audit["official_api_called"] is False
    assert audit["submit_allowed"] is False
    assert audit["real_submit_performed"] is False
    assert audit["raw_candidate_row_count"] == 2
    assert audit["payload_candidate_row_count"] == 2
    assert audit["recovered_candidate_count"] == 2
    assert audit["total_candidate_count"] == 7
    assert audit["lifecycle_row_count"] == 2
    assert audit["lifecycle_rows_used_count"] == 1
    assert audit["candidates_with_production_decision"] == 2
    assert audit["production_decision_counts"]["official_validation_queue"] == 1
    assert audit["production_decision_counts"]["optimize"] == 1
    assert audit["scientific_audit_summary_available"] is True
    assert audit["candidates_with_scientific_audit"] == 2
    assert audit["candidates_missing_scientific_audit"] == 0
    assert audit["scientific_submit_boundary_intact"] is True
    assert audit["workflow_plan_available"] is True
    assert audit["workflow_queue_counts"]["validator"] == 1
    assert audit["workflow_queue_counts"]["rework"] == 1
    assert audit["readiness_blocker_counts"]["missing_official_metrics"] == 1
    assert audit["readiness_blocker_counts"]["lifecycle_history_failed"] == 1
    assert audit["execution_gap_counts"]["pool_deficit"] == 9
    assert audit["stop_rule"] == "scripts/check_live_submit_readiness.py"
    assert audit["submit_boundary_intact"] is True


def test_latest_result_snapshot_preserves_run_history_produced_total(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [_run_history_candidate("retained", "rank(close)", 82)],
                    "produced_count": 25,
                    "total_candidates": 25,
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    result = snapshot["result"]
    assert result["count"] == 1
    assert result["candidate_count"] == 25
    assert result["total_count"] == 25
    assert result["total"] == 25


def test_latest_result_snapshot_adds_empty_replay_audit_for_non_candidate_history(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {"candidates": [{"note": "no alpha identity"}], "produced_count": 3},
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    audit = snapshot["result"]["replay_audit"]
    assert audit["schema_version"] == "run-history-replay-audit-v1"
    assert audit["raw_candidate_row_count"] == 1
    assert audit["recovered_candidate_count"] == 0
    assert audit["total_candidate_count"] == 3
    assert audit["workflow_plan_available"] is False
    assert audit["submit_boundary_intact"] is True


def test_latest_result_snapshot_unwraps_candidate_rows_from_run_history(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [
                        {
                            "candidate": _run_history_candidate("wrapped", "rank(open)", 80),
                            "source": "legacy_wrapper",
                        }
                    ],
                    "produced_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    candidate = snapshot["result"]["candidates"][0]
    audit = snapshot["result"]["replay_audit"]
    assert candidate["alpha_id"] == "wrapped"
    assert candidate["production_decision"]["action"] == "optimize"
    assert "candidate" not in candidate
    assert audit["raw_candidate_row_count"] == 1
    assert audit["payload_candidate_row_count"] == 1
    assert audit["recovered_candidate_count"] == 1
    assert audit["lifecycle_row_count"] == 0
    assert audit["lifecycle_rows_used_count"] == 0
    assert audit["submit_boundary_intact"] is True


def test_latest_result_snapshot_uses_lifecycle_history_when_recovering_run_history(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [
                        _run_history_candidate(
                            "queue",
                            "rank(close)",
                            92,
                            decision_band="submit_candidate",
                        )
                    ],
                    "produced_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    lifecycle_rows = [
        {
            "alpha_id": "queue",
            "stage": "official_validation",
            "status": "FAILED",
            "timestamp": "2026-06-12T01:00:00Z",
        }
    ]

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
        read_storage_jsonl=(
            lambda filename, **_kwargs: lifecycle_rows
            if filename == "lifecycle.jsonl"
            else []
        ),
    )

    result = snapshot["result"]
    candidate = result["candidates"][0]
    decision = candidate["production_decision"]
    assert decision["action"] == "optimize"
    assert "lifecycle_history_failed" in decision["reason_codes"]
    assert decision["decision_evidence"]["lifecycle_risk"]["official_api_called"] is False
    assert decision["decision_evidence"]["lifecycle_risk"]["submit_allowed"] is False
    assert result["workflow_plan"]["validator"]["candidate_ids"] == []
    assert result["workflow_plan"]["rework"]["candidate_ids"] == ["queue"]
    assert result["replay_audit"]["lifecycle_row_count"] == 1
    assert result["replay_audit"]["lifecycle_rows_used_count"] == 1
    assert result["replay_audit"]["readiness_blocker_counts"]["lifecycle_history_failed"] == 1
    assert result["replay_audit"]["submit_boundary_intact"] is True


def test_latest_result_snapshot_replay_audit_counts_expression_lifecycle_match(tmp_path):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [
                        _run_history_candidate(
                            "expr_candidate",
                            "rank(volume)",
                            93,
                            decision_band="submit_candidate",
                        )
                    ],
                    "produced_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    lifecycle_rows = [
        {
            "expression": "rank(volume)",
            "stage": "local_prefilter_rejected",
            "status": "REJECTED",
            "timestamp": "2026-06-12T01:01:00Z",
        }
    ]

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
        read_storage_jsonl=(
            lambda filename, **_kwargs: lifecycle_rows
            if filename == "lifecycle.jsonl"
            else []
        ),
    )

    candidate = snapshot["result"]["candidates"][0]
    risk = candidate["production_decision"]["decision_evidence"]["lifecycle_risk"]
    audit = snapshot["result"]["replay_audit"]
    assert risk["matched_by"] == "expression"
    assert candidate["production_decision"]["action"] == "archive"
    assert audit["lifecycle_row_count"] == 1
    assert audit["lifecycle_rows_used_count"] == 1
    assert audit["production_decision_counts"]["archive"] == 1
    assert audit["readiness_blocker_counts"]["lifecycle_history_failed"] == 1
    assert audit["submit_boundary_intact"] is True


def test_latest_result_snapshot_recovers_when_lifecycle_history_read_fails(tmp_path, caplog):
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {
                    "candidates": [_run_history_candidate("safe", "rank(close)", 78)],
                    "produced_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    def fail_read_storage_jsonl(filename, **_kwargs):
        raise RuntimeError(f"{filename} unavailable")

    with caplog.at_level(logging.WARNING):
        snapshot = latest_result_snapshot(
            job_store=_EmptyJobStore(),
            latest_run_history_path=lambda: path,
            enrich_progress=lambda progress: progress,
            read_storage_jsonl=fail_read_storage_jsonl,
        )

    candidate = snapshot["result"]["candidates"][0]
    audit = snapshot["result"]["replay_audit"]
    assert snapshot["ok"] is True
    assert snapshot["source"] == "run_history"
    assert candidate["alpha_id"] == "safe"
    assert candidate["production_decision"]["official_api_called"] is False
    assert audit["raw_candidate_row_count"] == 1
    assert audit["payload_candidate_row_count"] == 1
    assert audit["recovered_candidate_count"] == 1
    assert audit["lifecycle_row_count"] == 0
    assert audit["lifecycle_rows_used_count"] == 0
    assert audit["submit_boundary_intact"] is True
    assert "run history lifecycle rows unavailable" in caplog.text


def test_latest_result_snapshot_replay_audit_reports_unsafe_scientific_audit(tmp_path):
    candidate = _run_history_candidate(
        "unsafe",
        "rank(close)",
        92,
        decision_band="submit_candidate",
    )
    candidate["scientific_audit"] = {
        "schema_version": "candidate-scientific-audit-v1",
        "operation": "candidate_generation",
        "source": "web_candidate_generation",
        "safety_boundary": {
            "local_only": True,
            "official_api_called": False,
            "submit_allowed": True,
            "real_submit_performed": False,
        },
        "anti_overfit": {
            "test_script_outcomes_used": False,
            "test_feedback_allowed": False,
        },
        "evidence": {"feedback_sources": ["local_scorecard"]},
    }
    path = tmp_path / "run_1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "status": "completed",
                "summary": {"candidates": [candidate], "produced_count": 1},
            }
        ),
        encoding="utf-8",
    )

    snapshot = latest_result_snapshot(
        job_store=_EmptyJobStore(),
        latest_run_history_path=lambda: path,
        enrich_progress=lambda progress: progress,
    )

    audit = snapshot["result"]["replay_audit"]
    decision = snapshot["result"]["candidates"][0]["production_decision"]
    assert audit["scientific_submit_boundary_intact"] is False
    assert audit["submit_boundary_intact"] is False
    assert audit["readiness_blocker_counts"]["scientific_audit_submit_boundary_breached"] == 1
    assert "scientific_audit_submit_boundary_breached" in decision["reason_codes"]
    assert decision["official_api_called"] is False
    assert decision["submit_allowed"] is False


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
