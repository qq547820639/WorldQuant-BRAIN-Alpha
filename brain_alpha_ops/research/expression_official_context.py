"""Offline official-context proof for parsed Alpha expressions.

The proof in this module is deliberately local-only: it reads the same
``official_*.json`` cache used by the capability registry and never refreshes or
calls BRAIN APIs.  Callers can use the resulting payload to show exactly which
parsed fields/operators were checked against the official cache before a
candidate is retained, optimized, or sent to any official-validation queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader
from brain_alpha_ops.data.official_context_validation import validate_official_context
from brain_alpha_ops.research.expression_ast import ExpressionProfile, profile_expression

EXPRESSION_OFFICIAL_CONTEXT_PROOF_SCHEMA = "expression-official-context-proof.v1"
EXPRESSION_DELTA_SCHEMA = "expression-delta.v1"
GROUP_CONTEXT_FIELDS = frozenset({"market", "sector", "industry", "subindustry", "country", "exchange"})

@dataclass(frozen=True)
class OfficialCapabilitySets:
    field_names: frozenset[str]
    operator_names: frozenset[str]
    dataset_field_names: frozenset[str]
    dataset_id: str
    cache_summary: dict[str, Any]

def expression_official_context_proof(
    expression: str,
    *,
    dataset_id: str = "",
    loader: OfficialDataLoader | None = None,
    mapper: FieldDatasetMapper | None = None,
    data_dir: str | None = None,
    require_fresh_cache: bool = False,
) -> dict[str, Any]:
    """Return a serializable proof that expression symbols match official cache.

    ``require_fresh_cache`` is intentionally opt-in.  Some local workflows can
    continue with a stale but internally consistent cache while showing a
    refresh warning, but official-validation or release gates may choose to fail
    closed on any cache warning.
    """

    profile = profile_expression(expression)
    capability_sets = official_capability_sets(
        dataset_id=dataset_id,
        loader=loader,
        mapper=mapper,
        data_dir=data_dir,
    )
    parsed_fields = _normalized_list(profile.fields)
    parsed_operators = _normalized_list(profile.operators)
    checked_fields = [field for field in parsed_fields if field not in GROUP_CONTEXT_FIELDS]
    missing_fields = [field for field in checked_fields if field not in capability_sets.field_names]
    missing_operators = [operator for operator in parsed_operators if operator not in capability_sets.operator_names]
    dataset_mismatches: list[str] = []
    if capability_sets.dataset_id and capability_sets.dataset_field_names:
        dataset_mismatches = [
            field
            for field in checked_fields
            if field not in capability_sets.dataset_field_names and field not in GROUP_CONTEXT_FIELDS
        ]
    cache = capability_sets.cache_summary
    blocking_count = _safe_int(cache.get("blocking_count"))
    p1_count = _safe_int(cache.get("p1_count"))
    cache_passed = blocking_count == 0 and (not require_fresh_cache or p1_count == 0)
    passed = bool(
        profile.parsed
        and cache_passed
        and not missing_fields
        and not missing_operators
        and not dataset_mismatches
    )
    reasons: list[str] = []
    if not profile.parsed:
        reasons.append("parse_error")
    if blocking_count:
        reasons.append("official_context_cache_blocking_findings")
    if require_fresh_cache and p1_count:
        reasons.append("official_context_cache_warning_findings")
    if missing_fields:
        reasons.append("missing_official_fields")
    if missing_operators:
        reasons.append("missing_official_operators")
    if dataset_mismatches:
        reasons.append("active_dataset_field_mismatch")

    return {
        "schema_version": EXPRESSION_OFFICIAL_CONTEXT_PROOF_SCHEMA,
        "source": "local_official_context_cache",
        "official_api_called": False,
        "passed": passed,
        "valid": passed,
        "blocked": not passed,
        "reasons": reasons,
        "expression": {
            "parsed": profile.parsed,
            "canonical": profile.canonical,
            "fingerprint": profile.fingerprint,
            "parse_error": profile.parse_error,
            "fields": parsed_fields,
            "operators": parsed_operators,
            "windows": list(profile.windows),
        },
        "dataset": {
            "id": capability_sets.dataset_id,
            "field_count": len(capability_sets.dataset_field_names),
            "checked": bool(capability_sets.dataset_id and capability_sets.dataset_field_names),
        },
        "checked_fields": checked_fields,
        "group_context_fields": [field for field in parsed_fields if field in GROUP_CONTEXT_FIELDS],
        "missing_fields": missing_fields,
        "missing_operators": missing_operators,
        "dataset_mismatches": dataset_mismatches,
        "official_context": cache,
    }

def official_capability_sets(
    *,
    dataset_id: str = "",
    loader: OfficialDataLoader | None = None,
    mapper: FieldDatasetMapper | None = None,
    data_dir: str | None = None,
) -> OfficialCapabilitySets:
    """Build field/operator/dataset sets from local official context only."""

    active_loader = loader or OfficialDataLoader()
    active_loader.load_all(data_dir or "data")
    active_mapper = mapper or FieldDatasetMapper().build(active_loader)
    dataset = str(dataset_id or "").strip()
    fields = {
        str(getattr(field, "id", "") or "").strip().lower()
        for field in active_loader.get_fields()
        if str(getattr(field, "id", "") or "").strip()
    }
    operators = {
        str(getattr(operator, "name", "") or "").strip().lower()
        for operator in active_loader.get_operators()
        if str(getattr(operator, "name", "") or "").strip()
    }
    dataset_fields = set(active_mapper.fields_for(dataset)) if dataset else set()
    cache = _cache_summary(data_dir=data_dir)
    return OfficialCapabilitySets(
        field_names=frozenset(fields),
        operator_names=frozenset(operators),
        dataset_field_names=frozenset(str(field).strip().lower() for field in dataset_fields if str(field).strip()),
        dataset_id=dataset,
        cache_summary=cache,
    )

def expression_delta(
    child_expression: str,
    parent_expression: str = "",
) -> dict[str, Any]:
    """Return parser-derived parent/child field/operator/window differences."""

    child = profile_expression(child_expression)
    parent = profile_expression(parent_expression) if str(parent_expression or "").strip() else None
    return expression_delta_from_profiles(child, parent)

def expression_delta_from_profiles(
    child: ExpressionProfile,
    parent: ExpressionProfile | None = None,
) -> dict[str, Any]:
    parent_fields = set(parent.fields) if parent else set()
    child_fields = set(child.fields)
    parent_operators = set(parent.operators) if parent else set()
    child_operators = set(child.operators)
    parent_windows = set(parent.windows) if parent else set()
    child_windows = set(child.windows)
    return {
        "schema_version": EXPRESSION_DELTA_SCHEMA,
        "parent": _profile_block(parent),
        "child": _profile_block(child),
        "fields_added": sorted(child_fields - parent_fields),
        "fields_removed": sorted(parent_fields - child_fields),
        "fields_unchanged": sorted(parent_fields & child_fields),
        "operators_added": sorted(child_operators - parent_operators),
        "operators_removed": sorted(parent_operators - child_operators),
        "operators_unchanged": sorted(parent_operators & child_operators),
        "windows_added": sorted(child_windows - parent_windows),
        "windows_removed": sorted(parent_windows - child_windows),
        "windows_unchanged": sorted(parent_windows & child_windows),
        "changed": bool(
            not parent
            or child.fingerprint != parent.fingerprint
            or child_fields != parent_fields
            or child_operators != parent_operators
            or child_windows != parent_windows
        ),
    }

def _cache_summary(*, data_dir: str | None) -> dict[str, Any]:
    validation = validate_official_context(data_dir=data_dir, require_metadata=True, require_official_source=True)
    files = validation.get("files") if isinstance(validation.get("files"), dict) else {}
    lineage = validation.get("lineage") if isinstance(validation.get("lineage"), dict) else {}
    file_counts = {
        filename: _safe_int(summary.get("record_count"))
        for filename, summary in files.items()
        if isinstance(summary, dict)
    }
    stale_files = [
        filename
        for filename, summary in files.items()
        if isinstance(summary, dict)
        and isinstance(summary.get("metadata"), dict)
        and summary["metadata"].get("is_stale") is True
    ]
    return {
        "schema_version": "expression-official-context-cache.v1",
        "blocking_ok": bool(validation.get("blocking_ok")),
        "ok": bool(validation.get("ok")),
        "blocking_count": _safe_int(validation.get("blocking_count")),
        "p1_count": _safe_int(validation.get("p1_count")),
        "record_counts": file_counts,
        "metadata": {
            filename: {
                "source": str((summary.get("metadata") or {}).get("source") or ""),
                "sha256_matches": bool((summary.get("metadata") or {}).get("sha256_matches")),
                "record_count_matches": bool((summary.get("metadata") or {}).get("record_count_matches")),
                "complete": bool((summary.get("metadata") or {}).get("complete")),
                "is_stale": bool((summary.get("metadata") or {}).get("is_stale")),
            }
            for filename, summary in files.items()
            if isinstance(summary, dict)
        },
        "stale_files": stale_files,
        "lineage": {
            "field_count": _safe_int(lineage.get("field_count")),
            "dataset_count": _safe_int(lineage.get("dataset_count")),
            "dataset_field_count_sum": _safe_int(lineage.get("dataset_field_count_sum")),
            "field_count_sum_matches": bool(lineage.get("field_count_sum_matches")),
        },
    }

def _profile_block(profile: ExpressionProfile | None) -> dict[str, Any]:
    if profile is None:
        return {
            "parsed": False,
            "fingerprint": "",
            "fields": [],
            "operators": [],
            "windows": [],
        }
    return {
        "parsed": profile.parsed,
        "fingerprint": profile.fingerprint,
        "fields": list(profile.fields),
        "operators": list(profile.operators),
        "windows": list(profile.windows),
    }

def _normalized_list(values: tuple[str, ...] | list[str] | set[str]) -> list[str]:
    return sorted(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))

def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
