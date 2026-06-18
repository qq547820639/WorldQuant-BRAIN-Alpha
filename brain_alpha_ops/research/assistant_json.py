"""JSON extraction helpers for assistant responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger("brain_alpha_ops.research.assistant")


class AssistantResponseParseError(ValueError):
    """Raised when an assistant response cannot be parsed as useful JSON."""


def extract_json_payload(raw_output: str) -> Any:
    raw = str(raw_output or "").strip()
    if not raw:
        raise AssistantResponseParseError("assistant response is empty")
    last_json_error: json.JSONDecodeError | None = None
    if raw.startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            last_json_error = exc
            logger.warning("invalid assistant response JSON prefix skipped: %s", redact_error_message(exc))

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError as exc:
            last_json_error = exc
            logger.warning("invalid fenced assistant response JSON skipped: %s", redact_error_message(exc))

    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                last_json_error = exc
                logger.warning("invalid assistant response JSON candidate skipped: %s", redact_error_message(exc))
                continue
    detail = f"; last JSON error: {last_json_error}" if last_json_error else ""
    raise AssistantResponseParseError(f"cannot extract valid JSON from assistant response: {raw[:200]}{detail}")
