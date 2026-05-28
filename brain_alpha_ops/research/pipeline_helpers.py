"""Small pure helpers for the alpha research pipeline coordinator."""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.models import Candidate

from .expression_ast import expression_key
from .guidance import assistant_guidance_candidate_metadata, ensure_assistant_guidance_digest


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (
            bool(c.gate.get("submission_ready")),
            bool(c.official_metrics),
            ranking_score(c),
            c.scorecard.get("local_rank_score", 0.0),
            c.local_quality.get("score", 0.0),
        ),
        reverse=True,
    )


def ranking_score(candidate: Candidate) -> float:
    return float(candidate.scorecard.get("total_score", 0.0) or 0.0)


def assistant_guidance_for_generator(guidance: dict) -> dict:
    if not guidance or guidance.get("ok") is False:
        return {}
    if not truthy(guidance.get("usable", True)):
        return {}
    top_operators = unique_strings(guidance.get("top_operators"))
    preferred_windows = unique_numbers(guidance.get("preferred_windows"))
    field_combinations = normalize_field_combinations(guidance.get("field_combinations"))
    top_fields = unique_strings(guidance.get("top_fields"))
    if top_fields:
        field_combinations = unique_field_combinations(
            field_combinations + [{"fields": top_fields, "rationale": "assistant top fields"}]
        )
    if not top_operators and not preferred_windows and not field_combinations:
        return {}
    return {
        "sample_size": max(3, safe_int(guidance.get("sample_size"), 0)),
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "field_combinations": field_combinations,
    }


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def string_items(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def unique_strings(value: Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in string_items(value):
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def number_items(value: Any) -> list[int | float]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    rows: list[int | float] = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number != number or number in (float("inf"), float("-inf")):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def unique_numbers(value: Any) -> list[int | float]:
    seen: set[float] = set()
    unique: list[int | float] = []
    for item in number_items(value):
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def normalize_field_combinations(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            fields = unique_strings(item.get("fields") or item.get("field") or item.get("value"))
            rationale = str(item.get("rationale") or "")
        else:
            fields = unique_strings(item)
            rationale = ""
        if fields:
            rows.append({"fields": fields, "rationale": rationale})
    return rows


def unique_field_combinations(value: Any) -> list[dict]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict] = []
    for combo in normalize_field_combinations(value):
        fields = unique_strings(combo.get("fields"))
        marker = tuple(field.lower() for field in fields)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append({"fields": fields, "rationale": str(combo.get("rationale") or "")})
    return unique


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_hard_backtest_blocked(status: str) -> bool:
    text = str(status or "").lower()
    if "simulation_deferred_concurrency_limit" in text or "simulation_deferred_rate_limit" in text:
        return False
    return any(
        marker in text
        for marker in (
            "official_validation_failed",
            "observability_duplicate_blocked",
            "local_standard_rejected",
            "official_standard_rejected",
            "simulation_request_failed",
            "simulation_poll_failed",
            "simulation_result_failed",
            "simulation_failed",
            "simulation_timeout",
            "rejected",
        )
    )


def merge_context_defaults(items: list[dict], defaults: list[dict]) -> list[dict]:
    merged = list(items)
    seen = {str(item.get("name", "")).lower() for item in merged if item.get("name")}
    for item in defaults:
        name = str(item.get("name", "")).lower()
        if name and name not in seen:
            merged.append(dict(item))
            seen.add(name)
    return merged


def expr_key(candidate: Candidate) -> str:
    return expression_key(candidate.expression)


def cloud_row_expression(row: dict) -> str:
    expression = row.get("expression", "")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return str(code)
    regular = row.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return str(regular.get("code"))
    raw = row.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return str(raw_regular.get("code"))
    return str(expression or "")


def blocked_gate(status: str, reasons: list[str]) -> dict:
    return {
        "schema_version": "production-gate-v2.1",
        "submission_ready": False,
        "status": status,
        "failed_reasons": list(reasons),
        "warnings": [],
    }


def attach_assistant_guidance(candidate: Candidate, guidance: dict) -> None:
    guidance = ensure_assistant_guidance_digest(guidance)
    digest = str(guidance.get("guidance_digest") or "")
    candidate.assistant_guidance_digest = digest
    metadata = assistant_guidance_candidate_metadata(guidance)
    candidate.submission.update(metadata)
    candidate.submission.setdefault("assistant_guidance", {}).update(metadata)
    candidate.extra_fields.setdefault("assistant_guidance_digest", digest)
    tags = list(candidate.source_tags or [])
    for tag in ("assistant_guided", f"assistant_guidance_{digest}" if digest else ""):
        if tag and tag not in tags:
            tags.append(tag)
    candidate.source_tags = tags


def slot_progress_percent(status: str) -> int:
    value = str(status or "").upper()
    if value == "EMPTY":
        return 0
    if value == "CAPACITY_WAIT":
        return 5
    if value in {"SUBMITTED", "SIMULATION_SUBMITTED"}:
        return 25
    if value in {"RUNNING", "SIMULATION_RUNNING"}:
        return 65
    if value in {"COMPLETED", "OFFICIAL_SIMULATED", "SUBMISSION_READY"}:
        return 100
    if "DEFERRED" in value:
        return 40
    if "FAILED" in value or "REJECTED" in value:
        return 100
    return 50


def slot_message(status: str) -> str:
    value = str(status or "").upper()
    if value == "CAPACITY_WAIT":
        return "官方并发容量占满，暂缓提交新回测。"
    if value == "EMPTY":
        return "等待排名靠前的候选 Alpha。"
    if value in {"SUBMITTED", "SIMULATION_SUBMITTED"}:
        return "已提交，等待官方开始计算。"
    if value in {"RUNNING", "SIMULATION_RUNNING"}:
        return "官方回测运行中，按 6 秒节奏顺序轮询。"
    if value in {"COMPLETED", "OFFICIAL_SIMULATED", "SUBMISSION_READY"}:
        return "回测完成，结果已进入评价/排序。"
    if "DEFERRED" in value:
        return "官方限流或并发限制，保持本地生产并稍后恢复。"
    if "FAILED" in value:
        return "未达标，已进入生命周期回溯。"
    if "REJECTED" in value:
        return "未通过官方/本地门禁，已记录原因。"
    return "状态更新中。"


def compute_score_distribution(candidates: list) -> dict:
    dist = Counter()
    for candidate in candidates:
        score = candidate.scorecard.get("total_score", 0.0)
        if score >= 85:
            dist["submit (≥85)"] += 1
        elif score >= 70:
            dist["optimize (70-84)"] += 1
        elif score >= 50:
            dist["research (50-69)"] += 1
        else:
            dist["abandon (<50)"] += 1
    return dict(dist)


def compute_gate_summary(candidates: list) -> dict:
    result = {
        "local_prefilter": {"pass": 0, "fail": 0, "block": 0},
        "expression_validate": {"pass": 0, "fail": 0, "block": 0},
        "official_simulation": {"pass": 0, "fail": 0, "block": 0},
        "quality_gate": {"pass": 0, "fail": 0, "block": 0},
    }
    for candidate in candidates:
        if candidate.lifecycle_status == "local_prefilter_rejected":
            result["local_prefilter"]["fail"] += 1
        elif candidate.lifecycle_status in ("validation_rejected", "expression_invalid"):
            result["expression_validate"]["fail"] += 1
        elif candidate.lifecycle_status in ("simulation_failed", "simulation_rejected"):
            result["official_simulation"]["fail"] += 1
        elif candidate.gate.get("submission_ready"):
            result["quality_gate"]["pass"] += 1
        elif candidate.gate.get("hard_gate_blocked"):
            result["quality_gate"]["block"] += 1
        elif candidate.official_metrics:
            result["quality_gate"]["fail"] += 1
    return result
