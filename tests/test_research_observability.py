from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research import expression_index as expression_index_module
from brain_alpha_ops.research.observability import (
    actionable_duplicate_expression_buckets,
    actionable_duplicate_expression_records,
    build_research_observability_snapshot,
    diagnose_research_health,
    observability_context,
)
from brain_alpha_ops.research.repository import ResearchRepository


def test_research_observability_snapshot_summarizes_local_health(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            scorecard={"total_score": 88},
        ),
    )
    repo.save_backtest_record(
        "run_1",
        {
            "action": "simulation_result",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "simulation_failed",
            "expression": " rank ( ts_delta ( close , 20 ) ) ",
            "note": "rate limit retry pending",
        },
    )
    repo.save_check_record({"alpha_id": "a1", "expression": "rank(ts_delta(close, 20))", "error": "Too many requests"})

    snapshot = build_research_observability_snapshot(tmp_path, limit=100, top_n=5, include_cloud=False)
    context = observability_context(snapshot, top_n=3)

    assert snapshot["ok"] is True
    assert snapshot["expression_index"]["duplicate_expression_count"] == 1
    assert snapshot["backtests"]["failed_count"] == 1
    assert snapshot["errors"]["category_counts"]["rate_limit"] == 2
    assert snapshot["health"]["risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in snapshot["health"]["health_flags"]
    assert "retryable_official_errors_present" in snapshot["health"]["warning_flags"]
    assert context["duplicate_expression_count"] == 1
    assert context["retryable_error_count"] == 2
    assert context["risk_level"] == snapshot["health"]["risk_level"]
    assert "duplicate_expression_history" in context["health_flags"]
    assert context["recommended_actions"]


def test_research_observability_snapshot_summarizes_official_call_guard(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    expression = "rank(ts_delta(close, 20))"
    repo.save_lifecycle_record(
        "run_1",
        {
            "timestamp": 1,
            "alpha_id": "a1",
            "stage": "observability_duplicate_blocked",
            "status": "observability_duplicate_blocked",
            "note": "official_validation",
            "family": "Momentum",
            "score": 91,
            "expression": expression,
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_validation"],
            },
        },
    )
    repo.save_lifecycle_record(
        "run_1",
        {
            "timestamp": 2,
            "alpha_id": "a2",
            "stage": "observability_duplicate_blocked",
            "status": "observability_duplicate_blocked",
            "note": "official_simulation",
            "family": "Momentum",
            "score": 88,
            "expression": expression,
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_simulation"],
            },
        },
    )

    snapshot = build_research_observability_snapshot(tmp_path, limit=100, top_n=5, include_cloud=False)
    context = observability_context(snapshot, top_n=3)

    guard = snapshot["official_call_guard"]
    assert guard["blocked_count"] == 2
    assert guard["validation_blocked_count"] == 1
    assert guard["simulation_blocked_count"] == 1
    assert guard["phase_counts"]["official_validation"] == 1
    assert guard["recent_blocks"][-1]["alpha_id"] == "a2"
    assert context["official_guard_blocked_count"] == 2


def test_actionable_duplicate_helpers_ignore_single_alpha_lifecycle_noise():
    expression = "rank(ts_delta(close, 20))"
    same_alpha_lifecycle_bucket = {
        "expression_canonical": expression,
        "source_count": 1,
        "sources": {"lifecycle": 2},
        "alpha_ids": ["a1"],
    }
    cross_source_bucket = {
        "expression_canonical": expression,
        "source_count": 2,
        "sources": {"candidate": 1, "backtest": 1},
        "alpha_ids": ["a1"],
    }
    same_alpha_records = [
        {"source": "lifecycle", "alpha_id": "a1", "expression": expression},
        {"source": "lifecycle", "alpha_id": "a1", "expression": expression},
    ]
    cross_source_records = [
        {"source": "candidate", "alpha_id": "a1", "expression": expression},
        {"source": "backtest", "alpha_id": "a1", "expression": expression},
    ]

    assert actionable_duplicate_expression_buckets([same_alpha_lifecycle_bucket]) == []
    assert actionable_duplicate_expression_buckets([cross_source_bucket]) == [cross_source_bucket]
    assert actionable_duplicate_expression_records(same_alpha_records, expression) == []
    assert len(actionable_duplicate_expression_records(cross_source_records, expression)) == 2


def test_research_observability_snapshot_degrades_when_expression_index_fails(monkeypatch, tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record(
        "run_1",
        {
            "action": "simulation_result",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "simulation_failed",
            "expression": "rank(ts_delta(close, 20))",
            "note": "rate limit retry pending",
        },
    )

    def fail_summary(self, **kwargs):
        raise RuntimeError("expression index parser unavailable")

    monkeypatch.setattr(
        "brain_alpha_ops.research.expression_index.ExpressionHistoryIndex.summary",
        fail_summary,
    )

    snapshot = build_research_observability_snapshot(tmp_path, limit=100, top_n=5, include_cloud=False)
    context = observability_context(snapshot, top_n=3)

    assert snapshot["ok"] is True
    assert snapshot["expression_index"]["ok"] is False
    assert "expression index parser unavailable" in snapshot["expression_index"]["error"]
    assert snapshot["backtests"]["failed_count"] == 1
    assert snapshot["partial_errors"][0]["component"] == "expression_index"
    assert "expression_index_unavailable" in snapshot["health"]["health_flags"]
    assert "expression_index_unavailable" in context["health_flags"]
    assert snapshot["recommendations"]


def test_research_observability_snapshot_reuses_jsonl_reads_for_expression_index(monkeypatch, tmp_path):
    repo = ResearchRepository(str(tmp_path))
    expression = "rank(ts_delta(close, 20))"
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression=expression,
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
        ),
    )
    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "a2",
            "status": "SUBMITTED",
            "expression": expression,
        },
    )
    loaded_files: list[str] = []
    original_load_jsonl = expression_index_module._load_jsonl

    def spy_load_jsonl(path, *, limit):
        loaded_files.append(path.name)
        return original_load_jsonl(path, limit=limit)

    monkeypatch.setattr(expression_index_module, "_load_jsonl", spy_load_jsonl)

    snapshot = build_research_observability_snapshot(tmp_path, limit=100, top_n=5, include_cloud=False)

    assert snapshot["expression_index"]["duplicate_expression_count"] == 1
    assert "candidates.jsonl" not in loaded_files
    assert "backtests.jsonl" not in loaded_files
    assert "lifecycle.jsonl" not in loaded_files
    assert "checks.jsonl" not in loaded_files


def test_research_health_diagnostics_flags_blocking_rate_limit_pressure():
    health = diagnose_research_health(
        expression_payload={
            "total_expression_records": 12,
            "unique_expression_count": 8,
            "duplicate_expression_count": 3,
            "duplicate_ratio": 0.375,
        },
        backtests={
            "total": 8,
            "failed_count": 5,
            "failure_rate": 0.625,
            "retryable_count": 2,
        },
        errors={
            "total": 6,
            "retryable_count": 4,
            "retryable_rate": 0.667,
            "category_counts": {"rate_limit": 4},
        },
        jsonl={},
        sqlite_cache={"exists": True, "error": ""},
    )

    assert health["risk_level"] == "blocked"
    assert "high_duplicate_expression_ratio" in health["health_flags"]
    assert "backtest_failure_rate_elevated" in health["blocking_flags"]
    assert "rate_limit_pressure" in health["blocking_flags"]
    assert health["flag_details"]["rate_limit_pressure"]["evidence"]["rate_limit_count"] == 4
