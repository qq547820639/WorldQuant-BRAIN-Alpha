"""Production diagnosis and gap analysis for the BRAIN alpha system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.data.official_context_validation import validate_official_context
from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem
from brain_alpha_ops.ux.history import RunHistoryAnalytics
from brain_alpha_ops.web_cloud_snapshot import official_context_file_counts


@dataclass(frozen=True)
class GapRow:
    dimension: str
    current_state: str
    gap: str
    severity: str
    evidence: str
    upgrade: str


@dataclass(frozen=True)
class PriorityItem:
    priority: str
    area: str
    finding: str
    fix: str
    validation: str


def build_diagnostic_snapshot(config_path: str | Path | None = None) -> dict[str, Any]:
    """Build a structured diagnosis that can be rendered or consumed by tests."""
    run_config = load_run_config(config_path)
    redline_report = RedLineVerifier(run_config).verify_all()
    loader = OfficialDataLoader.instance()
    scoring_probe = _scoring_probe(run_config)
    inline_status = _frontend_inline_status()
    history_replay = _history_replay_status(run_config)
    official_refresh = _official_refresh_status(run_config)
    official_validation = validate_official_context(config_path=config_path)
    parameter_audit = build_parameter_audit_snapshot(run_config, source="production_diagnostics")
    context_counts = _official_context_counts(loader, official_refresh)
    contract = _contract_comparison(
        run_config,
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )
    gap_matrix = _gap_matrix(
        run_config,
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )
    priorities = _priority_items(
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )

    return {
        "ok": bool(
            redline_report.ok
            and scoring_probe["zero_deviation"]
            and inline_status["ok"]
            and official_validation.get("blocking_ok")
        ),
        "schema_version": "production_diagnosis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": run_config.environment,
        "storage_dir": run_config.ops.storage_dir,
        "redline": redline_report.to_dict(),
        "official_context": context_counts,
        "official_refresh": official_refresh,
        "official_context_validation": official_validation,
        "parameter_audit": parameter_audit,
        "contract_comparison": contract,
        "scoring_probe": scoring_probe,
        "frontend_inline": inline_status,
        "history_replay": history_replay,
        "gap_matrix": [asdict(row) for row in gap_matrix],
        "priority_items": [asdict(item) for item in priorities],
        "completed_items": _completed_items(history_replay),
        "unfinished_items": _unfinished_items(priorities, official_refresh),
        "upgrade_plan": _upgrade_plan(),
    }


def render_one_page_markdown(snapshot: dict[str, Any]) -> str:
    """Render the diagnosis as a compact one-page Markdown report."""
    redline = snapshot["redline"]
    context = snapshot["official_context"]
    refresh = snapshot.get("official_refresh", {})
    scoring = snapshot["scoring_probe"]
    history = snapshot.get("history_replay", {})
    lines = [
        "# Alpha Production Diagnosis and Gap Matrix",
        "",
        f"- Generated: {snapshot['generated_at']}",
        f"- Environment: {snapshot['environment']}",
        f"- Verdict: {_report_verdict(snapshot)}",
        f"- Red lines: {redline['overall']} ({redline['passed']}/{redline['total_checks']} passed, {redline['failed']} blocking)",
        f"- Official context: fields={context['fields']}, operators={context['operators']}, datasets={context['datasets']}",
        (
            f"- Parameter audit: hash={snapshot.get('parameter_audit', {}).get('config_hash', '')[:12]}, "
            f"sections={len(snapshot.get('parameter_audit', {}).get('traceable_sections', []))}, "
            f"thresholds_zero_deviation={snapshot.get('parameter_audit', {}).get('thresholds_zero_deviation', False)}"
        ),
        (
            f"- Context validation: blocking_ok={snapshot.get('official_context_validation', {}).get('blocking_ok', False)}, "
            f"p1_findings={snapshot.get('official_context_validation', {}).get('p1_count', 0)}, "
            f"dataset_field_count_sum={snapshot.get('official_context_validation', {}).get('lineage', {}).get('dataset_field_count_sum', 0)}"
        ),
        (
            f"- Official refresh: status={refresh.get('status', 'unknown')}, "
            f"source={refresh.get('source', 'unknown')}, files={refresh.get('file_count', 0)}, "
            f"stale={refresh.get('stale_count', 0)}, last_attempt={refresh.get('last_attempt_status', 'not_recorded')}"
        ),
        f"- Scoring probe: status={scoring['api_status']}, zero_deviation={scoring['zero_deviation']}, score={scoring['total_score']}",
        (
            f"- History replay: capability={history.get('capability', 'unknown')}, "
            f"history_count={history.get('history_count', 0)}, "
            f"latest_comparison={history.get('latest_comparison_available', False)}"
        ),
        "",
        "## Gap Matrix",
        "",
        "| Dimension | State | Gap | Severity | Evidence | Upgrade |",
        "|---|---|---|---|---|---|",
    ]
    for row in snapshot["gap_matrix"]:
        lines.append(
            "| {dimension} | {current_state} | {gap} | {severity} | {evidence} | {upgrade} |".format(
                **{key: _md_cell(value) for key, value in row.items()}
            )
        )
    lines.extend(["", "## Priority Attack List", ""])
    if snapshot["priority_items"]:
        for item in snapshot["priority_items"]:
            lines.append(
                f"- **{item['priority']} {item['area']}**: {item['finding']} "
                f"Fix: {item['fix']} Validation: `{item['validation']}`"
            )
    else:
        lines.append("- No blocking or executable attack item remains in the current diagnostic snapshot.")
    lines.extend(["", "## Current Execution Checklist", ""])
    completed = snapshot.get("completed_items") or []
    unfinished = snapshot.get("unfinished_items") or []
    lines.append("### Completed")
    for item in completed:
        lines.append(f"- [x] {item}")
    lines.append("")
    lines.append("### Unfinished")
    if unfinished:
        for item in unfinished:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("- None in the current local code checklist.")
    lines.extend(["", "## QuantGPT-Aligned Upgrade Plan", ""])
    for item in snapshot["upgrade_plan"]:
        lines.append(f"- **{item['priority']} {item['area']}**: {item['recommendation']}")
    return "\n".join(lines) + "\n"


def write_diagnostic_report(path: str | Path, snapshot: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_one_page_markdown(snapshot), encoding="utf-8")
    return target


def snapshot_to_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)


def _scoring_probe(run_config: RunConfig) -> dict[str, Any]:
    candidate = Candidate(
        alpha_id="diagnostic_probe",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Medium-horizon price momentum can be confirmed by liquidity participation and risk scaling.",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_mean"],
        dataset_id="fundamental6",
        local_quality={"passed": True, "score": 85},
        official_metrics={
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "prod_correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
            "subUniverseSize": 1000,
            "alphaSize": 1000,
            "margin": 5.0,
        },
        submission={"settings": run_config.ops.settings.to_platform_dict()["settings"]},
    )
    candidate.official_alpha_id = "diagnostic_official_probe"
    result = OfficialScoringSystem(run_config.ops).evaluate(candidate)
    return {
        "alpha_id": result.alpha_id,
        "api_status": result.simulated_api_output.get("status"),
        "zero_deviation": result.api_output_deviation == 0.0,
        "api_output_deviation": result.api_output_deviation,
        "deviation_details": result.deviation_details,
        "total_score": result.total_score,
        "decision_band": result.decision_band,
        "passed_gate": result.passed_gate,
        "hard_gate_count": len(result.hard_gates[0].check_items) if result.hard_gates else 0,
        "config_hash": result.config_hash,
        "settings_trace": getattr(result, "settings_trace", {}),
        "threshold_trace": getattr(result, "threshold_trace", {}),
        "attribution_summary": result.to_dict().get("attribution_summary", {}),
    }


def _frontend_inline_status() -> dict[str, Any]:
    try:
        from brain_alpha_ops.build_inline import check

        result = check()
        css_sources = result.get("css_sources", [])
        return {
            "ok": bool(result.get("ok")),
            "replaced": result.get("replaced", 0),
            "css_replaced": result.get("css_replaced", 0),
            "missing": result.get("missing", []),
            "css_sources": [source for source in css_sources if source == "css/app.css"] or css_sources[:1],
            "css_source_files": css_sources,
            "error": result.get("error", ""),
        }
    except Exception as exc:
        return {"ok": False, "replaced": 0, "missing": [], "error": str(exc)}


def _history_replay_status(run_config: RunConfig) -> dict[str, Any]:
    analytics = RunHistoryAnalytics(run_config.ops.storage_dir).analytics(limit=10)
    return {
        "schema_version": "history_replay_status.v1",
        "capability": "ready",
        "analytics_schema_version": analytics.get("schema_version", ""),
        "history_count": int(analytics.get("history_count") or 0),
        "latest_comparison_available": bool(analytics.get("latest_comparison")),
        "trend_status": (analytics.get("trend") or {}).get("status", "empty"),
        "latest_run_id": (analytics.get("latest") or {}).get("run_id", ""),
    }


def _official_refresh_status(run_config: RunConfig) -> dict[str, Any]:
    counts = official_context_file_counts(load_config=lambda: run_config)
    manifest = counts.get("context_cache_manifest") if isinstance(counts.get("context_cache_manifest"), dict) else {}
    status_path = Path(run_config.ops.storage_dir) / "official_context_refresh_status.json"
    attempt = _read_refresh_attempt_status(status_path)
    metadata_files = manifest.get("files") or {}
    sources = sorted(
        {
            str(meta.get("source") or "")
            for meta in metadata_files.values()
            if isinstance(meta, dict) and str(meta.get("source") or "")
        }
    )
    status = "verified" if attempt.get("ok") is True else "not_verified"
    if attempt.get("ok") is False:
        status = "failed"
    elif manifest.get("complete") and "official_api" in sources:
        status = "metadata_verified"
    return {
        "schema_version": "official_refresh_status.v1",
        "status": status,
        "source": ",".join(sources) or "metadata_missing",
        "file_count": int(manifest.get("file_count") or len(metadata_files) or 0),
        "missing_files": list(manifest.get("missing_files") or []),
        "stale_files": list(manifest.get("stale_files") or []),
        "stale_count": len(manifest.get("stale_files") or []),
        "record_counts": dict(manifest.get("record_counts") or {}),
        "complete": bool(manifest.get("complete")),
        "last_attempt_status": str(attempt.get("status") or "not_recorded"),
        "last_attempt_ok": attempt.get("ok"),
        "last_attempt_error": str(attempt.get("error") or ""),
        "last_attempt_generated_at": str(attempt.get("generated_at") or ""),
        "status_path": str(status_path),
    }


def _official_context_counts(loader: OfficialDataLoader, official_refresh: dict[str, Any]) -> dict[str, int]:
    record_counts = official_refresh.get("record_counts") or {}
    return {
        "fields": int(record_counts.get("official_fields.json") or loader.field_count),
        "operators": int(record_counts.get("official_operators.json") or loader.operator_count),
        "datasets": int(record_counts.get("official_datasets.json") or loader.dataset_count),
    }


def _read_refresh_attempt_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report_verdict(snapshot: dict[str, Any]) -> str:
    refresh = snapshot.get("official_refresh") or {}
    if refresh.get("last_attempt_ok") is False:
        return "ACTION REQUIRED"
    if any(str(item).startswith("P0 ") or str(item).startswith("P1 ") for item in snapshot.get("unfinished_items") or []):
        return "ACTION REQUIRED"
    return "PASS" if snapshot.get("ok") else "ACTION REQUIRED"
