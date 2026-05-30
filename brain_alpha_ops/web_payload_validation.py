"""Request payload validation helpers for local web route dispatch."""

from __future__ import annotations

import re
from typing import Any


MAX_GENERATE_CANDIDATES = 100
MAX_ALPHA_ID_LENGTH = 128
MAX_BATCH_ALPHA_IDS = 100
MAX_ASSISTANT_TEXT_LENGTH = 200_000
ALLOWED_SYNC_RANGES = {"3d", "7d", "all"}
ALPHA_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def validate_json_object_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "request body must be a JSON object"
    return ""


def validate_generate_candidates_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    for field in ("count", "candidates"):
        if field not in payload or payload.get(field) in ("", None):
            continue
        try:
            count = int(payload[field])
        except (TypeError, ValueError):
            return f"{field} must be an integer between 1 and {MAX_GENERATE_CANDIDATES}"
        if count < 1 or count > MAX_GENERATE_CANDIDATES:
            return f"{field} must be between 1 and {MAX_GENERATE_CANDIDATES}"
    return ""


def validate_submit_batch_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    alpha_ids = payload.get("alpha_ids")
    if not isinstance(alpha_ids, list) or not alpha_ids:
        return "alpha_ids must be a non-empty list of Alpha IDs"
    if len(alpha_ids) > MAX_BATCH_ALPHA_IDS:
        return f"alpha_ids must contain at most {MAX_BATCH_ALPHA_IDS} items"
    for item in alpha_ids:
        error = validate_alpha_id_value(item, "alpha_ids[]")
        if error:
            return error
    raw_candidates = payload.get("submit_candidates")
    if raw_candidates is not None and not isinstance(raw_candidates, list):
        return "submit_candidates must be a list when provided"
    error = validate_candidate_rows(raw_candidates, "submit_candidates")
    if error:
        return error
    return ""


def validate_check_batch_payload(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    error = validate_json_object_payload(payload)
    if error:
        return error
    candidate_ids = payload.get("candidate_ids")
    if candidate_ids is not None:
        if not isinstance(candidate_ids, list):
            return "candidate_ids must be a list of Alpha IDs"
        for item in candidate_ids:
            error = validate_alpha_id_value(item, "candidate_ids[]")
            if error:
                return error
    mode = payload.get("mode")
    if mode is not None and str(mode) not in {"quick", "all"}:
        return "mode must be quick or all"
    for field in ("check_candidates", "candidates"):
        error = validate_candidate_rows(payload.get(field), field)
        if error:
            return error
    return ""


def validate_candidate_rows(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, list):
        return f"{field} must be a list when provided"
    if len(value) > MAX_BATCH_ALPHA_IDS:
        return f"{field} must contain at most {MAX_BATCH_ALPHA_IDS} items"
    for row in value:
        if not isinstance(row, dict):
            return f"{field}[] must be an object"
        for key in ("alpha_id", "official_alpha_id", "simulation_id"):
            if key not in row or row.get(key) in ("", None):
                continue
            error = validate_alpha_id_value(row.get(key), f"{field}[].{key}")
            if error:
                return error
    return ""


def validate_job_cancel_payload(payload: dict[str, Any] | None, *, field: str = "job_id") -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    job_id = payload.get(field)
    if not isinstance(job_id, str) or not job_id.strip():
        return f"{field} must be a non-empty string"
    if len(job_id.strip()) > MAX_ALPHA_ID_LENGTH:
        return f"{field} must be {MAX_ALPHA_ID_LENGTH} characters or fewer"
    if not ALPHA_ID_PATTERN.fullmatch(job_id.strip()):
        return f"{field} may only contain letters, numbers, underscore, dash, dot, or colon"
    return ""


def validate_assistant_text_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    raw_output = payload.get("raw_output") if payload.get("raw_output") is not None else payload.get("text")
    if not isinstance(raw_output, str) or not raw_output.strip():
        return "raw_output or text must be a non-empty string"
    if len(raw_output) > MAX_ASSISTANT_TEXT_LENGTH:
        return f"raw_output or text must be {MAX_ASSISTANT_TEXT_LENGTH} characters or fewer"
    return ""


def validate_assistant_guidance_save_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    supplied_guidance = payload.get("assistant_guidance")
    if supplied_guidance is not None:
        if not isinstance(supplied_guidance, dict):
            return "assistant_guidance must be an object"
        if not supplied_guidance:
            return "assistant_guidance must not be empty"
        return ""
    raw_output = (
        payload.get("assistant_response")
        if payload.get("assistant_response") is not None
        else payload.get("raw_output")
        if payload.get("raw_output") is not None
        else payload.get("text")
    )
    if not isinstance(raw_output, str) or not raw_output.strip():
        return "assistant_response, raw_output, text, or assistant_guidance is required"
    if len(raw_output) > MAX_ASSISTANT_TEXT_LENGTH:
        return f"assistant_response, raw_output, or text must be {MAX_ASSISTANT_TEXT_LENGTH} characters or fewer"
    return ""


def validate_assistant_cross_review_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    request_pack = payload.get("request_pack") if payload.get("request_pack") is not None else payload.get("request")
    if not isinstance(request_pack, dict):
        return "request_pack must be an object"
    if payload.get("primary_response") is None and payload.get("primary") is None:
        return "primary_response is required"
    return ""


def validate_alpha_action_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    candidate = payload.get("candidate")
    if candidate is not None and not isinstance(candidate, dict):
        return "candidate must be an object when provided"
    for field in ("alpha_id", "official_alpha_id", "simulation_id"):
        if field in payload and payload.get(field) not in ("", None):
            error = validate_alpha_id_value(payload.get(field), field)
            if error:
                return error
    if isinstance(candidate, dict):
        for field in ("alpha_id", "official_alpha_id", "simulation_id"):
            if field in candidate and candidate.get(field) not in ("", None):
                error = validate_alpha_id_value(candidate.get(field), f"candidate.{field}")
                if error:
                    return error
    has_top_level_id = any(str(payload.get(field) or "").strip() for field in ("alpha_id", "official_alpha_id", "simulation_id"))
    has_candidate = isinstance(candidate, dict) and bool(candidate)
    if not has_top_level_id and not has_candidate:
        return "candidate or alpha_id is required"
    return ""


def validate_sync_alphas_payload(payload: dict[str, Any] | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    sync_range = payload.get("syncRange") if payload.get("syncRange") not in ("", None) else payload.get("range")
    if sync_range not in ("", None) and str(sync_range) not in ALLOWED_SYNC_RANGES:
        return "syncRange must be one of 3d, 7d, all"
    return ""


def validate_alpha_id_value(value: Any, field: str) -> str:
    if not isinstance(value, str):
        return f"{field} must be a string Alpha ID"
    text = value.strip()
    if not text:
        return f"{field} must be a non-empty Alpha ID"
    if len(text) > MAX_ALPHA_ID_LENGTH:
        return f"{field} must be {MAX_ALPHA_ID_LENGTH} characters or fewer"
    if not ALPHA_ID_PATTERN.fullmatch(text):
        return f"{field} may only contain letters, numbers, underscore, dash, dot, or colon"
    return ""
