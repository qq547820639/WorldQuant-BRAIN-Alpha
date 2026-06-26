"""Constants for live submit readiness audits."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
DEFAULT_JOB_LEDGER_GLOB = "jobs_*.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "candidates.jsonl"
SCHEMA_VERSION = "live_submit_readiness.v1"
DEFAULT_SIMILARITY_THRESHOLD = 0.90
