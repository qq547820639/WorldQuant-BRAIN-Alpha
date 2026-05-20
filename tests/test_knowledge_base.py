import pytest

from brain_alpha_ops.research.knowledge_base import KnowledgeRecord, ResearchKnowledgeBase


def test_research_knowledge_base_adds_and_summarizes_records(tmp_path):
    kb = ResearchKnowledgeBase(tmp_path)
    saved = kb.add(
        KnowledgeRecord(
            kind="rules",
            title="Avoid stale cloud cache",
            body="Refresh cloud cache before submission-sensitive work.",
            confidence=0.9,
            evidence=[{"run_id": "run_1"}],
            source_run_id="run_1",
        )
    )

    summary = kb.summary(min_confidence=0.8)

    assert saved["schema_version"] == "research_knowledge_record.v1"
    assert saved["knowledge_id"].startswith("rk_")
    assert summary["schema_version"] == "research_knowledge_summary.v1"
    assert summary["counts"]["rules"] == 1
    assert summary["items"][0]["title"] == "Avoid stale cloud cache"


def test_research_knowledge_base_filters_by_kind_and_confidence(tmp_path):
    kb = ResearchKnowledgeBase(tmp_path)
    kb.add({"kind": "findings", "title": "Strong rank delta", "body": "rank ts_delta worked", "confidence": 0.75})
    kb.add({"kind": "failures", "title": "Weak turnover", "body": "turnover too high", "confidence": 0.4})

    rows = kb.latest("findings", min_confidence=0.7)

    assert len(rows) == 1
    assert rows[0]["kind"] == "findings"
    assert rows[0]["title"] == "Strong rank delta"


def test_research_knowledge_base_rejects_unknown_kind(tmp_path):
    kb = ResearchKnowledgeBase(tmp_path)

    with pytest.raises(ValueError, match="unsupported knowledge kind"):
        kb.add({"kind": "notes", "title": "bad", "body": "bad"})
