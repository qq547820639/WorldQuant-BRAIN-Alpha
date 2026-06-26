"""Shared digest and string helpers for the ``llm_review`` subpackage.

Split from the former monolithic ``llm_review.py`` to keep provider, review,
and ledger modules free of duplicated low-level utilities.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _digest_json(value: Any) -> str:
    return _digest_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _digest_text(value: str) -> str:
    return sha256(str(value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
