"""Report availability of gradual code-quality tooling.

This check is intentionally non-blocking by default so CI can surface ruff,
mypy, and pip-audit readiness before making them mandatory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Callable


DEFAULT_TOOLS = {
    "ruff": ["-m", "ruff", "--version"],
    "mypy": ["-m", "mypy", "--version"],
    "pip_audit": ["-m", "pip_audit", "--version"],
}

ToolRunner = Callable[[list[str]], tuple[int, str, str, float]]


def check_optional_tooling(*, strict: bool = False, runner: ToolRunner | None = None) -> dict:
    runner = runner or _run_tool
    tools = {}
    for name, args in DEFAULT_TOOLS.items():
        exit_code, stdout, stderr, duration = runner(args)
        available = exit_code == 0
        tools[name] = {
            "available": available,
            "status": "available" if available else "missing",
            "command": [sys.executable, *args],
            "exit_code": exit_code,
            "duration_seconds": round(duration, 3),
            "version": (stdout or stderr).strip().splitlines()[0] if (stdout or stderr).strip() else "",
        }
    missing = [name for name, row in tools.items() if not row["available"]]
    return {
        "ok": not missing or not strict,
        "schema_version": "optional_tooling.v1",
        "strict": bool(strict),
        "missing": missing,
        "tools": tools,
        "recommendation": (
            "Install project dev extras and enable strict mode once the checks are stable."
            if missing else
            "All optional tooling is available; CI can start enforcing selected checks."
        ),
    }


def _run_tool(args: list[str]) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            text=True,
            capture_output=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "tool check timed out", time.perf_counter() - started
    return proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check optional ruff/mypy/pip-audit tooling availability.")
    parser.add_argument("--strict", action="store_true", help="Fail when any optional tool is missing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_optional_tooling(strict=args.strict)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for name, row in result["tools"].items():
            status = "OK" if row["available"] else "SKIP"
            detail = row["version"] or "not installed"
            print(f"[{status}] {name}: {detail}")
        print(result["recommendation"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
