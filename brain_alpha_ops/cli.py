"""Command line entry point for BRAIN Alpha Ops."""

from __future__ import annotations

import argparse
import json
import os
import sys

from brain_alpha_ops.config import (
    DEFAULT_RUN_CONFIG_PATH,
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
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.llm_review import (
    PromptRunLedger,
    cross_review_assistant_response,
)
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.runner import run_pipeline_from_config


_CRED_DEPRECATION = (
    "WARNING: command-line credentials are deprecated because they can leak through shell history and process lists.\n"
    "Use BRAIN_USERNAME / BRAIN_PASSWORD / BRAIN_TOKEN environment variables instead."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain-alpha-ops")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run the research pipeline")
    run.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    run.add_argument("--env", choices=["mock", "production"], default=None)
    run.add_argument("--cycles", type=int, default=None)
    run.add_argument("--candidates", type=int, default=None)
    run.add_argument("--validations", type=int, default=None)
    run.add_argument("--simulations", type=int, default=None)
    auto = run.add_mutually_exclusive_group()
    auto.add_argument("--auto-submit", dest="auto_submit", action="store_true", default=None)
    auto.add_argument("--no-auto-submit", dest="auto_submit", action="store_false")
    run.add_argument("--storage-dir", default=None)
    run.add_argument("--base-url", default=None)
    run.add_argument(
        "--username", default=None,
        help="[弃用] 凭据请使用环境变量 BRAIN_USERNAME，此参数会暴露在 shell 历史中",
    )
    run.add_argument(
        "--password", default=None,
        help="[弃用] 凭据请使用环境变量 BRAIN_PASSWORD，此参数会暴露在 shell 历史中",
    )
    run.add_argument(
        "--token", default=None,
        help="[弃用] 凭据请使用环境变量 BRAIN_TOKEN，此参数会暴露在 shell 历史中",
    )

    init = sub.add_parser("init-config", help="write a default JSON run config")
    init.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    init.add_argument("--force", action="store_true")

    validate = sub.add_parser("validate-config", help="validate a JSON run config")
    validate.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))

    memory = sub.add_parser("memory-summary", help="summarize local research memory")
    memory.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    memory.add_argument("--output", default="")
    memory.add_argument("--limit", type=int, default=5000)
    memory.add_argument("--top-n", type=int, default=10)
    memory.add_argument("--write", action="store_true", help="write research_memory_summary.json and print its path")

    guidance = sub.add_parser("memory-guidance", help="emit generator-ready research memory guidance")
    guidance.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    guidance.add_argument("--limit", type=int, default=5000)
    guidance.add_argument("--top-n", type=int, default=10)
    guidance.add_argument("--min-success-rate", type=float, default=0.0)

    expression_index = sub.add_parser("expression-index", help="summarize or query persisted FASTEXPR expression history")
    expression_index.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    expression_index.add_argument("--limit", type=int, default=5000)
    expression_index.add_argument("--top-n", type=int, default=10)
    expression_index.add_argument("--expression", default="", help="optional expression to look up by canonical fingerprint")
    expression_index.add_argument("--min-similarity", type=float, default=0.75)
    expression_index.add_argument("--no-cloud", action="store_true", help="exclude cloud_alphas.jsonl from the index")
    expression_index.add_argument("--sqlite", action="store_true", help="refresh and query the optional SQLite expression index cache")

    record_index = sub.add_parser("record-index", help="summarize or query cloud alpha/backtest SQLite record index")
    record_index.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    record_index.add_argument("--limit", type=int, default=10000)
    record_index.add_argument("--alpha-id", default="", help="lookup by alpha_id, official_alpha_id, or simulation_id")
    record_index.add_argument("--refresh", action="store_true", help="rebuild the SQLite record index from JSONL audit logs")

    observability = sub.add_parser("research-observability", help="summarize local research health, backtests, errors, and JSONL status")
    observability.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    observability.add_argument("--limit", type=int, default=5000)
    observability.add_argument("--top-n", type=int, default=10)
    observability.add_argument("--no-cloud", action="store_true", help="exclude cloud_alphas.jsonl from expression-index health")

    context = sub.add_parser("assistant-context", help="emit an LLM-ready assistant context pack")
    context.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    context.add_argument("--limit", type=int, default=5000)
    context.add_argument("--top-n", type=int, default=10)
    context.add_argument("--prompt-only", action="store_true", help="print only the rendered text prompt")
    context.add_argument("--no-prompt", action="store_true", help="omit the rendered text prompt from JSON output")

    request = sub.add_parser("assistant-request", help="emit a provider-neutral LLM request envelope")
    request.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    request.add_argument("--limit", type=int, default=5000)
    request.add_argument("--top-n", type=int, default=10)
    request.add_argument("--prompt-only", action="store_true", help="print only the user prompt")
    request.add_argument("--no-prompt", action="store_true", help="omit the top-level prompt from JSON output")
    request.add_argument("--no-draft", action="store_true", help="omit the deterministic offline response draft")

    parse = sub.add_parser("assistant-parse", help="parse and normalize an assistant model JSON response")
    parse.add_argument("--input", default="-", help="response file path, or '-' for stdin")

    guidance_parse = sub.add_parser("assistant-guidance", help="convert an assistant response into generator-ready guidance")
    guidance_parse.add_argument("--input", default="-", help="response file path, or '-' for stdin")
    guidance_parse.add_argument("--min-confidence", type=float, default=0.0)

    guidance_save = sub.add_parser("assistant-save-guidance", help="convert and persist an assistant response as reusable guidance")
    guidance_save.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    guidance_save.add_argument("--input", default="-", help="response file path, or '-' for stdin")
    guidance_save.add_argument("--min-confidence", type=float, default=None)
    guidance_save.add_argument("--source", default="cli_save_assistant_guidance")

    guidance_audit = sub.add_parser("assistant-guidance-audit", help="audit saved assistant guidance reuse and scoring eligibility")
    guidance_audit.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    guidance_audit.add_argument("--limit", type=int, default=100)
    guidance_audit.add_argument("--min-confidence", type=float, default=None)

    anti_overfit = sub.add_parser("anti-overfit", help="run deterministic anti-overfit checks for a candidate JSON")
    anti_overfit.add_argument("--candidate-json", required=True, help="candidate JSON text or path to a JSON file")

    rolling = sub.add_parser("rolling-validate", help="run rolling validation checks for a candidate JSON")
    rolling.add_argument("--candidate-json", required=True, help="candidate JSON text or path to a JSON file")
    rolling.add_argument("--windows", type=int, default=4)

    cross = sub.add_parser("assistant-cross-review", help="cross-review a primary assistant response against a request pack")
    cross.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    cross.add_argument("--request-json", required=True, help="assistant request JSON text or path")
    cross.add_argument("--primary-response", required=True, help="primary assistant response text or path")
    cross.add_argument("--reviewer-response", default="", help="optional reviewer response text or path")
    cross.add_argument("--min-confidence", type=float, default=0.6)
    cross.add_argument("--record-ledger", action="store_true", help="append prompt run metadata to prompt_runs.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _main(args, parser)
    except ConfigValidationError as exc:
        _print_cli_error("CONFIG_VALIDATION_ERROR", exc, config_path=getattr(args, "config", ""))
        return 1
    except json.JSONDecodeError as exc:
        _print_cli_error("CONFIG_JSON_ERROR", exc, config_path=getattr(args, "config", ""))
        return 1


def _main(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "init-config":
        from pathlib import Path

        path = Path(args.config)
        if path.exists() and not args.force:
            print(f"config already exists: {path}")
            return 1
        written = write_run_config(load_run_config(None), path)
        print(f"wrote {written}")
        return 0

    if args.command == "validate-config":
        run_config = load_run_config(args.config)
        print(json.dumps({
            "ok": True,
            "schema_version": "config_validation.v1",
            "config": str(args.config),
            "environment": run_config.environment,
            "storage_dir": run_config.ops.storage_dir,
        }, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "memory-summary":
        run_config = load_run_config(args.config)
        memory = ResearchMemory(run_config.ops.storage_dir)
        if args.write or args.output:
            written = memory.write_summary(args.output or None, limit=args.limit, top_n=args.top_n)
            print(str(written))
        else:
            print(json.dumps(memory.summary(limit=args.limit, top_n=args.top_n), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "memory-guidance":
        run_config = load_run_config(args.config)
        memory = ResearchMemory(run_config.ops.storage_dir)
        payload = memory.generation_guidance(
            limit=args.limit,
            top_n=args.top_n,
            min_success_rate=args.min_success_rate,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "expression-index":
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

    if args.command == "record-index":
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

    if args.command == "research-observability":
        run_config = load_run_config(args.config)
        payload = build_research_observability_snapshot(
            run_config.ops.storage_dir,
            limit=args.limit,
            top_n=args.top_n,
            include_cloud=not args.no_cloud,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "assistant-context":
        run_config = load_run_config(args.config)
        payload = build_assistant_context_pack(
            run_config,
            limit=args.limit,
            top_n=args.top_n,
            include_prompt=not args.no_prompt or args.prompt_only,
        )
        if args.prompt_only:
            print(payload.get("prompt", ""))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "assistant-request":
        run_config = load_run_config(args.config)
        context_pack = build_assistant_context_pack(
            run_config,
            limit=args.limit,
            top_n=args.top_n,
            include_prompt=True,
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

    if args.command == "assistant-parse":
        raw_output = sys.stdin.read() if args.input == "-" else _read_text_file(args.input)
        try:
            payload = parse_assistant_response(raw_output)
        except AssistantResponseParseError as exc:
            _print_payload(_cli_error_payload("ASSISTANT_RESPONSE_PARSE_ERROR", exc))
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "assistant-guidance":
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

    if args.command == "assistant-save-guidance":
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

    if args.command == "assistant-guidance-audit":
        run_config = load_run_config(args.config)
        payload = build_assistant_guidance_audit(
            run_config,
            limit=args.limit,
            min_confidence=args.min_confidence,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "anti-overfit":
        candidate = _load_json_argument(args.candidate_json)
        print(json.dumps(AntiOverfitService().evaluate(candidate), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "rolling-validate":
        candidate = _load_json_argument(args.candidate_json)
        payload = RollingValidationService().evaluate(candidate, windows=args.windows)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "assistant-cross-review":
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

    if args.command != "run":
        parser.print_help()
        return 2

    run_config = load_run_config(args.config)
    if args.env is not None:
        run_config.environment = args.env
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
        run_config.ops.storage_dir = args.storage_dir
    if args.base_url is not None:
        run_config.ops.official_api.base_url = args.base_url
    if _has_cli_credentials(args) and str(run_config.environment).lower() == "production":
        raise ConfigValidationError(
            "command-line credentials are disabled in production; "
            "use BRAIN_USERNAME / BRAIN_PASSWORD / BRAIN_TOKEN environment variables"
        )
    if args.username is not None:
        print(_CRED_DEPRECATION, file=sys.stderr)
        run_config.credentials.username = args.username
    if args.password is not None:
        print(_CRED_DEPRECATION, file=sys.stderr)
        run_config.credentials.password = args.password
    if args.token is not None:
        print(_CRED_DEPRECATION, file=sys.stderr)
        run_config.credentials.token = args.token

    validate_run_config(run_config)
    result = run_pipeline_from_config(run_config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def _has_cli_credentials(args: argparse.Namespace) -> bool:
    return any(getattr(args, name, None) is not None for name in ("username", "password", "token"))


def _read_text_file(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")


def _read_text_or_literal(value: str) -> str:
    from pathlib import Path

    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def _load_json_argument(value: str) -> dict:
    raw = _read_text_or_literal(value)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("expected JSON object", raw, 0)
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
