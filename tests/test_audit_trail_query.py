"""Tests for the retrospective audit-trail query interface."""

from datetime import datetime, timezone

from brain_alpha_ops.audit_trail.lifecycle_writer import LifecycleAuditWriter
from brain_alpha_ops.audit_trail.query import (
    AuditQuery,
    count_records_by_state,
    find_similar_expressions,
    query_audit_records,
)


def _seed(tmp_path):
    w = LifecycleAuditWriter(tmp_path)
    w.record_lifecycle_transition(
        alpha_id="A1", from_state="generated", to_state="submission_ready",
        reason="passed gate", trigger_rule="default",
        context={"dataset_id": "cn", "region": "cn", "score": 0.8},
    )
    w.record_gate_decision(
        alpha_id="A1", gate_name="quality", passed=True, reason="ok",
        context={"score": 0.8},
    )
    w.record_gate_decision(
        alpha_id="B2", gate_name="quality", passed=False, reason="sharpe too low",
        context={"score": 0.2},
    )
    w.record_simulation_writeback(
        alpha_id="A1",
        sim_config={"dataset": "cn", "universe": "us"},
        result_summary={
            "total_score": 12.5,
            "expression": "rank(ts_delta(close, 20))",
            "simulation_result": "ts_delta",
        },
    )
    return w


def test_query_audit_records_filters_by_alpha_id(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(alpha_id="A1"), audit_dir=tmp_path)
    assert result.total == 3
    assert all(r["alpha_id"] == "A1" for r in result.records)


def test_query_audit_records_filters_by_event_type(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(event_type="gate_decision"), audit_dir=tmp_path)
    assert result.total == 2
    assert all(r["event_type"] == "gate_decision" for r in result.records)


def test_query_audit_records_filters_by_state(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(state="submission_ready"), audit_dir=tmp_path)
    assert result.total == 1
    assert result.records[0]["alpha_id"] == "A1"


def test_query_audit_records_filters_by_dataset(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(dataset="cn"), audit_dir=tmp_path)
    assert result.total == 2


def test_query_audit_records_filters_by_score_range(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(score_min=0.5), audit_dir=tmp_path)
    assert result.total == 3


def test_query_audit_records_filters_by_date_range(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(
        AuditQuery(
            date_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2099, 1, 1, tzinfo=timezone.utc),
        ),
        audit_dir=tmp_path,
    )
    assert result.total == 4


def test_query_audit_records_gate_failure_reason(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(
        AuditQuery(gate_failure_reason="sharpe too low"), audit_dir=tmp_path
    )
    assert result.total == 1
    assert result.records[0]["alpha_id"] == "B2"


def test_query_audit_records_sim_result_and_expression(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(
        AuditQuery(sim_result="ts_delta"), audit_dir=tmp_path
    )
    assert result.total == 1
    assert result.records[0]["alpha_id"] == "A1"


def test_audit_query_to_dict_serializes_datetimes():
    q = AuditQuery(alpha_id="A1", date_from=datetime(2026, 1, 1, 12, 0, 0))
    d = q.to_dict()
    assert d["alpha_id"] == "A1"
    assert d["date_from"].endswith("T12:00:00")


def test_count_records_by_state(tmp_path):
    _seed(tmp_path)
    counts = count_records_by_state(audit_dir=tmp_path)
    assert counts.get("submission_ready") == 1


def test_find_similar_expressions(tmp_path):
    _seed(tmp_path)
    matches = find_similar_expressions("rank(ts_delta(close, 20))", audit_dir=tmp_path)
    assert len(matches) >= 1
    assert matches[0]["alpha_id"] == "A1"


def test_query_audit_records_truncated(tmp_path):
    _seed(tmp_path)
    result = query_audit_records(AuditQuery(limit=2), audit_dir=tmp_path)
    assert len(result.records) == 2
    assert result.truncated is True