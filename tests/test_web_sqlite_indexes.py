from __future__ import annotations

from types import SimpleNamespace

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_sqlite_indexes import (
    sqlite_expression_lookup_payload,
    sqlite_index_snapshot,
    sqlite_record_lookup_payload,
)


def _config(storage_dir):
    return SimpleNamespace(ops=SimpleNamespace(storage_dir=str(storage_dir)))


def test_sqlite_index_snapshot_reports_expression_and_record_indexes(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            scorecard={"total_score": 80},
        ),
    )
    repo.save_backtest_record("run_1", {"alpha_id": "a1", "simulation_id": "sim_1", "expression": "rank(close)"})

    snapshot = sqlite_index_snapshot(top_n=5, load_config=lambda: _config(tmp_path))

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "sqlite_index_snapshot.v1"
    assert snapshot["expression_index"]["ok"] is True
    assert snapshot["record_index"]["ok"] is True
    assert snapshot["has_stale_index"] is False


def test_sqlite_expression_lookup_payload_reads_expression_cache(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(close)",
            family="Momentum",
            hypothesis="price rank",
            scorecard={"total_score": 80},
        ),
    )

    payload = sqlite_expression_lookup_payload(
        expression="rank(close)",
        top_n=3,
        load_config=lambda: _config(tmp_path),
    )

    assert payload["ok"] is True
    assert payload["exact_match"] is True
    assert payload["exact_records"][0]["alpha_id"] == "a1"


def test_sqlite_record_lookup_payload_reads_record_cache(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record("run_1", {"alpha_id": "a1", "simulation_id": "sim_1", "expression": "rank(close)"})

    payload = sqlite_record_lookup_payload(alpha_id="sim_1", limit=5, load_config=lambda: _config(tmp_path))

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["records"][0]["simulation_id"] == "sim_1"
