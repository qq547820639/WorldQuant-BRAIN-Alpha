from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex
from brain_alpha_ops.research.repository import ResearchRepository


def test_record_sqlite_index_refresh_summary_and_lookup(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.merge_cloud_alphas(
        [
            {
                "id": "cloud_a1",
                "status": "SUBMITTED",
                "expression": "rank(ts_delta(close, 20))",
                "metrics": {"official_alpha_id": "off_a1"},
            }
        ],
        sync_range="3d",
    )
    repo.save_backtest_record(
        "run_1",
        {
            "action": "completed",
            "alpha_id": "local_a1",
            "official_alpha_id": "off_a1",
            "simulation_id": "sim_a1",
            "status": "COMPLETED",
            "expression": "rank(ts_delta(close, 20))",
        },
    )

    index = RecordSqliteIndex(tmp_path)
    refresh = index.refresh()
    summary = index.summary()
    lookup = index.lookup_alpha("off_a1")

    assert refresh["record_count"] == 2
    assert summary["schema_version"] == "record-sqlite-index.v1"
    assert summary["counts"]["cloud_alpha"] == 1
    assert summary["counts"]["backtest_record"] == 1
    assert summary["manifest"]["schema_version"] == "sqlite_index_manifest.v1"
    assert summary["manifest"]["sources"]["cloud_alphas.jsonl"]["record_count"] == 1
    assert summary["manifest"]["sources"]["backtests.jsonl"]["indexed_count"] == 1
    assert summary["is_stale"] is False
    assert lookup["ok"] is True
    assert lookup["count"] == 2
    assert {row["kind"] for row in lookup["records"]} == {"cloud_alpha", "backtest_record"}


def test_record_sqlite_index_is_incrementally_updated_by_repository(tmp_path):
    repo = ResearchRepository(str(tmp_path))

    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "expression": "rank(close)",
        },
    )

    summary = RecordSqliteIndex(tmp_path).summary()
    lookup = RecordSqliteIndex(tmp_path).lookup_alpha("sim_1")

    assert summary["ok"] is True
    assert summary["row_count"] == 1
    assert summary["manifest"]["sources"]["backtests.jsonl"]["record_count"] == 1
    assert lookup["count"] == 1
    assert lookup["records"][0]["action"] == "submitted"


def test_record_sqlite_index_reports_missing_cache(tmp_path):
    summary = RecordSqliteIndex(tmp_path).summary()

    assert summary["ok"] is False
    assert summary["error_code"] == "INDEX_NOT_BUILT"


def test_record_sqlite_index_manifest_marks_stale_after_jsonl_append(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record("run_1", {"alpha_id": "a1", "simulation_id": "sim_1", "expression": "rank(close)"})
    index = RecordSqliteIndex(tmp_path)
    assert index.summary()["is_stale"] is False

    (tmp_path / "backtests.jsonl").write_text(
        (tmp_path / "backtests.jsonl").read_text(encoding="utf-8")
        + '{"alpha_id":"a2","simulation_id":"sim_2","expression":"rank(volume)"}\n',
        encoding="utf-8",
    )

    summary = index.summary()

    assert summary["is_stale"] is True
    assert "backtests.jsonl" in summary["manifest"]["stale_sources"]
    assert summary["manifest"]["sources"]["backtests.jsonl"]["missing_index_rows"] == 1
