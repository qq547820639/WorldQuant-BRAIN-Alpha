from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.parameter_search import ParameterSearchService


def test_parameter_search_ranks_better_mutations():
    service = ParameterSearchService(search_budget=3)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 80},
        official_metrics={"sharpe": 0.5, "fitness": 0.4},
    )

    result = service.search(
        candidate,
        diagnosis={
            "failed_dimensions": ["sharpe", "fitness"],
            "suggested_mutations": [],
        },
        max_mutations=2,
    )

    assert result["ok"] is True
    assert result["mutation_count"] == 2
    assert len(result["results"]) == 2
    assert result["budget"]["bounded"] is True
    assert result["termination_reason"] in {"budget_exhausted", "mutation_space_exhausted"}
    assert result["best_result"]["score"] >= result["results"][-1]["score"]


def test_parameter_search_rank_creates_sorted_results():
    service = ParameterSearchService(search_budget=3)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 80},
        official_metrics={"sharpe": 0.5, "fitness": 0.4},
    )
    mutations = [
        type("M", (), {"expression": "rank(ts_delta(close, 30))", "mode": "longer_window", "reason": "test", "parent_failure": "sharpe", "metadata": {}})(),
        type("M", (), {"expression": "rank(ts_mean(close, 20))", "mode": "structure_refine", "reason": "test", "parent_failure": "fitness", "metadata": {}})(),
    ]

    ranked = service.rank(candidate, mutations, diagnosis={"failed_dimensions": ["sharpe", "fitness"]})

    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
    assert ranked[0].candidate.parent_id == "a1"
    assert ranked[0].metadata["lineage"]["parent_alpha_id"] == "a1"


def test_parameter_search_rank_deduplicates_parent_and_repeated_mutations():
    service = ParameterSearchService(search_budget=5)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 80},
    )
    mutations = [
        type("M", (), {"expression": "rank(ts_delta(close, 20))", "mode": "same", "reason": "", "parent_failure": "", "metadata": {}})(),
        type("M", (), {"expression": "rank(ts_delta(close, 30))", "mode": "window", "reason": "", "parent_failure": "", "metadata": {}})(),
        type("M", (), {"expression": "rank(ts_delta(close, 30))", "mode": "window", "reason": "", "parent_failure": "", "metadata": {}})(),
    ]

    ranked = service.rank(candidate, mutations)

    assert len(ranked) == 1
    assert ranked[0].candidate.expression == "rank(ts_delta(close, 30))"
