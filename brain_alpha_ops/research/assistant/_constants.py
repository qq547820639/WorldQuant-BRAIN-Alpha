"""Schema versions and constants for the assistant sub-package."""

from __future__ import annotations

import logging
from typing import Any

ASSISTANT_REQUEST_SCHEMA_VERSION = "assistant_request_pack.v1"
ASSISTANT_RESPONSE_SCHEMA_VERSION = "assistant_response.v1"
ASSISTANT_GUIDANCE_SCHEMA_VERSION = "assistant_generation_guidance.v1"
DEFAULT_MAX_PROMPT_TOKENS = 6000
INTERNAL_CONTEXT_METADATA_KEYS = {"sensitive_fields_redacted"}
logger = logging.getLogger(__name__)

ASSISTANT_RESPONSE_SCHEMA: dict[str, Any] = {
    "schema_version": ASSISTANT_RESPONSE_SCHEMA_VERSION,
    "type": "object",
    "required": [
        "summary",
        "recommended_next_actions",
        "risk_flags",
        "candidate_adjustments",
        "follow_up_questions",
        "confidence",
    ],
    "properties": {
        "summary": {"type": "string"},
        "recommended_next_actions": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "candidate_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["target", "value", "rationale"],
                "properties": {
                    "target": {"type": "string"},
                    "value": {"type": ["string", "number", "array", "object", "boolean", "null"]},
                    "rationale": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "object"},
    },
    "additionalProperties": True,
}
