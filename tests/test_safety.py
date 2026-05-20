import json
import tempfile
from pathlib import Path

from brain_alpha_ops.config import SubmissionPolicy
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.safety import SubmissionLedger, similarity


def _candidate(expression="rank(ts_delta(close, 20))", official_id="official_1"):
    c = Candidate(
        alpha_id="A1",
        expression=expression,
        family="Momentum",
        hypothesis="Recent price strength continues.",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
    )
    c.official_alpha_id = official_id
    c.official_metrics = {
        "sharpe": 1.8,
        "fitness": 1.2,
        "turnover": 0.2,
        "correlation": 0.3,
        "weight_concentration": 0.2,
    }
    c.gate = {"submission_ready": True, "failed_reasons": []}
    return c


def test_ledger_blocks_duplicate_expression():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = SubmissionLedger(tmp)
        c = _candidate()
        ledger.record(c, {"status": "SUBMITTED"}, mode="auto")
        result = ledger.assess(_candidate(official_id="official_2"), SubmissionPolicy(min_minutes_between_auto_submissions=0), mode="auto")
        assert not result["allowed"]
        assert any("already submitted" in reason for reason in result["failed_reasons"])


def test_ledger_blocks_canonical_duplicate_expression():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = SubmissionLedger(tmp)
        ledger.record(_candidate("rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))"), {"status": "SUBMITTED"}, mode="manual")
        result = ledger.assess(
            _candidate(
                " rank ( ts_mean ( volume , 10 ) ) + rank ( ts_delta ( close , 20 ) ) ",
                official_id="official_2",
            ),
            SubmissionPolicy(min_minutes_between_auto_submissions=0),
            mode="manual",
        )
        assert not result["allowed"]
        assert any("already submitted" in reason for reason in result["failed_reasons"])


def test_ledger_persists_expression_summary():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = SubmissionLedger(tmp)
        ledger.record(_candidate(" Rank ( TS_Delta ( Close , 20 ) ) "), {"status": "SUBMITTED"}, mode="manual")

        row = json.loads((Path(tmp) / "submissions.jsonl").read_text(encoding="utf-8").splitlines()[0])

        assert row["expression_canonical"] == "rank(ts_delta(close,20))"
        assert row["expression_fingerprint"]
        assert row["expression_profile"]["operators"] == ["rank", "ts_delta"]
        assert row["expression_profile"]["fields"] == ["close"]


def test_similarity_detects_micro_variant():
    assert similarity("rank(ts_delta(close, 20))", "rank(ts_delta(close, 21))") >= 0.90
