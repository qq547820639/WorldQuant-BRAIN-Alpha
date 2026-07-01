"""Constants and path helpers for E2E report."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain_alpha_ops.e2e_report")

SCHEMA_VERSION = "e2e_artifact_summary.v1"
DEFAULT_EVIDENCE_DIR = Path("data/e2e_screenshots")
DEFAULT_JOB_LEDGER_PATHS = (
    Path("data/jobs_sync.json"),
    Path("data/jobs_production.json"),
    Path("data/jobs_check.json"),
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_PREVIEW_BYTES = 2_000_000
CONSOLE_PREVIEW_LINES = 40
JOB_PREVIEW_LIMIT = 5
LIST_PREVIEW_LIMIT = 8
SKIPPED_RESULT_KEYS = {
    "alphas",
    "alphas_preview",
    "archive",
    "backtests",
    "candidates",
    "candidate_preview",
    "cloud_alphas",
    "lifecycle_records",
    "raw",
    "ready_results",
}
RESULT_SUMMARY_KEYWORDS = (
    "attempted",
    "available",
    "best_score",
    "blocked",
    "cache",
    "cancel",
    "count",
    "deferred",
    "failed",
    "halt",
    "limit",
    "mode",
    "ok",
    "operators",
    "passed",
    "pending",
    "produced",
    "range",
    "ready",
    "rejected",
    "scanned",
    "simulated",
    "skipped",
    "status",
    "submitted",
    "sync",
    "total",
    "updated",
)


def _read_text(path: Path, *, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max(1, max_bytes)]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _resolve_under_root(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _numeric(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:240]
