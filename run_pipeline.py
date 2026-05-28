"""Editor-friendly pipeline entry point.

Run this file directly from VS Code/PyCharm. Runtime parameters are read from
config/run_config.json unless another JSON path is passed as argv[1].
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brain_alpha_ops.config import DEFAULT_RUN_CONFIG_PATH, ConfigValidationError, load_run_config
from brain_alpha_ops.runner import run_pipeline_from_config


def _format_result(result) -> str:
    """Format pipeline result as a human-readable summary."""
    summary = getattr(result, "summary", {})
    if not isinstance(summary, dict):
        summary = {}

    lines = [
        "=" * 56,
        "  BRAIN Alpha Ops - Production Summary",
        "=" * 56,
        f"  Run ID      : {getattr(result, 'run_id', '-')}",
        f"  Candidates  : {summary.get('total_candidates', 0):>5} generated",
        f"  Simulated   : {summary.get('officially_simulated', 0):>5} via BRAIN API",
        f"  Submitted   : {summary.get('auto_submitted', 0):>5} auto-submitted",
        "",
    ]

    profile = summary.get("user_profile") or {}
    if isinstance(profile, dict) and profile.get("tier"):
        lines.append(
            f"  User        : {profile.get('tier', '-')} "
            f"Lv.{profile.get('level', '-')} {profile.get('points', '-')} pts"
        )

    score_dist = summary.get("score_distribution") or {}
    if isinstance(score_dist, dict) and score_dist:
        lines.extend(["", "  Score Distribution:"])
        for band, count in score_dist.items():
            count_int = int(count or 0)
            lines.append(f"    {band:<22} {count_int:>4} {'#' * min(count_int, 40)}")

    gates = summary.get("gate_summary") or {}
    if isinstance(gates, dict) and gates:
        lines.extend(["", "  Gate Results:"])
        for gate_name, counts in gates.items():
            counts = counts if isinstance(counts, dict) else {}
            lines.append(
                f"    {gate_name:<22} pass={counts.get('pass', 0)} "
                f"fail={counts.get('fail', 0)} block={counts.get('block', 0)}"
            )

    cloud = summary.get("cloud_sync") or {}
    if isinstance(cloud, dict) and cloud:
        lines.extend([
            "",
            f"  Cloud Sync  : {cloud.get('status', 'unknown')} ({cloud.get('count', 0)} alphas)",
        ])

    conv = summary.get("convergence") or {}
    if isinstance(conv, dict) and conv:
        trend = conv.get("sharpe_trend", "stable")
        trend_icon = {"improving": "up", "declining": "down", "stable": "flat"}.get(trend, "?")
        lines.extend([
            "",
            f"  Convergence : {trend_icon} {trend} "
            f"avg_sharpe={float(conv.get('recent_avg_sharpe', 0) or 0):.3f} "
            f"stalled={conv.get('stalled', False)}",
        ])

    rejected = summary.get("rejected_stats") or {}
    if isinstance(rejected, dict) and rejected:
        lines.extend(["", "  Rejected:"])
        for reason, count in sorted(rejected.items(), key=lambda item: -int(item[1] or 0))[:5]:
            lines.append(f"    {reason:<30} {int(count or 0):>4}")

    lines.extend(["", "=" * 56])
    return "\n".join(lines)


def _print_failure(message: str, *, detail: Exception | str = "", suggestions: list[str] | None = None) -> None:
    print(f"ERROR: {message}")
    if detail:
        print(f"Detail: {detail}")
    for index, suggestion in enumerate(suggestions or [], start=1):
        print(f"Next {index}: {suggestion}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or validate the BRAIN Alpha Ops production pipeline config.",
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        help="backward-compatible JSON config path; defaults to config/run_config.json",
    )
    parser.add_argument(
        "--config",
        dest="config_option",
        default=None,
        help="JSON config path; preferred over the positional compatibility argument",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="load and validate the config without starting the production pipeline",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print machine-readable JSON for validation results or pipeline output",
    )
    return parser


def _resolve_config_path(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Path | str:
    if args.config_path and args.config_option:
        parser.error("pass either positional config_path or --config, not both")
    return args.config_option or args.config_path or DEFAULT_RUN_CONFIG_PATH


def _print_json_payload(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _print_error(
    message: str,
    *,
    detail: Exception | str = "",
    suggestions: list[str] | None = None,
    json_output: bool = False,
    config_path: Path | str | None = None,
) -> None:
    if json_output:
        _print_json_payload({
            "ok": False,
            "error": message,
            "detail": str(detail) if detail else "",
            "suggestions": suggestions or [],
            "config": str(config_path or ""),
        })
        return
    _print_failure(message, detail=detail, suggestions=suggestions)


def _result_to_dict(result) -> dict:
    if hasattr(result, "to_dict"):
        data = result.to_dict()
        if isinstance(data, dict):
            return data
    summary = getattr(result, "summary", {})
    return {
        "ok": True,
        "run_id": getattr(result, "run_id", ""),
        "summary": summary if isinstance(summary, dict) else {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    config_path = _resolve_config_path(args, parser)
    try:
        run_config = load_run_config(config_path)
    except FileNotFoundError as exc:
        _print_error(
            f"Config file was not found: {config_path}",
            detail=exc,
            suggestions=[
                "Check the config path passed to run_pipeline.py.",
                "Create or restore config/run_config.json before running the pipeline.",
            ],
            json_output=args.json_output,
            config_path=config_path,
        )
        return 1
    except (json.JSONDecodeError, ConfigValidationError, ValueError) as exc:
        _print_error(
            f"Config file is invalid: {config_path}",
            detail=exc,
            suggestions=[
                "Fix the JSON/config validation error shown above.",
                "Run the config validation command from the CLI before starting production.",
            ],
            json_output=args.json_output,
            config_path=config_path,
        )
        return 1

    if args.validate_only:
        payload = {
            "ok": True,
            "schema_version": "run_pipeline_entrypoint.v1",
            "mode": "validate-only",
            "config": str(config_path),
            "environment": run_config.environment,
            "storage_dir": run_config.ops.storage_dir,
        }
        if args.json_output:
            _print_json_payload(payload)
        else:
            print(f"Config valid: {config_path}")
        return 0

    try:
        result = run_pipeline_from_config(run_config)
    except Exception as exc:
        _print_error(
            "Pipeline run failed.",
            detail=exc,
            suggestions=[
                "Check BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN for production runs.",
                "Check network access and BRAIN API availability.",
                "Validate config/run_config.json before retrying.",
            ],
            json_output=args.json_output,
            config_path=config_path,
        )
        return 1

    try:
        if args.json_output:
            _print_json_payload(_result_to_dict(result))
        else:
            print(_format_result(result))
    except Exception:
        _print_json_payload(_result_to_dict(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
