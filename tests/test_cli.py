import json

from brain_alpha_ops.cli import main
from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository


def test_cli_memory_summary_prints_json(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    repo = ResearchRepository(config.ops.storage_dir)
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

    code = main(["memory-summary", "--config", str(config_path), "--top-n", "3"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_candidates"] == 1
    assert payload["fields"][0]["name"] == "close"


def test_cli_memory_summary_writes_file(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    ResearchRepository(config.ops.storage_dir).save_candidate(
        "run_1",
        Candidate(alpha_id="a1", expression="rank(close)", family="Value", hypothesis="value"),
    )

    code = main(["memory-summary", "--config", str(config_path), "--write"])
    output = capsys.readouterr().out.strip()

    assert code == 0
    assert output.endswith("research_memory_summary.json")


def test_cli_memory_guidance_prints_generator_ready_json(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    ResearchRepository(config.ops.storage_dir).save_candidate(
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

    code = main(["memory-guidance", "--config", str(config_path), "--top-n", "3"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sample_size"] == 1
    assert payload["top_operators"] == ["rank", "ts_delta"]
    assert payload["preferred_windows"] == [20]
    assert payload["field_combinations"][0]["fields"] == ["close"]


def test_cli_expression_index_prints_summary_and_lookup(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    repo = ResearchRepository(config.ops.storage_dir)
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

    code = main(["expression-index", "--config", str(config_path), "--top-n", "3"])
    summary = json.loads(capsys.readouterr().out)
    lookup_code = main([
        "expression-index",
        "--config",
        str(config_path),
        "--expression",
        " Rank ( TS_Delta ( Close , 20 ) ) ",
    ])
    lookup = json.loads(capsys.readouterr().out)

    assert code == 0
    assert summary["schema_version"] == "expression-index.v1"
    assert summary["unique_expression_count"] == 1
    assert lookup_code == 0
    assert lookup["exact_match"] is True
    assert lookup["exact_records"][0]["alpha_id"] == "a1"


def test_cli_expression_index_can_use_sqlite_cache(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    ResearchRepository(config.ops.storage_dir).save_candidate(
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

    code = main(["expression-index", "--config", str(config_path), "--sqlite", "--top-n", "3"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == "expression-sqlite-index.v1"
    assert payload["refresh"]["record_count"] == 1
    assert payload["unique_expression_count"] == 1


def test_cli_record_index_refreshes_and_looks_up_records(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    repo = ResearchRepository(config.ops.storage_dir)
    repo.merge_cloud_alphas(
        [
            {
                "id": "cloud_a1",
                "status": "SUBMITTED",
                "expression": "rank(close)",
                "metrics": {"official_alpha_id": "off_a1"},
            }
        ],
        sync_range="3d",
    )
    repo.save_backtest_record(
        "run_1",
        {
            "action": "completed",
            "alpha_id": "local_a1",
            "official_alpha_id": "off_a1",
            "simulation_id": "sim_a1",
            "expression": "rank(close)",
        },
    )

    summary_code = main(["record-index", "--config", str(config_path), "--refresh"])
    summary = json.loads(capsys.readouterr().out)
    lookup_code = main(["record-index", "--config", str(config_path), "--alpha-id", "off_a1"])
    lookup = json.loads(capsys.readouterr().out)

    assert summary_code == 0
    assert summary["schema_version"] == "record-sqlite-index.v1"
    assert summary["refresh"]["record_count"] == 2
    assert lookup_code == 0
    assert lookup["count"] == 2
    assert {row["kind"] for row in lookup["records"]} == {"cloud_alpha", "backtest_record"}


def test_cli_research_observability_prints_health_snapshot(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    repo = ResearchRepository(config.ops.storage_dir)
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
            "note": "official_validation",
            "family": "Momentum",
            "score": 90,
            "expression": "rank(ts_delta(close, 20))",
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_validation"],
            },
        },
    )

    code = main(["research-observability", "--config", str(config_path), "--top-n", "3", "--no-cloud"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == "research_observability_snapshot.v1"
    assert payload["expression_index"]["duplicate_expression_count"] == 1
    assert payload["backtests"]["retryable_count"] == 1
    assert payload["official_call_guard"]["blocked_count"] == 1
    assert payload["official_call_guard"]["validation_blocked_count"] == 1
    assert "health" in payload
    assert payload["health"]["risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in payload["health"]["health_flags"]


def test_cli_assistant_context_prints_json(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    ResearchRepository(config.ops.storage_dir).save_candidate(
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

    code = main(["assistant-context", "--config", str(config_path), "--top-n", "3"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "assistant_context_pack.v1"
    assert payload["generation_focus"]["operators"] == ["rank", "ts_delta"]
    assert "WorldQuant BRAIN FASTEXPR" in payload["prompt"]


def test_cli_assistant_context_prompt_only(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    code = main(["assistant-context", "--config", str(config_path), "--prompt-only"])

    assert code == 0
    output = capsys.readouterr().out
    assert output.startswith("You are the quant investment AI assistant")
    assert "schema_version" not in output


def test_cli_assistant_request_prints_llm_envelope(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    ResearchRepository(config.ops.storage_dir).save_candidate(
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

    code = main(["assistant-request", "--config", str(config_path), "--top-n", "3"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "assistant_request_pack.v1"
    assert payload["request"]["messages"][0]["role"] == "system"
    assert payload["request"]["response_schema"]["schema_version"] == "assistant_response.v1"
    assert payload["offline_draft"]["candidate_adjustments"]


def test_cli_assistant_request_can_omit_prompt_and_draft(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    code = main(["assistant-request", "--config", str(config_path), "--no-prompt", "--no-draft"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "prompt" not in payload
    assert "offline_draft" not in payload


def test_cli_assistant_parse_reads_response_file(tmp_path, capsys):
    response_path = tmp_path / "assistant_response.txt"
    response_path.write_text(
        '```json\n{"summary":"Use memory guidance.","actions":["rank candidates"],"risks":["cloud_sync_required"],"confidence":75}\n```',
        encoding="utf-8",
    )

    code = main(["assistant-parse", "--input", str(response_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"] == "Use memory guidance."
    assert payload["recommended_next_actions"] == ["rank candidates"]
    assert payload["risk_flags"] == ["cloud_sync_required"]
    assert payload["confidence"] == 0.75


def test_cli_assistant_parse_reports_invalid_json(tmp_path, capsys):
    response_path = tmp_path / "bad_response.txt"
    response_path.write_text("not json", encoding="utf-8")

    code = main(["assistant-parse", "--input", str(response_path)])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == "ASSISTANT_RESPONSE_PARSE_ERROR"
    assert payload["error_category"] == "validation"
    assert payload["retryable"] is False
    assert payload["error_type"] == "AssistantResponseParseError"


def test_cli_assistant_guidance_maps_response_to_generator_fields(tmp_path, capsys):
    response_path = tmp_path / "assistant_response.txt"
    response_path.write_text(
        json.dumps(
            {
                "summary": "Use close momentum.",
                "actions": ["refresh cloud cache"],
                "risks": ["submit_requires_confirmation"],
                "candidate_adjustments": [
                    {"target": "fields", "value": ["close"], "rationale": "memory"},
                    {"target": "operators", "value": ["rank", "ts_delta"], "rationale": "memory"},
                    {"target": "windows", "value": [20], "rationale": "lookback"},
                ],
                "confidence": 0.8,
            }
        ),
        encoding="utf-8",
    )

    code = main(["assistant-guidance", "--input", str(response_path), "--min-confidence", "0.7"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "assistant_generation_guidance.v1"
    assert payload["usable"] is True
    assert payload["top_fields"] == ["close"]
    assert payload["top_operators"] == ["rank", "ts_delta"]
    assert payload["preferred_windows"] == [20]


def test_cli_assistant_save_guidance_persists_response_guidance(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    response_path = tmp_path / "assistant_response.txt"
    response_path.write_text(
        json.dumps(
            {
                "summary": "Reuse close momentum.",
                "candidate_adjustments": [
                    {"target": "fields", "value": ["close"], "rationale": "memory"},
                    {"target": "operators", "value": ["rank"], "rationale": "memory"},
                ],
                "confidence": 0.9,
            }
        ),
        encoding="utf-8",
    )

    code = main([
        "assistant-save-guidance",
        "--config",
        str(config_path),
        "--input",
        str(response_path),
        "--min-confidence",
        "0.7",
    ])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["saved"] is True
    path = tmp_path / "data" / "assistant_guidance.jsonl"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["source"] == "cli_save_assistant_guidance"
    assert row["guidance_digest"].startswith("ag_")
    assert row["guidance"]["guidance_digest"] == row["guidance_digest"]
    assert row["guidance"]["top_fields"] == ["close"]
    assert row["guidance"]["top_operators"] == ["rank"]


def test_cli_assistant_save_guidance_skips_low_confidence(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    response_path = tmp_path / "assistant_response.txt"
    response_path.write_text(
        json.dumps(
            {
                "summary": "Weak operator hint.",
                "candidate_adjustments": [{"target": "operators", "value": ["rank"], "rationale": "thin"}],
                "confidence": 0.2,
            }
        ),
        encoding="utf-8",
    )

    code = main([
        "assistant-save-guidance",
        "--config",
        str(config_path),
        "--input",
        str(response_path),
        "--min-confidence",
        "0.7",
    ])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["saved"] is False
    assert payload["reason"] == "confidence_below_threshold"
    assert not (tmp_path / "data" / "assistant_guidance.jsonl").exists()


def test_cli_anti_overfit_and_rolling_validate_print_reports(tmp_path, capsys):
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(
            {
                "alpha_id": "a1",
                "expression": "rank(ts_delta(close, 20))",
                "official_metrics": {
                    "ic_series": [0.03, 0.035, 0.04, 0.025] * 20,
                    "rolling_fitness": [1.0, 1.1, 1.0, 0.9, 0.85, 0.8, 0.75, 0.7],
                },
                "submission": {},
            }
        ),
        encoding="utf-8",
    )

    anti_code = main(["anti-overfit", "--candidate-json", str(candidate_path)])
    anti = json.loads(capsys.readouterr().out)
    rolling_code = main(["rolling-validate", "--candidate-json", str(candidate_path), "--windows", "4"])
    rolling = json.loads(capsys.readouterr().out)

    assert anti_code == 0
    assert anti["schema_version"] == "anti_overfit_report.v1"
    assert rolling_code == 0
    assert rolling["schema_version"] == "rolling_validation_report.v1"


def test_cli_assistant_cross_review_can_record_ledger(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"prompt_digest": "pd_1"}), encoding="utf-8")
    response_path = tmp_path / "response.txt"
    response_path.write_text(
        '{"summary":"Keep cloud cache fresh.",'
        '"recommended_next_actions":["refresh cloud cache"],'
        '"risk_flags":["cloud_sync_required"],'
        '"candidate_adjustments":[],"follow_up_questions":[],"confidence":0.9}',
        encoding="utf-8",
    )

    code = main(
        [
            "assistant-cross-review",
            "--config",
            str(config_path),
            "--request-json",
            str(request_path),
            "--primary-response",
            str(response_path),
            "--reviewer-response",
            str(response_path),
            "--record-ledger",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["decision"] == "accept"
    assert (tmp_path / "data" / "prompt_runs.jsonl").is_file()


def test_cli_assistant_guidance_audit_reports_scoring_eligibility(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.budget.assistant_guidance_min_confidence = 0.7
    config.ops.scoring.assistant_guidance_score_min_confidence = 0.8
    config.ops.scoring.assistant_guidance_score_min_outcome_count = 1
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    repo = ResearchRepository(config.ops.storage_dir)
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.9,
            "guidance_digest": "ag_cli_audit",
            "top_fields": ["close"],
            "top_operators": ["rank"],
            "preferred_windows": [20],
        },
        source="audit_test",
    )
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="guided_cli",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="guided cli audit",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            source_tags=["assistant_guided"],
            submission={"assistant_guidance_digest": "ag_cli_audit"},
            official_metrics={"pass_fail": "PASS", "sharpe": 1.6, "fitness": 1.1},
            scorecard={"total_score": 82},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )

    code = main(["assistant-guidance-audit", "--config", str(config_path), "--limit", "50"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "assistant_guidance_audit.v1"
    assert payload["configured_min_confidence"] == 0.7
    assert payload["scoring_policy"]["min_confidence"] == 0.8
    assert payload["latest_guidance"]["guidance_digest"] == "ag_cli_audit"
    assert payload["latest_score_adjustment_eligibility"]["eligible"] is True
    assert payload["latest_score_adjustment_eligibility"]["adjustment_direction"] == "bonus"
    assert payload["history"][0]["score_adjustment_eligible"] is True
    assert payload["history"][0]["historical_outcome_status"] == "strong"


def test_cli_validate_config_reports_valid_config(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    code = main(["validate-config", "--config", str(config_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["schema_version"] == "config_validation.v1"
    assert payload["environment"] == "mock"


def test_cli_validate_config_reports_validation_error(tmp_path, capsys):
    config_path = tmp_path / "bad_run_config.json"
    config_path.write_text(json.dumps({"ops": {"settings": {"region": "MARS"}}}), encoding="utf-8")

    code = main(["validate-config", "--config", str(config_path)])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == "CONFIG_VALIDATION_ERROR"
    assert payload["error_category"] == "validation"
    assert "ops.settings.region" in payload["error"]


def test_cli_validate_config_reports_json_error(tmp_path, capsys):
    config_path = tmp_path / "bad_json.json"
    config_path.write_text("{not-json", encoding="utf-8")

    code = main(["validate-config", "--config", str(config_path)])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == "CONFIG_JSON_ERROR"
    assert payload["error_category"] == "validation"
    assert payload["error_type"] == "JSONDecodeError"


def test_cli_run_validates_overridden_arguments(tmp_path, capsys):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    code = main(["run", "--config", str(config_path), "--candidates", "0"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == "CONFIG_VALIDATION_ERROR"
    assert "max_candidates_per_cycle" in payload["error"]


def test_cli_run_rejects_command_line_credentials_in_production(tmp_path, capsys):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    code = main(["run", "--config", str(config_path), "--token", "secret-token"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "CONFIG_VALIDATION_ERROR"
    assert "command-line credentials are disabled" in payload["error"]
