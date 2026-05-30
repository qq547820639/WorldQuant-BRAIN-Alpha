from __future__ import annotations

import pytest

from brain_alpha_ops.web_payload_validation import (
    MAX_ALPHA_ID_LENGTH,
    MAX_ASSISTANT_TEXT_LENGTH,
    MAX_BATCH_ALPHA_IDS,
    MAX_GENERATE_CANDIDATES,
    validate_alpha_action_payload,
    validate_alpha_id_value,
    validate_assistant_cross_review_payload,
    validate_assistant_guidance_save_payload,
    validate_assistant_text_payload,
    validate_check_batch_payload,
    validate_generate_candidates_payload,
    validate_json_object_payload,
    validate_job_cancel_payload,
    validate_submit_batch_payload,
    validate_sync_alphas_payload,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, "request body must be a JSON object"),
        ({"count": "abc"}, f"count must be an integer between 1 and {MAX_GENERATE_CANDIDATES}"),
        ({"candidates": 0}, f"candidates must be between 1 and {MAX_GENERATE_CANDIDATES}"),
        ({"count": MAX_GENERATE_CANDIDATES + 1}, f"count must be between 1 and {MAX_GENERATE_CANDIDATES}"),
        ({"count": 1, "candidates": ""}, ""),
    ],
)
def test_validate_generate_candidates_payload_boundaries(payload, expected):
    assert validate_generate_candidates_payload(payload) == expected


def test_validate_submit_batch_payload_rejects_bad_shapes_and_accepts_optional_candidates():
    assert validate_submit_batch_payload(None) == "request body must be a JSON object"
    assert validate_submit_batch_payload({"alpha_ids": []}) == "alpha_ids must be a non-empty list of Alpha IDs"
    assert validate_submit_batch_payload({"alpha_ids": ["a"] * (MAX_BATCH_ALPHA_IDS + 1)}).startswith(
        "alpha_ids must contain at most"
    )
    assert validate_submit_batch_payload({"alpha_ids": ["a"], "submit_candidates": {}}) == (
        "submit_candidates must be a list when provided"
    )
    assert validate_submit_batch_payload({"alpha_ids": ["a.1:ok"], "submit_candidates": []}) == ""


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, ""),
        ([], "request body must be a JSON object"),
        ({"candidate_ids": "a"}, "candidate_ids must be a list of Alpha IDs"),
        ({"candidate_ids": ["bad id"]}, "candidate_ids[] may only contain letters"),
        ({"check_candidates": {}}, "check_candidates must be a list when provided"),
        ({"check_candidates": ["a"]}, "check_candidates[] must be an object"),
        ({"check_candidates": [{"alpha_id": "bad id"}]}, "check_candidates[].alpha_id may only"),
        ({"candidates": [{}] * (MAX_BATCH_ALPHA_IDS + 1)}, "candidates must contain at most"),
        ({"mode": "deep"}, "mode must be quick or all"),
        ({"candidate_ids": ["a"], "mode": "quick", "check_candidates": [{"alpha_id": "a"}]}, ""),
    ],
)
def test_validate_check_batch_payload(payload, expected):
    error = validate_check_batch_payload(payload)
    assert error.startswith(expected) if expected else error == ""


def test_validate_job_cancel_payload_checks_custom_field():
    assert validate_job_cancel_payload([], field="task_id") == "request body must be a JSON object"
    assert validate_job_cancel_payload({"task_id": " "}, field="task_id") == "task_id must be a non-empty string"
    assert validate_job_cancel_payload({"task_id": "a" * (MAX_ALPHA_ID_LENGTH + 1)}, field="task_id").startswith(
        "task_id must be"
    )
    assert validate_job_cancel_payload({"task_id": "bad id"}, field="task_id").startswith("task_id may only")
    assert validate_job_cancel_payload({"task_id": "job_1:ok"}, field="task_id") == ""


def test_validate_json_object_and_sync_alphas_payloads():
    assert validate_json_object_payload([]) == "request body must be a JSON object"
    assert validate_json_object_payload({}) == ""
    assert validate_sync_alphas_payload([]) == "request body must be a JSON object"
    assert validate_sync_alphas_payload({}) == ""
    assert validate_sync_alphas_payload({"syncRange": "3d"}) == ""
    assert validate_sync_alphas_payload({"range": "all"}) == ""
    assert validate_sync_alphas_payload({"syncRange": "30d"}) == "syncRange must be one of 3d, 7d, all"


def test_validate_assistant_payloads_cover_size_aliases_and_cross_review():
    assert validate_assistant_text_payload(None) == "request body must be a JSON object"
    assert validate_assistant_text_payload({"text": " "}) == "raw_output or text must be a non-empty string"
    assert validate_assistant_text_payload({"raw_output": "x" * (MAX_ASSISTANT_TEXT_LENGTH + 1)}).startswith(
        "raw_output or text must be"
    )
    assert validate_assistant_text_payload({"text": "usable"}) == ""

    assert validate_assistant_cross_review_payload(None) == "request body must be a JSON object"
    assert validate_assistant_cross_review_payload({"request_pack": []}) == "request_pack must be an object"
    assert validate_assistant_cross_review_payload({"request": {}}) == "primary_response is required"
    assert validate_assistant_cross_review_payload({"request": {}, "primary": "ok"}) == ""


def test_validate_assistant_guidance_save_payload_accepts_raw_or_structured_guidance():
    assert validate_assistant_guidance_save_payload(None) == "request body must be a JSON object"
    assert validate_assistant_guidance_save_payload({}) == (
        "assistant_response, raw_output, text, or assistant_guidance is required"
    )
    assert validate_assistant_guidance_save_payload({"assistant_response": " "}) == (
        "assistant_response, raw_output, text, or assistant_guidance is required"
    )
    assert validate_assistant_guidance_save_payload({"assistant_guidance": []}) == "assistant_guidance must be an object"
    assert validate_assistant_guidance_save_payload({"assistant_guidance": {}}) == "assistant_guidance must not be empty"
    assert validate_assistant_guidance_save_payload({"raw_output": "x" * (MAX_ASSISTANT_TEXT_LENGTH + 1)}).startswith(
        "assistant_response, raw_output, or text must be"
    )
    assert validate_assistant_guidance_save_payload({"text": "usable"}) == ""
    assert validate_assistant_guidance_save_payload({"assistant_guidance": {"top_fields": ["close"]}}) == ""


def test_validate_alpha_action_payload_and_alpha_id_value():
    assert validate_alpha_action_payload(None) == "request body must be a JSON object"
    assert validate_alpha_action_payload({"candidate": []}) == "candidate must be an object when provided"
    assert validate_alpha_action_payload({}) == "candidate or alpha_id is required"
    assert validate_alpha_action_payload({"alpha_id": "bad id"}).startswith("alpha_id may only")
    assert validate_alpha_action_payload({"candidate": {"official_alpha_id": 7}}) == (
        "candidate.official_alpha_id must be a string Alpha ID"
    )
    assert validate_alpha_action_payload({"candidate": {"simulation_id": "sim-1"}}) == ""
    assert validate_alpha_action_payload({"official_alpha_id": "off:1"}) == ""

    assert validate_alpha_id_value(123, "alpha_id") == "alpha_id must be a string Alpha ID"
    assert validate_alpha_id_value(" ", "alpha_id") == "alpha_id must be a non-empty Alpha ID"
    assert validate_alpha_id_value("a" * (MAX_ALPHA_ID_LENGTH + 1), "alpha_id").startswith("alpha_id must be")
    assert validate_alpha_id_value("ok_1.2:3", "alpha_id") == ""
