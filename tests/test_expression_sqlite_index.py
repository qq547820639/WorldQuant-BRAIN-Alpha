from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex
from brain_alpha_ops.research.repository import ResearchRepository


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


def test_expression_sqlite_index_refresh_summary_and_lookup(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate("run_1", _candidate("a1", "rank(ts_delta(close, 20))"))
    repo.save_lifecycle_record("run_1", {"alpha_id": "a2", "expression": " Rank ( TS_Delta ( Close , 20 ) ) "})
    index = ExpressionSqliteIndex(tmp_path)

    refresh = index.refresh(limit=100)
    summary = index.summary(top_n=5)
    lookup = index.lookup("rank(ts_delta(close,20))")

    assert refresh["ok"] is True
    assert refresh["record_count"] == 2
    assert summary["ok"] is True
    assert summary["schema_version"] == "expression-sqlite-index.v1"
    assert summary["unique_expression_count"] == 1
    assert summary["duplicate_expression_count"] == 1
    assert summary["duplicates"][0]["count"] == 2
    assert summary["manifest"]["schema_version"] == "sqlite_index_manifest.v1"
    assert summary["manifest"]["sources"]["candidates.jsonl"]["record_count"] == 1
    assert summary["manifest"]["sources"]["lifecycle.jsonl"]["indexed_count"] == 1
    assert summary["is_stale"] is False
    assert lookup["ok"] is True
    assert lookup["exact_match"] is True
    assert lookup["exact_count"] == 2


def test_expression_sqlite_index_is_incrementally_updated_by_repository(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate("run_1", _candidate("a1", "rank(ts_delta(close, 20))"))

    index = ExpressionSqliteIndex(tmp_path)
    summary = index.summary(top_n=5)
    lookup = index.lookup("rank(ts_delta(close,20))")

    assert summary["ok"] is True
    assert summary["source"] == "sqlite_expression_index"
    assert summary["total_expression_records"] == 1
    assert summary["unique_expression_count"] == 1
    assert summary["manifest"]["sources"]["candidates.jsonl"]["record_count"] == 1
    assert lookup["exact_match"] is True
    assert lookup["exact_records"][0]["alpha_id"] == "a1"


def test_expression_sqlite_index_reports_missing_cache(tmp_path):
    index = ExpressionSqliteIndex(tmp_path)

    summary = index.summary()

    assert summary["ok"] is False
    assert summary["error_code"] == "INDEX_NOT_BUILT"


def test_expression_sqlite_index_manifest_marks_stale_after_jsonl_append(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate("run_1", _candidate("a1", "rank(ts_delta(close, 20))"))
    index = ExpressionSqliteIndex(tmp_path)
    assert index.summary(top_n=5)["is_stale"] is False

    (tmp_path / "candidates.jsonl").write_text(
        (tmp_path / "candidates.jsonl").read_text(encoding="utf-8")
        + '{"alpha_id":"a2","expression":"rank(volume)"}\n',
        encoding="utf-8",
    )

    summary = index.summary(top_n=5)

    assert summary["is_stale"] is True
    assert "candidates.jsonl" in summary["manifest"]["stale_sources"]
    assert summary["manifest"]["sources"]["candidates.jsonl"]["missing_index_rows"] == 1
