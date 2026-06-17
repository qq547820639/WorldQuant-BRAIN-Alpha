"""State helpers for Web candidate official simulation jobs."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.field_quality import is_generation_eligible_field
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidate_audit import scientific_audit_policy_reasons

DEFERRED_SIMULATION_STATUSES = frozenset({
    "simulation_deferred_concurrency_limit",
    "simulation_deferred_rate_limit",
})
SIMULATION_COOLDOWN_FILENAME = "simulation_cooldown.json"
SIMULATION_COOLDOWN_SCOPE = "official_simulation"
GROUP_KEY_FIELDS = frozenset({"market", "sector", "industry", "subindustry"})
COOLDOWN_UPDATE_FIELDS = [
    "lifecycle_status",
    "simulation_deferred_at",
    "simulation_deferred_until",
    "simulation_retry_after_seconds",
    "simulation_deferred_reason",
    "simulation_cooldown_active",
]

_CANDIDATES_FILE_LOCK = threading.Lock()
_SIMULATION_COOLDOWN_FILE_LOCK = threading.Lock()


def defer_candidate(
    candidate: dict[str, Any],
    *,
    lifecycle_status: str,
    error_text: str,
    retry_seconds: float,
    now: float | None = None,
) -> None:
    now_value = time.time() if now is None else float(now)
    retry_value = max(0.0, float(retry_seconds or 0.0))
    candidate["lifecycle_status"] = lifecycle_status
    candidate["simulation_deferred_at"] = now_value
    candidate["simulation_deferred_until"] = now_value + retry_value
    candidate["simulation_retry_after_seconds"] = retry_value
    candidate["simulation_deferred_reason"] = error_text
    candidate["simulation_cooldown_active"] = True


def clear_candidate_simulation_cooldown(candidate: dict[str, Any]) -> None:
    candidate["simulation_deferred_at"] = None
    candidate["simulation_deferred_until"] = None
    candidate["simulation_retry_after_seconds"] = None
    candidate["simulation_deferred_reason"] = None
    candidate["simulation_cooldown_active"] = False


def _safe_storage_file(storage_dir: str, filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).is_absolute():
        raise ValueError(f"unsafe storage file: {filename}")
    root = Path(storage_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / filename).resolve()
    if path.parent != root:
        raise ValueError(f"storage file escapes storage_dir: {filename}")
    return path


def _read_simulation_cooldowns_unlocked(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_simulation_cooldowns_unlocked(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def record_account_simulation_cooldown(
    storage_dir: str,
    *,
    lifecycle_status: str,
    error_text: str,
    retry_seconds: float,
    now: float | None = None,
) -> dict[str, Any]:
    now_value = time.time() if now is None else float(now)
    retry_value = max(0.0, float(retry_seconds or 0.0))
    record = {
        "scope": "account",
        "endpoint": SIMULATION_COOLDOWN_SCOPE,
        "active": True,
        "lifecycle_status": lifecycle_status,
        "reason": error_text,
        "recorded_at": now_value,
        "deferred_until": now_value + retry_value,
        "retry_after_seconds": retry_value,
    }
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        payload[SIMULATION_COOLDOWN_SCOPE] = record
        _write_simulation_cooldowns_unlocked(path, payload)
    return record


def clear_account_simulation_cooldown(storage_dir: str, *, now: float | None = None) -> None:
    current = time.time() if now is None else float(now)
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        record = payload.get(SIMULATION_COOLDOWN_SCOPE)
        if not isinstance(record, dict):
            return
        payload[SIMULATION_COOLDOWN_SCOPE] = {
            **record,
            "active": False,
            "cleared_at": current,
            "remaining_seconds": 0.0,
        }
        _write_simulation_cooldowns_unlocked(path, payload)


def active_account_simulation_cooldown(storage_dir: str, *, now: float | None = None) -> dict[str, Any] | None:
    current = time.time() if now is None else float(now)
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        record = payload.get(SIMULATION_COOLDOWN_SCOPE)
        if not isinstance(record, dict) or not record.get("active"):
            return None
        try:
            deferred_until = float(record.get("deferred_until"))
        except (TypeError, ValueError):
            deferred_until = current
        if current < deferred_until:
            remaining = max(0.0, deferred_until - current)
            return {**record, "deferred_until": deferred_until, "remaining_seconds": remaining}
        payload[SIMULATION_COOLDOWN_SCOPE] = {
            **record,
            "active": False,
            "cleared_at": current,
            "remaining_seconds": 0.0,
        }
        _write_simulation_cooldowns_unlocked(path, payload)
    return None


def _simulation_deferred_until(candidate: dict[str, Any]) -> float | None:
    value = candidate.get("simulation_deferred_until")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_simulation_cooling_down(candidate: dict[str, Any], *, now: float | None = None) -> bool:
    lifecycle = str(candidate.get("lifecycle_status", "")).lower()
    if lifecycle not in DEFERRED_SIMULATION_STATUSES:
        return False
    until = _simulation_deferred_until(candidate)
    if until is None:
        return True
    current = time.time() if now is None else float(now)
    if current < until:
        return True
    candidate["simulation_cooldown_active"] = False
    return False


def load_candidates(storage_dir: str) -> list[dict[str, Any]]:
    if not Path(storage_dir).is_dir():
        return []
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("candidates.jsonl")
    with _CANDIDATES_FILE_LOCK:
        with repo._file_lock("candidates.jsonl"):
            return _read_candidates_unlocked(path)


def _read_candidates_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def save_candidates(storage_dir: str, candidates: list[dict[str, Any]]) -> None:
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("candidates.jsonl")
    with _CANDIDATES_FILE_LOCK:
        with repo._file_lock("candidates.jsonl"):
            current = _read_candidates_unlocked(path)
            merged = _merge_candidate_rows(current, candidates)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                for row in merged:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            tmp.replace(path)


def candidate_update_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    update: dict[str, Any] = {}
    alpha_id = candidate.get("alpha_id")
    official_alpha_id = candidate.get("official_alpha_id")
    expression = candidate.get("expression")
    if alpha_id not in (None, ""):
        update["alpha_id"] = alpha_id
    elif official_alpha_id not in (None, ""):
        update["official_alpha_id"] = official_alpha_id
    elif expression not in (None, ""):
        update["expression"] = expression
        dataset = candidate.get("dataset_id")
        if dataset not in (None, ""):
            update["dataset_id"] = dataset
    for key in fields:
        if key in candidate:
            update[key] = candidate[key]
    return update


def save_candidate_update(storage_dir: str, candidate: dict[str, Any], fields: list[str]) -> None:
    update = candidate_update_row(candidate, fields)
    if update:
        save_candidates(storage_dir, [update])


def _merge_candidate_rows(current: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for row in current:
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        key = _candidate_merge_key(clean)
        if key and key not in positions:
            positions[key] = len(merged)
        merged.append(clean)
    for row in updates:
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        key = _candidate_merge_key(clean)
        if key and key in positions:
            merged[positions[key]] = {**merged[positions[key]], **clean}
            continue
        if key:
            positions[key] = len(merged)
        merged.append(clean)
    return merged


def _candidate_merge_key(candidate: dict[str, Any]) -> str:
    for field in ("alpha_id", "official_alpha_id", "expression"):
        value = str(candidate.get(field) or "").strip()
        if value:
            if field == "expression":
                dataset = str(candidate.get("dataset_id") or "").strip()
                return f"{field}:{value}:dataset:{dataset}"
            return f"{field}:{value}"
    return ""


def append_backtest_record(storage_dir: str, record: dict[str, Any]) -> None:
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("backtests.jsonl")
    with repo._file_lock("backtests.jsonl"):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def score_simulated_candidate(candidate: dict[str, Any], config: RunConfig) -> dict[str, Any]:
    data = dict(candidate)
    data.setdefault("alpha_id", "")
    data.setdefault("expression", "")
    data.setdefault("family", "")
    data.setdefault("hypothesis", "")
    model = Candidate.from_dict(data)
    model.scorecard = build_scorecard(model, config.ops.thresholds, config.ops.scoring)
    gate = _official_simulation_gate(model, config)
    rescored = model.to_dict()
    merged = dict(candidate)
    for key, value in rescored.items():
        if key != "extra_fields":
            merged[key] = value
    merged["gate"] = gate
    extra_fields = dict(candidate.get("extra_fields") or {})
    for key, value in dict(rescored.get("extra_fields") or {}).items():
        if key not in merged:
            extra_fields[key] = value
    if extra_fields:
        merged["extra_fields"] = extra_fields
    return merged


def _official_simulation_gate(candidate: Candidate, config: RunConfig) -> dict[str, Any]:
    metrics = candidate.official_metrics or {}
    missing_fields = missing_official_metric_fields(metrics) if metrics else []
    pass_fail = str(metrics.get("pass_fail") or "").strip().upper()
    release_gate = (
        evaluate_release_score(
            metrics,
            config.ops.thresholds,
            settings=_candidate_settings(candidate),
        ).to_dict()
        if metrics
        else {}
    )
    if metrics and not missing_fields and pass_fail in {"PASS", "FAIL"} and release_gate.get("status") == "PASS":
        gate = evaluate_quality_gate(
            candidate,
            config.ops.thresholds,
            settings=_candidate_settings(candidate),
        )
        gate["official_release_gate"] = release_gate
        return gate

    failed_reasons: list[str] = []
    if not metrics:
        failed_reasons.append("official_metrics_present: missing official simulation result")
    if missing_fields:
        failed_reasons.append("official_metric_fields_complete: missing " + ", ".join(missing_fields))
    if pass_fail not in {"PASS", "FAIL"}:
        failed_reasons.append("official_pass_fail: missing official pass/fail")
    if release_gate and release_gate.get("status") != "PASS":
        failed_reasons.append(f"official_release_gate: {release_gate.get('status', 'UNKNOWN')}")
    return {
        "schema_version": "production-gate-v2.2",
        "submission_ready": False,
        "status": "NEEDS_ITERATION",
        "failed_reasons": failed_reasons,
        "warnings": ["official_simulation_gate_fail_closed"],
        "hard_gate_blocked": True,
        "official_release_gate": release_gate,
    }


def _candidate_settings(candidate: Candidate) -> dict[str, Any]:
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    for key in ("settings", "brain_settings"):
        value = submission.get(key)
        if isinstance(value, dict):
            return value
    output_config = candidate.alpha_output_config if isinstance(candidate.alpha_output_config, dict) else {}
    settings = output_config.get("settings")
    return dict(settings) if isinstance(settings, dict) else {}


def candidate_score(candidate: dict[str, Any]) -> float:
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    value = scorecard.get("total_score", candidate.get("score"))
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score else 0.0


def default_simulation_dataset(config: RunConfig) -> str:
    try:
        settings = config.ops.settings.to_platform_dict()["settings"]
    except Exception:
        return ""
    return str(settings.get("dataset") or "")


def _candidate_dataset_key(candidate: dict[str, Any], default_dataset: str = "") -> str:
    settings = candidate.get("settings") if isinstance(candidate.get("settings"), dict) else {}
    return str(
        candidate.get("dataset_id")
        or candidate.get("dataset")
        or settings.get("dataset")
        or default_dataset
        or ""
    ).strip().lower()


def simulation_target_key(candidate: dict[str, Any], *, default_dataset: str = "") -> str:
    expression = "".join(str(candidate.get("expression") or "").split()).lower()
    if expression:
        dataset = _candidate_dataset_key(candidate, default_dataset)
        return f"expression:{expression}:dataset:{dataset}"
    alpha_id = str(candidate.get("alpha_id") or "").strip()
    return f"alpha_id:{alpha_id}" if alpha_id else ""


def dedupe_simulation_targets(candidates: list[dict[str, Any]], *, default_dataset: str = "") -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = simulation_target_key(candidate, default_dataset=default_dataset)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        targets.append(candidate)
    return targets


def eligible_for_simulation(candidate: dict[str, Any], min_score: float, *, now: float | None = None) -> bool:
    if is_simulation_cooling_down(candidate, now=now):
        return False
    if _has_complete_official_simulation_result(candidate):
        return False
    if candidate.get("simulation_id"):
        lifecycle = str(candidate.get("lifecycle_status", "")).lower()
        if "simulation_running" in lifecycle or "simulation_submitted" in lifecycle:
            return False
    if candidate_score(candidate) < min_score:
        return False
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return False
    if _has_explicit_unsupported_local_backtest(candidate, local_quality):
        return False
    if _has_non_signal_candidate_fields(candidate):
        return False
    if scientific_audit_policy_reasons(candidate):
        return False
    return True


def _has_non_signal_candidate_fields(candidate: dict[str, Any]) -> bool:
    raw_fields = candidate.get("data_fields")
    fields: set[str] = {
        str(field).strip().lower()
        for field in (raw_fields if isinstance(raw_fields, list) else [])
        if str(field).strip()
    }
    expression = str(candidate.get("expression") or "").strip()
    if expression:
        profile = profile_expression(expression)
        expression_fields = {str(field).strip().lower() for field in profile.fields if str(field).strip()}
        if any(str(operator).lower().startswith("group_") for operator in profile.operators):
            expression_fields -= GROUP_KEY_FIELDS
        fields.update(expression_fields)
    if not fields:
        return False
    return any(field and not is_generation_eligible_field(field) for field in fields)


def _has_explicit_unsupported_local_backtest(
    candidate: dict[str, Any],
    local_quality: dict[str, Any] | None = None,
) -> bool:
    """Block official simulation only when local backtest support is explicitly false."""
    sources: list[dict[str, Any]] = []
    if isinstance(local_quality, dict):
        sources.append(local_quality)
    if isinstance(candidate, dict):
        sources.append(candidate)
    for source in sources:
        support = source.get("local_backtest_support")
        if not isinstance(support, dict):
            continue
        supported = support.get("supported")
        if supported is False:
            return True
        if isinstance(supported, str) and supported.strip().lower() in {"false", "0", "no"}:
            return True
    return False


def _has_complete_official_simulation_result(candidate: dict[str, Any]) -> bool:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    if not metrics:
        return False
    if missing_official_metric_fields(metrics):
        return False
    return str(metrics.get("pass_fail") or "").strip().upper() in {"PASS", "FAIL"}
