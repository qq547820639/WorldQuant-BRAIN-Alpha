"""Cloud-alpha matching and ranking helpers for the research pipeline."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import Candidate

from .expression_ast import expression_key, expression_similarity
from .pipeline_helpers import cloud_row_expression, expr_key, ranking_score
from .safety import normalize


def build_cloud_similarity_rows(cloud_alphas: list[dict]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in cloud_alphas:
        expr = cloud_row_expression(row)
        norm = normalize(expr)
        rows.append(
            {
                "id": str(row.get("id") or row.get("alpha_id") or ""),
                "status": str(row.get("status", "")),
                "expression": expr,
                "norm": norm,
                "tokens": set(norm.split()) if norm else set(),
            }
        )
    return rows


def cloud_correlation_risk(
    candidate: Candidate,
    similarity_rows: list[dict[str, object]],
    *,
    official_alpha_id: str = "",
) -> dict:
    if not similarity_rows:
        return {
            "level": "unknown",
            "max_similarity": 0.0,
            "matched_alpha_id": "",
            "note": "cloud alpha sync unavailable",
        }
    official_id = official_alpha_id or candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
    candidate_norm = normalize(candidate.expression)
    candidate_tokens = set(candidate_norm.split()) if candidate_norm else set()
    best = {"score": 0.0, "id": "", "status": ""}
    top_matches: list[tuple[float, dict[str, object]]] = []
    for row in similarity_rows:
        row_id = str(row.get("id") or "")
        if official_id and row_id == official_id:
            continue
        row_tokens = row.get("tokens") or set()
        union = candidate_tokens | row_tokens
        score = (len(candidate_tokens & row_tokens) / len(union)) if union else 0.0
        if score > best["score"]:
            best = {"score": round(score, 4), "id": row_id, "status": str(row.get("status", ""))}
        if score > 0.0:
            top_matches.append((score, row))
            if len(top_matches) > 25:
                top_matches.sort(key=lambda item: item[0], reverse=True)
                del top_matches[25:]
    for token_score, row in sorted(top_matches, key=lambda item: item[0], reverse=True):
        ast_score = expression_similarity(candidate.expression, str(row.get("expression") or ""))
        score = round(max(token_score, ast_score), 4)
        if score > best["score"]:
            best = {"score": score, "id": str(row.get("id") or ""), "status": str(row.get("status", ""))}
    level = "high" if best["score"] >= 0.90 else "medium" if best["score"] >= 0.75 else "low"
    return {
        "level": level,
        "max_similarity": best["score"],
        "matched_alpha_id": best["id"],
        "matched_status": best["status"],
        "note": "Used to avoid self-correlation or duplicate submission, not to bypass compliance gates.",
    }


def cloud_status_for_candidate(candidate: Candidate, cloud_alphas: list[dict]) -> dict:
    official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
    candidate_expr_key = expr_key(candidate)
    for row in cloud_alphas:
        row_id = str(row.get("id") or row.get("alpha_id") or "")
        if official_alpha_id and row_id == official_alpha_id:
            return {"id": row_id, "status": str(row.get("status", "")), "match": "official_id"}
    for row in cloud_alphas:
        row_expression = expression_key(cloud_row_expression(row))
        if candidate_expr_key and row_expression == candidate_expr_key:
            return {"id": str(row.get("id") or row.get("alpha_id") or ""), "status": str(row.get("status", "")), "match": "expression"}
    return {"id": "", "status": "", "match": "none"}


def remember_accepted(accepted_candidates: list[Candidate], candidate: Candidate, *, limit: int = 50) -> None:
    key = expr_key(candidate)
    if any(expr_key(item) == key for item in accepted_candidates):
        return
    candidate.lifecycle_status = "submission_ready"
    accepted_candidates.append(candidate)
    accepted_candidates.sort(key=ranking_score, reverse=True)
    del accepted_candidates[limit:]


def smart_ranking_score(candidate: Candidate, risk: dict[str, Any]) -> float:
    score = ranking_score(candidate)
    if risk.get("level") == "high":
        score -= 30.0
    elif risk.get("level") == "medium":
        score -= 10.0
    return round(score, 2)


def smart_rank_candidates(candidates: list[Candidate], risk_fn) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            bool(candidate.gate.get("submission_ready")),
            bool(candidate.official_metrics),
            smart_ranking_score(candidate, risk_fn(candidate)),
            candidate.scorecard.get("local_rank_score", 0.0),
            candidate.local_quality.get("score", 0.0),
        ),
        reverse=True,
    )

