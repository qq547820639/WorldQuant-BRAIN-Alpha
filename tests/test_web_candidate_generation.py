import json
import time

from brain_alpha_ops.config import RunConfig
import brain_alpha_ops.web as web
import brain_alpha_ops.web_candidate_generation as web_candidate_generation
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload


class FakeToolbox:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def call(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        return self.result


class RaisingToolbox:
    def __init__(self, exc, calls):
        self.exc = exc
        self.calls = calls

    def call(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        raise self.exc


class FakeRepository:
    def __init__(self, storage_dir, saves):
        self.storage_dir = storage_dir
        self.saves = saves

    def save_assistant_guidance(self, guidance, source):
        self.saves.append({"storage_dir": self.storage_dir, "guidance": dict(guidance), "source": source})


class FakeLocalBacktestEngine:
    supported_fields = {"close", "returns"}
    supported_operators = {"rank", "ts_delta"}

    def evaluate(self, expression, *, cache_key="default"):
        return {
            "ok": True,
            "expression": expression,
            "cache_key": cache_key,
            "pass_local": False,
            "sharpe": 1.6,
            "fitness": 1.2,
            "turnover": 0.95,
            "weight_concentration": 0.04,
            "pass_reasons": [
                "Sharpe 1.60 >= 1.25",
                "Fitness 1.20 >= 1.0",
                "Turnover 95.00% > 70% (FAIL)",
            ],
        }


def test_generate_candidates_payload_delegates_to_toolbox_and_scores_candidates(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    calls = []
    saves = []
    toolbox_result = {
        "ok": True,
        "assistant_guidance": {
            "ok": True,
            "applied": True,
            "usable": True,
            "confidence": 0.9,
            "top_fields": ["close"],
            "top_operators": ["rank"],
            "preferred_windows": [20],
            "historical_outcome_status": "strong",
            "historical_outcome": {"count": 2, "success_count": 1, "success_rate": 0.5},
        },
        "candidates": [
            {
                "alpha_id": "alpha_1",
                "expression": "rank(close)",
                "family": "demo",
                "hypothesis": "close rank",
                "data_fields": ["close"],
                "operators": ["rank"],
            }
        ],
    }

    payload = generate_candidates_payload(
        {"count": 2000, "assistant_min_confidence": 2, "use_research_memory": False},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(toolbox_result, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, saves),
    )

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert calls[0][0] == "generate_candidates"
    assert calls[0][1]["count"] == 1000
    assert calls[0][1]["assistant_min_confidence"] == 1.0
    assert calls[0][1]["use_research_memory"] is False
    assert payload["candidates"][0]["scorecard"]["score_basis"] == "local_prior"
    assert "assistant_guided" in payload["candidates"][0]["source_tags"]
    assert payload["candidates"][0]["submission"]["assistant_guidance_digest"].startswith("ag_")
    assert saves[0]["source"] == "web_generate_candidates"


def test_generate_candidates_payload_attaches_local_backtest_evidence(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.settings.dataset = "pv1"
    monkeypatch.setattr(web_candidate_generation, "LocalBacktestEngine", FakeLocalBacktestEngine)
    calls = []
    toolbox_result = {
        "ok": True,
        "candidates": [
            {
                "alpha_id": "alpha_high_turnover",
                "expression": "rank(close)",
                "family": "demo",
                "hypothesis": "Local backtest evidence should block high turnover.",
                "data_fields": ["close"],
                "operators": ["rank"],
            }
        ],
    }

    payload = generate_candidates_payload(
        {"count": 1},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(toolbox_result, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    candidate = payload["candidates"][0]
    assert payload["ok"] is True
    assert candidate["submission"]["local_backtest"]["pass_local"] is False
    assert candidate["submission"]["local_backtest"]["turnover"] == 0.95
    assert candidate["local_quality"]["local_backtest"]["pass_local"] is False
    assert candidate["local_quality"]["local_backtest_support"]["supported"] is True
    assert "local_backtest_failed:Turnover 95.00% > 70% (FAIL)" in candidate["local_quality"]["reasons"]
    assert candidate["quality_diagnosis"]["qualified"] is False
    assert "local_quality_failed" in candidate["quality_diagnosis"]["blocking_reasons"]
    assert payload["summary"]["quality_summary"]["invalid_count"] == 1
    assert payload["summary"]["official_api_called"] is False


def test_generate_candidates_payload_marks_generation_risk_candidate(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.settings.dataset = "pv1"
    monkeypatch.setattr(web_candidate_generation, "LocalBacktestEngine", FakeLocalBacktestEngine)
    toolbox_result = {
        "ok": True,
        "candidates": [
            {
                "alpha_id": "alpha_risky_returns_delta",
                "expression": "rank(ts_delta(returns, 10))",
                "family": "momentum",
                "hypothesis": "Direct returns delta should be visible as blocked generation risk.",
                "data_fields": ["returns"],
                "operators": ["rank", "ts_delta"],
            }
        ],
    }

    payload = generate_candidates_payload(
        {"count": 1},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(toolbox_result, []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    candidate = payload["candidates"][0]
    assert payload["ok"] is True
    assert candidate["lifecycle_status"] == "local_prefilter_rejected"
    assert "generation_risk_blocked" in candidate["source_tags"]
    assert "high_turnover_generation_risk:direct_returns_delta_window=10" in candidate["local_quality"]["reasons"]
    assert "expression_high_turnover_generation_risk" in candidate["quality_diagnosis"]["blocking_reasons"]
    assert payload["summary"]["quality_summary"]["reason_counts"]["expression_high_turnover_generation_risk"] == 1


def test_generate_candidates_payload_empty_payload_uses_defaults(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.settings.dataset = "dataset_default"
    calls = []

    payload = generate_candidates_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": True, "candidates": []}, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is True
    assert payload["count"] == 0
    assert calls[0][1]["count"] == 10
    assert calls[0][1]["dataset_id"] == "dataset_default"
    assert calls[0][1]["use_research_memory"] is True
    assert calls[0][1]["top_n"] == 10
    assert calls[0][1]["min_success_rate"] == 0.0
    assert calls[0][1]["assistant_min_confidence"] == 0.0


def test_generate_candidates_payload_resolves_empty_dataset_from_cache(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    (tmp_path / "official_datasets.json").write_text(
        '[{"id":"ds_a"},{"id":"pv1"},{"id":"ds_b"}]',
        encoding="utf-8",
    )
    run_config.ops.settings.dataset = ""
    calls = []

    payload = generate_candidates_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": True, "candidates": []}, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is True
    assert calls[0][1]["dataset_id"] == "pv1"
    assert run_config.ops.settings.dataset == "pv1"


def test_generate_candidates_payload_returns_toolbox_error_without_post_processing(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": False, "error": "bad"}, []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload == {"ok": False, "error": "bad"}


def test_generate_candidates_payload_returns_structured_error_on_toolbox_exception(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    calls = []

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: RaisingToolbox(RuntimeError("token secret-token-123 failed"), calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "GENERATE_CANDIDATES_TOOLBOX_ERROR"
    assert payload["error_type"] == "RuntimeError"
    assert payload["phase"] == "web_generate_candidates"
    assert "secret-token-123" not in payload["error"]
    assert calls[0][0] == "generate_candidates"


def test_web_generate_route_creates_tracked_quality_job(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    generated = {
        "alpha_id": "alpha_tracked",
        "expression": "rank(close)",
        "family": "demo",
        "hypothesis": "quality is visible",
        "data_fields": ["close"],
        "operators": ["rank"],
        "local_quality": {"score": 75.0, "threshold": 70.0, "passed": True},
        "scorecard": {"total_score": 75.0, "decision_band": "research_only"},
        "quality_diagnosis": {
            "qualified": False,
            "local_candidate_valid": True,
            "status": "local_only_needs_official_evidence",
            "blocking_reasons": ["missing_official_alpha_id", "missing_official_metrics"],
        },
        "alpha_output_config": {"schema_version": "alpha-output-config-v1"},
    }

    def fake_generate(payload, *, run_config_from_payload):
        assert payload["count"] == 1
        assert run_config_from_payload(payload) is run_config
        return {
            "ok": True,
            "count": 1,
            "candidates": [generated],
            "summary": {
                "local_only": True,
                "official_api_called": False,
                "quality_summary": {
                    "qualified_count": 0,
                    "local_valid_count": 1,
                    "invalid_count": 1,
                },
            },
        }

    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    monkeypatch.setattr(web_candidate_generation, "generate_candidates_payload", fake_generate)
    web.ASYNC_JOBS.clear()

    response = web._real_generate({"count": 1})
    assert response["ok"] is True
    assert response["job_id"]
    assert response["sse_url"] == f"/sse?job_id={response['job_id']}"

    row = None
    for _ in range(50):
        row = web._job_get(response["job_id"])
        if row and row.get("status") == "completed":
            break
        time.sleep(0.02)

    assert row is not None
    assert row["status"] == "completed"
    assert row["result"]["summary"]["quality_summary"]["local_valid_count"] == 1
    assert row["result"]["summary"]["persistence"]["persisted_count"] == 1
    saved = json.loads((tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert saved["alpha_id"] == "alpha_tracked"
    assert saved["quality_diagnosis"]["status"] == "local_only_needs_official_evidence"


def test_web_local_check_and_submit_routes_do_not_claim_official_actions():
    check = web._real_check({"expression": "rank(close)"})
    assert check["ok"] is True
    assert check["local_only"] is True
    assert check["official_api_called"] is False
    assert check["requires_official_check"] is True

    submit = web._real_submit({"alpha_id": "alpha_1"})
    assert submit["ok"] is False
    assert submit["submitted"] is False
    assert submit["error_code"] == "SUBMIT_DISABLED_REQUIRES_OFFICIAL_PREFLIGHT"


def test_generate_candidates_payload_rejects_non_mapping_toolbox_response(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(["not", "a", "dict"], []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "GENERATE_CANDIDATES_VALIDATION_ERROR"
    assert payload["error_category"] == "validation"
