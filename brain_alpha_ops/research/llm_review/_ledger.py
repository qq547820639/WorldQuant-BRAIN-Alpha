"""Append-only prompt run ledger for the ``llm_review`` subpackage.

Never stores provider secrets; records digests of prompts, context, and
responses alongside model metadata for auditability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.llm_review._utils import (
    _digest_json,
    _digest_text,
)

PROMPT_RUN_LEDGER_SCHEMA_VERSION = "prompt_run_ledger.v1"


class PromptRunLedger:
    """Append-only prompt run ledger that never stores provider secrets."""

    def __init__(self, storage_dir: str | Path):
        self.path = Path(storage_dir) / "prompt_runs.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        request_pack: dict[str, Any],
        model: str = "",
        temperature: float | None = None,
        response_text: str = "",
        parse_status: str = "",
    ) -> dict[str, Any]:
        row = redact_data(
            {
                "schema_version": PROMPT_RUN_LEDGER_SCHEMA_VERSION,
                "timestamp": utc_now(),
                "prompt_digest": request_pack.get("prompt_digest") or _digest_text(str(request_pack.get("prompt") or "")),
                "context_digest": request_pack.get("context_digest") or _digest_json(request_pack.get("context_pack") or {}),
                "model": model,
                "temperature": temperature,
                "response_digest": _digest_text(response_text),
                "parse_status": parse_status or "unknown",
            }
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return row
