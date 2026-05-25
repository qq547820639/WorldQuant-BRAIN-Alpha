"""Editor-friendly pipeline entry point.

Run this file directly from VS Code/PyCharm. Runtime parameters are read from
config/run_config.json unless another JSON path is passed as argv[1].
"""

from __future__ import annotations

import json
import sys

from brain_alpha_ops.config import DEFAULT_RUN_CONFIG_PATH, load_run_config
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


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_CONFIG_PATH
    try:
        run_config = load_run_config(config_path)
    except FileNotFoundError as exc:
        _print_failure(
            f"Config file was not found: {config_path}",
            detail=exc,
            suggestions=[
                "Check the config path passed to run_pipeline.py.",
                "Create or restore config/run_config.json before running the pipeline.",
            ],
        )
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        _print_failure(
            f"Config file is invalid: {config_path}",
            detail=exc,
            suggestions=[
                "Fix the JSON/config validation error shown above.",
                "Run the config validation command from the CLI before starting production.",
            ],
        )
        return 1

    try:
        result = run_pipeline_from_config(run_config)
    except Exception as exc:
        _print_failure(
            "Pipeline run failed.",
            detail=exc,
            suggestions=[
                "Check BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN for production runs.",
                "Check network access and BRAIN API availability.",
                "Validate config/run_config.json before retrying.",
            ],
        )
        return 1

    try:
        print(_format_result(result))
    except Exception:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
