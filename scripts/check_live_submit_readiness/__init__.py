"""Audit whether current local evidence is ready for a live BRAIN submit."""

from __future__ import annotations

from ._constants import (
    DEFAULT_CANDIDATE_LEDGER,
    DEFAULT_CONFIG,
    DEFAULT_JOB_LEDGER_GLOB,
    DEFAULT_JOBS,
    DEFAULT_SIMILARITY_THRESHOLD,
    ROOT,
    SCHEMA_VERSION,
)
from ._runners import check_live_submit_readiness, main

__all__ = [
    "DEFAULT_CANDIDATE_LEDGER",
    "DEFAULT_CONFIG",
    "DEFAULT_JOB_LEDGER_GLOB",
    "DEFAULT_JOBS",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "ROOT",
    "SCHEMA_VERSION",
    "check_live_submit_readiness",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
