"""Pure helpers for the official BRAIN API adapter."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from typing import Any

from brain_alpha_ops.config import BrainSettings
from brain_alpha_ops.redaction import redact_data

from .base import BrainAPIError


def looks_partial_context_cache(kind: str, items: list[dict], total: int, page_limit: int) -> bool:
    if total and len(items) >= total:
        return False
    if total and len(items) < total:
        return True
    return kind in {"fields", "datasets", "operators"} and len(items) == int(page_limit)


def build_simulation_payload(expression: str, settings: dict | BrainSettings) -> dict:
    if isinstance(settings, BrainSettings):
        settings_obj = settings
    else:
        settings_obj = BrainSettings(**{**BrainSettings().__dict__, **(settings or {})})
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
        ["correlation", "prodCorrelation", "selfCorrelation", "self_correlation"],
        None,
    ))
    self_correlation_value = _num_or_none(_first_value(
        metrics_root,
        ["selfCorrelation", "self_correlation", "correlation", "prodCorrelation"],
        None,
    ))
    if self_correlation_value is None:
        self_correlation_value = self_correlation_check_value

    metrics = {
        "sharpe": is_sharpe,
        "fitness": _num(_first_value(metrics_root, ["fitness", "Fitness"])),
        "turnover": _ratio(_first_value(metrics_root, ["turnover", "Turnover"])),
        "turnover_raw": _num(_first_value(metrics_root, ["turnover", "Turnover"])),
        "returns": _num_or_none(_first_value(metrics_root, ["returns", "Returns", "return"], None)),
        "drawdown": abs(_ratio(_first_value(metrics_root, ["drawdown", "maxDrawdown", "MaxDrawdown"]))),
        "margin": _num_or_none(_first_value(metrics_root, ["margin", "Margin"], None)),
        "sub_universe_sharpe": _num(_first_value(metrics_root, ["subUniverseSharpe", "sub_universe_sharpe"])),
        "correlation": abs(_ratio(correlation_value)) if correlation_value is not None else None,
        "self_correlation": abs(_ratio(self_correlation_value)) if self_correlation_value is not None else None,
        "self_correlation_status": self_correlation_status or None,
        "weight_concentration": _ratio(_first_value(metrics_root, ["weightConcentration", "weight_concentration"], 0.0)),
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


def build_official_url(base: str, path_or_url: str, query: dict | None) -> str:
    if path_or_url.startswith(("http://", "https://")):
        base_parts = urllib.parse.urlparse(base)
        target_parts = urllib.parse.urlparse(path_or_url)
        base_origin = (base_parts.scheme.lower(), base_parts.netloc.lower())
        target_origin = (target_parts.scheme.lower(), target_parts.netloc.lower())
        if target_origin != base_origin:
            raise BrainAPIError("refusing cross-origin official API URL")
        url = path_or_url
    else:
        url = base.rstrip("/") + "/" + path_or_url.lstrip("/")
    if query:
        clean = {k: v for k, v in query.items() if v not in ("", None)}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url


def retry_after(headers) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return int(status_code) in {408, 429, 500, 502, 503, 504}


def retry_delay(headers, attempt: int, base_seconds: float) -> float:
    retry_after_value = retry_after(headers)
    if retry_after_value is not None:
        return retry_after_value
    return max(0.0, float(base_seconds)) * (attempt + 1)


def parse_response(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def looks_non_production_alpha_id(value: str) -> bool:
    text = str(value or "").strip().lower()
    prefixes = (
        "mock_",
        "mock-",
        "demo_",
        "demo-",
        "dry_run_",
        "dry-run-",
        "dryrun_",
        "test_",
        "test-",
        "fake_",
        "fake-",
        "sample_",
        "sample-",
    )
    return bool(text and (text in {"mock", "demo", "dry-run", "dry_run", "dryrun", "test", "testing", "fake", "sample"} or text.startswith(prefixes)))


def items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "items", "fields", "datasets", "dataSets", "data_sets", "operators", "checks"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def total_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    for key in ("count", "total", "totalCount", "total_count", "recordsTotal", "records_total"):
        value = data.get(key)
        if isinstance(value, bool):
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count >= 0:
            return count
    return 0


def page_signature(items: list[dict], *, keys: tuple[str, ...]) -> str:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key, "") for key in keys}
        if not any(str(value or "") for value in row.values()):
            row = item
        rows.append(row)
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
    cat = item.get("category")
    if isinstance(cat, dict):
        cat = cat.get("id", str(cat))
    elif not isinstance(cat, str):
        cat = ""
    return {
        "name": str(_first_value(item, ["name", "id", "field", "fieldId"], "")),
        "category": cat,
        "delay": _first_value(item, ["delay"], None),
        "coverage": _num(_first_value(item, ["coverage"], 0.0)),
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


def is_user_alpha_offset_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return getattr(exc, "status_code", None) == 400 and "invalid offset" in text and "filter" in text


def oldest_alpha_created_at(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        created = str(row.get("created_at") or "").strip()
        if created:
            return created
    return ""


def dedupe_alpha_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        alpha_id = str(row.get("id") or "").strip()
        if alpha_id:
            if alpha_id in seen:
                continue
            seen.add(alpha_id)
        deduped.append(row)
    return deduped


def user_alpha_offset_recovery(
    exc: Exception,
    rows: list[dict[str, Any]],
    page_params: dict[str, Any],
    *,
    sync_range: str,
    total: int,
) -> dict[str, Any] | None:
    if not is_user_alpha_offset_limit(exc):
        return None
    cursor = oldest_alpha_created_at(rows)
    if not cursor or page_params.get("dateCreated<") == cursor:
        return None
    next_params = dict(page_params)
    next_params["dateCreated<"] = cursor
    next_params["offset"] = 0
    return {
        "page_params": next_params,
        "progress": user_alpha_progress(
            sync_range,
            rows,
            max(total, len(rows)),
            page_size=0,
            offset=0,
            cursor_before=cursor,
            warning="offset_limit_narrowed_by_date",
        ),
    }


def user_alpha_progress(sync_range: str, rows: list, total: int, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"range": sync_range, "scanned": len(rows), "total": total}
    payload.update(extra)
    return payload


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _num_or_none(value: Any):
    if value in (None, ""):
        return None
    return _num(value)


def _ratio(value: Any) -> float:
    """Convert a metric value to a decimal ratio.

    BRAIN API can return metrics as either percentages (e.g. 75.0 → 0.75) or
    decimals (e.g. 0.75).  The old heuristic of dividing everything > 1.0 by
    100 produced incorrect results for metrics like turnover whose raw value
    naturally exceeds 1.0 (e.g. 2.5 → 0.025 instead of 2.5).

    We now only divide by 100 when the value is unambiguously in percentage
    range (>= 2.0), which catches real percentage values like 75% without
    harming ratios that naturally live between 0 and 2.  Metrics that *do*
    naturally exceed 2.0 (e.g. turnover, correlation) pass through unchanged.
    """
    numeric = _num(value)
    # Only treat values >= 2.0 as percentage-scale; values in [0, 2) are
    # kept as-is to avoid mutilating turnover / correlation ratios.
    if numeric >= 2.0:
        return numeric / 100.0
    return numeric


def merge_payloads(left: Any, right: Any) -> dict:
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        merged.update(right)
        return merged
    return {"simulation": left, "alpha": right}


def scrub(data: Any) -> Any:
    return redact_data(data)
