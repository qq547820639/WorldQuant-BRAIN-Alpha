"""Gap matrix, contract comparison, and priority attack list builders.

These functions consume the probe outputs and produce the structured
analysis sections of the diagnostic snapshot.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
from brain_alpha_ops.config import RunConfig

from ._models import GapRow, PriorityItem


def _contract_comparison(
    run_config: RunConfig,
    redline_report: Any,
    context_counts: dict[str, int],
    scoring_probe: dict[str, Any],
    inline_status: dict[str, Any],
    history_replay: dict[str, Any],
    official_refresh: dict[str, Any],
    official_validation: dict[str, Any],
    parameter_audit: dict[str, Any],
) -> dict[str, Any]:
    thresholds = run_config.ops.thresholds
    threshold_diffs = {
        key: {
            "configured": getattr(thresholds, key),
            "canonical": canonical,
            "deviation": getattr(thresholds, key) - canonical,
            "match": getattr(thresholds, key) == canonical,
        }
        for key, canonical in CANONICAL_THRESHOLDS.items()
    }
    return {
        "schema_version": "contract_comparison.v1",
        "thresholds_zero_deviation": all(row["match"] for row in threshold_diffs.values()),
        "thresholds": threshold_diffs,
        "redlines_pass": redline_report.ok,
        "official_context_loaded": all(value > 0 for value in context_counts.values()),
        "official_context_blocking_ok": bool(official_validation.get("blocking_ok")),
        "dataset_field_counts_match": bool((official_validation.get("lineage") or {}).get("field_count_sum_matches")),
        "scoring_zero_deviation": scoring_probe["zero_deviation"],
        "frontend_inline_synced": inline_status["ok"],
        "history_replay_ready": history_replay.get("capability") == "ready",
        "official_refresh_recorded": official_refresh.get("last_attempt_status") != "not_recorded",
        "parameter_audit_complete": bool(parameter_audit.get("ok")),
        "parameter_audit_hash": parameter_audit.get("config_hash", ""),
    }


def _gap_matrix(
    run_config: RunConfig,
    redline_report: Any,
    context_counts: dict[str, int],
    scoring_probe: dict[str, Any],
    inline_status: dict[str, Any],
    history_replay: dict[str, Any],
    official_refresh: dict[str, Any],
    official_validation: dict[str, Any],
    parameter_audit: dict[str, Any],
) -> list[GapRow]:
    lineage = official_validation.get("lineage") or {}
    validation_blocking_ok = bool(official_validation.get("blocking_ok"))
    validation_p1_count = int(official_validation.get("p1_count") or 0)
    official_refresh_ok = official_refresh.get("last_attempt_ok") is True
    parameter_gap = (
        "No parameter-accuracy gap in the current evidence record."
        if official_refresh_ok
        else "Accuracy depends on periodic official context refresh and recorded refresh evidence."
    )
    parameter_upgrade = (
        "Keep credential-backed official context refresh in the production preflight."
        if official_refresh_ok
        else "Run fetch_official_context.py --config config/run_config.json --json before production batches."
    )
    lineage_gap = "No blocking data-lineage gap in current context files."
    if not validation_blocking_ok:
        lineage_gap = "Official context has blocking structural or lineage findings."
    elif validation_p1_count:
        lineage_gap = "Refresh metadata is expired; API credentials are needed to renew current official evidence."
    lineage_upgrade = (
        "Keep field-count/hash metadata aligned with every official context refresh."
        if not validation_p1_count
        else "Refresh from official /data-sets with BRAIN credentials; keep field-count/hash metadata aligned."
    )
    return [
        GapRow(
            "Functional closure",
            "Guided production, checkpoint resume, run-history analytics, official check, scoring, gate, and submission paths are wired.",
            "No blocking functional gap in current code; richer comparison depends on accumulated run history.",
            "PASS",
            f"env={run_config.environment}, history_count={history_replay.get('history_count', 0)}, storage={run_config.ops.storage_dir}",
            "Keep checkpoint resume and history comparison in the quality-gated flow.",
        ),
        GapRow(
            "Technical compliance",
            "Six red lines are executable and blocking.",
            "No blocking gap in current tree.",
            "PASS" if redline_report.ok else "P0",
            f"{redline_report.passed}/{redline_report.total_checks} checks passed",
            "Keep redline verifier in pre-run and quality-gate flows.",
        ),
        GapRow(
            "Parameter accuracy",
            "Thresholds, settings, API paths, and score config are traceable.",
            parameter_gap,
            "P1" if official_refresh.get("last_attempt_ok") is not True else "PASS",
            (
                f"config_hash={scoring_probe['config_hash']}, "
                f"parameter_hash={str(parameter_audit.get('config_hash', ''))[:12]}, "
                f"refresh_status={official_refresh.get('last_attempt_status')}"
            ),
            parameter_upgrade,
        ),
        GapRow(
            "Data lineage",
            "Official fields/operators/datasets are loaded through the shared loader and cross-checked against metadata.",
            lineage_gap,
            "P0" if not validation_blocking_ok else ("P1" if validation_p1_count else "PASS"),
            (
                f"fields={context_counts['fields']}, operators={context_counts['operators']}, datasets={context_counts['datasets']}, "
                f"dataset_field_count_sum={lineage.get('dataset_field_count_sum', 0)}, blocking_ok={validation_blocking_ok}"
            ),
            lineage_upgrade,
        ),
        GapRow(
            "Experience",
            "Web console has status strips, toasts, detail modal, checkpoint/history analytics, structured errors, and phase-aware guided progress.",
            "No blocking UX gap in the current code checklist; live history depth depends on stored runs.",
            "PASS" if inline_status["ok"] else "P1",
            (
                f"frontend_inline_ok={inline_status['ok']}, js_modules={inline_status.get('replaced', 0)}, "
                f"css_modules={inline_status.get('css_replaced', 0)}, comparison={history_replay.get('latest_comparison_available')}"
            ),
            "Continue adding deeper visual history analytics as a non-blocking follow-up.",
        ),
        GapRow(
            "Scoring",
            "OfficialScoringSystem returns API-shaped simulation, gates, attribution, history, and traces.",
            "Calibration still needs more real PASS/FAIL samples.",
            "P2",
            f"probe_status={scoring_probe['api_status']}, zero_deviation={scoring_probe['zero_deviation']}",
            "Use score history and auto-calibration only after enough official outcomes accumulate.",
        ),
    ]


def _priority_items(
    redline_report: Any,
    context_counts: dict[str, int],
    scoring_probe: dict[str, Any],
    inline_status: dict[str, Any],
    history_replay: dict[str, Any],
    official_refresh: dict[str, Any],
    official_validation: dict[str, Any],
    parameter_audit: dict[str, Any],
) -> list[PriorityItem]:
    items: list[PriorityItem] = []
    if not redline_report.ok:
        items.append(PriorityItem("P0", "redlines", "Blocking red-line violations exist.", "Fix violations before production.", "python -m brain_alpha_ops.compliance.redline_verifier --block --json"))
    if not scoring_probe["zero_deviation"]:
        items.append(PriorityItem("P0", "scoring", "API-shaped simulation disagrees with official pass/fail.", "Inspect deviation_details and hard-gate reconstruction.", "python -m pytest tests/test_official_scoring_system.py -q"))
    if not inline_status["ok"]:
        items.append(PriorityItem("P1", "frontend", "Generated web console is stale or missing modules.", "Run inline builder and syntax checks.", "python brain_alpha_ops/web/build_inline.py --check --json"))
    if context_counts["datasets"] == 0:
        items.append(PriorityItem("P1", "data", "Official dataset cache is empty.", "Refresh official context from BRAIN API.", "python fetch_official_context.py"))
    if not official_validation.get("blocking_ok"):
        items.append(PriorityItem("P0", "official context", "Official context cache has structural or lineage violations.", "Fix official_*.json or regenerate from BRAIN API.", "python scripts/check_official_context.py --strict-freshness --json"))
    elif official_validation.get("p1_count", 0):
        items.append(PriorityItem("P1", "official context refresh", "Official context metadata is stale or incomplete.", "Refresh official context with BRAIN credentials and rerun validation.", "python fetch_official_context.py --config config/run_config.json --json"))
    if official_refresh.get("last_attempt_ok") is not True:
        items.append(PriorityItem("P1", "official refresh", "Live BRAIN context refresh has not completed in the current evidence record.", "Run online refresh and keep the failure reason in the report if blocked.", "python fetch_official_context.py --config config/run_config.json --json"))
    if not parameter_audit.get("ok"):
        items.append(PriorityItem("P0", "parameter audit", "Runtime parameter audit snapshot has blocking findings.", "Fix threshold/API drift or missing trace sections.", "python scripts/check_diagnosis_gap_coverage.py --json"))
    if history_replay.get("capability") != "ready":
        items.append(PriorityItem("P2", "history replay", "Checkpoint/run-history analytics capability is unavailable.", "Restore RunHistoryAnalytics integration.", "python -m pytest tests/test_run_history_analytics.py tests/test_web_redline_scoring.py -q"))
    items.extend([
        PriorityItem("P2", "architecture", "pipeline.py and web.py remain large hotspots.", "Continue extracting service/repository/serializer modules by workflow boundary.", "python scripts/check_module_size.py --json"),
    ])
    return items


def _completed_items(history_replay: dict[str, Any]) -> list[str]:
    return [
        "Six technical red lines are executable and blocking.",
        "Unified BRAIN contract comparison is quality-gated in default and strict-freshness modes.",
        "OfficialScoringSystem exposes API-shaped simulation, zero-deviation gates, traces, and attribution.",
        "Scoring settings trace covers the complete BRAIN platform settings envelope, including alpha type.",
        "Run parameter audit snapshots cover ops.settings, ops.budget, ops.thresholds, ops.submission_policy, scoring, and official API paths.",
        "Web frontend inline bundle, syntax, and approved innerHTML sinks are quality-gated.",
        f"Checkpoint/run-history analytics are wired (history_count={history_replay.get('history_count', 0)}, comparison={history_replay.get('latest_comparison_available', False)}).",
        "Assistant context/request output includes redline, scoring, observability, anti-overfit, rolling-validation, and duplicate-expression evidence.",
    ]


def _unfinished_items(priorities: list[PriorityItem], official_refresh: dict[str, Any]) -> list[str]:
    unfinished = [f"{item.priority} {item.area}: {item.finding}" for item in priorities if item.priority in {"P0", "P1"}]
    if official_refresh.get("last_attempt_ok") is False and official_refresh.get("last_attempt_error"):
        unfinished.append(f"Online official context refresh blocked: {official_refresh['last_attempt_error']}")
    return unfinished


def _upgrade_plan() -> list[dict[str, str]]:
    return [
        {"priority": "P1", "area": "Architecture", "recommendation": "Keep official API, scoring, gating, repository, and web routing as separate modules; continue shrinking pipeline and web hotspots."},
        {"priority": "P1", "area": "Data efficiency", "recommendation": "Use official context cache metadata, pagination truncation guards, and SQLite indexes for repeated lookup paths."},
        {"priority": "P1", "area": "LLM prompting", "recommendation": "Feed redline report, scoring attribution, anti-overfit, and research memory into assistant prompts as hard constraints."},
        {"priority": "P2", "area": "Backtest execution", "recommendation": "Let rolling validation and overfit findings alter candidate priority before spending official simulation budget."},
        {"priority": "P2", "area": "Errors and logs", "recommendation": "Keep user-facing errors structured and redacted; preserve full detail only in local logs with error ids."},
    ]
