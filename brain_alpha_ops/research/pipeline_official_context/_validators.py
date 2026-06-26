"""Validator helpers for official BRAIN context fields/operators.

Extracted from the original ``pipeline_official_context.py`` monolith.
These pure helpers inspect candidate expressions against the active
official context (fields, operators, dataset membership).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.expression_official_context import GROUP_CONTEXT_FIELDS

from brain_alpha_ops.research.pipeline_official_context._types import (
    GENERAL_DATASET_FIELDS,
    OfficialContextValidationState,
    logger,
)


def configured_official_context_files_exist(storage_dir: str | Path) -> bool:
    root = Path(storage_dir)
    return any(
        (root / filename).is_file()
        for filename in ("official_fields.json", "official_operators.json", "official_datasets.json")
    )


def refresh_context_validation_cache(fields: list[dict], operators: list[dict]) -> OfficialContextValidationState:
    field_names: set[str] = set()
    for item in fields:
        for key in ("id", "name"):
            value = str(item.get(key, "")).strip().lower()
            if value:
                field_names.add(value)
    operator_names = {
        str(item.get("name", "")).strip().lower()
        for item in operators
        if item.get("name")
    }
    return OfficialContextValidationState(
        field_names=field_names,
        operator_names=operator_names,
        dataset_field_names_cache={},
    )


def active_dataset_field_names(dataset_id: str, mapper: Any, cache: dict[str, set[str]]) -> set[str]:
    dataset = str(dataset_id or "")
    if not dataset or not mapper:
        return set()
    cached = cache.get(dataset)
    if cached is not None:
        return cached
    try:
        fields = {str(field).lower() for field in mapper.fields_for(dataset)}
    except Exception as exc:
        logger.warning("active dataset field lookup unavailable for dataset_id=%s", dataset, exc_info=True)
        fields = set()
    cache[dataset] = fields
    return fields


def official_context_reasons(
    candidate: Candidate,
    *,
    available_fields: set[str],
    available_operators: set[str],
    active_dataset_id: str,
    mapper: Any,
    dataset_field_names_cache: dict[str, set[str]],
) -> list[str]:
    reasons: list[str] = []
    profile = profile_expression(candidate.expression)
    expression_fields = [
        str(field).lower()
        for field in profile.fields
        if str(field).strip() and str(field).lower() not in GROUP_CONTEXT_FIELDS
    ]
    expression_operators = [str(operator).lower() for operator in profile.operators if str(operator).strip()]
    candidate_fields = [str(field).lower() for field in candidate.data_fields if str(field).strip()]
    candidate_operators = [str(operator).lower() for operator in candidate.operators if str(operator).strip()]
    fields_to_check = sorted(dict.fromkeys([*candidate_fields, *expression_fields]))
    operators_to_check = sorted(dict.fromkeys([*candidate_operators, *expression_operators]))
    if not profile.parsed:
        reasons.append("expression parse failed before official context validation: " + (profile.parse_error or "unknown parse error"))
    if available_fields:
        missing_fields = sorted(field for field in fields_to_check if field not in available_fields)
        if missing_fields:
            reasons.append("fields unavailable in current official context: " + ", ".join(missing_fields))
    if available_operators:
        missing_operators = sorted(operator for operator in operators_to_check if operator not in available_operators)
        if missing_operators:
            reasons.append("operators unavailable in current official context: " + ", ".join(missing_operators))
    if active_dataset_id and mapper:
        dataset_fields = active_dataset_field_names(active_dataset_id, mapper, dataset_field_names_cache)
        for field in fields_to_check:
            if field not in dataset_fields and field not in GENERAL_DATASET_FIELDS:
                reasons.append(
                    f"field '{field}' not in active dataset '{active_dataset_id}'. "
                    "Expression may use fields from wrong dataset."
                )
                break
    return reasons
