"""Console display helpers for the guided pipeline UX."""

from __future__ import annotations

from brain_alpha_ops.models import PipelineResult
from brain_alpha_ops.ux.guided_models import PipelinePhase


def print_progress(phases: dict[str, PipelinePhase]) -> None:
    """Print current progress to console."""
    total = len(phases)
    completed = sum(1 for phase in phases.values() if phase.status == "completed")

    bar_width = 40
    filled = int(bar_width * completed / total)
    bar = "=" * filled + "-" * (bar_width - filled)

    print(f"\n  Pipeline Progress: [{bar}] {completed}/{total} phases")
    for phase in phases.values():
        icon = {
            "completed": "[OK]",
            "running": "[..]",
            "failed": "[XX]",
            "pending": "[  ]",
            "skipped": "[--]",
        }.get(phase.status, "[??]")
        print(f"    {icon} {phase.description:<36} [{phase.status}]")
        if phase.errors:
            for err in phase.errors[:2]:
                print(f"       [W] {err}")


def print_summary(
    phases: dict[str, PipelinePhase],
    result: PipelineResult | None,
) -> None:
    """Print structured result summary."""
    if result is None:
        print("\n  No pipeline result is available yet.")
        return
    summary = result.summary
    print("\n" + "=" * 64)
    print("  BRAIN Alpha Ops — Guided Pipeline Summary")
    print("=" * 64)
    print(f"  Run ID        : {result.run_id}")
    print(f"  Candidates    : {summary.get('total_candidates', 0):>5} generated")
    print(f"  Simulated     : {summary.get('officially_simulated', 0):>5} via BRAIN API")
    print(f"  Submitted     : {summary.get('auto_submitted', 0):>5} auto-submitted")
    print("  Phase Status  :")

    for phase in phases.values():
        icon = {
            "completed": "[OK]",
            "failed": "[XX]",
            "running": "[..]",
            "pending": "[  ]",
        }.get(phase.status, "[??]")
        duration = f" ({phase.duration_seconds:.1f}s)" if phase.duration_seconds > 0 else ""
        print(f"    {icon} {phase.description:<36} {phase.status}{duration}")

    score_dist = summary.get("score_distribution") or {}
    if score_dist:
        print("\n  Score Distribution:")
        for band, count in score_dist.items():
            bar = "█" * min(count, 30)
            print(f"    {band:<22} {count:>4} {bar}")

    gates = summary.get("gate_summary") or {}
    if gates:
        print("\n  Gate Results:")
        for gate_name, counts in gates.items():
            print(f"    {gate_name:<22} pass={counts.get('pass', 0)} fail={counts.get('fail', 0)}")

    print("=" * 64)
