import json

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger


def _candidate(alpha_id: str, expression: str) -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="Momentum",
        hypothesis="price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        scorecard={"total_score": 80.0},
        lifecycle_status="submission_ready",
    )


def test_expression_index_summarizes_duplicates_across_jsonl_sources(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    first = _candidate("a1", "rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))")
    same = _candidate("a2", " rank ( ts_mean ( volume , 10 ) ) + rank ( ts_delta ( close , 20 ) ) ")
    repo.save_candidate("run_1", first)
    repo.save_lifecycle_record("run_1", {"alpha_id": "a2", "stage": "created", "expression": same.expression})
    repo.save_check_record({"candidate": same.to_dict(), "status": "BLOCKED"})
    repo.save_backtest_record("run_1", {"alpha_id": "a2", "action": "submitted", "slot": 1, "expression": same.expression})
    SubmissionLedger(str(tmp_path)).record(first, {"status": "SUBMITTED"}, mode="manual")

    summary = ExpressionHistoryIndex(tmp_path).summary(top_n=5)

    assert summary["ok"] is True
    assert summary["unique_expression_count"] == 1
    assert summary["duplicate_expression_count"] == 1
    duplicate = summary["duplicates"][0]
    assert duplicate["count"] == 5
    assert duplicate["sources"] == {"candidate": 1, "lifecycle": 1, "check": 1, "backtest": 1, "submission": 1}
    assert summary["fields"][0]["name"] == "close"
    assert summary["operators"][0]["name"] == "rank"
    assert summary["windows"][0]["window"] in {10, 20}


def test_expression_index_backfills_old_records_without_profile(tmp_path):
    (tmp_path / "candidates.jsonl").write_text(
        json.dumps({"alpha_id": "legacy", "expression": "Rank(TS_Delta(Close, 20))"}) + "\n",
        encoding="utf-8",
    )

    lookup = ExpressionHistoryIndex(tmp_path).lookup("rank(ts_delta(close,20))")

    assert lookup["exact_match"] is True
    assert lookup["exact_count"] == 1
    assert lookup["exact_records"][0]["alpha_id"] == "legacy"
    assert lookup["expression_profile"]["fields"] == ["close"]


def test_expression_index_lookup_reports_similar_records_when_no_exact_match(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate("run_1", _candidate("a1", "rank(ts_delta(close, 20))"))

    lookup = ExpressionHistoryIndex(tmp_path).lookup("rank(ts_delta(close, 21))", min_similarity=0.9)

    assert lookup["exact_match"] is False
    assert lookup["similar_count"] == 1
    assert lookup["similar_records"][0]["alpha_id"] == "a1"
    assert lookup["similar_records"][0]["similarity"] >= 0.9


def test_expression_index_summary_reuses_preloaded_source_rows(tmp_path):
    expression = "rank(ts_delta(close, 20))"
    source_rows = {
        "candidates.jsonl": [{"alpha_id": "a1", "expression": expression}],
        "backtests.jsonl": [{"alpha_id": "a2", "action": "submitted", "expression": expression}],
        "lifecycle.jsonl": [],
        "checks.jsonl": [],
        "submissions.jsonl": [],
    }

    summary = ExpressionHistoryIndex(tmp_path).summary(
        top_n=5,
        include_cloud=False,
        source_rows=source_rows,
    )

    assert summary["total_expression_records"] == 2
    assert summary["duplicate_expression_count"] == 1
    assert summary["duplicates"][0]["sources"] == {"candidate": 1, "backtest": 1}
