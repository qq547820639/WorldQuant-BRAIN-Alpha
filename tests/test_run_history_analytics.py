import json

from brain_alpha_ops.ux.history import RunHistoryAnalytics


def _write_run(path, run_id, *, best_score, candidates, ready, submitted, completed_at="2026-05-22T00:01:00+00:00"):
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "started_at": "2026-05-22T00:00:00+00:00",
                "completed_at": completed_at,
                "status": "completed",
                "phases": [{"status": "completed"}, {"status": "failed"}],
                "summary": {
                    "total_candidates": candidates,
                    "submission_ready": ready,
                    "auto_submitted": submitted,
                    "best_score": best_score,
                    "officially_simulated": ready,
                    "official_validation_attempted": candidates,
                    "official_validation_passed": ready,
                },
                "parameter_audit": {
                    "schema_version": "parameter_audit_snapshot.v1",
                    "ok": True,
                    "config_hash": "abc123",
                    "traceable_sections": ["ops.settings", "ops.thresholds"],
                    "thresholds_zero_deviation": True,
                    "api_paths_aligned": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_run_history_analytics_compares_latest_with_previous(tmp_path):
    history_dir = tmp_path / "run_history"
    history_dir.mkdir()
    older = history_dir / "run_old.json"
    newer = history_dir / "run_new.json"
    _write_run(older, "run_old", best_score=71.5, candidates=4, ready=1, submitted=0, completed_at="2026-05-22T00:01:00+00:00")
    _write_run(newer, "run_new", best_score=82.0, candidates=6, ready=3, submitted=1, completed_at="2026-05-22T00:02:00+00:00")

    analytics = RunHistoryAnalytics(str(tmp_path)).analytics(limit=10)

    assert analytics["schema_version"] == "run_history_analytics.v1"
    assert analytics["history_count"] == 2
    assert analytics["latest"]["run_id"] == "run_new"
    assert analytics["latest_comparison"]["deltas"]["best_score"] == 10.5
    assert analytics["latest_comparison"]["deltas"]["submission_ready"] == 2
    assert analytics["latest_comparison"]["better_than_right"]["best_score"] is True
    assert analytics["trend"]["status"] == "ready"
    assert analytics["latest"]["parameter_audit"]["schema_version"] == "parameter_audit_snapshot.v1"
    assert analytics["latest"]["parameter_audit"]["thresholds_zero_deviation"] is True


def test_run_history_analytics_loads_specific_comparison(tmp_path):
    history_dir = tmp_path / "run_history"
    history_dir.mkdir()
    _write_run(history_dir / "run_a.json", "run_a", best_score=70, candidates=3, ready=1, submitted=0)
    _write_run(history_dir / "run_b.json", "run_b", best_score=68, candidates=3, ready=0, submitted=0)

    comparison = RunHistoryAnalytics(str(tmp_path)).compare("run_a", "run_b")

    assert comparison["ok"] is True
    assert comparison["deltas"]["best_score"] == 2
    assert comparison["better_than_right"]["submission_ready"] is True
    assert comparison["comparison"]["left_run_id"] == "run_a"
