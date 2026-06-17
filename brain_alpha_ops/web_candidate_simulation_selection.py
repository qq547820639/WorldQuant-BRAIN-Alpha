"""Target selection helpers for Web official simulation jobs."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig


def requested_candidate_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    """Resolve the official validation queue from explicit IDs or a workflow plan.

    The candidate producer may keep writing to the local ledger while official
    validation runs. Accepting a queue snapshot here keeps validation scoped to
    the selected candidates instead of silently rescanning the newest ledger.
    """

    raw_ids = payload.get("candidate_ids")
    if not raw_ids:
        plan = payload.get("workflow_plan") or payload.get("candidate_workflow")
        if isinstance(plan, dict):
            validator = plan.get("validator")
            if isinstance(validator, dict):
                raw_ids = validator.get("next_candidate_ids") or validator.get("candidate_ids")
    ids: list[str] = []
    for raw_id in raw_ids if isinstance(raw_ids, list) else []:
        value = str(raw_id).strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def candidate_matches_requested_ids(candidate: dict[str, Any], requested_ids: set[str]) -> bool:
    if not requested_ids:
        return False
    for key in ("alpha_id", "official_alpha_id", "simulation_id"):
        value = str(candidate.get(key) or "").strip()
        if value and value in requested_ids:
            return True
    return False


def simulation_candidates_payload(
    payload: dict[str, Any],
    *,
    config: RunConfig,
    candidates: list[dict[str, Any]],
    account_cooldown: dict[str, Any] | None,
    eligible_for_simulation: Callable[[dict[str, Any], float], bool],
    candidate_score: Callable[[dict[str, Any]], float],
    dedupe_simulation_targets: Callable[..., list[dict[str, Any]]],
    default_dataset: str,
) -> dict[str, Any]:
    """Prepare the preview payload for candidate official simulation."""

    min_score = float(payload.get("min_score", config.ops.budget.min_prior_score_for_official_simulation))
    if account_cooldown:
        return {
            "ok": True,
            "eligible_count": 0,
            "total_candidates": len(candidates),
            "min_score": min_score,
            "account_cooldown": account_cooldown,
            "eligible_alphas": [],
        }

    candidate_ids = requested_candidate_ids_from_payload(payload)
    if candidate_ids:
        requested_ids = {str(candidate_id).strip() for candidate_id in candidate_ids if str(candidate_id).strip()}
        targets = [
            c for c in candidates
            if candidate_matches_requested_ids(c, requested_ids) and eligible_for_simulation(c, min_score)
        ]
        targets = sorted(targets, key=candidate_score, reverse=True)
    else:
        targets = sorted(
            (c for c in candidates if eligible_for_simulation(c, min_score)),
            key=candidate_score,
            reverse=True,
        )

    targets = dedupe_simulation_targets(targets, default_dataset=default_dataset)

    return {
        "ok": True,
        "eligible_count": len(targets),
        "total_candidates": len(candidates),
        "min_score": min_score,
        "eligible_alphas": [
            {
                "alpha_id": c.get("alpha_id", ""),
                "score": candidate_score(c),
                "expression": (c.get("expression", "") or "")[:80],
            }
            for c in targets[:20]
        ],
    }
