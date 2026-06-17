import json
import logging

from brain_alpha_ops.agent_research_tools import collect_job_rows, collect_job_rows_with_diagnostics
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


def test_collect_job_rows_warns_when_store_fails(caplog):
    class BrokenStore:
        def all(self, *, limit):
            raise RuntimeError("job store unavailable")

    class GoodStore:
        def all(self, *, limit):
            return [("job_1", {"status": "completed"})]

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.agent_research_tools"):
        rows = collect_job_rows({"broken": BrokenStore(), "good": GoodStore()}, limit=10)

    assert rows == [{"source": "good_job", "job_id": "job_1", "status": "completed"}]
    assert "failed to collect broken job rows for agent research context" in caplog.text


def test_collect_job_rows_with_diagnostics_reports_partial_failures(caplog):
    class BrokenStore:
        def all(self, *, limit):
            raise RuntimeError("job store unavailable")

    class GoodStore:
        def all(self, *, limit):
            return [("job_1", {"status": "completed"})]

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.agent_research_tools"):
        payload = collect_job_rows_with_diagnostics({"broken": BrokenStore(), "good": GoodStore()}, limit=10)

    assert payload["ok"] is False
    assert payload["partial"] is True
    assert payload["rows"] == [{"source": "good_job", "job_id": "job_1", "status": "completed"}]
    assert payload["diagnostics"][0]["source"] == "broken_job"
    assert payload["diagnostics"][0]["error_context"]["error_code"] == "JOB_ROWS_COLLECTION_FAILED"
    assert "failed to collect broken job rows for agent research context" in caplog.text


def test_query_research_observability_surfaces_job_collection_diagnostics(tmp_path):
    class BrokenStore:
        def all(self, *, limit):
            raise RuntimeError("job store unavailable")

    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(
        run_config=config,
        api=ProductionBrainAPIStub(),
        job_stores={"broken": BrokenStore()},
    )

    result = toolbox.call("query_research_observability", {"limit": 10, "top_n": 3, "include_cloud": False})

    assert result["ok"] is True
    assert result["job_diagnostics"][0]["source"] == "broken_job"
    assert result["partial_errors"][0]["component"] == "job_rows"
    assert result["errors"]["total"] >= 1
    assert result["errors"]["code_counts"]["JOB_ROWS_COLLECTION_FAILED"] == 1


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


def test_market_data_cache_tool_defaults_to_complete_cloud_source(tmp_path):
    toolbox = _toolbox(tmp_path)
    rows = [
        {"symbol": f"SYM{index}", "timestamp": "2026-05-25T00:00:00Z", "metrics": {"close": index + 1.0}}
        for index in range(5001)
    ]
    (tmp_path / "cloud_alphas.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    cache_result = toolbox.call(
        "build_market_data_cache",
        {
            "source_file": "cloud_alphas.jsonl",
            "refresh": True,
        },
    )

    assert cache_result["ok"] is True
    assert cache_result["record_count"] == 5001
    assert cache_result["symbol_count"] == 5001


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
