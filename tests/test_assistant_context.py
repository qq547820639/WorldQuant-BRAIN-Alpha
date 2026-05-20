from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.assistant import build_assistant_request_pack
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.repository import ResearchRepository


def test_assistant_context_pack_merges_runtime_memory_and_guidance(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    repo = ResearchRepository(str(tmp_path))

    winner = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        source_tags=["assistant_guided", "assistant_guidance_ag_contextdigest"],
        official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
        scorecard={"total_score": 88},
        gate={"submission_ready": True},
        submission={"assistant_guidance_digest": "ag_contextdigest"},
        lifecycle_status="submission_ready",
    )
    loser = Candidate(
        alpha_id="a2",
        expression="rank(ts_mean(volume, 5))",
        family="Liquidity",
        hypothesis="volume pressure",
        data_fields=["volume"],
        operators=["rank", "ts_mean"],
        official_metrics={"sharpe": 0.3, "fitness": 0.1, "pass_fail": "FAIL", "failure_reason": "LOW_SHARPE"},
        scorecard={"total_score": 24},
        gate={"failed_reasons": ["LOW_SHARPE"]},
        lifecycle_status="official_standard_rejected",
    )
    repo.save_candidate("run_1", winner)
    repo.save_candidate("run_1", loser)
    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "slot": 1,
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "SUBMITTED",
            "expression": winner.expression,
        },
    )
    repo.save_lifecycle_record(
        "run_1",
        {
            "alpha_id": "dup_guard",
            "stage": "observability_duplicate_blocked",
            "status": "observability_duplicate_blocked",
            "note": "official_validation",
            "family": "Momentum",
            "score": 92,
            "expression": winner.expression,
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_validation"],
            },
        },
    )
    repo.save_run_history(
        "run_1",
        {
            "summary": {
                "cycle": 2,
                "candidates": [winner.to_dict(), loser.to_dict()],
                "passed_candidates": [winner.to_dict()],
                "pending_backtest_candidates": [winner.to_dict()],
                "backtest_slots": [{"slot": 1, "alpha_id": "a1", "status": "running"}],
                "backtest_records": [
                    {
                        "action": "submitted",
                        "slot": 1,
                        "alpha_id": "a1",
                        "simulation_id": "sim_1",
                        "status": "SUBMITTED",
                        "expression_fingerprint": "fp_test",
                    }
                ],
            },
            "candidates": [winner.to_dict(), loser.to_dict()],
        },
    )
    repo.merge_cloud_alphas(
        [{"id": "cloud_a1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS", "sharpe": 1.6}}],
        sync_range="3d",
    )

    pack = build_assistant_context_pack(config, top_n=5)

    assert pack["ok"] is True
    assert pack["schema_version"] == "assistant_context_pack.v1"
    assert pack["latest_result"]["candidate_count"] == 2
    assert pack["latest_result"]["pending_backtest_count"] == 1
    assert pack["cloud_alphas"]["count"] == 1
    assert pack["research_memory"]["total_candidates"] == 2
    assert pack["research_memory"]["assistant_guided"]["count"] == 1
    assert pack["research_memory"]["assistant_guidance_outcomes"][0]["guidance_digest"] == "ag_contextdigest"
    assert pack["expression_index"]["unique_expression_count"] == 2
    assert pack["expression_index"]["duplicate_expression_count"] >= 1
    assert pack["observability"]["duplicate_expression_count"] >= 1
    assert pack["observability"]["official_guard_blocked_count"] == 1
    assert pack["observability"]["risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in pack["observability"]["health_flags"]
    assert pack["latest_result"]["backtest_records"][0]["action"] == "submitted"
    assert "rank" in pack["generation_focus"]["operators"]
    assert 20 in pack["generation_focus"]["windows"]
    assert pack["generation_focus"]["duplicate_expressions"]
    assert pack["generation_focus"]["guidance_outcomes"][0]["success_rate"] == 1.0
    assert any(row["reason"] == "LOW_SHARPE" for row in pack["generation_focus"]["failure_patterns"])
    assert "Use local evidence first" in pack["prompt"]
    assert "Guidance feedback" in pack["prompt"]
    assert "Expression index" in pack["prompt"]
    assert "Observability:" in pack["prompt"]
    assert "risk=" in pack["prompt"]
    assert "Prompt diagnostics" in pack["prompt"]
    assert "official_guard_blocked=1" in pack["prompt"]
    assert pack["prompt_diagnostics"]["schema_version"] == "assistant_prompt_diagnostics.v1"
    assert pack["prompt_diagnostics"]["duplicate_focus_count"] >= 1
    assert pack["prompt_diagnostics"]["official_guard_blocked_count"] == 1
    assert "duplicate_expression_history" in pack["prompt_diagnostics"]["risk_flags"]
    assert "observability_official_call_guard_active" in pack["prompt_diagnostics"]["risk_flags"]
    assert "duplicate_expression_history" in pack["prompt"]
    assert "ag_contextdigest" in pack["prompt"]
    assert any("ag_contextdigest" in item for item in pack["recommended_next_actions"])

    request = build_assistant_request_pack(pack)
    assert "duplicate_expression_history" in request["offline_draft"]["risk_flags"]
    assert "observability_official_call_guard_active" in request["offline_draft"]["risk_flags"]
    assert "persisted_backtest_state_available" in request["offline_draft"]["risk_flags"]
    assert request["offline_draft"]["evidence"]["observability_risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in request["offline_draft"]["evidence"]["observability_health_flags"]
    assert request["offline_draft"]["evidence"]["duplicate_expression_count"] >= 1
    assert request["offline_draft"]["evidence"]["observability_official_guard_blocked_count"] == 1
    assert request["offline_draft"]["evidence"]["recent_backtest_record_count"] == 1


def test_assistant_context_pack_can_redact_sensitive_paths(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)

    pack = build_assistant_context_pack(config, include_sensitive=False)

    assert "storage_dir" not in pack
    assert pack["sensitive_fields_redacted"] == ["storage_dir"]


def test_assistant_context_pack_reuses_memory_summary_for_guidance(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    ResearchRepository(str(tmp_path)).save_candidate(
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
    original_summary = ResearchMemory.summary
    calls = {"summary": 0}

    def count_summary(self, *args, **kwargs):
        calls["summary"] += 1
        return original_summary(self, *args, **kwargs)

    monkeypatch.setattr(ResearchMemory, "summary", count_summary)

    pack = build_assistant_context_pack(config, top_n=5, include_prompt=False)

    assert pack["research_memory"]["total_candidates"] == 1
    assert "ts_delta" in pack["generation_focus"]["operators"]
    assert calls["summary"] == 1
