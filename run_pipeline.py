"""Editor-friendly entry point.

Run this file directly from VS Code/PyCharm. All runtime parameters are read
from config/run_config.json unless another JSON path is passed as argv[1].
"""

from __future__ import annotations

import json
import sys

from brain_alpha_ops.config import DEFAULT_RUN_CONFIG_PATH, load_run_config
from brain_alpha_ops.runner import run_pipeline_from_config


def _format_result(result) -> str:
    """Format pipeline result as a human-readable summary."""
    s = result.summary
    lines = []
    lines.append("=" * 56)
    lines.append("  BRAIN Alpha Ops — Production Summary")
    lines.append("=" * 56)

    # Run metadata
    lines.append(f"  Run ID      : {result.run_id}")
    lines.append(f"  Candidates  : {s.get('total_candidates', 0):>5} generated")
    lines.append(f"  Simulated   : {s.get('officially_simulated', 0):>5} via BRAIN API")
    lines.append(f"  Submitted   : {s.get('auto_submitted', 0):>5} auto-submitted")
    lines.append("")

    # User profile
    profile = s.get("user_profile") or {}
    if profile and profile.get("tier"):
        lines.append(f"  User        : {profile.get('tier', '-')} "
                      f"Lv.{profile.get('level', '-')}  "
                      f"{profile.get('points', '-')} pts")

    # Scoring distribution
    score_dist = s.get("score_distribution") or {}
    if score_dist:
        lines.append("")
        lines.append("  Score Distribution:")
        for band, count in score_dist.items():
            bar = "█" * min(count, 40)
            lines.append(f"    {band:<22} {count:>4} {bar}")

    # Gate summary
    gates = s.get("gate_summary") or {}
    if gates:
        lines.append("")
        lines.append("  Gate Results:")
        for gate_name, counts in gates.items():
            lines.append(f"    {gate_name:<22} pass={counts.get('pass',0)} "
                          f"fail={counts.get('fail',0)} "
                          f"block={counts.get('block',0)}")

    # Cloud sync
    cloud = s.get("cloud_sync") or {}
    if cloud:
        lines.append("")
        lines.append(f"  Cloud Sync  : {cloud.get('status', 'unknown')} "
                      f"({cloud.get('count', 0)} alphas)")

    # Convergence
    conv = s.get("convergence") or {}
    if conv:
        lines.append("")
        trend = conv.get("sharpe_trend", "stable")
        trend_icon = {"improving": "↑", "declining": "↓", "stable": "→"}.get(trend, "?")
        lines.append(f"  Convergence : {trend_icon} {trend}  "
                      f"avg_sharpe={conv.get('recent_avg_sharpe', 0):.3f}  "
                      f"stalled={conv.get('stalled', False)}")

    # Rejected summary
    rejected = s.get("rejected_stats") or {}
    if rejected:
        lines.append("")
        lines.append("  Rejected:")
        for reason, count in sorted(rejected.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"    {reason:<30} {count:>4}")

    lines.append("")
    lines.append("=" * 56)
    return "\n".join(lines)


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_CONFIG_PATH
    run_config = load_run_config(config_path)
    result = run_pipeline_from_config(run_config)
    # P2-8: Human-readable CLI output with structured summary
    try:
        print(_format_result(result))
    except Exception:
        # Fallback to JSON if formatting fails
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
