from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.search_orchestrator import ParameterSearchOrchestrator


def test_parameter_search_orchestrator_runs_bounded_rounds():
    candidate = Candidate(
        alpha_id="seed",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 75},
        official_metrics={"sharpe": 0.4, "fitness": 0.5},
    )

    result = ParameterSearchOrchestrator().run(candidate, rounds=2, max_mutations=2, keep_top=2)

    assert result["ok"] is True
    assert result["schema_version"] == "parameter_search_orchestration.v1"
    assert result["budget"]["live_api_calls"] == 0
    assert result["result_count"] >= 1
    assert result["best_result"]
    assert result["round_summaries"][0]["selected_count"] >= 1
    assert result["budget"]["evaluated_candidates"] >= 1
    assert result["termination_reason"] in {"round_budget_exhausted", "frontier_exhausted"}
