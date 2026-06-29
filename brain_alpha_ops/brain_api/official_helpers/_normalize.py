"""Data normalization, metrics extraction, and numeric helper functions."""

from __future__ import annotations
from dataclasses import asdict

import logging
from typing import Any

from brain_alpha_ops.config import BrainSettings
from brain_alpha_ops.redaction import redact_data

_logger = logging.getLogger("brain_alpha_ops.brain_api.official_helpers")


def build_simulation_payload(expression: str, settings: dict | BrainSettings) -> dict:
    if isinstance(settings, BrainSettings):
        settings_obj = settings
    else:
        settings_obj = BrainSettings(**{**asdict(BrainSettings()), **(settings or {})})
    platform = settings_obj.to_platform_dict()
    platform["regular"] = expression
    return platform


def normalize_metrics(payload: Any) -> dict:
    """Extract all BRAIN response metrics into a flat, scoring-ready dict."""
    metrics_root = _first_value(payload, ["is", "metrics", "result", "results"], payload)
    os_root = _first_value(payload, ["os"], {}) or {}

    checks = _find_all(payload, "checks")
    flat_checks = []
    for item in checks:
        if isinstance(item, list):
            flat_checks.extend(item)

    failed = []
    passed = []
    pending = []
    brain_checks = {}
    for item in flat_checks:
        if not isinstance(item, dict):
            continue
        result = str(_first_value(item, ["result", "status"], "")).upper()
        name = str(_first_value(item, ["name", "check"], "?"))
        entry = {
            "result": result,
            "limit": _first_value(item, ["limit"], None),
            "value": _first_value(item, ["value"], None),
        }
        brain_checks[name] = entry
        if result in {"FAIL", "FAILED"}:
            failed.append(item)
        elif result == "PASS":
            passed.append(item)
        elif result == "PENDING":
            pending.append(item)

    non_pending_fails = [f for f in failed if str(_first_value(f, ["name", "check"], "")) != "SELF_CORRELATION"]
    brain_pass = len(non_pending_fails) == 0

    os_sharpe = _num(_first_value(os_root, ["sharpe", "Sharpe"]))
    is_sharpe = _num(_first_value(metrics_root, ["sharpe", "Sharpe"]))
    is_oos_ratio = round(is_sharpe / os_sharpe, 4) if os_sharpe != 0 else 0.0

    self_correlation_check = brain_checks.get("SELF_CORRELATION") if isinstance(brain_checks, dict) else None
    self_correlation_status = ""
    self_correlation_check_value = None
    if isinstance(self_correlation_check, dict):
        self_correlation_status = str(self_correlation_check.get("result") or "")
        self_correlation_check_value = _num_or_none(self_correlation_check.get("value"))
    correlation_value = _num_or_none(_first_value(
        metrics_root,
        ["correlation", "selfCorrelation", "self_correlation", "prodCorrelation", "prod_correlation"],
        None,
    ))
    self_correlation_value = _num_or_none(_first_value(
        metrics_root,
        ["selfCorrelation", "self_correlation"],
        None,
    ))
    if self_correlation_value is None:
        self_correlation_value = self_correlation_check_value
    prod_correlation_value = _num_or_none(_first_value(
        metrics_root,
        ["prodCorrelation", "prod_correlation"],
        None,
    ))
    sub_universe_sharpe_value = _num_or_none(_first_value(
        metrics_root,
        ["subUniverseSharpe", "sub_universe_sharpe"],
        None,
    ))
    if sub_universe_sharpe_value is None:
        low_sub_universe_check = brain_checks.get("LOW_SUB_UNIVERSE_SHARPE") if isinstance(brain_checks, dict) else None
        if isinstance(low_sub_universe_check, dict):
            sub_universe_sharpe_value = _num_or_none(low_sub_universe_check.get("value"))

    metrics = {
        "sharpe": is_sharpe,
        "fitness": _num(_first_value(metrics_root, ["fitness", "Fitness"])),
        "turnover": _ratio(_first_value(metrics_root, ["turnover", "Turnover"])),
        "turnover_raw": _num(_first_value(metrics_root, ["turnover", "Turnover"])),
        "returns": _num_or_none(_first_value(metrics_root, ["returns", "Returns", "return"], None)),
        "drawdown": abs(_ratio(_first_value(metrics_root, ["drawdown", "maxDrawdown", "MaxDrawdown"]), bounded=True)),
        "margin": _num_or_none(_first_value(metrics_root, ["margin", "Margin"], None)),
        "sub_universe_sharpe": sub_universe_sharpe_value,
        "subUniverseSize": _num_or_none(_first_value(metrics_root, ["subUniverseSize", "sub_universe_size", "subSize"], None)),
        "alphaSize": _num_or_none(_first_value(metrics_root, ["alphaSize", "alpha_size"], None)),
        "correlation": abs(_ratio(correlation_value, bounded=True)) if correlation_value is not None else None,
        "self_correlation": abs(_ratio(self_correlation_value, bounded=True)) if self_correlation_value is not None else None,
        "prod_correlation": abs(_ratio(prod_correlation_value, bounded=True)) if prod_correlation_value is not None else None,
        "self_correlation_status": self_correlation_status or None,
        "weight_concentration": _ratio(_first_value(metrics_root, ["weightConcentration", "weight_concentration"], 0.0), bounded=True),
        "pass_fail": "FAIL" if failed else "PASS",
        "failure_reason": ", ".join(str(_first_value(item, ["name", "title", "check"], "FAILED_CHECK")) for item in failed[:3]) or None,
        "brain_checks": brain_checks,
        "brain_pass": brain_pass,
        "brain_failed_names": [str(_first_value(f, ["name", "check"], "?")) for f in failed],
        "brain_passed_names": [str(_first_value(p, ["name", "check"], "?")) for p in passed],
        "brain_pending_names": [str(_first_value(p, ["name", "check"], "?")) for p in pending],
        "is_oos_ratio": is_oos_ratio,
        "os_sharpe": os_sharpe,
    }
    return {key: value for key, value in metrics.items() if value is not None}


def _first_value(data: Any, keys: list[str], default: Any = None) -> Any:
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        for value in data.values():
            found = _first_value(value, keys, None)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _first_value(value, keys, None)
            if found is not None:
                return found
    return default


def _find_all(data: Any, key: str) -> list:
    found = []
    if isinstance(data, dict):
        for item_key, value in data.items():
            if item_key == key:
                found.append(value)
            found.extend(_find_all(value, key))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_all(item, key))
    return found


def normal_field(item: dict) -> dict:
    field_id = _first_value(item, ["id", "fieldId", "field", "name"], "")
    field_name = _first_value(item, ["name", "field", "id", "fieldId"], "")
    dataset = _first_value(item, ["dataset", "dataSet", "data_set"], "")
    dataset_id = ""
    if isinstance(dataset, dict):
        dataset_id = _first_value(dataset, ["id", "code", "datasetId", "name"], "")
        dataset_value: Any = scrub(dataset)
    else:
        dataset_id = dataset
        dataset_value = str(dataset or "")
    cat = item.get("category")
    if isinstance(cat, dict):
        cat = cat.get("id", str(cat))
    elif not isinstance(cat, str):
        cat = ""
    return {
        "id": str(field_id or field_name or ""),
        "name": str(field_name or field_id or ""),
        "description": _first_value(item, ["description", "definition", "help", "doc"], ""),
        "dataset": dataset_value,
        "dataset_id": str(dataset_id or ""),
        "type": _first_value(item, ["type", "dataType", "fieldType"], ""),
        "userCount": _first_value(item, ["userCount", "user_count"], None),
        "alphaCount": _first_value(item, ["alphaCount", "alpha_count"], None),
        "category": cat,
        "delay": _first_value(item, ["delay"], None),
        "coverage": _num(_first_value(item, ["coverage"], 0.0)),
        "raw": scrub(item),
    }


def normal_operator(item: dict) -> dict:
    return {
        "name": str(_first_value(item, ["name", "id", "operator"], "")),
        "category": _first_value(item, ["category", "scope", "type"], ""),
        "description": _first_value(item, ["description", "definition", "help", "doc"], ""),
        "raw": scrub(item),
    }


def normal_dataset(item: dict) -> dict:
    dataset_id = _first_value(item, ["id", "code", "datasetId", "dataset"], "")
    if isinstance(dataset_id, dict):
        dataset_id = _first_value(dataset_id, ["id", "code", "datasetId"], "")
    field_count = _first_value(
        item,
        ["field_count", "fieldCount", "fieldsCount", "dataFieldCount", "data_field_count", "fields"],
        0,
    )
    if isinstance(field_count, list):
        field_count = len(field_count)
    try:
        numeric_field_count = int(field_count or 0)
    except (TypeError, ValueError):
        numeric_field_count = 0
    return {
        "id": str(dataset_id or ""),
        "name": str(_first_value(item, ["name", "title", "description"], dataset_id or "")),
        "field_count": numeric_field_count,
        "category": _first_value(item, ["category", "group"], ""),
        "region": _first_value(item, ["region"], ""),
        "delay": _first_value(item, ["delay"], None),
        "universe": _first_value(item, ["universe"], ""),
        "raw": scrub(item),
    }


def normal_data_category(item: dict) -> dict:
    category_id = _first_value(item, ["id", "code", "category", "name"], "")
    return {
        "id": str(category_id or ""),
        "name": str(_first_value(item, ["name", "title", "description"], category_id or "")),
        "raw": scrub(item),
    }


def normal_alpha(item: dict) -> dict:
    expression = _first_value(item, ["expression", "regular", "code", "formula"], "")
    settings = _first_value(item, ["settings"], {})
    metrics = normalize_metrics(item)
    alpha_id = _first_value(item, ["id", "alpha_id", "alphaId"], "")
    return {
        "id": str(alpha_id),
        "status": str(_first_value(item, ["status", "state", "lifecycle"], "")),
        "expression": str(expression or ""),
        "created_at": str(_first_value(item, ["created_at", "dateCreated", "createdDate", "timestamp"], "")),
        "settings": settings if isinstance(settings, dict) else {},
        "metrics": metrics,
        "raw": scrub(item),
    }


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        if isinstance(value, bool):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _num_or_none(value: Any):
    if value in (None, ""):
        return None
    return _num(value)


def _ratio(value: Any, *, bounded: bool = False) -> float:
    """Convert a metric value to a decimal ratio (unified rule).

    Delegates to :func:`brain_alpha_ops.research._ratio.normalize_brain_ratio`
    so that ``official_helpers`` uses the same threshold as the rest of the
    codebase: ``abs(value) >= 100`` triggers division by 100 in unbounded
    mode (default), and ``abs(value) > 1.0`` triggers it in bounded mode for
    metrics mathematically clamped to ``[0, 1]`` (drawdown, correlation,
    weight concentration).

    This replaces the legacy ``abs >= 2.0`` heuristic which incorrectly
    compressed natural turnover values like ``2.5 → 0.025``.
    """
    from brain_alpha_ops.research._ratio import normalize_brain_ratio

    return normalize_brain_ratio(value, bounded=bounded)


def merge_payloads(left: Any, right: Any) -> dict:
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        merged.update(right)
        return merged
    return {"simulation": left, "alpha": right}


def scrub(data: Any) -> Any:
    return redact_data(data)
