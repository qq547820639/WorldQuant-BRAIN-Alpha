from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate


def _toolbox(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    return BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub())


def test_new_tool_manifest_entries_exist():
    toolbox = _toolbox(".")
    names = {tool["name"] for tool in toolbox.list_tools()}

    assert "build_market_data_cache" in names
    assert "build_vectorized_market_data" in names
    assert "search_parameters" in names
    assert "orchestrate_parameter_search" in names
    assert "plan_parallel_backtest" in names
    assert "run_parallel_backtest" in names
    assert "send_alert" in names
    assert "route_alert" in names


def test_market_data_cache_tool_and_alert_tool(tmp_path):
    toolbox = _toolbox(tmp_path)

    cache_result = toolbox.call(
        "build_market_data_cache",
        {
            "source_file": "missing.jsonl",
            "refresh": True,
            "limit": 10,
        },
    )
    alert_result = toolbox.call(
        "send_alert",
        {
            "title": "cache stale",
            "message": "refresh required",
            "severity": "warning",
            "channel": "local",
        },
    )

    assert cache_result["ok"] is True
    assert cache_result["symbol_count"] == 0
    assert alert_result["ok"] is True
    assert alert_result["channel"] == "local"


def test_parameter_search_tool_returns_structured_result(tmp_path):
    toolbox = _toolbox(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 80},
        official_metrics={"sharpe": 0.5, "fitness": 0.4},
    )

    result = toolbox.call("search_parameters", {"candidate": candidate.to_dict(), "max_mutations": 2})

    assert result["ok"] is True
    assert result["schema_version"] == "parameter_search_result.v1"
    assert "results" in result


def test_productization_tools_return_bounded_payloads(tmp_path):
    toolbox = _toolbox(tmp_path)
    toolbox.call(
        "build_market_data_cache",
        {"refresh": True, "source_file": "missing.jsonl", "limit": 10},
    )

    vector = toolbox.call("build_vectorized_market_data", {"fields": ["close"], "limit_symbols": 5})
    plan = toolbox.call(
        "plan_parallel_backtest",
        {
            "expressions": ["rank(close)", "rank(volume)", "rank(close)"],
            "markets": ["USA", "EUR"],
            "max_workers": 8,
            "max_batches": 1,
            "per_account_limit": 3,
        },
    )
    routed = toolbox.call(
        "route_alert",
        {
            "title": "planned",
            "message": "jobs ready",
            "channels": ["local", "ops"],
        },
    )

    assert vector["ok"] is True
    assert vector["schema_version"] == "market_data_vector.v1"
    assert plan["selected_jobs"] == 3
    assert plan["account_safety"]["capacity_limited"] is True
    assert routed["ok"] is True


def test_productization_tools_normalize_scalar_list_arguments(tmp_path):
    toolbox = _toolbox(tmp_path)
    toolbox.call(
        "build_market_data_cache",
        {"refresh": True, "source_file": "missing.jsonl", "limit": 10},
    )

    vector = toolbox.call("build_vectorized_market_data", {"fields": "close", "limit_symbols": 5})
    plan = toolbox.call(
        "plan_parallel_backtest",
        {
            "expressions": "rank(close)",
            "markets": "USA",
            "max_workers": 8,
            "max_batches": 1,
            "per_account_limit": 3,
        },
    )
    routed = toolbox.call(
        "route_alert",
        {
            "title": "planned",
            "message": "jobs ready",
            "channels": "ops",
        },
    )

    assert vector["fields"] == ["close"]
    assert plan["markets"] == ["USA"]
    assert plan["requested_jobs"] == 1
    assert routed["channels"] == ["ops"]


def test_orchestrate_parameter_search_tool_returns_budget(tmp_path):
    toolbox = _toolbox(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="momentum",
        scorecard={"total_score": 80},
        official_metrics={"sharpe": 0.5, "fitness": 0.4},
    )

    result = toolbox.call(
        "orchestrate_parameter_search",
        {"candidate": candidate.to_dict(), "rounds": 2, "max_mutations": 2, "keep_top": 2},
    )

    assert result["ok"] is True
    assert result["schema_version"] == "parameter_search_orchestration.v1"
    assert result["budget"]["bounded"] is True
