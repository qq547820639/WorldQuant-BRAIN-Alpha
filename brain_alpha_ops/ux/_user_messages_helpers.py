"""Helper definitions split out from ``user_messages.py``.

This internal helper module exists to keep ``user_messages.py`` within the
project's 350-line hard limit. It holds the ``UserMessage`` data model, which
is a leaf definition with no dependencies on the rest of the parent module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserMessage:
    """Structured user-facing message with actionable guidance."""
    title: str           # Chinese human-readable title
    detail: str          # English technical detail
    suggestion: str      # Actionable next step
    severity: str        # "error" | "warning" | "info"
    error_code: str = ""
