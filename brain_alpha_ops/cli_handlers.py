"""Command handlers for the brain-alpha-ops CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import os
from pathlib import Path
import sys

from brain_alpha_ops.config import (
    ConfigValidationError,
    load_run_config,
    validate_run_config,
    write_run_config,
)
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.llm_review import PromptRunLedger, cross_review_assistant_response
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.runner import run_pipeline_from_config


CommandHandler = Callable[[argparse.Namespace, argparse.ArgumentParser], int]


def run_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    handler = COMMAND_HANDLERS.get(str(args.command or ""))
    if handler is None:
        parser.print_help()
        return 2
    return handler(args, parser)


def _handle_init_config(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"config already exists: {path}")
        return 1
    written = write_run_config(load_run_config(None), path)
    print(f"wrote {written}")
    return 0


def _handle_validate_config(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    print(json.dumps({
        "ok": True,
        "schema_version": "config_validation.v1",
        "config": str(args.config),
        "environment": run_config.environment,
        "storage_dir": run_config.ops.storage_dir,
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_memory_summary(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    memory = ResearchMemory(run_config.ops.storage_dir)
    if args.write or args.output:
        written = memory.write_summary(args.output or None, limit=args.limit, top_n=args.top_n)
        print(str(written))
    else:
        print(json.dumps(memory.summary(limit=args.limit, top_n=args.top_n), ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_memory_guidance(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    memory = ResearchMemory(run_config.ops.storage_dir)
    payload = memory.generation_guidance(
        limit=args.limit,
        top_n=args.top_n,
        min_success_rate=args.min_success_rate,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_expression_index(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    if args.sqlite:
        sqlite_index = ExpressionSqliteIndex(run_config.ops.storage_dir)
        refresh = sqlite_index.refresh(limit=args.limit, include_cloud=not args.no_cloud)
        if str(args.expression or "").strip():
            payload = sqlite_index.lookup(
                args.expression,
                top_n=args.top_n,
                min_similarity=args.min_similarity,
            )
        else:
            payload = sqlite_index.summary(top_n=args.top_n)
        payload["refresh"] = refresh
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    index = ExpressionHistoryIndex(run_config.ops.storage_dir)
    if str(args.expression or "").strip():
        payload = index.lookup(
            args.expression,
            limit=args.limit,
            top_n=args.top_n,
            include_cloud=not args.no_cloud,
            min_similarity=args.min_similarity,
        )
    else:
        payload = index.summary(
            limit=args.limit,
            top_n=args.top_n,
            include_cloud=not args.no_cloud,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_record_index(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    record_index = RecordSqliteIndex(run_config.ops.storage_dir)
    refresh = record_index.refresh(limit=args.limit) if args.refresh else None
    if str(args.alpha_id or "").strip():
        payload = record_index.lookup_alpha(args.alpha_id, limit=args.limit)
    else:
        payload = record_index.summary()
    if refresh is not None:
        payload["refresh"] = refresh
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_research_observability(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    payload = build_research_observability_snapshot(
        run_config.ops.storage_dir,
        limit=args.limit,
        top_n=args.top_n,
        include_cloud=not args.no_cloud,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_context(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    payload = build_assistant_context_pack(
        run_config,
        limit=args.limit,
        top_n=args.top_n,
        include_prompt=not args.no_prompt or args.prompt_only,
        include_sensitive=bool(args.include_sensitive),
    )
    if args.prompt_only:
        print(payload.get("prompt", ""))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_request(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    context_pack = build_assistant_context_pack(
        run_config,
        limit=args.limit,
        top_n=args.top_n,
        include_prompt=True,
        include_sensitive=bool(args.include_sensitive),
    )
    payload = build_assistant_request_pack(
        context_pack,
        include_prompt=not args.no_prompt or args.prompt_only,
        include_offline_draft=not args.no_draft,
    )
    if args.prompt_only:
        print(payload.get("prompt", ""))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_parse(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    raw_output = sys.stdin.read() if args.input == "-" else _read_text_file(args.input)
    try:
        payload = parse_assistant_response(raw_output)
    except AssistantResponseParseError as exc:
        _print_payload(_cli_error_payload("ASSISTANT_RESPONSE_PARSE_ERROR", exc))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_guidance(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    raw_output = sys.stdin.read() if args.input == "-" else _read_text_file(args.input)
    try:
        response = parse_assistant_response(raw_output)
        payload = assistant_response_to_generation_guidance(
            response,
            min_confidence=args.min_confidence,
        )
    except AssistantResponseParseError as exc:
        _print_payload(_cli_error_payload("ASSISTANT_RESPONSE_PARSE_ERROR", exc))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_save_guidance(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    raw_output = sys.stdin.read() if args.input == "-" else _read_text_file(args.input)
    min_confidence = (
        args.min_confidence
        if args.min_confidence is not None
        else run_config.ops.budget.assistant_guidance_min_confidence
    )
    try:
        response = parse_assistant_response(raw_output)
        payload = assistant_response_to_generation_guidance(
            response,
            min_confidence=min_confidence,
        )
    except AssistantResponseParseError as exc:
        _print_payload(_cli_error_payload("ASSISTANT_RESPONSE_PARSE_ERROR", exc))
        return 1

    result = {
        "ok": True,
        "saved": False,
        "assistant_guidance": payload,
        "path": os.path.join(run_config.ops.storage_dir, "assistant_guidance.jsonl"),
    }
    if payload.get("ok") is False or payload.get("usable") is False:
        result["reason"] = payload.get("reason") or "confidence_below_threshold"
    elif not _guidance_has_generator_bias(payload):
        result["reason"] = "no_generator_bias"
    else:
        ResearchRepository(run_config.ops.storage_dir).save_assistant_guidance(
            payload,
            source=args.source,
        )
        result["saved"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_guidance_audit(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    payload = build_assistant_guidance_audit(
        run_config,
        limit=args.limit,
        min_confidence=args.min_confidence,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_anti_overfit(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    candidate = _load_json_argument(args.candidate_json)
    print(json.dumps(AntiOverfitService().evaluate(candidate), ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_rolling_validate(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    candidate = _load_json_argument(args.candidate_json)
    payload = RollingValidationService().evaluate(candidate, windows=args.windows)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_assistant_cross_review(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    run_config = load_run_config(args.config)
    request_pack = _load_json_argument(args.request_json)
    primary = _read_text_or_literal(args.primary_response)
    reviewer = _read_text_or_literal(args.reviewer_response) if args.reviewer_response else None
    try:
        payload = cross_review_assistant_response(
            request_pack,
            primary,
            reviewer_response=reviewer,
            min_confidence=args.min_confidence,
        )
    except AssistantResponseParseError as exc:
        _print_payload(_cli_error_payload("ASSISTANT_CROSS_REVIEW_PARSE_ERROR", exc))
        return 1
    if args.record_ledger:
        PromptRunLedger(run_config.ops.storage_dir).record(
            request_pack=request_pack,
            model="cli",
            response_text=primary,
            parse_status="cross_reviewed" if payload.get("ok") else "failed",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _handle_redline(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

    run_config = load_run_config(args.config)
    verifier = RedLineVerifier(run_config)
    if args.json:
        report = verifier.verify_all()
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
        return 1 if (args.block and not report.ok) else 0
    if args.block:
        verifier.verify_and_block()
        print("OK: all six technical red lines passed.")
    else:
        report = verifier.verify_all()
        print(report.report())
        if not report.ok:
            print(f"WARNING: {len(report.violations)} violation(s) found.")
    return 0


def _handle_release_gate(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from scripts.final_release_gate import run_final_release_gate

    report = run_final_release_gate(config_path=args.config)
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif report.passed:
        print(f"Final release gate passed. manifest_hash={report.manifest_hash}")
    else:
        print("Final release gate failed.")
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.code}: {finding.message}")
    return 0 if report.passed else 1


def _handle_score(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from brain_alpha_ops.models import Candidate
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

    candidate = Candidate.from_dict(_load_json_argument(args.candidate_json))
    run_config = load_run_config(args.config)
    system = OfficialScoringSystem(run_config.ops)
    result = system.evaluate(candidate)
    if args.attribution_only:
        print(result.attribution_report())
    elif args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print(result.attribution_report())
    return 0


def _handle_guided_run(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline

    run_config = load_run_config(args.config)
    if args.cycles is not None:
        run_config.ops.budget.max_cycles = args.cycles
    pipeline = GuidedPipeline(run_config)
    result = pipeline.resume() if args.resume else pipeline.run_guided()
    pipeline.print_summary(result)
    return 0


def _handle_diagnose(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from brain_alpha_ops.production_diagnostics import (
        build_diagnostic_snapshot,
        render_one_page_markdown,
        snapshot_to_json,
        write_diagnostic_report,
    )

    snapshot = build_diagnostic_snapshot(args.config)
    if args.output:
        write_diagnostic_report(args.output, snapshot)
    print(snapshot_to_json(snapshot) if args.json else render_one_page_markdown(snapshot))
    return 0 if snapshot.get("ok") else 1


def _handle_run(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from brain_alpha_ops import cli as cli_module

    run_config = load_run_config(args.config)
    if args.auto_submit is not None:
        run_config.auto_submit = args.auto_submit
    if args.candidates is not None:
        run_config.ops.budget.max_candidates_per_cycle = args.candidates
    if args.validations is not None:
        run_config.ops.budget.max_official_validations_per_cycle = args.validations
    if args.simulations is not None:
        run_config.ops.budget.max_official_simulations_per_cycle = args.simulations
    if args.cycles is not None:
        run_config.ops.budget.max_cycles = args.cycles
    if args.storage_dir is not None:
        run_config.ops.storage_dir = str(Path(args.storage_dir).resolve())
    if args.base_url is not None:
        from brain_alpha_ops.web_config import _ALLOWED_BASE_URLS

        base_url = str(args.base_url).rstrip("/")
        allowed = _ALLOWED_BASE_URLS.get(run_config.environment, set())
        if allowed and base_url not in allowed:
            raise ConfigValidationError(
                f"base-url not allowed for environment '{run_config.environment}'; "
                f"allowed: {sorted(allowed)}"
            )
        run_config.ops.official_api.base_url = base_url
    validate_run_config(run_config)
    result = cli_module.run_pipeline_from_config(run_config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "init-config": _handle_init_config,
    "validate-config": _handle_validate_config,
    "memory-summary": _handle_memory_summary,
    "memory-guidance": _handle_memory_guidance,
    "expression-index": _handle_expression_index,
    "record-index": _handle_record_index,
    "research-observability": _handle_research_observability,
    "assistant-context": _handle_assistant_context,
    "assistant-request": _handle_assistant_request,
    "assistant-parse": _handle_assistant_parse,
    "assistant-guidance": _handle_assistant_guidance,
    "assistant-save-guidance": _handle_assistant_save_guidance,
    "assistant-guidance-audit": _handle_assistant_guidance_audit,
    "anti-overfit": _handle_anti_overfit,
    "rolling-validate": _handle_rolling_validate,
    "assistant-cross-review": _handle_assistant_cross_review,
    "redline": _handle_redline,
    "release-gate": _handle_release_gate,
    "score": _handle_score,
    "guided-run": _handle_guided_run,
    "diagnose": _handle_diagnose,
    "run": _handle_run,
}


def _read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def _read_text_or_literal(value: str) -> str:
    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8-sig")
    return value


def _load_json_argument(value: str) -> dict:
    raw = _read_text_or_literal(value)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("expected JSON object", "<redacted>", 0)
    return data


def _print_cli_error(error_code: str, exc: Exception, *, config_path: str = "") -> None:
    _print_payload(_cli_error_payload(error_code, exc, config=config_path))


def _cli_error_payload(error_code: str, exc: Exception, **context) -> dict:
    return user_error_payload(exc, error_code=error_code, **context)


def _print_payload(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _guidance_has_generator_bias(guidance: dict) -> bool:
    return bool(
        guidance.get("top_fields")
        or guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
    )


def build_assistant_guidance_audit(
    run_config,
    *,
    limit: int = 100,
    min_confidence: float | None = None,
) -> dict:
    memory = ResearchMemory(run_config.ops.storage_dir)
    configured_min_confidence = _clamp_float(
        getattr(run_config.ops.budget, "assistant_guidance_min_confidence", 0.6),
        0.0,
        1.0,
    )
    threshold = configured_min_confidence if min_confidence is None else _clamp_float(min_confidence, 0.0, 1.0)
    latest = memory.latest_assistant_guidance(limit=limit, min_confidence=threshold)
    summary = memory.summary(limit=5000, top_n=max(10, int(limit or 10)))
    outcomes_by_guidance = {
        str(row.get("guidance_digest") or ""): row
        for row in summary.get("assistant_guidance_outcomes", [])
        if row.get("guidance_digest")
    }
    policy = assistant_guidance_scoring_policy(run_config.ops.scoring)
    latest_outcome = latest.get("historical_outcome") if isinstance(latest, dict) else {}
    return {
        "ok": True,
        "schema_version": "assistant_guidance_audit.v1",
        "source": "local_jsonl_cli",
        "storage_dir": run_config.ops.storage_dir,
        "enabled": bool(getattr(run_config.ops.budget, "use_assistant_guidance", True)),
        "configured_min_confidence": configured_min_confidence,
        "min_confidence": threshold,
        "scoring_policy": policy,
        "latest_guidance": latest,
        "latest_score_adjustment_eligibility": assistant_guidance_scoring_eligibility(
            latest,
            latest_outcome if isinstance(latest_outcome, dict) else {},
            policy,
        ),
        "outcomes": summary.get("assistant_guided", {}),
        "outcomes_by_guidance": summary.get("assistant_guidance_outcomes", []),
        "history": _assistant_guidance_audit_history(
            run_config.ops.storage_dir,
            limit=limit,
            min_confidence=threshold,
            scoring_policy=policy,
            outcomes_by_guidance=outcomes_by_guidance,
        ),
    }


def _assistant_guidance_audit_history(
    storage_dir: str,
    *,
    limit: int,
    min_confidence: float,
    scoring_policy: dict,
    outcomes_by_guidance: dict[str, dict],
) -> list[dict]:
    rows = _read_jsonl_tail(os.path.join(storage_dir, "assistant_guidance.jsonl"), limit=limit)
    history: list[dict] = []
    for index, row in enumerate(rows):
        guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else row
        if not isinstance(guidance, dict):
            continue
        guidance = ensure_assistant_guidance_digest(guidance)
        digest = str(row.get("guidance_digest") or guidance.get("guidance_digest") or "")
        guidance["guidance_digest"] = digest or guidance.get("guidance_digest")
        confidence = _confidence_float(guidance.get("confidence", 1.0))
        outcomes = outcomes_by_guidance.get(str(guidance.get("guidance_digest") or ""), {})
        eligibility = assistant_guidance_scoring_eligibility(guidance, outcomes, scoring_policy)
        history.append({
            "history_index": index,
            "timestamp": row.get("timestamp") or row.get("persisted_at") or "",
            "source": row.get("source") or guidance.get("source") or "assistant_guidance_jsonl",
            "guidance_digest": guidance.get("guidance_digest"),
            "usable": guidance.get("ok") is not False and _truthy(guidance.get("usable", True)),
            "meets_min_confidence": confidence >= min_confidence,
            "has_generator_bias": _guidance_has_generator_bias(guidance),
            "historical_outcome_status": assistant_guidance_outcome_status(outcomes),
            "score_adjustment_eligible": eligibility.get("eligible", False),
            "score_adjustment_reason": eligibility.get("reason", ""),
            "confidence": confidence,
            "top_fields": guidance.get("top_fields") if isinstance(guidance.get("top_fields"), list) else [],
            "top_operators": guidance.get("top_operators") if isinstance(guidance.get("top_operators"), list) else [],
            "preferred_windows": guidance.get("preferred_windows") if isinstance(guidance.get("preferred_windows"), list) else [],
            "outcomes": outcomes,
            "score_adjustment_eligibility": eligibility,
        })
    return list(reversed(history))


def _read_jsonl_tail(path: str, *, limit: int) -> list[dict]:
    return read_jsonl_tail(path, limit=limit)


def _confidence_float(value) -> float:
    number = _clamp_float(value, 0.0, 100.0)
    if number > 1.0:
        number = number / 100.0
    return _clamp_float(number, 0.0, 1.0)


def _clamp_float(value, lower: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return min(max(number, lower), upper)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)
