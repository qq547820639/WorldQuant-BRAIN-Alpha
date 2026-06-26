"""Auto-trigger orchestration for ``calibration_engine``.

Extracted from the original ``calibration_engine.py``.
"""
from __future__ import annotations

from ._calibration import calibrate_prior_weights, calibrate_scorecard_weights
from ._data import load_alpha_features


def auto_calibrate_if_stalled(
    storage_dir: str = "data",
    *,
    min_evaluations: int = 12,
    stall_threshold: float = 3.0,
    min_pass_rate: float = 0.3,
    features_path: str = "data/alpha_features.jsonl",
) -> dict:
    """Check convergence stats and auto-trigger calibration if stalled.

    Called by the research pipeline after accumulating enough score history.
    Returns a dict with advice / override config, or ok: False if not triggered.
    """
    try:
        from brain_alpha_ops.scoring.history import ScoreHistoryDB
        db = ScoreHistoryDB(storage_dir)
        stats = db.convergence_stats()
    except Exception as exc:
        return {"ok": False, "triggered": False, "reason": f"ScoreHistoryDB unavailable: {exc}"}

    if stats.get("status") != "ready":
        return {"ok": True, "triggered": False, "reason": "insufficient_data", "stats": stats}

    n = stats.get("total_evaluations", 0)
    if n < min_evaluations:
        return {"ok": True, "triggered": False, "reason": f"below min_evaluations ({n} < {min_evaluations})", "stats": stats}

    trend = stats.get("trend", "stable")
    recent_avg = stats.get("recent_avg", 0)
    global_avg = stats.get("avg_score", 0)
    pass_rate = stats.get("pass_rate", 0)

    stalled = (
        trend == "declining"
        or (trend == "stable" and abs(recent_avg - global_avg) < stall_threshold)
    )

    if not stalled:
        return {"ok": True, "triggered": False, "reason": f"trend={trend} not stalled", "stats": stats}

    # Load features and calibrate
    features = load_alpha_features(features_path)
    if len(features) < 8:
        return {"ok": True, "triggered": True, "calibration_failed": True, "reason": "insufficient features for calibration", "stats": stats}

    prior_result = calibrate_prior_weights(features, target_metric="sharpe")
    scorecard_result = calibrate_scorecard_weights(features)

    advice = {}
    if prior_result.get("optimized_weights"):
        advice["prior_weights_override"] = prior_result["optimized_weights"]
    if scorecard_result.get("optimized_weights"):
        advice.update(scorecard_result["optimized_weights"])

    return {
        "ok": True,
        "triggered": True,
        "reason": f"score convergence stalled (trend={trend}, pass_rate={pass_rate})",
        "stats": stats,
        "prior_calibration": prior_result,
        "scorecard_calibration": scorecard_result,
        "advice": advice,
        "recommendation": "Review the advice in the Web console and let maintainer automation apply approved scoring configuration changes.",
    }
