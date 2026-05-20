import json
from pathlib import Path

from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from brain_alpha_ops.brain_api import MockBrainAPI
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.repository import ResearchRepository


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_research_memory_summarizes_fields_operators_failures_and_lineage(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    winner = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
        scorecard={"total_score": 88},
        gate={"submission_ready": True},
        lifecycle_status="submission_ready",
        source_tags=["assistant_guided", "assistant_guidance_ag_testdigest"],
        submission={"assistant_guidance_digest": "ag_testdigest"},
    )
    loser = Candidate(
        alpha_id="a2",
        expression="rank(ts_mean(volume, 5))",
        family="Liquidity",
        hypothesis="volume pressure",
        data_fields=["volume"],
        operators=["rank", "ts_mean"],
        official_metrics={"sharpe": 0.4, "fitness": 0.2, "pass_fail": "FAIL", "failure_reason": "LOW_SHARPE"},
        scorecard={"total_score": 42},
        gate={"failed_reasons": ["LOW_SHARPE"]},
        parent_id="a1",
        mutation_type="window_change",
        lifecycle_status="official_standard_rejected",
    )
    repo.save_candidate("run_1", winner)
    repo.save_candidate("run_1", loser)
    repo.save_lifecycle_record("run_1", {"alpha_id": "a2", "stage": "backtest_failed", "note": "LOW_SHARPE"})
    repo.save_check_record({"alpha_id": "a2", "error": "SELF_CORRELATION"})
    _write_jsonl(
        tmp_path / "alpha_features.jsonl",
        [
            {"alpha_id": "a1", "field_set": ["close"], "operator_set": ["rank", "ts_delta"], "sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            {"alpha_id": "a2", "field_set": ["volume"], "operator_set": ["rank", "ts_mean"], "sharpe": 0.4, "fitness": 0.2, "pass_fail": "FAIL"},
        ],
    )

    summary = ResearchMemory(tmp_path).summary(top_n=5)

    assert summary["ok"] is True
    assert summary["total_candidates"] == 2
    assert summary["status_counts"]["submission_ready"] == 1
    assert summary["fields"][0]["name"] == "close"
    assert summary["operators"][0]["name"] in {"rank", "ts_delta"}
    assert summary["assistant_guided"]["count"] == 1
    assert summary["assistant_guided"]["success_rate"] == 1.0
    assert summary["assistant_guided"]["avg_score"] == 88.0
    assert summary["assistant_guidance_outcomes"][0]["guidance_digest"] == "ag_testdigest"
    assert summary["assistant_guidance_outcomes"][0]["success_rate"] == 1.0
    assert summary["expression_index"]["unique_expression_count"] == 2
    assert summary["expression_index"]["operators"][0]["name"] in {"rank", "ts_delta", "ts_mean"}
    assert any(item["reason"] == "LOW_SHARPE" for item in summary["failure_patterns"])
    assert summary["lineage"][0]["parent_id"] == "a1"
    assert summary["lineage"][0]["child_count"] == 1


def test_repository_persists_expression_summary_for_candidate_lifecycle_and_check(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    candidate = Candidate(
        alpha_id="a1",
        expression=" Rank ( TS_Delta ( Close , 20 ) ) ",
        family="Momentum",
        hypothesis="price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
    )

    repo.save_candidate("run_1", candidate)
    repo.save_lifecycle_record("run_1", {"alpha_id": "a1", "stage": "created", "expression": candidate.expression})
    repo.save_check_record({"alpha_id": "a1", "candidate": candidate.to_dict(), "status": "BLOCKED"})
    repo.save_backtest_record("run_1", {"alpha_id": "a1", "action": "submitted", "slot": 1, "simulation_id": "sim_1", "expression": candidate.expression})

    candidate_row = json.loads((tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()[0])
    lifecycle_row = json.loads((tmp_path / "lifecycle.jsonl").read_text(encoding="utf-8").splitlines()[0])
    check_row = json.loads((tmp_path / "checks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    backtest_row = json.loads((tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert candidate_row["expression_canonical"] == "rank(ts_delta(close,20))"
    assert lifecycle_row["expression_fingerprint"] == candidate_row["expression_fingerprint"]
    assert check_row["expression_fingerprint"] == candidate_row["expression_fingerprint"]
    assert backtest_row["expression_fingerprint"] == candidate_row["expression_fingerprint"]
    assert check_row["expression_profile"]["fields"] == ["close"]


def test_repository_redacts_sensitive_values_before_persisting(tmp_path):
    repo = ResearchRepository(str(tmp_path))

    repo.save_lifecycle_record(
        "run_1",
        {
            "alpha_id": "a1",
            "expression": "rank(close)",
            "note": "failed with secret-token-123",
            "headers": {"Authorization": "Bearer live-token-456"},
        },
    )
    repo.save_check_record({"alpha_id": "a1", "error": "token=SECRET789"})
    repo.merge_cloud_alphas([
        {"id": "cloud_1", "status": "UNSUBMITTED", "Authorization": "Bearer cloud-token-111"}
    ])
    repo.save_run_history(
        "run_1",
        {"credentials": {"password": "pw", "token": "secret-token-222"}, "error": "cookie=session-cookie-333"},
    )

    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / "lifecycle.jsonl",
            tmp_path / "checks.jsonl",
            tmp_path / "cloud_alphas.jsonl",
            tmp_path / "run_history" / "latest.json",
        ]
    )

    assert "secret-token-123" not in persisted
    assert "live-token-456" not in persisted
    assert "SECRET789" not in persisted
    assert "cloud-token-111" not in persisted
    assert "secret-token-222" not in persisted
    assert "session-cookie-333" not in persisted
    assert "<redacted>" in persisted


def test_research_memory_writes_summary_file(tmp_path):
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
        ),
    )

    path = ResearchMemory(tmp_path).write_summary()

    assert path.name == "research_memory_summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["total_candidates"] == 1


def test_research_memory_builds_generation_guidance(tmp_path):
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
            official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            scorecard={"total_score": 88},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a2",
            expression="rank(ts_mean(volume, 5))",
            family="Liquidity",
            hypothesis="volume pressure",
            data_fields=["volume"],
            operators=["rank", "ts_mean"],
            official_metrics={"sharpe": 1.1, "fitness": 0.9, "pass_fail": "PASS"},
            scorecard={"total_score": 76},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )

    guidance = ResearchMemory(tmp_path).generation_guidance(top_n=5)

    assert guidance["ok"] is True
    assert guidance["sample_size"] == 2
    assert "rank" in guidance["top_operators"]
    assert guidance["preferred_windows"][:2] == [20, 5]
    assert guidance["field_combinations"][0]["fields"] in (["close"], ["volume"])
    assert guidance["top_categories"][0] in {"Momentum", "Liquidity"}


def test_research_memory_summary_contains_generator_guidance_features(tmp_path):
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
            official_metrics={"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"},
            scorecard={"total_score": 82},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )

    summary = ResearchMemory(tmp_path).summary(top_n=5)

    assert summary["preferred_windows"] == [20]
    assert summary["field_combinations"][0]["fields"] == ["close"]


def test_research_memory_summary_reuses_loaded_rows_for_expression_index(monkeypatch, tmp_path):
    repo = ResearchRepository(str(tmp_path))
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
    )
    repo.save_candidate("run_1", candidate)
    repo.save_lifecycle_record("run_1", {"alpha_id": "a1", "stage": "created", "expression": candidate.expression})
    repo.save_check_record({"alpha_id": "a1", "candidate": candidate.to_dict(), "status": "PASS"})
    loaded_by_expression_index = []

    def track_expression_index_load(path, *, limit):
        loaded_by_expression_index.append(path.name)
        return []

    monkeypatch.setattr("brain_alpha_ops.research.expression_index._load_jsonl", track_expression_index_load)

    summary = ResearchMemory(tmp_path).summary(top_n=5)

    assert summary["expression_index"]["source_counts"]["candidate"] == 1
    assert summary["expression_index"]["source_counts"]["lifecycle"] == 1
    assert summary["expression_index"]["source_counts"]["check"] == 1
    assert "candidates.jsonl" not in loaded_by_expression_index
    assert "lifecycle.jsonl" not in loaded_by_expression_index
    assert "checks.jsonl" not in loaded_by_expression_index


def test_research_memory_generation_guidance_reuses_summary_without_jsonl_reads(monkeypatch, tmp_path):
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
            official_metrics={"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"},
            scorecard={"total_score": 82},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )
    memory = ResearchMemory(tmp_path)
    summary = memory.summary(top_n=5)

    def fail_summary(*args, **kwargs):
        raise AssertionError("generation_guidance should reuse supplied summary")

    def fail_load_jsonl(*args, **kwargs):
        raise AssertionError("generation_guidance should reuse supplied summary features without JSONL reads")

    monkeypatch.setattr(memory, "summary", fail_summary)
    monkeypatch.setattr(memory, "_load_jsonl", fail_load_jsonl)
    monkeypatch.setattr(memory, "_load_candidate_records", fail_load_jsonl)

    guidance = memory.generation_guidance(top_n=5, summary=summary)

    assert guidance["sample_size"] == 1
    assert guidance["top_fields"] == ["close"]
    assert "ts_delta" in guidance["top_operators"]
    assert guidance["preferred_windows"] == [20]
    assert guidance["field_combinations"][0]["fields"] == ["close"]


def test_agent_toolbox_queries_research_memory(tmp_path):
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
        ),
    )
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(run_config=config, api=MockBrainAPI())

    result = toolbox.call("query_research_memory", {"top_n": 3, "persist": True})

    assert result["ok"] is True
    assert result["total_candidates"] == 1
    assert result["written_to"].endswith("research_memory_summary.json")


def test_research_memory_generation_guidance_is_generator_ready(tmp_path):
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
            official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            scorecard={"total_score": 88},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )

    guidance = ResearchMemory(tmp_path).generation_guidance()

    assert guidance["sample_size"] == 1
    assert guidance["ok"] is True
    assert isinstance(guidance["top_operators"], list)
    assert isinstance(guidance["preferred_windows"], list)
    assert isinstance(guidance["field_combinations"], list)


def test_research_memory_reads_latest_persisted_assistant_guidance(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": False,
            "confidence": 0.9,
            "top_operators": ["rank"],
            "preferred_windows": [20],
        },
        source="test",
    )
    repo.save_assistant_guidance(
        {
            "ok": True,
            "schema_version": "assistant_generation_guidance.v1",
            "usable": True,
            "confidence": 0.75,
            "top_fields": ["close"],
            "top_operators": ["ts_rank"],
            "preferred_windows": [10],
        },
        source="test",
    )

    guidance = ResearchMemory(tmp_path).latest_assistant_guidance(min_confidence=0.6)

    assert guidance["usable"] is True
    assert guidance["guidance_digest"].startswith("ag_")
    assert guidance["persistence_source"] == "test"
    assert guidance["top_fields"] == ["close"]
    assert guidance["top_operators"] == ["ts_rank"]
    assert guidance["preferred_windows"] == [10]


def test_research_memory_skips_latest_guidance_with_weak_historical_outcomes(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "schema_version": "assistant_generation_guidance.v1",
            "usable": True,
            "confidence": 0.8,
            "guidance_digest": "ag_strong",
            "top_fields": ["close"],
            "top_operators": ["rank"],
            "preferred_windows": [20],
        },
        source="test",
    )
    repo.save_assistant_guidance(
        {
            "ok": True,
            "schema_version": "assistant_generation_guidance.v1",
            "usable": True,
            "confidence": 0.9,
            "guidance_digest": "ag_weak",
            "top_fields": ["volume"],
            "top_operators": ["ts_mean"],
            "preferred_windows": [5],
        },
        source="test",
    )
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="strong_1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            source_tags=["assistant_guided"],
            official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            scorecard={"total_score": 88},
            gate={"submission_ready": True},
            submission={"assistant_guidance_digest": "ag_strong"},
            lifecycle_status="submission_ready",
        ),
    )
    for index in range(2):
        repo.save_candidate(
            "run_1",
            Candidate(
                alpha_id=f"weak_{index}",
                expression="rank(ts_mean(volume, 5))",
                family="Liquidity",
                hypothesis="volume pressure",
                data_fields=["volume"],
                operators=["rank", "ts_mean"],
                source_tags=["assistant_guided"],
                official_metrics={"sharpe": 0.2, "fitness": 0.1, "pass_fail": "FAIL"},
                scorecard={"total_score": 24},
                gate={"failed_reasons": ["LOW_SHARPE"]},
                submission={"assistant_guidance_digest": "ag_weak"},
                lifecycle_status="official_standard_rejected",
            ),
        )

    guidance = ResearchMemory(tmp_path).latest_assistant_guidance(min_confidence=0.6)

    assert guidance["usable"] is True
    assert guidance["guidance_digest"] == "ag_strong"
    assert guidance["historical_outcome_status"] == "strong"
    assert guidance["historical_outcome"]["guidance_digest"] == "ag_strong"


def test_research_memory_returns_unusable_when_persisted_guidance_below_threshold(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.35,
            "top_operators": ["rank"],
            "preferred_windows": [20],
        },
        source="test",
    )

    guidance = ResearchMemory(tmp_path).latest_assistant_guidance(min_confidence=0.7)

    assert guidance["usable"] is False
    assert guidance["reason"] == "no_persisted_usable_guidance"


def test_research_memory_returns_weak_outcome_reason_when_all_guidance_is_weak(tmp_path):
    repo = ResearchRepository(str(tmp_path))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "schema_version": "assistant_generation_guidance.v1",
            "usable": True,
            "confidence": 0.9,
            "guidance_digest": "ag_allweak",
            "top_fields": ["volume"],
            "top_operators": ["ts_mean"],
            "preferred_windows": [5],
        },
        source="test",
    )
    for index in range(2):
        repo.save_candidate(
            "run_1",
            Candidate(
                alpha_id=f"weak_only_{index}",
                expression="rank(ts_mean(volume, 5))",
                family="Liquidity",
                hypothesis="volume pressure",
                data_fields=["volume"],
                operators=["rank", "ts_mean"],
                source_tags=["assistant_guided"],
                official_metrics={"sharpe": 0.2, "fitness": 0.1, "pass_fail": "FAIL"},
                scorecard={"total_score": 24},
                gate={"failed_reasons": ["LOW_SHARPE"]},
                submission={"assistant_guidance_digest": "ag_allweak"},
                lifecycle_status="official_standard_rejected",
            ),
        )

    guidance = ResearchMemory(tmp_path).latest_assistant_guidance(min_confidence=0.6)

    assert guidance["usable"] is False
    assert guidance["reason"] == "weak_historical_guidance_outcome"
    assert guidance["guidance_digest"] == "ag_allweak"
    assert guidance["historical_outcome_status"] == "weak"
