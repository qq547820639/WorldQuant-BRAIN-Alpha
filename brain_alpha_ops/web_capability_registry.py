"""Auditable BRAIN capability registry for the local Web console.

The registry is deliberately offline. It combines immutable canonical settings
with the local official context cache and never refreshes or calls BRAIN APIs.
When cache evidence is missing or internally inconsistent, callers get a
``needs_human_confirmation`` status instead of inferred platform rules.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS, CANONICAL_SETTINGS
from brain_alpha_ops.config_models import BrainSettings
from brain_alpha_ops.web_cloud_snapshot import official_context_file_counts as _official_context_file_counts

REGISTRY_SCHEMA_VERSION = "brain_capability_registry.v1"
_CONTEXT_FILES = {
    "fields": "official_fields.json",
    "operators": "official_operators.json",
    "datasets": "official_datasets.json",
}
_CONTEXT_COUNT_KEYS = {
    "fields": "fields_count",
    "operators": "operators_count",
    "datasets": "datasets_count",
}

def capability_settings_options(dataset_options: list[dict[str, Any]] | None = None) -> dict[str, list[Any]]:
    """Return Web-config enum options from the canonical settings contract."""

    options = {key: _sorted_values(values) for key, values in CANONICAL_SETTINGS.items()}
    dataset_ids = [
        str(row.get("id") or "").strip()
        for row in dataset_options or []
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    ]
    if dataset_ids:
        options["dataset"] = sorted(dict.fromkeys(dataset_ids))
    return options

def build_capability_registry(
    *,
    public_config_schema: Callable[[], dict[str, Any]] | None = None,
    official_context_file_counts: Callable[[], dict[str, Any]] = _official_context_file_counts,
) -> dict[str, Any]:
    """Build the current local capability registry without remote side effects."""

    schema, schema_error = _safe_call(public_config_schema) if public_config_schema else ({}, "")
    counts, counts_error = _safe_call(official_context_file_counts)
    schema = schema if isinstance(schema, dict) else {}
    counts = counts if isinstance(counts, dict) else {}

    dataset_options = schema.get("dataset_options") if isinstance(schema.get("dataset_options"), list) else []
    settings_options = capability_settings_options(dataset_options)
    parameters = _parameter_specs()
    official_context = _official_context_summary(counts)
    findings = _registry_findings(schema, counts, settings_options, parameters)
    if schema_error:
        findings.append(_finding("config_schema_unavailable", "P0", schema_error, "configuration schema"))
    if counts_error:
        findings.append(_finding("official_context_counts_unavailable", "P0", counts_error, "official context cache"))

    blocking = [item for item in findings if item.get("severity") == "P0"]
    status = "ready" if not blocking else "needs_human_confirmation"
    return {
        "ok": True,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "status": status,
        "human_confirmation_required": bool(blocking),
        "official_api_called": False,
        "source": "canonical_settings_and_local_official_cache",
        "source_refs": [
            "brain_alpha_ops.brain_api.canonical.CANONICAL_SETTINGS",
            "brain_alpha_ops.web_cloud_snapshot.official_context_file_counts",
            "brain_alpha_ops.config_models.BrainSettings",
        ],
        "settings_options": settings_options,
        "parameters": parameters,
        "api_paths": _api_path_specs(),
        "official_context": official_context,
        "config_schema_version": schema.get("schema_version", ""),
        "findings": findings,
        "blocking_count": len(blocking),
    }

def check_capability_registry(
    *,
    public_config_schema: Callable[[], dict[str, Any]] | None = None,
    official_context_file_counts: Callable[[], dict[str, Any]] = _official_context_file_counts,
) -> dict[str, Any]:
    """Return a machine-readable pass/fail check for CI and local audits."""

    registry = build_capability_registry(
        public_config_schema=public_config_schema,
        official_context_file_counts=official_context_file_counts,
    )
    return {
        "ok": registry["blocking_count"] == 0,
        "schema_version": "brain_capability_registry_check.v1",
        "registry_schema_version": registry["schema_version"],
        "status": registry["status"],
        "official_api_called": False,
        "blocking_count": registry["blocking_count"],
        "findings": registry["findings"],
        "summary": {
            "settings_count": len(registry["settings_options"]),
            "parameter_count": len(registry["parameters"]),
            "official_context": registry["official_context"],
        },
    }

def _parameter_specs() -> dict[str, dict[str, Any]]:
    defaults = BrainSettings()
    specs: dict[str, dict[str, Any]] = {}
    for key, allowed in CANONICAL_SETTINGS.items():
        specs[key] = {
            "kind": "enum",
            "required": True,
            "default": getattr(defaults, key),
            "allowed": _sorted_values(allowed),
            "source": f"canonical.CANONICAL_SETTINGS.{key}",
        }
    specs.update(
        {
            "dataset": {
                "kind": "official_context_reference",
                "required": False,
                "default": defaults.dataset,
                "source": "local official_datasets.json cache",
                "missing_behavior": "needs_human_confirmation",
            },
            "decay": {
                "kind": "integer",
                "required": True,
                "default": defaults.decay,
                "min": 0,
                "source": "brain_alpha_ops.config_domain_validation.validate_settings",
            },
            "truncation": {
                "kind": "float",
                "required": True,
                "default": defaults.truncation,
                "min": 0.0,
                "max": 1.0,
                "source": "brain_alpha_ops.config_domain_validation.validate_settings",
            },
            "visualization": {
                "kind": "boolean",
                "required": True,
                "default": defaults.visualization,
                "allowed": [False, True],
                "source": "brain_alpha_ops.config_domain_validation.validate_settings",
            },
        }
    )
    return specs

def _api_path_specs() -> dict[str, dict[str, str]]:
    return {
        key: {"path": path, "source": f"canonical.CANONICAL_API_PATHS.{key}"}
        for key, path in sorted(CANONICAL_API_PATHS.items())
    }

def _official_context_summary(counts: dict[str, Any]) -> dict[str, Any]:
    manifest = counts.get("context_cache_manifest") if isinstance(counts.get("context_cache_manifest"), dict) else {}
    files = {}
    for group, filename in _CONTEXT_FILES.items():
        record_count = _safe_int(counts.get(_CONTEXT_COUNT_KEYS[group]))
        files[filename] = {
            "group": group,
            "record_count": record_count,
            "source": "local_cache",
            "required": True,
            "complete": filename not in set(manifest.get("invalid_files") or []),
            "stale": filename in set(manifest.get("stale_files") or manifest.get("expired_files") or []),
        }
    return {
        "files": files,
        "manifest_complete": bool(manifest.get("complete")),
        "manifest_stale": bool(manifest.get("is_stale")),
        "missing_files": list(manifest.get("missing_files") or []),
        "invalid_files": list(manifest.get("invalid_files") or []),
        "stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or []),
        "record_counts": dict(manifest.get("record_counts") or {}),
    }

def _registry_findings(
    schema: dict[str, Any],
    counts: dict[str, Any],
    settings_options: dict[str, list[Any]],
    parameters: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    schema_options = schema.get("settings_options") if isinstance(schema.get("settings_options"), dict) else {}
    for key, expected in settings_options.items():
        if key == "dataset" and key not in schema_options:
            continue
        actual = schema_options.get(key)
        if actual is None:
            findings.append(_finding(f"schema_missing_setting_options:{key}", "P0", "config schema is missing setting options", key))
            continue
        if _normalized_values(actual) != _normalized_values(expected):
            findings.append(
                _finding(
                    f"schema_setting_options_drift:{key}",
                    "P0",
                    "config schema setting options drift from the capability registry",
                    key,
                    {"expected": expected, "actual": actual},
                )
            )

    for field in schema.get("required_settings_fields") or []:
        if str(field) not in parameters:
            findings.append(
                _finding(
                    f"required_setting_missing_registry:{field}",
                    "P0",
                    "required production setting is absent from the capability registry",
                    str(field),
                )
            )

    manifest = counts.get("context_cache_manifest") if isinstance(counts.get("context_cache_manifest"), dict) else {}
    if not manifest:
        findings.append(
            _finding(
                "official_context_manifest_missing",
                "P0",
                "official context cache manifest is missing; field/operator/dataset capability freshness is unknown",
                "official_context",
            )
        )
    elif not bool(manifest.get("complete")):
        findings.append(
            _finding(
                "official_context_manifest_incomplete",
                "P0",
                "official context cache manifest is incomplete",
                "official_context",
                {
                    "missing_files": list(manifest.get("missing_files") or []),
                    "invalid_files": list(manifest.get("invalid_files") or []),
                },
            )
        )
    if bool(manifest.get("is_stale")):
        findings.append(
            _finding(
                "official_context_manifest_stale",
                "P1",
                "official context cache is stale and should be refreshed before production use",
                "official_context",
                {"stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or [])},
            )
        )

    for group, count_key in _CONTEXT_COUNT_KEYS.items():
        if _safe_int(counts.get(count_key)) <= 0:
            findings.append(
                _finding(
                    f"official_{group}_empty",
                    "P0",
                    f"official {group} capability cache is empty",
                    _CONTEXT_FILES[group],
                )
            )
    return findings

def _safe_call(func: Callable[[], dict[str, Any]] | None) -> tuple[dict[str, Any], str]:
    if func is None:
        return {}, ""
    try:
        value = func()
    except Exception as exc:  # pragma: no cover - defensive route guard
        return {}, str(exc)
    return value if isinstance(value, dict) else {}, ""

def _finding(code: str, severity: str, message: str, capability: str, evidence: Any = None) -> dict[str, Any]:
    result = {
        "code": code,
        "severity": severity,
        "message": message,
        "capability": capability,
    }
    if evidence is not None:
        result["evidence"] = evidence
    return result

def _sorted_values(values: Any) -> list[Any]:
    return sorted(list(values), key=lambda item: str(item))

def _normalized_values(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set, frozenset)):
        return []
    return sorted(str(value) for value in values)

def _safe_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
