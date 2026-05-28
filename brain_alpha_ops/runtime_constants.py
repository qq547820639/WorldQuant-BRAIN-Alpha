"""Centralized runtime constants for the Brain Alpha Ops project.

All hardcoded numeric values, timeouts, limits, and defaults that were previously
scattered across web.py, web_cloud_snapshot.py, agent_tools.py, and other modules
are consolidated here.  Every constant has a docstring explaining its purpose
and affected component.

Import conventions
------------------
    from brain_alpha_ops.runtime_constants import WebDefaults, CloudDefaults, AgentLimits
"""

from __future__ import annotations

from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
# Web console defaults (web.py)
# ═══════════════════════════════════════════════════════════════════════════

class WebDefaults:
    """Defaults for the local web console HTTP server."""

    HOST: str = "127.0.0.1"
    """Default bind address — local-only by design for security."""

    PORT: int = 8765
    """Default listen port."""

    SERVER_VERSION: str = "BrainAlphaOps/0.3"
    """HTTP Server header value."""

    MAX_BODY_BYTES: int = 2 * 1024 * 1024
    """Maximum incoming request body size (2 MB)."""

    TASK_EXECUTOR_MAX_WORKERS: int = 4
    """Max threads in the background task executor."""

    SSE_PUSH_INTERVAL: float = 1.0
    """Interval in seconds between SSE status push events."""

    MAX_SSE_DURATION: int = 600
    """Hard cap on SSE stream lifetime in seconds (10 minutes)."""

    ARCHIVE_CHECK_INTERVAL: float = 3600.0
    """Seconds between archive staleness checks."""

    MAIN_LOOP_WAIT_SECONDS: float = 3600.0
    """Seconds to block main loop waiting on server stop signal."""

    JOB_ID_WIDTH: int = 4
    """Zero-pad width for legacy job IDs (e.g. job_0001)."""


class SnapshotDefaults:
    """Defaults for web console snapshot / query endpoints."""

    LIFECYCLE_LIMIT: int = 1000
    RESEARCH_MEMORY_LIMIT: int = 5000
    RESEARCH_MEMORY_TOP_N: int = 10
    KNOWLEDGE_LIMIT: int = 100
    KNOWLEDGE_MIN_CONFIDENCE: float = 0.0
    OBSERVABILITY_LIMIT: int = 5000
    OBSERVABILITY_TOP_N: int = 10
    RUN_LEDGER_LIMIT: int = 100
    SQLITE_TOP_N: int = 10
    SQLITE_MIN_SIMILARITY: float = 0.75
    SQLITE_MAX_SCAN_ROWS: int = 2000
    SQLITE_RECORD_LIMIT: int = 50
    ASSISTANT_GUIDANCE_LIMIT: int = 100
    ROLLING_WINDOWS: int = 4
    SUBMISSION_PREFLIGHT_LIMIT: int = 5000
    SUBMISSION_PREFLIGHT_TOP_N: int = 5
    STORAGE_JSONL_LIMIT: int = 500
    TAIL_CHUNK_SIZE: int = 1024 * 1024  # 1 MB


# ═══════════════════════════════════════════════════════════════════════════
# Cloud snapshot / context cache defaults (web_cloud_snapshot.py)
# ═══════════════════════════════════════════════════════════════════════════

class CloudDefaults:
    """Defaults for cloud alpha caching and official context snapshots."""

    CLOUD_SYNC_STALE_SECONDS: int = 24 * 60 * 60
    """Staleness threshold for cloud sync cache (24 hours)."""

    MAX_CACHED_USER_ALPHA_FILES: int = 50
    """Maximum number of cached user alpha JSON files to retain."""

    CONTEXT_CACHE_MANIFEST_SCHEMA: str = "official_context_cache_manifest.v1"
    """Schema version string for the context cache manifest."""

    STORAGE_JSONL_LIMIT: int = 500
    """Default row limit when reading storage JSONL files."""

    CONTEXT_CACHE_TTL_SECONDS: int = 86400
    """Default TTL for official context JSON cache files."""

    OFFICIAL_CONTEXT_DATA_DIR: str = "data"
    """Default relative path for official context files."""


# ═══════════════════════════════════════════════════════════════════════════
# Agent tool limits (agent_tools.py)
# ═══════════════════════════════════════════════════════════════════════════

class AgentLimits:
    """Hard limits for the agent tool surface to protect API quota."""

    MAX_TOOL_CANDIDATES: int = 100
    """Maximum candidates a single generate_candidates call can produce."""

    MAX_SYNC_RANGE: set[str] = {"1d", "3d", "7d", "all"}
    """Allowed values for sync_range parameter."""

    MAX_BATCH_SIMULATIONS: int = 10
    """Maximum expressions per run_simulation_batch call."""

    MAX_BATCH_SIMULATION_WORKERS: int = 3
    """Maximum concurrent workers for batch simulation."""

    MAX_POLLS_DEFAULT: int = 5
    MAX_POLLS_UPPER: int = 20
    POLL_INTERVAL_MIN: float = 0.5
    POLL_INTERVAL_MAX: float = 30.0
    POLL_INTERVAL_DEFAULT: float = 2.0

    EXPRESSION_INDEX_LIMIT_MAX: int = 50000
    MEMORY_LIMIT_MAX: int = 50000
    TOP_N_MAX: int = 50
    LIST_LIMIT_MAX: int = 200


# ═══════════════════════════════════════════════════════════════════════════
# Research / repository defaults (repository.py)
# ═══════════════════════════════════════════════════════════════════════════

class RepositoryDefaults:
    """Defaults for the ResearchRepository JSONL persistence layer."""

    LOCK_STALE_SECONDS: float = 120.0
    """Seconds after which a file lock is considered stale."""

    LOCK_POLL_SECONDS: float = 0.05
    """Polling interval for lock acquisition."""

    EXPRESSION_INDEXED_FILES: set[str] = {
        "candidates.jsonl",
        "lifecycle.jsonl",
        "checks.jsonl",
        "backtests.jsonl",
        "submissions.jsonl",
        "cloud_alphas.jsonl",
    }

    RECORD_INDEXED_FILES: set[str] = {
        "cloud_alphas.jsonl",
        "backtests.jsonl",
    }

    REPOSITORY_JSONL_FILES: set[str] = {
        "candidates.jsonl",
        "lifecycle.jsonl",
        "checks.jsonl",
        "backtests.jsonl",
        "submissions.jsonl",
        "cloud_alphas.jsonl",
        "ab_tests.jsonl",
        "assistant_guidance.jsonl",
        "events.jsonl",
        "families.jsonl",
        "strategy_lifecycle.jsonl",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Scoring / pipeline defaults
# ═══════════════════════════════════════════════════════════════════════════

class ScoringDefaults:
    """Defaults for the scoring system and quality gates."""

    DEFAULT_PRIOR_LAYER_WEIGHT: float = 0.30
    DEFAULT_EMPIRICAL_LAYER_WEIGHT: float = 0.45
    DEFAULT_CHECKLIST_LAYER_WEIGHT: float = 0.25
    DEFAULT_LOCAL_PRIOR_WEIGHT: float = 0.65
    DEFAULT_LOCAL_QUALITY_WEIGHT: float = 0.35
    DEFAULT_SUBMIT_THRESHOLD: float = 85.0
    DEFAULT_OPTIMIZE_THRESHOLD: float = 70.0
    DEFAULT_RESEARCH_THRESHOLD: float = 50.0
    ASSISTANT_BONUS_CAP: float = 4.0
    ASSISTANT_PENALTY_CAP: float = 5.0


class PipelineDefaults:
    """Defaults for the alpha research pipeline."""

    DEFAULT_MAX_CANDIDATES_PER_CYCLE: int = 20
    DEFAULT_MAX_VALIDATIONS_PER_CYCLE: int = 10
    DEFAULT_MAX_SIMULATIONS_PER_CYCLE: int = 3
    DEFAULT_RETAINED_POOL_SIZE: int = 10
    DEFAULT_BACKTEST_BATCH_SIZE: int = 3
    DEFAULT_MIN_LOCAL_QUALITY: float = 4.0
    DEFAULT_CYCLE_PAUSE_SECONDS: float = 2.0
    DEFAULT_MAX_CYCLES: int = 10
    CONVERGENCE_STALL_CYCLES: int = 5
