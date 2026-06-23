"""Unified BRAIN capability registry validation.

Validates bidirectional consistency between:
  - Registry fields vs generator template fields
  - Registry operators vs scoring/gates operators
  - Dataset IDs in config vs registry datasets
  - Threshold version snapshot tracking

All checks are offline and deterministic — no API calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

REGISTRY_VALIDATION_SCHEMA = "registry_validation.v1"


def validate_registry_consistency(
    *,
    registry: dict[str, Any] | None = None,
    scoring_operators: set[str] | None = None,
    gate_operators: set[str] | None = None,
    generator_template_fields: set[str] | None = None,
    config_dataset_ids: set[str] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run full bidirectional consistency checks between registry and code.

    Args:
        registry: capability registry dict (from build_capability_registry)
        scoring_operators: set of operator names used in scoring
        gate_operators: set of operator names used in gates
        generator_template_fields: set of field names used in generator templates
        config_dataset_ids: set of dataset IDs from run_config
        thresholds: threshold values dict for version snapshot

    Returns dict with ok status, findings, and threshold snapshot.
    """
    findings: list[dict[str, Any]] = []

    if registry is None:
        registry = _load_default_registry()

    registry_fields = _extract_registry_fields(registry)
    registry_operators = _extract_registry_operators(registry)
    registry_datasets = _extract_registry_datasets(registry)

    if generator_template_fields is not None:
        field_findings = _check_fields_vs_templates(
            registry_fields, generator_template_fields
        )
        findings.extend(field_findings)

    all_operators = set()
    if scoring_operators:
        all_operators.update(scoring_operators)
    if gate_operators:
        all_operators.update(gate_operators)
    if all_operators:
        operator_findings = _check_operators_vs_registry(
            registry_operators, all_operators, scoring_operators or set(), gate_operators or set()
        )
        findings.extend(operator_findings)

    if config_dataset_ids is not None:
        dataset_findings = _check_datasets_vs_config(
            registry_datasets, config_dataset_ids
        )
        findings.extend(dataset_findings)

    threshold_snapshot = _build_threshold_snapshot(thresholds) if thresholds else {}

    blocking = [f for f in findings if f.get("severity") == "BLOCKING"]
    warnings = [f for f in findings if f.get("severity") == "WARNING"]

    return {
        "ok": len(blocking) == 0,
        "schema_version": REGISTRY_VALIDATION_SCHEMA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "findings": findings,
        "threshold_snapshot": threshold_snapshot,
        "summary": {
            "registry_fields_count": len(registry_fields),
            "registry_operators_count": len(registry_operators),
            "registry_datasets_count": len(registry_datasets),
            "template_fields_count": len(generator_template_fields) if generator_template_fields else None,
            "scoring_operators_count": len(scoring_operators) if scoring_operators else None,
            "config_datasets_count": len(config_dataset_ids) if config_dataset_ids else None,
        },
    }


def snapshot_threshold_version(
    thresholds: dict[str, Any],
    *,
    version_label: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Create a threshold version snapshot for audit trail.

    Captures the current threshold values with a hash for change detection.
    """
    sorted_json = json.dumps(thresholds, sort_keys=True, default=str)
    content_hash = hashlib.sha256(sorted_json.encode()).hexdigest()[:16]
    snapshot = {
        "schema_version": REGISTRY_VALIDATION_SCHEMA,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "version_label": version_label,
        "description": description,
        "content_hash": content_hash,
        "thresholds": dict(thresholds),
        "threshold_count": len(thresholds),
    }
    return snapshot


def compare_threshold_snapshots(
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two threshold version snapshots to detect drift.

    Returns diff details and whether snapshots are identical.
    """
    thresholds_a = snapshot_a.get("thresholds", {})
    thresholds_b = snapshot_b.get("thresholds", {})
    all_keys = sorted(set(list(thresholds_a.keys()) + list(thresholds_b.keys())))
    changed: list[dict[str, Any]] = []
    added: list[str] = []
    removed: list[str] = []
    for key in all_keys:
        val_a = thresholds_a.get(key)
        val_b = thresholds_b.get(key)
        if val_a is None:
            added.append(key)
        elif val_b is None:
            removed.append(key)
        elif val_a != val_b:
            changed.append({"key": key, "from": val_a, "to": val_b})
    identical = not changed and not added and not removed
    return {
        "identical": identical,
        "changed": changed,
        "added": added,
        "removed": removed,
        "snapshot_a_hash": snapshot_a.get("content_hash", ""),
        "snapshot_b_hash": snapshot_b.get("content_hash", ""),
    }


def _check_fields_vs_templates(
    registry_fields: set[str],
    template_fields: set[str],
) -> list[dict[str, Any]]:
    """Check that template fields exist in the registry."""
    findings: list[dict[str, Any]] = []
    missing = template_fields - registry_fields
    if missing:
        findings.append({
            "code": "template_field_not_in_registry",
            "severity": "BLOCKING",
            "message": f"Generator template uses fields not in registry: {sorted(missing)[:10]}",
            "details": {"missing_fields": sorted(missing)},
        })
    unused = registry_fields - template_fields
    if unused and len(unused) < len(registry_fields):
        findings.append({
            "code": "registry_field_not_in_templates",
            "severity": "WARNING",
            "message": f"Registry has fields not used in any template: {sorted(unused)[:10]}",
            "details": {"unused_fields": sorted(unused)},
        })
    return findings


def _check_operators_vs_registry(
    registry_operators: set[str],
    code_operators: set[str],
    scoring_operators: set[str],
    gate_operators: set[str],
) -> list[dict[str, Any]]:
    """Check that scoring/gate operators exist in the registry."""
    findings: list[dict[str, Any]] = []
    missing = code_operators - registry_operators
    if missing:
        findings.append({
            "code": "operator_not_in_registry",
            "severity": "BLOCKING",
            "message": f"Code uses operators not in registry: {sorted(missing)[:10]}",
            "details": {"missing_operators": sorted(missing)},
        })
    scoring_missing = scoring_operators - registry_operators
    if scoring_missing:
        findings.append({
            "code": "scoring_operator_not_in_registry",
            "severity": "BLOCKING",
            "message": f"Scoring uses operators not in registry: {sorted(scoring_missing)[:10]}",
            "details": {"missing_operators": sorted(scoring_missing)},
        })
    gate_missing = gate_operators - registry_operators
    if gate_missing:
        findings.append({
            "code": "gate_operator_not_in_registry",
            "severity": "BLOCKING",
            "message": f"Gates use operators not in registry: {sorted(gate_missing)[:10]}",
            "details": {"missing_operators": sorted(gate_missing)},
        })
    return findings


def _check_datasets_vs_config(
    registry_datasets: set[str],
    config_datasets: set[str],
) -> list[dict[str, Any]]:
    """Check that config dataset IDs exist in the registry."""
    findings: list[dict[str, Any]] = []
    missing = config_datasets - registry_datasets
    if missing:
        findings.append({
            "code": "config_dataset_not_in_registry",
            "severity": "BLOCKING",
            "message": f"Config references datasets not in registry: {sorted(missing)[:10]}",
            "details": {"missing_datasets": sorted(missing)},
        })
    return findings


def _extract_registry_fields(registry: dict[str, Any]) -> set[str]:
    """Extract field names from the capability registry."""
    fields: set[str] = set()
    settings_options = registry.get("settings_options", {})
    for key, values in settings_options.items():
        if isinstance(values, list):
            for val in values:
                fields.add(str(val).lower())
    return fields


def _extract_registry_operators(registry: dict[str, Any]) -> set[str]:
    """Extract operator names from the capability registry."""
    operators: set[str] = set()
    parameters = registry.get("parameters", {})
    for key, spec in parameters.items():
        if isinstance(spec, dict) and spec.get("kind") == "enum":
            allowed = spec.get("allowed", [])
            if isinstance(allowed, list):
                for val in allowed:
                    operators.add(str(val).lower())
    return operators


def _extract_registry_datasets(registry: dict[str, Any]) -> set[str]:
    """Extract dataset IDs from the capability registry."""
    datasets: set[str] = set()
    official = registry.get("official_context", {})
    files = official.get("files", {})
    for filename, info in files.items():
        if isinstance(info, dict) and "dataset" in filename.lower():
            datasets.add(filename)
    settings_options = registry.get("settings_options", {})
    dataset_options = settings_options.get("dataset", [])
    if isinstance(dataset_options, list):
        for val in dataset_options:
            datasets.add(str(val))
    return datasets


def _build_threshold_snapshot(thresholds: dict[str, Any]) -> dict[str, Any]:
    """Build a threshold version snapshot from threshold values."""
    return snapshot_threshold_version(thresholds)


def _load_default_registry() -> dict[str, Any]:
    """Load the default capability registry if available."""
    try:
        from brain_alpha_ops.web.config.web_capability_registry import build_capability_registry
        return build_capability_registry()
    except Exception:
        logger.debug("failed to load default capability registry", exc_info=True)
        return {}
