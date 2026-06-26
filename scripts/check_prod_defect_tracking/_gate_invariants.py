"""Readiness gate invariant probes for production defect tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def _base_gate_candidate() -> dict[str, Any]:
    return {
        "alpha_id": "alpha_gate_invariant",
        "official_alpha_id": "ab12cd34ef56",
        "lifecycle_status": "submission_ready",
        "gate": {"submission_ready": True},
        "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
        "official_metrics": {
            "official_alpha_id": "ab12cd34ef56",
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.2,
            "turnover": 0.25,
            "correlation": 0.2,
            "weight_concentration": 0.05,
        },
        "cloud_correlation_risk": {"level": "low", "max_similarity": 0.1},
        "submission": {"local_backtest": {"pass_local": True}},
    }


def _readiness_invariant_candidate(reason: str) -> dict[str, Any]:
    candidate = _base_gate_candidate()
    if reason == "not_submission_ready":
        candidate["lifecycle_status"] = "official_validation_passed"
        candidate["gate"] = {"submission_ready": False}
    elif reason == "decision_band_not_submit_candidate":
        candidate["scorecard"] = {"total_score": 66.9, "decision_band": "research_only"}
    elif reason == "local_backtest_failed":
        candidate["submission"] = {"local_backtest": {"pass_local": False}}
    elif reason == "missing_official_alpha_id":
        candidate["official_alpha_id"] = ""
        candidate["official_metrics"] = dict(candidate["official_metrics"], official_alpha_id="")
    elif reason == "non_production_official_alpha_id":
        candidate["official_alpha_id"] = "prod_stub_alpha_0001"
        candidate["official_metrics"] = dict(candidate["official_metrics"], official_alpha_id="prod_stub_alpha_0001")
    elif reason == "missing_official_metrics":
        candidate["official_metrics"] = {}
    elif reason == "official_pass_fail_not_pass":
        candidate["official_metrics"] = dict(candidate["official_metrics"], pass_fail="FAIL")
    elif reason == "missing_official_metric_fields":
        candidate["official_metrics"] = {
            "official_alpha_id": "ab12cd34ef56",
            "pass_fail": "PASS",
        }
    elif reason == "official_sharpe_below_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], sharpe=0.8)
    elif reason == "official_fitness_below_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], fitness=0.7)
    elif reason == "official_turnover_above_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], turnover=0.95)
    elif reason == "official_self_correlation_above_threshold":
        candidate["official_metrics"] = dict(
            candidate["official_metrics"],
            correlation=None,
            self_correlation=0.95,
            prod_correlation=0.2,
        )
    elif reason == "official_prod_correlation_above_threshold":
        candidate["official_metrics"] = dict(
            candidate["official_metrics"],
            correlation=None,
            self_correlation=0.2,
            prod_correlation=0.95,
        )
    elif reason == "official_weight_concentration_above_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], weight_concentration=0.2)
    elif reason == "missing_cloud_similarity":
        candidate["cloud_correlation_risk"] = {}
    elif reason == "high_cloud_similarity":
        candidate["cloud_correlation_risk"] = {"level": "high", "max_similarity": 0.9}
    return candidate


def _write_readiness_case(path: Path, candidate: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "stopped",
                        "result": {"summary": {"submission_ready": 1}},
                        "progress": {"data": {"candidates": [candidate]}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _check_readiness_gate_invariants(findings: list[dict[str, str]]) -> None:
    invariant_reasons = (
        "not_submission_ready",
        "decision_band_not_submit_candidate",
        "local_backtest_failed",
        "missing_official_alpha_id",
        "non_production_official_alpha_id",
        "missing_official_metrics",
        "missing_official_metric_fields",
        "official_pass_fail_not_pass",
        "official_sharpe_below_threshold",
        "official_fitness_below_threshold",
        "official_turnover_above_threshold",
        "official_self_correlation_above_threshold",
        "official_prod_correlation_above_threshold",
        "official_weight_concentration_above_threshold",
        "missing_cloud_similarity",
        "high_cloud_similarity",
    )
    # Late import so monkeypatch on
    # ``scripts.check_prod_defect_tracking.check_live_submit_readiness`` is
    # honored (tests rely on this attribute lookup path).
    from scripts.check_prod_defect_tracking import check_live_submit_readiness

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        for reason in invariant_reasons:
            path = tmp_root / f"{reason}.json"
            _write_readiness_case(path, _readiness_invariant_candidate(reason))
            result = check_live_submit_readiness(path)
            if result.get("ready_to_submit") or int(result.get("eligible_count") or 0) != 0:
                findings.append(
                    _finding(
                        "readiness_gate_invariant_ready",
                        f"{reason} blocks eligibility",
                        "readiness gate allowed a candidate that violates official submit standards",
                    )
                )
            best_candidate = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else {}
            reasons = best_candidate.get("blocking_reasons") if isinstance(best_candidate.get("blocking_reasons"), list) else []
            if reason not in reasons:
                findings.append(
                    _finding(
                        "readiness_gate_invariant_reason",
                        reason,
                        "readiness gate did not report the expected official submit standard blocker",
                    )
                )
