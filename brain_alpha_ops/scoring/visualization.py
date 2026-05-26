"""Stable score-attribution summary and chart payload helpers."""

from __future__ import annotations

from typing import Any


def build_score_visualization_payload(scorecard: dict[str, Any], *, max_nodes: int = 40) -> dict[str, Any]:
    """Return UI-friendly attribution bars and tree nodes from a scorecard."""
    tree = scorecard.get("attribution_tree") if isinstance(scorecard.get("attribution_tree"), dict) else {}
    if not tree and {"total_score", "prior", "empirical", "submission_checklist"} & set(scorecard):
        try:
            from brain_alpha_ops.scoring.attribution import build_attribution_tree

            tree = build_attribution_tree(scorecard).to_dict()
        except Exception:
            tree = {}

    nodes: list[dict[str, Any]] = []
    _flatten_tree(tree, nodes, parent="", depth=0, max_nodes=max(1, int(max_nodes or 1)))
    bars = [
        {
            "name": node["name"],
            "score": node["score"],
            "weight": node["weight"],
            "contribution": node["contribution"],
            "depth": node["depth"],
        }
        for node in nodes
        if node["depth"] <= 1
    ]
    bars.sort(key=lambda row: abs(float(row.get("contribution") or 0.0)), reverse=True)
    return {
        "ok": bool(tree),
        "schema_version": "score_visualization.v1",
        "total_score": _float(scorecard.get("total_score") or tree.get("score")),
        "decision_band": str(scorecard.get("decision_band") or ""),
        "node_count": len(nodes),
        "nodes": nodes,
        "contribution_bars": bars,
        "top_positive_contributors": _contributors(nodes, positive=True),
        "top_negative_contributors": _contributors(nodes, positive=False),
    }


def summarize_score_attribution(scorecard: dict[str, Any], *, max_nodes: int = 40) -> dict[str, Any]:
    """Return a compact attribution summary for API/tool responses."""
    visualization = build_score_visualization_payload(scorecard, max_nodes=max_nodes)
    top_failures = [
        dict(item)
        for item in scorecard.get("top_failures", [])
        if isinstance(item, dict)
    ][:8]
    improvement_hints = [str(item) for item in scorecard.get("improvement_hints", []) if str(item)][:8]
    return {
        "ok": visualization.get("ok", False),
        "schema_version": "score_attribution_summary.v1",
        "total_score": visualization.get("total_score", 0.0),
        "decision_band": visualization.get("decision_band", ""),
        "top_failures": top_failures,
        "improvement_hints": improvement_hints,
        "visualization": visualization,
    }


def _flatten_tree(
    node: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    parent: str,
    depth: int,
    max_nodes: int,
) -> None:
    if not isinstance(node, dict) or len(rows) >= max_nodes:
        return
    name = str(node.get("name") or "")
    rows.append(
        {
            "id": f"{parent}/{name}" if parent else name,
            "parent": parent,
            "name": name,
            "depth": depth,
            "score": _float(node.get("score")),
            "weight": _float(node.get("weight")),
            "contribution": _float(node.get("contribution")),
            "explanation": str(node.get("explanation") or ""),
            "calibratable": bool(node.get("calibratable")),
        }
    )
    current_id = rows[-1]["id"]
    for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
        _flatten_tree(child, rows, parent=current_id, depth=depth + 1, max_nodes=max_nodes)


def _contributors(nodes: list[dict[str, Any]], *, positive: bool) -> list[dict[str, Any]]:
    filtered = [
        node
        for node in nodes
        if (float(node.get("contribution") or 0.0) >= 0 if positive else float(node.get("contribution") or 0.0) < 0)
    ]
    filtered.sort(key=lambda row: abs(float(row.get("contribution") or 0.0)), reverse=True)
    return filtered[:5]


def _float(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0
