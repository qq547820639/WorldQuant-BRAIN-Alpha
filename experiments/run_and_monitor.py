"""End-to-end automated experiment pipeline.
Launch → monitor (2min init + 10min heartbeat) → analyze on completion.

Supports two modes:
    --mode basic    Original: simple progress tracking (backward compat)
    --mode r5       Round 5: full-dimensional monitoring (default)

Single entry point for the full BRAIN Alpha experiment lifecycle.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path


_EXPERIMENT_DIR = Path(__file__).resolve().parent


def run_pipeline_basic(candidate_count: int = 100):
    """Original basic monitor (legacy compat)."""
    from experiments.run_and_monitor import run_pipeline as _legacy_run
    _legacy_run(candidate_count)


def run_pipeline_r5(candidate_count: int = 100):
    """Round 5 full-dimensional monitor."""
    from experiments.monitor_round5 import Round5Monitor
    monitor = Round5Monitor(candidate_count=candidate_count)
    return monitor.run()


def run_pipeline(candidate_count: int = 100, mode: str = "r5"):
    """Unified entry point with mode selection."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if mode == "basic":
        run_pipeline_basic(candidate_count)
        return

    # Default: Round 5 monitor
    print(f"\n{'='*64}")
    print(f"  Round 5 实验 · 完整监控模式")
    print(f"  候选数: {candidate_count}  |  启动时间: {ts}")
    print(f"{'='*64}\n")

    return run_pipeline_r5(candidate_count)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="End-to-end experiment pipeline")
    p.add_argument("--candidates", type=int, default=100)
    p.add_argument("--mode", choices=["basic", "r5"], default="r5")
    args = p.parse_args()
    run_pipeline(args.candidates, args.mode)
