"""Auditable runtime parameter snapshots for BRAIN runs and reports."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS, CANONICAL_THRESHOLDS
from brain_alpha_ops.redaction import redact_data


SCHEMA_VERSION = "parameter_audit_snapshot.v1"
REQUIRED_TRACE_SECTIONS = (
    "ops.settings",
    "ops.budget",
    "ops.thresholds",
    "ops.submission_policy",
    "ops.scoring",
    "ops.official_api",
)
_API_ATTR_TO_CANONICAL = {
    "authentication_path": "authentication",
    "simulations_path": "simulations",
    "data_sets_path": "data_sets",
    "data_fields_path": "data_fields",
    "operators_path": "operators",
    "user_alphas_path": "user_alphas",
    "user_profile_path": "user_profile",
    "alpha_check_path_template": "alpha_check",
    "alpha_submit_path_template": "alpha_submit",
    "alpha_path_template": "alpha_detail",
    "alpha_correlations_path": "alpha_correlations",
}


def build_parameter_audit_snapshot(
    config_or_ops: Any,
    *,
    environment: str | None = None,
    auto_submit: bool | None = None,
    source: str = "runtime",
) -> dict[str, Any]:
    """Return a redacted parameter snapshot with canonical drift evidence."""
    ops = getattr(config_or_ops, "ops", config_or_ops)
    environment = str(environment if environment is not None else getattr(config_or_ops, "environment", ""))
    auto_submit_value = auto_submit if auto_submit is not None else getattr(config_or_ops, "auto_submit", None)
    sections = {
        "ops.settings": _public_dataclass_dict(getattr(ops, "settings", None)),
        "ops.budget": _public_dataclass_dict(getattr(ops, "budget", None)),
        "ops.thresholds": _public_dataclass_dict(getattr(ops, "thresholds", None)),
        "ops.submission_policy": _public_dataclass_dict(getattr(ops, "submission_policy", None)),
        "ops.scoring": _public_dataclass_dict(getattr(ops, "scoring", None)),
        "ops.official_api": _public_dataclass_dict(getattr(ops, "official_api", None)),
    }
    threshold_trace = _threshold_trace(sections["ops.thresholds"])
    api_trace = _api_trace(sections["ops.official_api"])
    findings = _findings(sections, threshold_trace, api_trace)
    stable_payload = {
        "environment": environment,
        "auto_submit": auto_submit_value,
        "sections": sections,
        "canonical_thresholds": threshold_trace,
        "canonical_api_paths": api_trace,
    }
    config_hash = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    blocking_count = sum(1 for item in findings if item["severity"] == "P0")
    return {
        "ok": blocking_count == 0,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "environment": environment,
        "auto_submit": auto_submit_value,
        "config_hash": config_hash,
        "traceable_sections": list(REQUIRED_TRACE_SECTIONS),
        "sections": sections,
        "canonical_thresholds": threshold_trace,
        "canonical_api_paths": api_trace,
        "thresholds_zero_deviation": all(row["match"] for row in threshold_trace.values()),
        "api_paths_aligned": all(row["match"] for row in api_trace.values()),
        "finding_count": len(findings),
        "blocking_count": blocking_count,
        "findings": findings,
    }


def _public_dataclass_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        payload = asdict(value)
    elif isinstance(value, dict):
        payload = dict(value)
    else:
        payload = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    redacted = redact_data(payload)
    return redacted if isinstance(redacted, dict) else {}


def _threshold_trace(thresholds: dict[str, Any]) -> dict[str, dict[str, Any]]:
    trace: dict[str, dict[str, Any]] = {}
    for key, canonical in CANONICAL_THRESHOLDS.items():
        current = thresholds.get(key)
        deviation = _num(current) - _num(canonical) if current is not None else None
        trace[key] = {
            "configured": current,
            "canonical": canonical,
            "deviation": deviation,
            "match": current == canonical,
            "source": "BRAIN_Official",
        }
    return trace


def _api_trace(official_api: dict[str, Any]) -> dict[str, dict[str, Any]]:
    trace: dict[str, dict[str, Any]] = {}
    for attr, canonical_key in _API_ATTR_TO_CANONICAL.items():
        canonical = CANONICAL_API_PATHS[canonical_key]
        current = official_api.get(attr)
        trace[attr] = {
            "configured": current,
            "canonical": canonical,
            "match": current == canonical,
            "source": "BRAIN_Official",
        }
    base_url = official_api.get("base_url")
    trace["base_url"] = {
        "configured": base_url,
        "canonical": "https://api.worldquantbrain.com",
        "match": base_url == "https://api.worldquantbrain.com",
        "source": "BRAIN_Official",
    }
    return trace


def _findings(
    sections: dict[str, dict[str, Any]],
    threshold_trace: dict[str, dict[str, Any]],
    api_trace: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for section in REQUIRED_TRACE_SECTIONS:
        if not sections.get(section):
            findings.append(
                {
                    "severity": "P0",
                    "code": "missing_parameter_section",
                    "section": section,
                    "message": f"{section} is missing from the runtime parameter audit snapshot.",
                }
            )
    for key, row in threshold_trace.items():
        if not row["match"]:
            findings.append(
                {
                    "severity": "P0",
                    "code": "threshold_drift",
                    "section": "ops.thresholds",
                    "parameter": key,
                    "configured": row["configured"],
                    "canonical": row["canonical"],
                    "message": f"Threshold {key} does not match the canonical BRAIN value.",
                }
            )
    for key, row in api_trace.items():
        if not row["match"]:
            findings.append(
                {
                    "severity": "P1",
                    "code": "official_api_path_drift",
                    "section": "ops.official_api",
                    "parameter": key,
                    "configured": row["configured"],
                    "canonical": row["canonical"],
                    "message": f"Official API parameter {key} differs from the canonical BRAIN path.",
                }
            )
    return findings


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
