"""Argument parser construction for the brain-alpha-ops CLI."""

from __future__ import annotations

import argparse

from brain_alpha_ops.config import DEFAULT_RUN_CONFIG_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain-alpha-ops")
    sub = parser.add_subparsers(dest="command")
    _add_run_parser(sub)
    _add_config_parsers(sub)
    _add_memory_parsers(sub)
    _add_index_parsers(sub)
    _add_assistant_parsers(sub)
    _add_validation_parsers(sub)
    _add_release_parsers(sub)
    return parser


def _add_run_parser(sub: argparse._SubParsersAction) -> None:
    run = sub.add_parser("run", help="run the research pipeline")
    run.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    run.add_argument("--cycles", type=int, default=None)
    run.add_argument("--candidates", type=int, default=None)
    run.add_argument("--validations", type=int, default=None)
    run.add_argument("--simulations", type=int, default=None)
    auto = run.add_mutually_exclusive_group()
    auto.add_argument("--auto-submit", dest="auto_submit", action="store_true", default=None)
    auto.add_argument("--no-auto-submit", dest="auto_submit", action="store_false")
    run.add_argument("--storage-dir", default=None)
    run.add_argument("--base-url", default=None)

    guided = sub.add_parser("guided-run", help="run the research pipeline with guided UX (checkpoints, progress, redline)")
    guided.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    guided.add_argument("--cycles", type=int, default=None)
    guided.add_argument("--resume", action="store_true", help="resume from the latest checkpoint")


def _add_config_parsers(sub: argparse._SubParsersAction) -> None:
    init = sub.add_parser("init-config", help="write a default JSON run config")
    init.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    init.add_argument("--force", action="store_true")

    validate = sub.add_parser("validate-config", help="validate a JSON run config")
    validate.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))


def _add_memory_parsers(sub: argparse._SubParsersAction) -> None:
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


def _add_index_parsers(sub: argparse._SubParsersAction) -> None:
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


def _add_assistant_parsers(sub: argparse._SubParsersAction) -> None:
    context = sub.add_parser("assistant-context", help="emit an LLM-ready assistant context pack")
    context.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    context.add_argument("--limit", type=int, default=5000)
    context.add_argument("--top-n", type=int, default=10)
    context.add_argument("--prompt-only", action="store_true", help="print only the rendered text prompt")
    context.add_argument("--no-prompt", action="store_true", help="omit the rendered text prompt from JSON output")
    context.add_argument("--include-sensitive", action="store_true", help="include local paths and other sensitive context fields")

    request = sub.add_parser("assistant-request", help="emit a provider-neutral LLM request envelope")
    request.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    request.add_argument("--limit", type=int, default=5000)
    request.add_argument("--top-n", type=int, default=10)
    request.add_argument("--prompt-only", action="store_true", help="print only the user prompt")
    request.add_argument("--no-prompt", action="store_true", help="omit the top-level prompt from JSON output")
    request.add_argument("--no-draft", action="store_true", help="omit the deterministic offline response draft")
    request.add_argument("--include-sensitive", action="store_true", help="include local paths and other sensitive context fields")

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

    cross = sub.add_parser("assistant-cross-review", help="cross-review a primary assistant response against a request pack")
    cross.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    cross.add_argument("--request-json", required=True, help="assistant request JSON text or path")
    cross.add_argument("--primary-response", required=True, help="primary assistant response text or path")
    cross.add_argument("--reviewer-response", default="", help="optional reviewer response text or path")
    cross.add_argument("--min-confidence", type=float, default=0.6)
    cross.add_argument("--record-ledger", action="store_true", help="append prompt run metadata to prompt_runs.jsonl")


def _add_validation_parsers(sub: argparse._SubParsersAction) -> None:
    anti_overfit = sub.add_parser("anti-overfit", help="run deterministic anti-overfit checks for a candidate JSON")
    anti_overfit.add_argument("--candidate-json", required=True, help="candidate JSON text or path to a JSON file")

    rolling = sub.add_parser("rolling-validate", help="run rolling validation checks for a candidate JSON")
    rolling.add_argument("--candidate-json", required=True, help="candidate JSON text or path to a JSON file")
    rolling.add_argument("--windows", type=int, default=4)

    score = sub.add_parser("score", help="evaluate a candidate alpha via the full scoring pipeline")
    score.add_argument("--candidate-json", required=True, help="candidate JSON text or path to a JSON file")
    score.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    score.add_argument("--json", action="store_true", help="print machine-readable JSON")
    score.add_argument("--attribution-only", action="store_true", help="print only the attribution tree")


def _add_release_parsers(sub: argparse._SubParsersAction) -> None:
    redline = sub.add_parser("redline", help="verify six technical red lines compliance (aggregate quality gate step)")
    redline.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    redline.add_argument("--block", action="store_true", help="exit with code 1 on violations")
    redline.add_argument("--json", action="store_true", help="print machine-readable JSON")

    release_gate = sub.add_parser("release-gate", help="run fail-closed final release readiness checks")
    release_gate.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    release_gate.add_argument("--json", action="store_true", help="print machine-readable JSON")

    diagnose = sub.add_parser("diagnose", help="build production diagnosis, gap matrix, and upgrade plan")
    diagnose.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH))
    diagnose.add_argument("--json", action="store_true", help="print machine-readable JSON")
    diagnose.add_argument("--output", default="", help="optional Markdown report output path")
