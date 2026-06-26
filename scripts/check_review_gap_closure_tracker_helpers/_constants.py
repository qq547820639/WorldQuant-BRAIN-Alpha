"""Constants for the review gap closure tracker helpers subpackage."""

from __future__ import annotations


OFFICIAL_CONTEXT_QUEUE_ITEM = "Official context refresh"


ADDITIONAL_TRIAGE_SNIPPETS = (
    "Review 2026-06-01 P0 baseUrl SSRF risk",
    "Review 2026-06-01 P0 request body size limit",
    "Review 2026-06-01 P1 traceback leakage",
    "Review 2026-06-01 P1 production budget numeric limits",
    "Review 2026-06-01 P1 silent exception swallowing",
)

ADDITIONAL_TRIAGE_ITEMS = (
    ("Review 2026-06-01 P0 baseUrl SSRF risk", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P0 request body size limit", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 traceback leakage", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 production budget numeric limits", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 silent exception swallowing", "CLOSED_CURRENT"),
)
