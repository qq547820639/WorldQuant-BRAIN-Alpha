"""LLM-ready context packs for alpha research assistance.

The context pack is a compact, structured snapshot of the current research
state.  It deliberately stays read-only: it combines run configuration, latest
local results, cloud alpha cache summaries, and research memory guidance into a
payload that an assistant can consume before proposing or generating alphas.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import build_research_observability_snapshot, observability_context


def build_assistant_context_pack(
    run_config: RunConfig | None = None,
    *,
    latest_result_snapshot: dict[str, Any] | None = None,
    cloud_alpha_snapshot: dict[str, Any] | None = None,
    memory_summary: dict[str, Any] | None = None,
    memory_guidance: dict[str, Any] | None = None,
    observability_snapshot: dict[str, Any] | None = None,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = True,
) -> dict[str, Any]:
    """Build a prompt-ready context pack for an alpha research assistant."""
    config = run_config or load_run_config()
    storage_dir = str(config.ops.storage_dir)
    memory = ResearchMemory(storage_dir)

    summary = memory_summary if memory_summary is not None else memory.summary(limit=limit, top_n=top_n)
    guidance = memory_guidance if memory_guidance is not None else memory.generation_guidance(limit=limit, top_n=top_n, summary=summary)
    latest = latest_result_snapshot if latest_result_snapshot is not None else _latest_result_from_storage(storage_dir)
    cloud = cloud_alpha_snapshot if cloud_alpha_snapshot is not None else _cloud_snapshot_from_storage(storage_dir, top_n=top_n)
    observability = observability_snapshot if observability_snapshot is not None else build_research_observability_snapshot(storage_dir, limit=limit, top_n=top_n)

    pack = {
        "ok": True,
        "schema_version": "assistant_context_pack.v1",
        "source": "local_config_run_history_cloud_memory",
        "generated_at": utc_now(),
        "storage_dir": storage_dir,
        "mission": {
            "role": "quant_investment_ai_assistant",
            "objective": "Generate, critique, and prioritize WorldQuant BRAIN FASTEXPR alpha ideas using local evidence before live API calls.",
            "operating_mode": "local_first_memory_guided_research",
        },
        "run_config": _run_config_context(config),
        "latest_result": _latest_result_context(latest),
        "cloud_alphas": _cloud_context(cloud, top_n=top_n),
        "research_memory": _memory_context(summary, guidance, top_n=top_n),
        "expression_index": _expression_index_context(
            summary.get("expression_index") if isinstance(summary, dict) else {},
            top_n=top_n,
        ),
        "observability": observability_context(observability, top_n=top_n),
        "generation_focus": _generation_focus(guidance, summary, top_n=top_n),
        "risk_controls": _risk_controls(config, cloud),
        "recommended_next_actions": _next_actions(summary, guidance, latest, cloud),
        "compliance": _compliance_context(config),
    }
    pack["prompt_diagnostics"] = _prompt_diagnostics(pack, top_n=top_n)
    if include_prompt:
        pack["prompt"] = render_context_prompt(pack)
    if not include_sensitive:
        pack.pop("storage_dir", None)
        pack["sensitive_fields_redacted"] = ["storage_dir"]
    return pack


def render_context_prompt(pack: dict[str, Any]) -> str:
    """Render a concise text prompt from a structured context pack."""
    config = pack.get("run_config") or {}
    settings = config.get("settings") or {}
    budget = config.get("budget") or {}
    latest = pack.get("latest_result") or {}
    memory = pack.get("research_memory") or {}
    expression_index = pack.get("expression_index") or {}
    observability = pack.get("observability") or {}
    focus = pack.get("generation_focus") or {}
    cloud = pack.get("cloud_alphas") or {}
    guardrails = pack.get("risk_controls") or {}
    compliance = pack.get("compliance") if isinstance(pack.get("compliance"), dict) else {}
    redline_info = compliance.get("redline") if isinstance(compliance.get("redline"), dict) else {}
    actions = pack.get("recommended_next_actions") or []
    diagnostics = pack.get("prompt_diagnostics") if isinstance(pack.get("prompt_diagnostics"), dict) else {}

    lines = [
        "You are the quant investment AI assistant for WorldQuant BRAIN FASTEXPR research.",
        "Use local evidence first, avoid duplicate or highly correlated variants, and do not submit alphas without explicit confirmation.",
        "",
        "Current market/run setup:",
        f"- Environment: {config.get('environment', '-')}; auto_submit={config.get('auto_submit', False)}",
        f"- Settings: region={settings.get('region', '-')}, universe={settings.get('universe', '-')}, delay={settings.get('delay', '-')}, neutralization={settings.get('neutralization', '-')}, decay={settings.get('decay', '-')}, truncation={settings.get('truncation', '-')}",
        f"- Budget: candidates/cycle={budget.get('max_candidates_per_cycle', '-')}, retained_pool={budget.get('retained_alpha_pool_size', '-')}, backtest_batch={budget.get('official_backtest_batch_size', '-')}, validation_threshold={budget.get('min_prior_score_for_official_validation', '-')}, simulation_threshold={budget.get('min_prior_score_for_official_simulation', '-')}",
        "",
        "Latest run snapshot:",
        f"- Source/status: {latest.get('source', '-')}/{latest.get('status', '-')}; cycle={latest.get('cycle', '-')}",
        f"- Counts: candidates={latest.get('candidate_count', 0)}, pending_backtests={latest.get('pending_backtest_count', 0)}, passed={latest.get('passed_count', 0)}, active_backtests={latest.get('active_backtest_count', 0)}",
        f"- Top candidates: {_join_candidate_briefs(latest.get('top_candidates') or [])}",
        "",
        "Research memory guidance:",
        f"- Candidates observed: {memory.get('total_candidates', 0)}; guidance sample={memory.get('guidance_sample_size', 0)}",
        f"- Fields: {', '.join(focus.get('fields') or []) or '-'}",
        f"- Operators: {', '.join(focus.get('operators') or []) or '-'}",
        f"- Windows: {', '.join(str(item) for item in (focus.get('windows') or [])) or '-'}",
        f"- Field combinations: {_join_field_combinations(focus.get('field_combinations') or [])}",
        f"- Failure patterns to avoid/fix: {_join_failures(focus.get('failure_patterns') or [])}",
        f"- Assistant-guided outcomes: {_join_stat_bucket(memory.get('assistant_guided') or {})}",
        f"- Guidance feedback: {_join_guidance_outcomes(focus.get('guidance_outcomes') or memory.get('assistant_guidance_outcomes') or [])}",
        f"- Expression index: unique={expression_index.get('unique_expression_count', 0)}, duplicates={expression_index.get('duplicate_expression_count', 0)}, top duplicates={_join_duplicate_expressions(expression_index.get('duplicates') or [])}",
        f"- Observability: risk={observability.get('risk_level', 'unknown')}, flags={_join_text_items(observability.get('health_flags') or [])}, blocking={_join_text_items(observability.get('blocking_flags') or [])}, backtest_failure_rate={observability.get('backtest_failure_rate', 0)}, retryable_errors={observability.get('retryable_error_count', 0)}, official_guard_blocked={observability.get('official_guard_blocked_count', 0)} (validation={observability.get('official_guard_validation_blocked_count', 0)}, simulation={observability.get('official_guard_simulation_blocked_count', 0)}), actions={_join_text_items(observability.get('recommended_actions') or observability.get('recommendations') or [])}",
        f"- Prompt diagnostics: tokens≈{diagnostics.get('estimated_context_tokens', 0)}, duplicate_focus={diagnostics.get('duplicate_focus_count', 0)}, risk_flags={_join_text_items(diagnostics.get('risk_flags') or [])}, evidence_digest={diagnostics.get('evidence_digest', '-')}",
        "",
        "Cloud/cache risk context:",
        f"- Cloud source={cloud.get('source', '-')}; count={cloud.get('count', 0)}; stale={cloud.get('is_stale', False)}",
        f"- Submitted={cloud.get('submitted_count', 0)}, passed_unsubmitted={cloud.get('passed_unsubmitted_count', 0)}, failed_unsubmitted={cloud.get('failed_unsubmitted_count', 0)}",
        "",
        "Guardrails:",
        f"- Live API allowed by context: {guardrails.get('live_api_default_allowed', False)}",
        f"- Submit requires explicit confirmation: {guardrails.get('submit_requires_confirmation', True)}",
        f"- Cloud sync required before submit: {guardrails.get('cloud_sync_required', True)}",
        "",
        "Compliance status:",
        f"- Redline verification: {'PASS' if redline_info.get('ok') else 'FAIL'} ({redline_info.get('violations', 0)} violations)",
        f"- Scoring thresholds synced: {compliance.get('thresholds_synced', True)}",
        f"- Redline detail: {redline_info.get('summary', '-')}",
        "",
        "Recommended next actions:",
    ]
    lines.extend(f"- {item}" for item in actions[:8])
    return "\n".join(lines).strip() + "\n"


def _run_config_context(config: RunConfig) -> dict[str, Any]:
    ops = config.ops
    return {
        "environment": config.environment,
        "auto_submit": bool(config.auto_submit),
        "settings": _dataclass_dict(ops.settings),
        "budget": _dataclass_dict(ops.budget),
        "thresholds": _dataclass_dict(ops.thresholds),
        "submission_policy": _dataclass_dict(ops.submission_policy),
        "source_tag_policy": ops.source_tag_policy,
    }


def _latest_result_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = snapshot or {}
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    progress = snapshot.get("progress") if isinstance(snapshot.get("progress"), dict) else {}
    summary = _first_dict(result.get("summary"), progress.get("data"), snapshot.get("summary"))
    candidates = _first_list(result.get("candidates"), summary.get("candidates"), snapshot.get("candidates"))
    pending = _first_list(summary.get("pending_backtest_candidates"), snapshot.get("pending_backtest_candidates"))
    passed = _first_list(summary.get("passed_candidates"), snapshot.get("passed_candidates"))
    backtests = _first_list(summary.get("backtest_slots"), summary.get("backtests"), snapshot.get("backtests"))
    backtest_records = _first_list(summary.get("backtest_records"), snapshot.get("backtest_records"))

    return {
        "source": snapshot.get("source", "empty"),
        "job_id": snapshot.get("job_id", ""),
        "status": snapshot.get("status") or progress.get("phase") or "",
        "cycle": summary.get("cycle", ""),
        "candidate_count": len(candidates),
        "pending_backtest_count": len(pending),
        "passed_count": len(passed),
        "active_backtest_count": len([row for row in backtests if str(row.get("status", "")).lower() not in {"", "empty", "completed", "failed"}]),
        "official_call_policy": summary.get("official_call_policy") or {},
        "strategy_profile": summary.get("strategy_profile") or {},
        "convergence": summary.get("convergence") or {},
        "top_candidates": [_candidate_brief(row) for row in candidates[:10]],
        "pending_backtests": [_candidate_brief(row) for row in pending[:10]],
        "passed_candidates": [_candidate_brief(row) for row in passed[:10]],
        "backtest_slots": [_backtest_brief(row) for row in backtests[:10]],
        "backtest_records": [_backtest_record_brief(row) for row in backtest_records[:10]],
    }


def _cloud_context(snapshot: dict[str, Any] | None, *, top_n: int) -> dict[str, Any]:
    snapshot = snapshot or {}
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    rows = _first_list(snapshot.get("alphas"), snapshot.get("cloud_alphas"))
    return {
        "source": summary.get("source") or snapshot.get("source") or "empty",
        "count": summary.get("count", len(rows)),
        "submitted_count": summary.get("submitted_count", 0),
        "passed_unsubmitted_count": summary.get("passed_unsubmitted_count", 0),
        "failed_unsubmitted_count": summary.get("failed_unsubmitted_count", 0),
        "loaded_at": summary.get("loaded_at", ""),
        "age_seconds": summary.get("age_seconds"),
        "is_stale": bool(summary.get("is_stale") or summary.get("stale")),
        "sample_alphas": [_cloud_alpha_brief(row) for row in rows[:top_n]],
    }


def _memory_context(summary: dict[str, Any], guidance: dict[str, Any], *, top_n: int) -> dict[str, Any]:
    expression_index = summary.get("expression_index") if isinstance(summary.get("expression_index"), dict) else {}
    return {
        "source": summary.get("source") or guidance.get("source") or "local_jsonl_research_memory",
        "total_candidates": summary.get("total_candidates", 0),
        "guidance_sample_size": guidance.get("sample_size", 0),
        "status_counts": summary.get("status_counts") or {},
        "families": (summary.get("families") or [])[:top_n],
        "hypotheses": (summary.get("hypotheses") or [])[:top_n],
        "fields": (summary.get("fields") or [])[:top_n],
        "operators": (summary.get("operators") or [])[:top_n],
        "assistant_guided": summary.get("assistant_guided") or {},
        "assistant_guidance_outcomes": _guidance_outcomes(summary, top_n=top_n),
        "failure_patterns": (summary.get("failure_patterns") or [])[:top_n],
        "lineage": (summary.get("lineage") or [])[:top_n],
        "recommendations": summary.get("recommendations") or [],
        "expression_index": _expression_index_context(expression_index, top_n=top_n),
        "guidance": guidance,
    }


def _expression_index_context(value: Any, *, top_n: int) -> dict[str, Any]:
    index = value if isinstance(value, dict) else {}
    return {
        "schema_version": index.get("schema_version", "expression-index.v1"),
        "source": index.get("source", "local_jsonl_expression_index"),
        "total_expression_records": index.get("total_expression_records", 0),
        "unique_expression_count": index.get("unique_expression_count", 0),
        "duplicate_expression_count": index.get("duplicate_expression_count", 0),
        "source_counts": dict(index.get("source_counts") or {}),
        "duplicates": list(index.get("duplicates") or [])[:top_n],
        "frequent_expressions": list(index.get("frequent_expressions") or [])[:top_n],
        "fields": list(index.get("fields") or [])[:top_n],
        "operators": list(index.get("operators") or [])[:top_n],
        "windows": list(index.get("windows") or [])[:top_n],
    }


def _generation_focus(guidance: dict[str, Any], summary: dict[str, Any], *, top_n: int) -> dict[str, Any]:
    expression_index = summary.get("expression_index") if isinstance(summary.get("expression_index"), dict) else {}
    return {
        "fields": list(guidance.get("top_fields") or [])[:top_n],
        "operators": list(guidance.get("top_operators") or [])[:top_n],
        "windows": list(guidance.get("preferred_windows") or [])[:top_n],
        "field_combinations": list(guidance.get("field_combinations") or [])[:top_n],
        "families": list(guidance.get("top_categories") or [])[:top_n],
        "hypotheses": list(guidance.get("top_hypotheses") or [])[:top_n],
        "guidance_outcomes": _guidance_outcomes(summary, top_n=top_n),
        "failure_patterns": list(guidance.get("failure_patterns") or summary.get("failure_patterns") or [])[:top_n],
        "duplicate_expressions": list(expression_index.get("duplicates") or [])[:top_n],
        "recommendations": list(guidance.get("recommendations") or summary.get("recommendations") or []),
    }


def _risk_controls(config: RunConfig, cloud_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    cloud_snapshot = cloud_snapshot or {}
    cloud_summary = cloud_snapshot.get("summary") if isinstance(cloud_snapshot.get("summary"), dict) else {}
    return {
        "live_api_default_allowed": str(config.environment).lower() == "mock",
        "submit_requires_confirmation": True,
        "auto_submit_enabled": bool(config.auto_submit),
        "cloud_sync_required": bool(config.ops.budget.require_cloud_sync),
        "cloud_cache_stale": bool(cloud_snapshot.get("is_stale") or cloud_summary.get("is_stale") or cloud_summary.get("stale")),
        "max_expression_similarity": config.ops.submission_policy.max_expression_similarity,
        "block_micro_variants": bool(config.ops.submission_policy.block_micro_variants),
        "quality_thresholds": {
            "min_sharpe": config.ops.thresholds.min_sharpe,
            "min_fitness": config.ops.thresholds.min_fitness,
            "min_turnover": config.ops.thresholds.min_turnover,
            "platform_max_turnover": config.ops.thresholds.platform_max_turnover,
            "max_self_correlation": config.ops.thresholds.max_self_correlation,
        },
    }


def _compliance_context(config: RunConfig) -> dict[str, Any]:
    """Build lightweight redline + scoring health snapshot."""
    try:
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
        verifier = RedLineVerifier(config)
        report = verifier.verify_all()
        redline = {
            "ok": report.ok,
            "violations": len(report.violations),
            "summary": report.report()[:300],
        }
    except Exception:
        redline = {"ok": True, "violations": 0, "summary": "redline unavailable"}

    try:
        from brain_alpha_ops.scoring.official_scoring import ScoreHistoryDB
        db = ScoreHistoryDB(config.ops.storage_dir)
        stats = db.convergence_stats()
        scoring_health = stats
    except Exception:
        scoring_health = {"available": False}

    return {
        "redline": redline,
        "scoring_health": scoring_health,
        "thresholds_synced": True,
    }


def _next_actions(
    summary: dict[str, Any],
    guidance: dict[str, Any],
    latest: dict[str, Any] | None,
    cloud: dict[str, Any] | None,
) -> list[str]:
    actions: list[str] = []
    if guidance.get("top_fields") or guidance.get("top_operators"):
        actions.append(
            "Generate new candidates biased toward top memory fields/operators while preserving exploration diversity."
        )
    if guidance.get("preferred_windows"):
        actions.append("Use preferred lookback windows from memory before trying wider window mutations.")
    outcomes = _guidance_outcomes(summary, top_n=5)
    strong_outcome = _strong_guidance_outcome(outcomes)
    weak_outcome = _weak_guidance_outcome(outcomes)
    if strong_outcome:
        actions.append(
            "Iterate on assistant guidance digest "
            f"{strong_outcome.get('guidance_digest')} where recorded success_rate="
            f"{strong_outcome.get('success_rate')} and avg_score={strong_outcome.get('avg_score')}."
        )
    if weak_outcome:
        actions.append(
            "Treat assistant guidance digest "
            f"{weak_outcome.get('guidance_digest')} cautiously; recorded outcomes show success_rate="
            f"{weak_outcome.get('success_rate')} and avg_score={weak_outcome.get('avg_score')}."
        )
    failures = guidance.get("failure_patterns") or summary.get("failure_patterns") or []
    if failures:
        actions.append(f"Prioritize fixes for recurring failure pattern: {failures[0].get('reason', 'unknown')}.")
    cloud_snapshot = cloud or {}
    cloud_summary = cloud_snapshot.get("summary") if isinstance(cloud_snapshot.get("summary"), dict) else {}
    if bool(cloud_snapshot.get("is_stale") or cloud_summary.get("is_stale") or cloud_summary.get("stale")):
        actions.append("Refresh cloud alpha cache before submission or correlation-sensitive ranking.")
    latest_context = _latest_result_context(latest)
    if latest_context.get("pending_backtest_count"):
        actions.append("Wait for or poll pending backtests before overproducing near-duplicate variants.")
    if not actions:
        actions.append("Run a local production cycle to populate research memory before asking for high-confidence recommendations.")
    return actions


def _prompt_diagnostics(pack: dict[str, Any], *, top_n: int) -> dict[str, Any]:
    latest = pack.get("latest_result") if isinstance(pack.get("latest_result"), dict) else {}
    memory = pack.get("research_memory") if isinstance(pack.get("research_memory"), dict) else {}
    focus = pack.get("generation_focus") if isinstance(pack.get("generation_focus"), dict) else {}
    observability = pack.get("observability") if isinstance(pack.get("observability"), dict) else {}
    cloud = pack.get("cloud_alphas") if isinstance(pack.get("cloud_alphas"), dict) else {}
    guardrails = pack.get("risk_controls") if isinstance(pack.get("risk_controls"), dict) else {}
    duplicate_rows = list(focus.get("duplicate_expressions") or [])[:top_n]
    official_guard_blocked = int(observability.get("official_guard_blocked_count") or 0)
    risk_flags = _unique_text_items(
        list(observability.get("warning_flags") or [])
        + list(observability.get("blocking_flags") or [])
        + (["observability_official_call_guard_active"] if official_guard_blocked else [])
        + (["cloud_cache_stale"] if cloud.get("is_stale") or guardrails.get("cloud_cache_stale") else [])
        + (["pending_backtests"] if int(latest.get("pending_backtest_count") or 0) else [])
    )
    evidence = {
        "candidate_count": latest.get("candidate_count", 0),
        "memory_candidates": memory.get("total_candidates", 0),
        "guidance_sample_size": memory.get("guidance_sample_size", 0),
        "duplicate_expression_count": len(duplicate_rows),
        "observability_risk_level": observability.get("risk_level", "unknown"),
        "official_guard_blocked_count": official_guard_blocked,
        "risk_flags": risk_flags[:top_n],
        "fields": list(focus.get("fields") or [])[:top_n],
        "operators": list(focus.get("operators") or [])[:top_n],
        "windows": list(focus.get("windows") or [])[:top_n],
    }
    compact_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "schema_version": "assistant_prompt_diagnostics.v1",
        "estimated_context_tokens": max(1, len(compact_text) // 4),
        "candidate_count": evidence["candidate_count"],
        "memory_candidates": evidence["memory_candidates"],
        "guidance_sample_size": evidence["guidance_sample_size"],
        "duplicate_focus_count": len(duplicate_rows),
        "official_guard_blocked_count": official_guard_blocked,
        "risk_flags": risk_flags[:top_n],
        "evidence_digest": sha256(compact_text.encode("utf-8")).hexdigest()[:12],
    }


def _latest_result_from_storage(storage_dir: str) -> dict[str, Any]:
    latest_path = Path(storage_dir) / "run_history" / "latest.json"
    if not latest_path.is_file():
        return {"ok": True, "source": "empty", "status": "idle", "result": None, "progress": {}}
    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "source": "run_history", "error": str(exc), "result": None, "progress": {}}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "ok": True,
        "source": "run_history",
        "job_id": str(data.get("run_id") or latest_path.stem),
        "status": data.get("status") or "completed",
        "result": {
            "summary": summary,
            "candidates": summary.get("candidates") or data.get("candidates") or [],
        },
        "progress": {"phase": data.get("status") or "completed", "data": summary},
    }


def _cloud_snapshot_from_storage(storage_dir: str, *, top_n: int) -> dict[str, Any]:
    rows = _read_jsonl(Path(storage_dir) / "cloud_alphas.jsonl", limit=max(top_n, 1000))
    latest_by_id: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in rows:
        alpha_id = str(row.get("id") or row.get("alpha_id") or "")
        if alpha_id:
            latest_by_id[alpha_id] = row
        else:
            anonymous.append(row)
    deduped = list(latest_by_id.values()) + anonymous
    summary = {
        "source": "storage" if deduped else "empty",
        "count": len(deduped),
        "submitted_count": sum(1 for row in deduped if str(row.get("status", "")).upper() in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}),
        "passed_unsubmitted_count": sum(1 for row in deduped if _cloud_pass_fail(row) == "PASS" and str(row.get("status", "")).upper() not in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}),
        "failed_unsubmitted_count": sum(1 for row in deduped if _cloud_pass_fail(row) == "FAIL"),
        "is_stale": False,
    }
    return {"alphas": deduped[:top_n], "summary": summary}


def _read_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    return read_jsonl_tail(path, limit=limit)


def _candidate_brief(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _first_dict(row.get("official_metrics"), row.get("metrics"))
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return {
        "alpha_id": row.get("alpha_id") or row.get("id") or "",
        "official_alpha_id": row.get("official_alpha_id") or "",
        "family": row.get("family") or "",
        "hypothesis": row.get("hypothesis") or "",
        "expression": _expression_from_row(row),
        "fields": list(row.get("data_fields") or []),
        "operators": list(row.get("operators") or []),
        "score": scorecard.get("total_score", row.get("smart_rank_score", row.get("score", 0))),
        "lifecycle_status": row.get("lifecycle_status") or gate.get("status") or row.get("status") or "",
        "metrics": {
            key: metrics.get(key)
            for key in ("sharpe", "fitness", "turnover", "returns", "drawdown", "correlation", "pass_fail")
            if key in metrics
        },
    }


def _backtest_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": row.get("slot", ""),
        "alpha_id": row.get("alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "status": row.get("status", ""),
        "message": row.get("message", ""),
        "next_poll_seconds": row.get("next_poll_seconds"),
    }


def _backtest_record_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": row.get("action", ""),
        "slot": row.get("slot", ""),
        "alpha_id": row.get("alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "status": row.get("status", ""),
        "lifecycle_status": row.get("lifecycle_status", ""),
        "score": row.get("score", 0.0),
        "poll_count": row.get("poll_count", 0),
        "expression_fingerprint": row.get("expression_fingerprint", ""),
        "note": row.get("note", ""),
    }


def _cloud_alpha_brief(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _first_dict(row.get("metrics"), row.get("is"))
    return {
        "alpha_id": row.get("id") or row.get("alpha_id") or "",
        "status": row.get("status", ""),
        "expression": _expression_from_row(row),
        "pass_fail": metrics.get("pass_fail") or row.get("pass_fail") or "",
        "sharpe": metrics.get("sharpe", row.get("sharpe")),
        "fitness": metrics.get("fitness", row.get("fitness")),
        "turnover": metrics.get("turnover", row.get("turnover")),
    }


def _expression_from_row(row: dict[str, Any]) -> str:
    expression = row.get("expression")
    if isinstance(expression, dict):
        return str(expression.get("code") or "")
    if expression:
        return str(expression)
    regular = row.get("regular") if isinstance(row.get("regular"), dict) else {}
    return str(regular.get("code") or "")


def _cloud_pass_fail(row: dict[str, Any]) -> str:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return str(metrics.get("pass_fail") or row.get("pass_fail") or "").upper()


def _join_candidate_briefs(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:5]:
        parts.append(f"{row.get('alpha_id') or '-'} score={row.get('score', '-')} {row.get('family') or ''}".strip())
    return "; ".join(parts)


def _join_field_combinations(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    return "; ".join("+".join(row.get("fields") or []) for row in rows[:5])


def _join_failures(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    return "; ".join(f"{row.get('reason', '-') } x{row.get('count', 0)}" for row in rows[:5])


def _join_stat_bucket(row: dict[str, Any]) -> str:
    count = _int_value(row.get("count"))
    if not count:
        return "-"
    return (
        f"count={count} success={_float_value(row.get('success_rate'))} "
        f"avg_score={_float_value(row.get('avg_score'))}"
    )


def _join_guidance_outcomes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:5]:
        parts.append(
            f"{row.get('guidance_digest') or '-'} count={row.get('count', 0)} "
            f"success={row.get('success_rate', 0)} avg_score={row.get('avg_score', 0)}"
        )
    return "; ".join(parts)


def _join_duplicate_expressions(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:3]:
        expression = str(row.get("expression_canonical") or "")[:80]
        parts.append(f"{row.get('count', 0)}x {expression or row.get('expression_fingerprint', '-')}")
    return "; ".join(parts)


def _join_text_items(rows: list[Any]) -> str:
    items = [str(item).strip() for item in rows[:5] if str(item).strip()]
    return "; ".join(items) if items else "-"


def _unique_text_items(rows: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in rows:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _guidance_outcomes(summary: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    rows = summary.get("assistant_guidance_outcomes") if isinstance(summary, dict) else []
    if not isinstance(rows, list):
        return []
    outcomes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        digest = str(row.get("guidance_digest") or "").strip()
        if not digest:
            continue
        pass_fail = row.get("pass_fail") if isinstance(row.get("pass_fail"), dict) else {}
        outcomes.append({
            "guidance_digest": digest,
            "count": _int_value(row.get("count")),
            "success_count": _int_value(row.get("success_count")),
            "success_rate": _float_value(row.get("success_rate")),
            "avg_score": _float_value(row.get("avg_score")),
            "avg_sharpe": _float_value(row.get("avg_sharpe")),
            "avg_fitness": _float_value(row.get("avg_fitness")),
            "pass_fail": dict(pass_fail),
        })
    return outcomes[:top_n]


def _strong_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        if _int_value(row.get("count")) <= 0:
            continue
        if _float_value(row.get("success_rate")) >= 0.5 or _float_value(row.get("avg_score")) >= 70:
            return row
    return {}


def _weak_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        count = _int_value(row.get("count"))
        if count <= 0:
            continue
        success_rate = _float_value(row.get("success_rate"))
        avg_score = _float_value(row.get("avg_score"))
        if (count >= 2 and success_rate <= 0.25) or (success_rate == 0.0 and avg_score <= 50):
            return row
    return {}


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(number, 4)


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_list(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _dataclass_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}
