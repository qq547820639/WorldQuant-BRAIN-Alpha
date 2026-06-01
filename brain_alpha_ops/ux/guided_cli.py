"""CLI adapter for the guided pipeline UX."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.ux.guided_formatting import format_error_for_user
from brain_alpha_ops.ux.guided_models import PipelinePhase


def main(
    *,
    pipeline_cls: type,
    phase_cls: type[PipelinePhase] = PipelinePhase,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="guided-pipeline",
        description="BRAIN Alpha Ops 引导式流水线 (含流程引导/实时反馈/断点续跑)",
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--history", action="store_true", help="查看运行历史")
    parser.add_argument("--show", type=str, default=None, help="查看指定 run_id 的详情")
    parser.add_argument("--checkpoints", action="store_true", help="查看断点列表")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    run_config = load_run_config(args.config)
    gp = pipeline_cls(run_config)

    if args.history:
        print("\n  Run History:")
        print("  " + "-" * 60)
        for record in gp.list_history()[:10]:
            print(f"  {record['run_id']}  [{record['status']}]  "
                  f"candidates={record['candidates']}  "
                  f"submissions={record['submissions']}")
        return 0

    if args.show:
        data = gp.show_run(args.show)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Run '{args.show}' not found.")
        return 0 if data else 1

    if args.checkpoints:
        checkpoints = gp.list_checkpoints()
        print(f"\n  Checkpoints ({len(checkpoints)}):")
        for cp in checkpoints[:10]:
            print(f"  {cp['run_id']}  phase={cp['phase']}  "
                  f"candidates={cp['candidates']}  time={cp['timestamp'][:19]}")
        return 0

    def progress_handler(phase_id: str, status: str, data: dict[str, Any]) -> None:
        if status == "running":
            desc = gp.phases.get(phase_id, phase_cls(name=phase_id, description=phase_id)).description
            print(f"  [..] {desc}...")
        elif status == "completed":
            print(f"  [OK] Phase complete: {phase_id}")
        elif status == "failed":
            print(f"  [XX] Phase failed: {phase_id} -- {data.get('message', '')[:80]}")
        elif status == "progress":
            msg = data.get("message", "")
            if msg:
                print(f"       {msg[:100]}")

    gp.on_progress(progress_handler)

    try:
        result = gp.run_guided()
        gp.print_summary(result)
        return 0
    except Exception as exc:
        print(format_error_for_user(exc))
        return 1
