from brain_alpha_ops.agent_tool_registry import resolve_tool_name, tool_aliases, tool_definitions
from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.tasks import JobStore


def production_toolbox(**kwargs):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(kwargs.pop("storage_dir", "."))
    kwargs.setdefault("allow_live_api", True)
    return BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub(), **kwargs)


def test_agent_tool_manifest_exposes_safe_whitelist():
    tools = {tool.name: tool for tool in tool_definitions()}

    assert "generate_candidates" in tools
    assert "build_assistant_context" in tools
    assert "build_assistant_request" in tools
    assert "parse_assistant_response" in tools
    assert "assistant_response_guidance" in tools
    assert "run_anti_overfit" in tools
    assert "run_rolling_validation" in tools
    assert "cross_review_assistant_response" in tools
    assert "query_expression_index" in tools
    assert "query_research_observability" in tools
    assert "run_simulation_batch" in tools
    assert "run_parallel_backtest" in tools
    assert "score_factor" in tools
    assert "run_backtest" in tools
    assert "run_batch_backtest" in tools
    assert "submit_alpha" in tools
    assert tools["submit_alpha"].destructive is True
    assert tools["run_simulation"].live_api is True
    assert tools["run_simulation_batch"].live_api is True
    assert tools["run_parallel_backtest"].live_api is True
    assert tools["score_factor"].alias_for == "score_candidate"
    assert tools["run_backtest"].alias_for == "run_simulation"
    assert tools["run_batch_backtest"].alias_for == "run_simulation_batch"
    assert tools["score_factor"].category == "scoring"
    assert tools["run_backtest"].chain_stage == "deep_validate"
    assert tools["run_simulation_batch"].input_schema["required"] == ["expressions"]
    assert tools["run_anti_overfit"].input_schema["required"] == ["candidate"]
    assert tools["cross_review_assistant_response"].input_schema["required"] == ["request_pack", "primary_response"]
    assert tool_aliases()["score_factor"] == "score_candidate"
    assert resolve_tool_name("run_backtest") == "run_simulation"
    assert resolve_tool_name("run_batch_backtest") == "run_simulation_batch"


def test_agent_toolbox_lists_context_and_generates_candidates(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    context = toolbox.call("list_context", {"limit": 5})
    generated = toolbox.call("generate_candidates", {"count": 3})

    assert context["ok"] is True
    assert context["fields_count"] > 0
    assert context["operators_count"] > 0
    assert generated["ok"] is True
    assert 1 <= generated["count"] <= 3
    assert generated["candidates"][0]["expression"]


def test_agent_toolbox_unknown_tool_returns_structured_error(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("missing_tool")

    assert result["ok"] is False
    assert result["error_code"] == "TOOL_NOT_FOUND"
    assert result["error_category"] == "validation"
    assert result["retryable"] is False
    assert result["error_type"] == "ValueError"


def test_agent_toolbox_handler_errors_are_classified_and_redacted(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("score_candidate", {})

    assert result["ok"] is False
    assert result["error_code"] == "TOOL_ERROR"
    assert result["error_category"] == "validation"
    assert result["error_type"] == "ValueError"


def test_agent_toolbox_generate_candidates_uses_research_memory_guidance(tmp_path, monkeypatch):
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
    toolbox = production_toolbox(storage_dir=tmp_path)

    captured = {}

    def fake_set_experience_guidance(self, patterns):
        captured["patterns"] = patterns

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)
    toolbox.call("generate_candidates", {"count": 2})

    assert captured["patterns"]["sample_size"] == 1
    assert "top_operators" in captured["patterns"]
    assert "preferred_windows" in captured["patterns"]


def test_agent_toolbox_generate_candidates_uses_assistant_response_guidance(tmp_path, monkeypatch):
    toolbox = production_toolbox(storage_dir=tmp_path)
    raw_output = (
        '{"summary":"Prefer stable close momentum.",'
        '"recommended_next_actions":["generate candidates"],'
        '"risk_flags":[],'
        '"candidate_adjustments":['
        '{"target":"fields","value":["close"],"rationale":"memory"},'
        '{"target":"operators","value":["rank","ts_delta"],"rationale":"memory"},'
        '{"target":"windows","value":[20,60],"rationale":"lookback"}'
        '],'
        '"follow_up_questions":[],"confidence":0.82}'
    )
    captured = {}

    def fake_set_experience_guidance(self, patterns):
        captured["patterns"] = patterns

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)

    result = toolbox.call(
        "generate_candidates",
        {
            "count": 2,
            "use_research_memory": False,
            "assistant_response": raw_output,
            "assistant_min_confidence": 0.7,
        },
    )

    assert result["ok"] is True
    assert result["assistant_guidance"]["applied"] is True
    assert result["assistant_guidance"]["guidance_digest"].startswith("ag_")
    assert result["assistant_guidance"]["reason"] == "applied_to_generator"
    assert captured["patterns"]["sample_size"] == 3
    assert captured["patterns"]["top_operators"] == ["rank", "ts_delta"]
    assert captured["patterns"]["preferred_windows"] == [20, 60]
    assert captured["patterns"]["field_combinations"] == [{"fields": ["close"], "rationale": "assistant top fields"}]
    if result["candidates"]:
        assert result["candidates"][0]["submission"]["assistant_guidance_digest"].startswith("ag_")


def test_agent_toolbox_generate_candidates_skips_low_confidence_assistant_guidance(tmp_path, monkeypatch):
    toolbox = production_toolbox(storage_dir=tmp_path)
    raw_output = (
        '{"summary":"Weak hint.",'
        '"recommended_next_actions":[],'
        '"risk_flags":[],'
        '"candidate_adjustments":[{"target":"operators","value":["rank"],"rationale":"thin evidence"}],'
        '"follow_up_questions":[],"confidence":0.35}'
    )
    captured = {"calls": 0}

    def fake_set_experience_guidance(self, patterns):
        captured["calls"] += 1

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)

    result = toolbox.call(
        "generate_candidates",
        {
            "count": 2,
            "use_research_memory": False,
            "assistant_response": raw_output,
            "assistant_min_confidence": 0.7,
        },
    )

    assert result["ok"] is True
    assert result["assistant_guidance"]["usable"] is False
    assert result["assistant_guidance"]["applied"] is False
    assert result["assistant_guidance"]["reason"] == "not_usable"
    assert captured["calls"] == 0


def test_agent_toolbox_generate_candidates_accepts_structured_assistant_guidance(tmp_path, monkeypatch):
    toolbox = production_toolbox(storage_dir=tmp_path)
    captured = {}

    def fake_set_experience_guidance(self, patterns):
        captured["patterns"] = patterns

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)

    result = toolbox.call(
        "generate_candidates",
        {
            "count": 2,
            "use_research_memory": False,
            "assistant_min_confidence": 0.6,
            "assistant_guidance": {
                "confidence": 0.75,
                "top_fields": ["volume"],
                "top_operators": ["ts_rank"],
                "preferred_windows": [10],
                "historical_outcome_status": "strong",
                "historical_outcome": {
                    "count": 3,
                    "success_count": 2,
                    "success_rate": 0.667,
                    "avg_score": 81.5,
                    "avg_sharpe": 1.4,
                },
            },
        },
    )

    assert result["ok"] is True
    assert result["assistant_guidance"]["applied"] is True
    assert result["assistant_guidance"]["guidance_digest"].startswith("ag_")
    assert result["assistant_guidance"]["source"] == "assistant_guidance_argument"
    assert captured["patterns"]["sample_size"] == 3
    assert captured["patterns"]["top_operators"] == ["ts_rank"]
    assert captured["patterns"]["preferred_windows"] == [10]
    assert captured["patterns"]["field_combinations"] == [{"fields": ["volume"], "rationale": "assistant top fields"}]
    assert result["assistant_guidance"]["historical_outcome_status"] == "strong"
    assert result["assistant_guidance"]["historical_outcome"]["success_rate"] == 0.667
    if result["candidates"]:
        submission = result["candidates"][0]["submission"]
        assert submission["assistant_guidance_outcome_status"] == "strong"
        assert submission["assistant_guidance_outcome_success_rate"] == 0.667
        assert submission["assistant_guidance_outcome"]["avg_score"] == 81.5


def test_agent_toolbox_builds_assistant_context_pack(tmp_path):
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
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("build_assistant_context", {"top_n": 3, "include_prompt": True})

    assert result["ok"] is True
    assert result["schema_version"] == "assistant_context_pack.v1"
    assert result["generation_focus"]["operators"] == ["rank", "ts_delta"]
    assert "WorldQuant BRAIN FASTEXPR" in result["prompt"]
    assert "storage_dir" not in result
    assert "storage_dir" in result["sensitive_fields_redacted"]

    sensitive = toolbox.call("build_assistant_context", {"top_n": 3, "include_prompt": False, "include_sensitive": True})
    assert sensitive["storage_dir"] == str(tmp_path)


def test_agent_toolbox_builds_assistant_request_pack(tmp_path):
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
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("build_assistant_request", {"top_n": 3})

    assert result["ok"] is True
    assert result["schema_version"] == "assistant_request_pack.v1"
    assert result["request"]["response_schema"]["schema_version"] == "assistant_response.v1"
    assert result["offline_draft"]["recommended_next_actions"]


def test_agent_toolbox_queries_expression_index(tmp_path):
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
    toolbox = production_toolbox(storage_dir=tmp_path)

    summary = toolbox.call("query_expression_index", {"top_n": 3})
    lookup = toolbox.call("query_expression_index", {"expression": " Rank ( TS_Delta ( Close , 20 ) ) "})

    assert summary["ok"] is True
    assert summary["schema_version"] == "expression-index.v1"
    assert summary["unique_expression_count"] == 1
    assert lookup["exact_match"] is True
    assert lookup["exact_records"][0]["alpha_id"] == "a1"


def test_agent_toolbox_queries_research_observability(tmp_path):
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
    repo.save_backtest_record(
        "run_1",
        {
            "action": "simulation_result",
            "alpha_id": "a1",
            "status": "simulation_failed",
            "expression": "rank(ts_delta(close, 20))",
            "note": "rate limit retry pending",
        },
    )
    repo.save_lifecycle_record(
        "run_1",
        {
            "alpha_id": "dup_guard",
            "stage": "observability_duplicate_blocked",
            "status": "observability_duplicate_blocked",
            "note": "official_simulation",
            "family": "Momentum",
            "score": 82,
            "expression": "rank(ts_delta(close, 20))",
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_simulation"],
            },
        },
    )
    store = JobStore()
    job_id = store.create()
    store.update(job_id, status="failed", error="Too many requests", progress={"error_context": {"error_category": "rate_limit", "error_code": "RUN_JOB_FAILED", "retryable": True}})
    toolbox = production_toolbox(storage_dir=tmp_path, job_stores={"production": store})

    result = toolbox.call("query_research_observability", {"top_n": 3, "include_cloud": False})

    assert result["ok"] is True
    assert result["schema_version"] == "research_observability_snapshot.v1"
    assert result["backtests"]["failed_count"] == 1
    assert result["errors"]["category_counts"]["rate_limit"] >= 1
    assert result["health"]["risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in result["health"]["health_flags"]
    assert "retryable_official_errors_present" in result["health"]["warning_flags"]
    assert result["official_call_guard"]["blocked_count"] == 1
    assert result["official_call_guard"]["simulation_blocked_count"] == 1


def test_agent_toolbox_parses_assistant_response(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    raw_output = (
        '{"summary":"Use memory-guided momentum ideas.",'
        '"recommended_next_actions":["generate candidates"],'
        '"risk_flags":["submit_requires_confirmation"],'
        '"candidate_adjustments":[{"target":"fields","value":["close"],"rationale":"memory"}],'
        '"follow_up_questions":[],"confidence":0.7}'
    )

    result = toolbox.call("parse_assistant_response", {"raw_output": raw_output})

    assert result["ok"] is True
    assert result["summary"].startswith("Use memory")
    assert result["candidate_adjustments"][0]["target"] == "fields"


def test_agent_toolbox_converts_assistant_response_to_guidance(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    raw_output = (
        '{"summary":"Use close momentum.",'
        '"recommended_next_actions":["refresh cloud cache"],'
        '"risk_flags":["submit_requires_confirmation"],'
        '"candidate_adjustments":['
        '{"target":"fields","value":["close"],"rationale":"memory"},'
        '{"target":"operators","value":["rank","ts_delta"],"rationale":"memory"},'
        '{"target":"windows","value":[20],"rationale":"lookback"}'
        '],'
        '"confidence":0.8}'
    )

    result = toolbox.call("assistant_response_guidance", {"raw_output": raw_output, "min_confidence": 0.7})

    assert result["ok"] is True
    assert result["usable"] is True
    assert result["top_fields"] == ["close"]
    assert result["top_operators"] == ["rank", "ts_delta"]
    assert result["preferred_windows"] == [20]
    assert result["operational_flags"]["refresh_cloud_before_submit"] is True


def test_agent_toolbox_parse_error_is_structured(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("parse_assistant_response", {"raw_output": "not json"})

    assert result["ok"] is False
    assert result["error_code"] == "ASSISTANT_RESPONSE_PARSE_ERROR"
    assert result["error_category"] == "validation"
    assert result["error_type"] == "AssistantResponseParseError"


def test_agent_toolbox_runs_anti_overfit_and_rolling_validation(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    candidate = {
        "alpha_id": "a1",
        "expression": "rank(ts_delta(close, 20))",
        "official_metrics": {
            "ic_series": [0.03, 0.035, 0.04, 0.025] * 20,
            "rolling_fitness": [1.0, 1.1, 1.0, 0.9, 0.85, 0.8, 0.75, 0.7],
        },
        "submission": {},
    }

    anti = toolbox.call("run_anti_overfit", {"candidate": candidate})
    rolling = toolbox.call("run_rolling_validation", {"candidate": candidate, "windows": 4})

    assert anti["ok"] is True
    assert anti["schema_version"] == "anti_overfit_report.v1"
    assert rolling["ok"] is True
    assert rolling["schema_version"] == "rolling_validation_report.v1"


def test_agent_toolbox_cross_reviews_assistant_response(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    response = (
        '{"summary":"Keep cloud cache fresh.",'
        '"recommended_next_actions":["refresh cloud cache"],'
        '"risk_flags":["cloud_sync_required"],'
        '"candidate_adjustments":[],"follow_up_questions":[],"confidence":0.9}'
    )

    result = toolbox.call(
        "cross_review_assistant_response",
        {
            "request_pack": {"prompt_digest": "pd_1"},
            "primary_response": response,
            "reviewer_response": response,
            "min_confidence": 0.7,
        },
    )

    assert result["ok"] is True
    assert result["decision"] == "accept"


def test_agent_toolbox_validates_and_scores_expression(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    expression = "rank(ts_delta(close, 20))"

    validation = toolbox.call("validate_expression", {"expression": expression})
    score = toolbox.call("score_candidate", {"expression": expression, "family": "Momentum"})

    assert validation["ok"] is True
    assert "local" in validation
    assert score["ok"] is True
    assert score["scorecard"]["total_score"] > 0
    assert score["candidate"]["operators"] == ["rank", "ts_delta"]


def test_agent_toolbox_quantgpt_style_aliases_follow_score_then_backtest_chain(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)
    expression = "rank(ts_delta(close, 20))"

    score = toolbox.call("score_factor", {"expression": expression, "family": "Momentum"})
    backtest = toolbox.call("run_backtest", {"expression": expression, "confirm_live_api": True})

    assert score["ok"] is True
    assert score["tool_alias"] == "score_factor"
    assert score["canonical_tool"] == "score_candidate"
    assert score["scorecard"]["total_score"] > 0
    assert backtest["ok"] is True
    assert backtest["tool_alias"] == "run_backtest"
    assert backtest["canonical_tool"] == "run_simulation"
    assert backtest["simulation_id"].startswith("prod_stub_sim_")


def test_agent_toolbox_runs_production_stub_simulation_without_live_confirmation(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call("run_simulation", {"expression": "rank(ts_delta(close, 20))"})

    assert result["ok"] is False
    assert result["error_code"] == "LIVE_API_NOT_ALLOWED"


def test_agent_toolbox_runs_production_stub_simulation_with_confirmation(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call(
        "run_simulation",
        {"expression": "rank(ts_delta(close, 20))", "confirm_live_api": True},
    )

    assert result["ok"] is True
    assert result["simulation_id"].startswith("prod_stub_sim_")
    assert result["result"]["alpha_id"].startswith("prod_stub_alpha_")


def test_agent_toolbox_runs_bounded_production_stub_simulation_batch(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call(
        "run_batch_backtest",
        {
            "expressions": [
                "rank(ts_delta(close, 20))",
                "rank(ts_mean(volume, 10))",
                "rank(ts_mean(volume, 10))",
                "rank(ts_delta(open, 5))",
            ],
            "max_batch_size": 2,
            "max_workers": 2,
            "confirm_live_api": True,
        },
    )

    assert result["ok"] is True
    assert result["tool_alias"] == "run_batch_backtest"
    assert result["canonical_tool"] == "run_simulation_batch"
    assert result["schema_version"] == "agent_simulation_batch_result.v1"
    assert result["requested_count"] == 3
    assert result["selected_count"] == 2
    assert result["submitted_count"] == 2
    assert result["completed_count"] == 2
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "batch_size_limit"
    assert [item["index"] for item in result["results"]] == [0, 1]
    assert all(item["simulation_id"].startswith("prod_stub_sim_") for item in result["results"])


def test_agent_toolbox_batch_simulation_reports_item_failures(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call(
        "run_simulation_batch",
        {
            "expressions": [
                "rank(ts_delta(close, 20))",
                "rank(ts_delta(close, 20)",
            ],
            "max_workers": 2,
            "confirm_live_api": True,
        },
    )

    assert result["ok"] is False
    assert result["submitted_count"] == 1
    assert result["failed_count"] == 1
    failed = [item for item in result["results"] if not item["ok"]][0]
    assert failed["error_code"] == "VALIDATION_FAILED"
    assert failed["index"] == 1


def test_agent_toolbox_batch_simulation_counts_terminal_failed_status(tmp_path):
    class FailedSimulationAPI(ProductionBrainAPIStub):
        def poll_simulation(self, simulation_id):
            return "FAILED"

    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(run_config=config, api=FailedSimulationAPI(), allow_live_api=True)

    result = toolbox.call(
        "run_simulation_batch",
        {"expressions": ["rank(ts_delta(close, 20))"], "confirm_live_api": True},
    )

    assert result["ok"] is False
    assert result["submitted_count"] == 1
    assert result["completed_count"] == 0
    assert result["failed_count"] == 1
    assert result["results"][0]["ok"] is False
    assert result["results"][0]["error_code"] == "SIMULATION_FAILED"
    assert result["results"][0]["status"] == "FAILED"


def test_agent_toolbox_runs_bounded_production_stub_parallel_backtest(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path)

    result = toolbox.call(
        "run_parallel_backtest",
        {
            "expressions": ["rank(ts_delta(close, 20))", "rank(ts_mean(volume, 10))"],
            "markets": ["USA", "EUR"],
            "max_workers": 2,
            "max_batches": 1,
            "per_account_limit": 3,
            "confirm_live_api": True,
        },
    )

    assert result["ok"] is True
    assert result["schema_version"] == "parallel_backtest_execution.v1"
    assert result["requested_jobs"] == 4
    assert result["selected_jobs"] == 3
    assert result["skipped_jobs"] == 1
    assert result["submitted_count"] == 3
    assert result["completed_count"] == 3
    assert {item["market"] for item in result["results"]} <= {"USA", "EUR"}
    assert all(item["settings"]["region"] in {"USA", "EUR"} for item in result["results"])


def test_agent_toolbox_blocks_production_simulation_batch_without_confirmation(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub(), allow_live_api=False)

    result = toolbox.call(
        "run_simulation_batch",
        {"expressions": ["rank(ts_delta(close, 20))"]},
    )

    assert result["ok"] is False
    assert result["error_code"] == "LIVE_API_NOT_ALLOWED"
    assert result["tool"] == "run_simulation_batch"


def test_agent_toolbox_blocks_production_parallel_backtest_without_confirmation(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub(), allow_live_api=False)

    result = toolbox.call(
        "run_parallel_backtest",
        {"expressions": ["rank(ts_delta(close, 20))"], "markets": ["USA"]},
    )

    assert result["ok"] is False
    assert result["error_code"] == "LIVE_API_NOT_ALLOWED"
    assert result["tool"] == "run_parallel_backtest"


def test_agent_toolbox_blocks_production_live_api_without_confirmation(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    toolbox = BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub(), allow_live_api=False)

    result = toolbox.call("sync_cloud_alphas", {"sync_range": "3d"})

    assert result["ok"] is False
    assert result["error_code"] == "LIVE_API_NOT_ALLOWED"


def test_agent_toolbox_blocks_duplicate_expression_before_live_validation(tmp_path):
    expression = "rank(ts_delta(close, 20))"
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "historical_alpha",
            "status": "SUBMITTED",
            "expression": expression,
        },
    )
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    called = {"validate": 0}

    class FailIfCalledAPI(ProductionBrainAPIStub):
        def validate_expression(self, expression, settings):
            called["validate"] += 1
            return super().validate_expression(expression, settings)

    toolbox = BrainAlphaToolbox(
        run_config=config,
        api=FailIfCalledAPI(),
        allow_live_api=True,
    )

    result = toolbox.call(
        "validate_expression",
        {"expression": expression, "use_api": True, "confirm_live_api": True},
    )

    assert result["ok"] is True
    assert result["api"]["ok"] is False
    assert result["api"]["error_code"] == "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED"
    assert result["api"]["expression_canonical"] == expression_key(expression)
    assert result["api"]["exact_count"] >= 1
    assert result["api"]["matching_records"][0]["alpha_id"] == "historical_alpha"
    assert "expression_fingerprint" in result["api"]["matching_records"][0]
    assert "secret" not in result["api"]
    assert called["validate"] == 0


def test_agent_toolbox_blocks_duplicate_expression_before_live_simulation(tmp_path):
    expression = "rank(ts_delta(close, 20))"
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "historical_alpha",
            "status": "SUBMITTED",
            "expression": expression,
        },
    )
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    called = {"submit": 0}

    class FailIfCalledAPI(ProductionBrainAPIStub):
        def submit_simulation(self, expression, settings):
            called["submit"] += 1
            return super().submit_simulation(expression, settings)

    toolbox = BrainAlphaToolbox(
        run_config=config,
        api=FailIfCalledAPI(),
        allow_live_api=True,
    )

    result = toolbox.call(
        "run_simulation",
        {"expression": expression, "confirm_live_api": True},
    )

    assert result["ok"] is False
    assert result["error_code"] == "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED"
    assert result["expression_canonical"] == expression_key(expression)
    assert result["exact_count"] >= 1
    assert result["matching_records"][0]["alpha_id"] == "historical_alpha"
    assert "expression_fingerprint" in result["matching_records"][0]
    assert "secret" not in result
    assert called["submit"] == 0


def test_agent_toolbox_batch_blocks_duplicate_expression_items_before_live_simulation(tmp_path):
    expression = "rank(ts_delta(close, 20))"
    repo = ResearchRepository(str(tmp_path))
    repo.save_backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "historical_alpha",
            "status": "SUBMITTED",
            "expression": expression,
        },
    )
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    called = {"submit": 0}

    class CountSubmitAPI(ProductionBrainAPIStub):
        def submit_simulation(self, expression, settings):
            called["submit"] += 1
            return super().submit_simulation(expression, settings)

    toolbox = BrainAlphaToolbox(
        run_config=config,
        api=CountSubmitAPI(),
        allow_live_api=True,
    )

    result = toolbox.call(
        "run_simulation_batch",
        {
            "expressions": [
                expression,
                "rank(ts_delta(open, 5))",
            ],
            "confirm_live_api": True,
            "max_workers": 1,
        },
    )

    assert result["ok"] is False
    assert result["submitted_count"] == 1
    assert result["failed_count"] == 1
    assert result["results"][0]["error_code"] == "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED"
    assert result["results"][0]["expression_canonical"] == expression_key(expression)
    assert result["results"][1]["ok"] is True
    assert called["submit"] == 1


def test_agent_toolbox_blocks_live_api_when_duplicate_preflight_fails(monkeypatch, tmp_path):
    expression = "rank(ts_delta(close, 20))"
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    called = {"validate": 0, "submit": 0}

    class FailIfCalledAPI(ProductionBrainAPIStub):
        def validate_expression(self, expression, settings):
            called["validate"] += 1
            return super().validate_expression(expression, settings)

        def submit_simulation(self, expression, settings):
            called["submit"] += 1
            return super().submit_simulation(expression, settings)

    def fail_lookup(self, *args, **kwargs):
        raise RuntimeError("index damaged token=SECRET123")

    monkeypatch.setattr("brain_alpha_ops.agent_tools.ExpressionHistoryIndex.lookup", fail_lookup)
    toolbox = BrainAlphaToolbox(
        run_config=config,
        api=FailIfCalledAPI(),
        allow_live_api=True,
    )

    validation = toolbox.call(
        "validate_expression",
        {"expression": expression, "use_api": True, "confirm_live_api": True},
    )
    simulation = toolbox.call(
        "run_simulation",
        {"expression": expression, "confirm_live_api": True},
    )

    assert validation["ok"] is True
    assert validation["api"]["ok"] is False
    assert validation["api"]["error_code"] == "OBSERVABILITY_DUPLICATE_PREFLIGHT_UNAVAILABLE"
    assert validation["api"]["detail"] == "index damaged token=<redacted>"
    assert simulation["ok"] is False
    assert simulation["error_code"] == "OBSERVABILITY_DUPLICATE_PREFLIGHT_UNAVAILABLE"
    assert simulation["detail"] == "index damaged token=<redacted>"
    assert called == {"validate": 0, "submit": 0}


def test_agent_toolbox_requires_submit_double_confirmation(tmp_path):
    toolbox = production_toolbox(storage_dir=tmp_path, allow_submit=False)

    result = toolbox.call(
        "submit_alpha",
        {"alpha_id": "prod_stub_alpha_0001", "expression": "rank(ts_delta(close, 20))"},
    )

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_NOT_ALLOWED"


def test_agent_toolbox_reads_configured_job_status(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job_id = store.create()
    store.update(job_id, status="running", progress={"phase": "simulation", "percent": 50})
    toolbox = production_toolbox(storage_dir=tmp_path, job_stores={"production": store})

    result = toolbox.call("get_job_status", {"kind": "production", "job_id": job_id})

    assert result["ok"] is True
    assert result["job_id"] == job_id
    assert result["status"] == "running"
