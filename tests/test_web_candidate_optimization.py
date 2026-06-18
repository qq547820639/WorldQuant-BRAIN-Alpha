from __future__ import annotations

import json
from pathlib import Path

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
import brain_alpha_ops.web_candidates.optimization as web_candidate_optimization
from brain_alpha_ops.web_candidates.optimization import optimize_candidates_payload, persist_optimized_candidates
from brain_alpha_ops.web_cloud.snapshot import save_official_context_json


class FakePassingLocalBacktestEngine:
    supported_fields = {"close", "returns"}
    supported_operators = {"rank", "zscore", "ts_rank"}

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, expression, *, cache_key="default"):
        return {
            "ok": True,
            "expression": expression,
            "cache_key": cache_key,
            "pass_local": True,
            "sharpe": 1.5,
            "fitness": 1.1,
            "turnover": 0.2,
            "weight_concentration": 0.04,
            "pass_reasons": ["local pass"],
        }


class FakeFailingLocalBacktestEngine(FakePassingLocalBacktestEngine):
    def evaluate(self, expression, *, cache_key="default"):
        return {
            "ok": True,
            "expression": expression,
            "cache_key": cache_key,
            "pass_local": False,
            "sharpe": 0.4,
            "fitness": 0.2,
            "turnover": 0.95,
            "weight_concentration": 0.3,
            "pass_reasons": ["Turnover 95.00% > 70% (FAIL)"],
        }


class FakePermissiveLocalBacktestEngine(FakePassingLocalBacktestEngine):
    supported_fields = {"close", "returns", "custom_field"}
    supported_operators = {"rank", "zscore", "ts_rank", "ts_fake"}


class FakeParameterSearchService:
    def __init__(self, *, expressions, parent_failure="sharpe"):
        self.expressions = list(expressions)
        self.parent_failure = parent_failure

    def search(self, parent, *, max_mutations=3, diagnosis=None, thresholds=None):
        rows = []
        for index, expression in enumerate(self.expressions[:max_mutations]):
            child = Candidate.from_dict(parent.to_dict())
            child.expression = expression
            child.data_fields = ["close"]
            child.operators = ["rank"]
            child.mutation_type = "window_refine"
            rows.append({
                "candidate": child.to_dict(),
                "score": 90 - index,
                "mutation_mode": "window_refine",
                "metadata": {
                    "parent_failure": self.parent_failure,
                    "optimizer_trace": {
                        "schema_version": "optimizer-trace-v1",
                        "failed_dimension": self.parent_failure,
                        "selected_strategy": "window_refine",
                        "official_api_called": False,
                        "submit_allowed": False,
                    },
                },
            })
        return {"ok": True, "results": rows}


def _make_config(tmp_path: Path) -> RunConfig:
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.settings.dataset = "pv1"
    save_official_context_json(
        "official_fields.json",
        [{"name": "close", "category": "pv"}, {"name": "returns", "category": "pv"}],
        load_config=lambda: run_config,
    )
    save_official_context_json(
        "official_operators.json",
        [{"name": "rank"}, {"name": "ts_rank"}, {"name": "zscore"}, {"name": "winsorize"}],
        load_config=lambda: run_config,
    )
    save_official_context_json(
        "official_datasets.json",
        [{"id": "pv1", "name": "Price Volume", "field_count": 2, "category": {"id": "pv"}}],
        load_config=lambda: run_config,
    )
    return run_config


def _parent_candidate() -> dict:
    return Candidate(
        alpha_id="alpha_parent",
        expression="rank(close)",
        family="demo",
        hypothesis="parent candidate",
        data_fields=["close"],
        operators=["rank"],
        source_tags=["seed"],
        dataset_id="pv1",
        local_quality={"passed": True, "score": 70},
        scorecard={"total_score": 72, "decision_band": "optimize"},
        quality_diagnosis={
            "local_candidate_valid": True,
            "submission_ready": False,
            "blocking_reasons": ["decision_band_not_submit_candidate"],
        },
        official_alpha_id="official_parent",
        simulation_id="/simulations/parent",
        official_metrics={"sharpe": 1.2},
    ).to_dict()


def test_optimize_candidates_payload_returns_local_only_children(monkeypatch, tmp_path):
    run_config = _make_config(tmp_path)
    monkeypatch.setattr(web_candidate_optimization, "LocalBacktestEngine", FakePassingLocalBacktestEngine)

    result = optimize_candidates_payload(
        {
            "dataset_id": "pv1",
            "target_pool_size": 10,
            "max_candidates": 1,
            "max_mutations": 2,
            "keep_top": 2,
            "candidates": [_parent_candidate()],
        },
        run_config_from_payload=lambda _body: run_config,
        parameter_search_factory=lambda: FakeParameterSearchService(
            expressions=["rank(ts_rank(close, 30))", "zscore(rank(close))"],
        ),
    )

    assert result["ok"] is True
    assert result["local_only"] is True
    assert result["official_api_called"] is False
    assert result["submit_allowed"] is False
    assert result["returned_count"] == 2
    child = result["candidates"][0]
    assert child["alpha_id"].startswith("alpha_")
    assert child["alpha_id"] != "alpha_parent"
    assert child["parent_id"] == "alpha_parent"
    assert child["mutation_type"] == "window_refine"
    assert child["official_alpha_id"] == ""
    assert child["simulation_id"] == ""
    assert child["official_metrics"] == {}
    assert child["alpha_output_config"]["official_api_called"] is False
    assert child["alpha_output_config"]["allow_submit"] is False
    assert "local_only" in child["source_tags"]
    assert "parameter_search" in child["source_tags"]
    assert "candidate_pool_optimization" in child["source_tags"]
    assert result["summary"]["automation"]["submit_allowed"] is False
    assert result["summary"]["automation"]["official_api_called"] is False
    explanation = child["extra_fields"]["optimization_explanation"]
    assert explanation["schema_version"] == "candidate-optimization-explanation-v1"
    assert explanation["local_only"] is True
    assert explanation["official_api_called"] is False
    assert explanation["submit_allowed"] is False
    assert explanation["parent"]["alpha_id"] == "alpha_parent"
    assert explanation["parent"]["blocking_reasons"] == ["decision_band_not_submit_candidate"]
    assert explanation["mutation"]["mode"] == "window_refine"
    assert explanation["mutation"]["search_score"] == 90
    assert explanation["mutation"]["optimizer_trace"]["schema_version"] == "optimizer-trace-v1"
    assert explanation["mutation"]["optimizer_trace"]["official_api_called"] is False
    assert explanation["mutation"]["optimizer_trace"]["submit_allowed"] is False
    assert explanation["expression_change"]["operators_added"] == ["ts_rank"]
    assert explanation["official_context"]["passed"] is True
    assert explanation["official_context"]["source"] == "local_official_context_cache"
    assert explanation["decision"]["action"] in {"optimize", "retain", "official_validation_queue"}
    assert explanation["next_action"] == "retain_for_candidate_pool"
    explanation_summary = result["summary"]["optimization_explanations"]
    assert explanation_summary["schema_version"] == "candidate-optimization-explanation-summary-v1"
    assert explanation_summary["candidate_count"] == 2
    assert explanation_summary["explained_count"] == 2
    assert explanation_summary["official_context_passed_count"] == 2
    assert explanation_summary["non_submit_boundary_intact"] is True
    concentration = explanation_summary["concentration_audit"]
    assert concentration["schema_version"] == "optimization-concentration-audit-v1"
    assert concentration["local_only"] is True
    assert concentration["official_api_called"] is False
    assert concentration["submit_allowed"] is False
    assert concentration["top_mutation_mode"] == "window_refine"
    assert concentration["top_mutation_mode_count"] == 2
    assert concentration["top_mutation_mode_share"] == 1.0
    assert concentration["unique_parent_failure_count"] == 1
    assert concentration["top_parent_failure"] == "sharpe"
    assert concentration["top_parent_failure_count"] == 2
    assert concentration["top_parent_failure_share"] == 1.0
    assert concentration["concentration_risk"] == "high"
    assert "single_mutation_mode" in concentration["risk_reasons"]
    assert "single_parent_failure" in concentration["risk_reasons"]

    persistence = persist_optimized_candidates("job_opt", run_config, result)
    assert persistence["persisted_count"] == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["run_id"] for row in rows] == ["job_opt", "job_opt"]
    assert all(row["parent_id"] == "alpha_parent" for row in rows)
    assert all(row["scientific_audit"]["operation"] == "candidate_optimization" for row in rows)
    assert all(row["scientific_audit"]["lineage"]["parent_alpha_id"] == "alpha_parent" for row in rows)
    assert all(row["scientific_audit"]["explainability"]["official_context_proof"]["passed"] is True for row in rows)
    assert rows[0]["scientific_audit"]["explainability"]["expression_delta"]["operators_added"] == ["ts_rank"]
    assert rows[0]["scientific_audit"]["explainability"]["optimization_explanation"]["mutation"]["mode"] == "window_refine"
    assert all(row["scientific_audit"]["safety_boundary"]["submit_allowed"] is False for row in rows)


def test_optimize_candidates_rejects_local_backtest_failures(monkeypatch, tmp_path):
    run_config = _make_config(tmp_path)
    monkeypatch.setattr(web_candidate_optimization, "LocalBacktestEngine", FakeFailingLocalBacktestEngine)

    result = optimize_candidates_payload(
        {
            "dataset_id": "pv1",
            "max_candidates": 1,
            "max_mutations": 1,
            "candidates": [_parent_candidate()],
        },
        run_config_from_payload=lambda _body: run_config,
        parameter_search_factory=lambda: FakeParameterSearchService(
            expressions=["rank(ts_rank(close, 30))"],
        ),
    )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["rejected_count"] == 1
    assert result["rejected_candidates_preview"][0]["local_quality"]["passed"] is False
    persistence = persist_optimized_candidates("job_opt", run_config, result)
    assert persistence["persisted_count"] == 0
    assert not (tmp_path / "candidates.jsonl").exists()


def test_optimize_candidates_rejects_unofficial_expression_even_when_metadata_is_safe(monkeypatch, tmp_path):
    run_config = _make_config(tmp_path)
    monkeypatch.setattr(web_candidate_optimization, "LocalBacktestEngine", FakePermissiveLocalBacktestEngine)

    result = optimize_candidates_payload(
        {
            "dataset_id": "pv1",
            "max_candidates": 1,
            "max_mutations": 1,
            "candidates": [_parent_candidate()],
        },
        run_config_from_payload=lambda _body: run_config,
        parameter_search_factory=lambda: FakeParameterSearchService(
            expressions=["rank(ts_fake(custom_field, 30))"],
        ),
    )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["rejected_count"] == 1
    rejected = result["rejected_candidates_preview"][0]
    proof = rejected["extra_fields"]["official_context_proof"]
    explanation = rejected["extra_fields"]["optimization_explanation"]
    assert proof["passed"] is False
    assert proof["missing_fields"] == ["custom_field"]
    assert proof["missing_operators"] == ["ts_fake"]
    assert explanation["official_context"]["passed"] is False
    assert explanation["official_context"]["missing_fields"] == ["custom_field"]
    assert explanation["official_context"]["missing_operators"] == ["ts_fake"]
    assert explanation["next_action"] == "reject_local_prefilter"
    assert result["summary"]["optimization_explanations"]["official_context_passed_count"] == 0
    assert "official_context_proof:missing_official_fields" in rejected["local_quality"]["reasons"]
    assert "official_context_proof:missing_official_operators" in rejected["local_quality"]["reasons"]
