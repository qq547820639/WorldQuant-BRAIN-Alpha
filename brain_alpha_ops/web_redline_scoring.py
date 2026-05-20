"""Web API endpoints for redline verification and scoring attribution.

Exposes:
  GET  /api/redline/report        -> ComplianceReport JSON
  POST /api/scoring/evaluate      -> ScoringResult JSON
  GET  /api/scoring/health        -> ScoreHistoryDB convergence stats
"""

from __future__ import annotations

import json
import os
from typing import Any

from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.scoring.official_scoring import (
    GateConfig,
    OfficialScoringSystem,
    ScoreHistoryDB,
)


def _get_storage_dir() -> str:
    config = load_run_config()
    return config.ops.storage_dir


def handle_redline_report(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/redline/report — full ComplianceReport as JSON."""
    config = load_run_config()
    verifier = RedLineVerifier(config)
    report = verifier.verify_all()
    return report.to_dict()


def handle_scoring_evaluate(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/evaluate — evaluate a candidate and return ScoringResult."""
    candidate = body.get("candidate")
    if not candidate or not isinstance(candidate, dict):
        return {"ok": False, "error": "missing or invalid 'candidate' in request body"}

    config = load_run_config()
    gate_config = GateConfig.from_thresholds(config.ops.thresholds)
    system = OfficialScoringSystem(gate_config=gate_config)
    result = system.evaluate(candidate)

    # Persist to score history
    try:
        db = ScoreHistoryDB(config.ops.storage_dir)
        db.append(result)
    except Exception:
        pass

    return result.to_dict()


def handle_scoring_health(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/scoring/health — convergence stats and scorecard health."""
    storage_dir = _get_storage_dir()
    db = ScoreHistoryDB(storage_dir)
    stats = db.convergence_stats()
    return {
        "ok": True,
        "schema_version": "scoring_health.v1",
        "storage_dir": storage_dir,
        **stats,
    }


def handle_scoring_attribution(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/attribution — lightweight attribution-only report."""
    result = handle_scoring_evaluate(body)
    if not result.get("ok", True):
        return result
    return {
        "ok": True,
        "attribution": result.get("attribution_tree"),
        "hard_gates": result.get("hard_gates"),
        "soft_gates": result.get("soft_gates"),
        "top_failures": result.get("top_failures"),
        "improvement_hints": result.get("improvement_hints"),
    }
