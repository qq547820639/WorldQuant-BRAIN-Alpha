from __future__ import annotations

"""Probe for optional development tooling (ruff / mypy / pip_audit).

These tools are optional rather than hard requirements: the quality gate
reports their availability but does not block on them unless ``--strict`` is
passed.  A ``runner`` callable may be injected for tests; it receives a command
argument list and returns ``(exit_code, stdout, stderr, duration_seconds)``.
"""

import argparse
import json
import subprocess
import sys
import time

TOOLS = ("ruff", "mypy", "pip_audit")


def _default_runner(args: list[str]) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - started
    except FileNotFoundError:
        return 1, "", "not found", time.perf_counter() - started


def check_optional_tooling(*, strict: bool = False, runner=None) -> dict[str, object]:
    runner = runner or _default_runner
    tools: dict[str, object] = {}
    missing: list[str] = []
    for name in TOOLS:
        code, stdout, stderr, _duration = runner([name, "--version"])
        if code == 0:
            tools[name] = {"status": "found", "version": (stdout or stderr).strip()}
        else:
            tools[name] = {"status": "missing", "error": (stderr or stdout).strip()}
            missing.append(name)
    ok = not (strict and missing)
    return {"ok": ok, "missing": missing, "tools": tools}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe for optional development tooling.")
    parser.add_argument("--strict", action="store_true", help="Fail when any optional tool is missing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_optional_tooling(strict=args.strict)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"optional tooling {status}: missing={result['missing']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())