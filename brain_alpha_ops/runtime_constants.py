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

from typing import Final

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

    CONTEXT_CACHE_MANIFEST_SCHEMA: str = "official_context_cache_manifest.v1"
    """Schema version string for the context cache manifest."""

    STORAGE_JSONL_LIMIT: int = 500
    """Default row limit when reading storage JSONL files."""

    CONTEXT_CACHE_TTL_SECONDS: int = 86400
    """Default TTL for official context JSON cache files."""

    OFFICIAL_CONTEXT_DATA_DIR: str = "data"
    """Default relative path for official context files."""


# ═══════════════════════════════════════════════════════════════════════════
# Official context refresh defaults
# ═══════════════════════════════════════════════════════════════════════════

class ContextRefreshDefaults:
    """Defaults for refreshing data/official_*.json from BRAIN API.

    P0-1 fix (2026-06-13): 120s timeout was empirically too short; raised to
    300s and added max_retries with progressive backoff. Previous failure
    mode: ``official_context_refresh_status.json`` showed ``status=failed``
    with the message ``refresh exceeded 120s timeout`` whenever the BRAIN
    upstream needed more than 2 minutes to stream the full field catalog.
    """

    DEFAULT_STALL_SECONDS: float = 300.0  # stall-detection window (not total timeout)
    """Overall refresh deadline in seconds. Matches ``fetch_official_context.py`` CLI default."""

    DEFAULT_MAX_RETRIES: int = 3
    """Number of retry attempts on transient failures (network 5xx, timeout)."""

    DEFAULT_RETRY_BASE_SECONDS: float = 1.0
    """Base backoff between retries; actual wait = base * attempt_index."""

    DEFAULT_STALE_HOURS: float = 24.0
    """Hours after which the cached official context is considered stale."""

    DEFAULT_CHUNK_SIZE: int = 500
    """Field/dataset rows per API page when chunked refresh is enabled."""

    # Single source of truth for sync range (P0-3 fix 2026-06-13)
    # Three legacy duplicates (AgentLimits, user_alpha_sync, web_payload_validation)
    # were unified to this set.
    ALLOWED_SYNC_RANGES: frozenset[str] = frozenset({"1d", "3d", "7d", "recent", "6months", "all"})
    """Canonical set of accepted sync ranges. Web + agent + sync layers must use this."""


# ═══════════════════════════════════════════════════════════════════════════
# Web human-in-the-loop confirmation gates (P0-2 fix 2026-06-13)
# ═══════════════════════════════════════════════════════════════════════════

class HILDefaults:
    """Defaults for human-in-the-loop confirmation gates on side-effecting
    web routes.

    These gates protect users from accidentally triggering BRAIN-side work
    (which costs API quota and may take hours to complete) by requiring an
    explicit ``confirm_*=True`` field in the request body. The check applies
    to routes that touch external services or that have a high financial /
    account risk if mis-triggered.
    """

    SIMULATION_CONFIRM_REQUIRED: bool = True
    """If True, ``/api/candidates/simulate`` requires
    ``confirm_simulation=True`` to actually start a job; otherwise it
    returns a 409 with the confirmation gate error code so the frontend
    can present a confirm dialog."""

    SIMULATION_CONFIRM_FIELD: str = "confirm_simulation"
    """Request body field checked for explicit user confirmation."""

    SIMULATION_CONFIRM_ERROR_CODE: str = "SIMULATION_CONFIRMATION_REQUIRED"
    """Error code returned when the confirmation field is missing/false."""

    SIMULATION_CONFIRM_HINT: str = (
        "请在前端确认弹窗中勾选 '我确认要发起官方 BRAIN 模拟' 后重试；"
        "BRAIN 模拟会消耗配额、可能耗时数小时。"
    )
    """Chinese-language hint surfaced to the user when the gate trips."""


# ═══════════════════════════════════════════════════════════════════════════
# Agent tool limits (agent_tools.py)
# ═══════════════════════════════════════════════════════════════════════════

class AgentLimits:
    """Hard limits for the agent tool surface to protect API quota."""

    MAX_TOOL_CANDIDATES: int = 100
    """Maximum candidates a single generate_candidates call can produce."""

    # P0-3 fix (2026-06-13): agent tools may advertise any value the canonical
    # ALLOWED_SYNC_RANGES exposes. The old literal was missing ``recent`` and
    # ``6months`` and is no longer authoritative. ContextRefreshDefaults is
    # defined above in this module so the reference resolves at class body
    # evaluation time.
    # ``6months`` and is no longer authoritative.
    MAX_SYNC_RANGE: frozenset[str] = ContextRefreshDefaults.ALLOWED_SYNC_RANGES
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
    """Allowed values for sync_range parameter."""

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
# JSONL archive policy (web_runtime_state.maybe_archive_lifecycle)
# ═══════════════════════════════════════════════════════════════════════════

class JournalArchiveDefaults:
    """Defaults for the JSONL journal archive policy (P1-9 fix 2026-06-13).

    Files larger than ``MAX_SIZE_MB`` are renamed to a timestamped archive
    under ``<storage>/archive/`` and the current file is recreated empty on
    the next append. Archives older than ``MAX_AGE_DAYS`` are removed.
    The throttle interval (``ARCHIVE_CHECK_INTERVAL``) is in ``WebDefaults``
    so the 1-hour cadence can be tuned independently from the policy below.
    """

    MAX_SIZE_MB: int = 50
    """Per-file size threshold (in MB) above which the JSONL gets archived."""

    MAX_AGE_DAYS: int = 30
    """Archive files older than this many days are deleted on cleanup."""

    # Phase 3 (P1-9): archive policy now covers the full set of journal
    # files that can grow unbounded. lifecycle.jsonl was the only one
    # archived before; candidates/checks/backtests/submissions join it.
    # alpha_features.jsonl / cloud_alphas.jsonl are intentionally excluded
    # because alpha_features is read by indexes that assume continuity and
    # cloud_alphas is the system of record for sync state (regenerated on
    # next sync rather than rotated).
    ARCHIVE_FILES: tuple[str, ...] = (
        "lifecycle.jsonl",
        "candidates.jsonl",
        "checks.jsonl",
        "backtests.jsonl",
        "submissions.jsonl",
    )
    """Filenames covered by the archive policy. Subset of ``REPOSITORY_JSONL_FILES``."""


# ═══════════════════════════════════════════════════════════════════════════
# Scoring / pipeline defaults
# ═══════════════════════════════════════════════════════════════════════════

class ScoringDefaults:
    """Defaults for the scoring system and quality gates.

    .. deprecated:: 0.3.1
        Target removal: v0.4 (2026-Q3).  Use ``ScoringConfig`` from ``brain_alpha_ops.config_models`` instead.
        This class is retained only for backward compatibility with
        ``tests/test_runtime_constants.py`` and will be removed in v0.4.
        The authoritative defaults now live in ``config_models.ScoringConfig``.
    """

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
    """Defaults for the alpha research pipeline.

    .. deprecated:: 0.3.1
        Target removal: v0.4 (2026-Q3).  Use ``ResearchBudget`` from ``brain_alpha_ops.config_models`` instead.
        This class is retained only for backward compatibility with
        ``tests/test_runtime_constants.py`` and will be removed in v0.4.
        The authoritative defaults now live in ``config_models.ResearchBudget``.
    """

    DEFAULT_MAX_CANDIDATES_PER_CYCLE: int = 20
    DEFAULT_MAX_VALIDATIONS_PER_CYCLE: int = 10
    DEFAULT_MAX_SIMULATIONS_PER_CYCLE: int = 3
    DEFAULT_RETAINED_POOL_SIZE: int = 10
    DEFAULT_BACKTEST_BATCH_SIZE: int = 3
    DEFAULT_MIN_LOCAL_QUALITY: float = 4.0
    DEFAULT_CYCLE_PAUSE_SECONDS: float = 2.0
    DEFAULT_MAX_CYCLES: int = 10
    CONVERGENCE_STALL_CYCLES: int = 5


# NOTE: ``ContextRefreshDefaults`` and ``HILDefaults`` are intentionally
# defined earlier in this module (before ``AgentLimits``) because
# ``AgentLimits.MAX_SYNC_RANGE`` now references
# ``ContextRefreshDefaults.ALLOWED_SYNC_RANGES`` directly. This is a P0-3
# fix from 2026-06-13; keep the class definitions ordered accordingly.


# ═══════════════════════════════════════════════════════════════════════════
# Hard kill-switches (MUST stay True unless the consultant relaxes the policy)
# ═══════════════════════════════════════════════════════════════════════════

# Web console must NEVER call api.submit_alpha for real.  Production submits
# require a separate approval path.  This constant is imported by every
# web_submission_*.py entry point and by the in-tree `REAL_SUBMIT_DISABLED_WEB_FLOW`
# blocker.  Tests can override via env BRAIN_ALPHA_FORCE_REAL_SUBMIT=1 only when
# the runtime_constants.allow_real_submit_override is True (consultant-gated).
REAL_SUBMIT_DISABLED_WEB_FLOW: Final[bool] = True
"""Hard kill-switch: when True, the Web console's submit endpoints always return
``REAL_SUBMIT_DISABLED_WEB_FLOW`` and never invoke ``api.submit_alpha``.

F-02 fix: ``Final[bool]`` annotation signals to type checkers this is a hard
constant.  The runtime guard in ``brain_api/official_simulation.py`` also
enforces it at the API layer so direct imports cannot bypass it.
"""
