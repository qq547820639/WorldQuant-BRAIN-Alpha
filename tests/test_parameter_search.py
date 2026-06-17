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
    assert ranked[0].mutation_mode == "longer_window"
    assert ranked[0].metadata["parent_failure"] == "sharpe"
    trace = ranked[0].metadata["optimizer_trace"]
    assert trace["schema_version"] == "optimizer-trace-v1"
    assert trace["failed_dimension"] == "sharpe"
    assert trace["selected_strategy"] == ranked[0].mutation_mode
    assert trace["strategy_order"] == [ranked[0].mutation_mode]
    assert trace["official_api_called"] is False
    assert trace["submit_allowed"] is False


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


def test_parameter_search_rank_derives_child_metadata_from_expression():
    service = ParameterSearchService(search_budget=2)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(close)",
        family="Momentum",
        hypothesis="metadata should not be inherited",
        data_fields=["close"],
        operators=["rank"],
        scorecard={"total_score": 80},
    )
    mutations = [
        type(
            "M",
            (),
            {
                "expression": "group_neutralize(rank(ts_rank(returns, 30)), subindustry)",
                "mode": "structure_refine",
                "reason": "",
                "parent_failure": "",
                "metadata": {"data_fields": ["close"], "operators": ["rank"]},
            },
        )(),
    ]

    ranked = service.rank(candidate, mutations)

    child = ranked[0].candidate
    assert child.data_fields == ["returns"]
    assert child.operators == ["group_neutralize", "rank", "ts_rank"]


def test_parameter_search_preserves_optimizer_trace_from_iterative_optimizer():
    service = ParameterSearchService(search_budget=2)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="trace optimizer decision",
        scorecard={"total_score": 80},
    )

    result = service.search(
        candidate,
        diagnosis={
            "failed_dimensions": ["sharpe"],
            "suggested_mutations": [{"mutation_mode": "window_perturb"}],
        },
        max_mutations=1,
    )

    trace = result["results"][0]["metadata"]["optimizer_trace"]
    assert trace["schema_version"] == "optimizer-trace-v1"
    assert trace["failed_dimension"] == "sharpe"
    assert trace["selected_strategy"] in trace["strategy_order"]
    assert trace["suggested_modes"] == ["window_perturb"]
    assert trace["official_api_called"] is False
    assert trace["submit_allowed"] is False
