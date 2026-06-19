"""Local expression proof payloads for the Web check-batch route."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_official_context import (
    expression_official_context_proof,
)


def check_batch_official_context_payload(
    payload: Mapping[str, Any] | None,
    *,
    load_run_config: Callable[[], Any] = _load_run_config,
) -> dict[str, Any]:
    """Validate expressions against parsed symbols and local official cache.

    This helper is local-only: it reads the same official context cache used by
    the capability registry and does not call BRAIN APIs or submit anything.
    """

    request = payload or {}
    expressions = request.get("expressions") or []
    if isinstance(expressions, str):
        expressions = [expressions]
    if not isinstance(expressions, list):
        return {"ok": False, "error": "expressions must be a list of strings"}

    dataset_id = str(request.get("dataset_id") or request.get("dataset") or "").strip()
    data_dir = None
    try:
        config = load_run_config()
        ops = getattr(config, "ops", None)
        data_dir = getattr(ops, "storage_dir", None)
        settings = getattr(ops, "settings", None)
        dataset_id = dataset_id or str(getattr(settings, "dataset", "") or "").strip()
    except Exception:
        data_dir = None

    results = [_check_expression(expr, dataset_id=dataset_id, data_dir=data_dir) for expr in expressions]
    return {
        "ok": True,
        "checked": len(results),
        "valid_count": sum(1 for result in results if result.get("valid")),
        "invalid_count": sum(1 for result in results if not result.get("valid")),
        "results": results,
    }


def _check_expression(expression: Any, *, dataset_id: str, data_dir: str | None) -> dict[str, Any]:
    if not isinstance(expression, str) or not expression.strip():
        return {"expression": str(expression), "valid": False, "reason": "empty or invalid expression"}
    normalized = expression.strip()
    try:
        proof = expression_official_context_proof(normalized, dataset_id=dataset_id, data_dir=data_dir)
        passed = proof.get("passed") is True
        return {
            "expression": normalized,
            "valid": passed,
            "expression_key": expression_key(normalized),
            "status": "OFFICIAL_CONTEXT_PASSED" if passed else "OFFICIAL_CONTEXT_FAILED",
            "official_context_proof": proof,
            "reason": "" if passed else "; ".join(proof.get("reasons") or []),
        }
    except Exception as exc:
        return {"expression": str(expression), "valid": False, "reason": str(exc)}


__all__ = ["check_batch_official_context_payload"]
