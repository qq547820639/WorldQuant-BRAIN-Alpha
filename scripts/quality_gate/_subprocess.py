"""Subprocess execution helpers for the quality_gate subpackage.

Split from the former ``scripts/quality_gate.py`` monolith (Task A5).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Callable

from ._constants import (
    DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    ROOT,
    SUBPROCESS_ENV_ALLOWLIST,
)


StepRunner = Callable[[], tuple[bool, dict]]


def _subprocess_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in SUBPROCESS_ENV_ALLOWLIST}
    local_deps = ROOT / ".codex_pydeps"
    pycache_prefix = ROOT / ".pytest_cache_runtime" / "pycache"
    pycache_prefix.mkdir(parents=True, exist_ok=True)
    python_paths: list[str] = []
    if local_deps.exists():
        python_paths.append(str(local_deps))
    existing = env.get("PYTHONPATH", "")
    if existing:
        python_paths.append(existing)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env.setdefault("PYTHONUTF8", "1")
    env["PYTHONPYCACHEPREFIX"] = str(pycache_prefix)
    return env


def _run_python_module(
    args: list[str],
    *,
    timeout_seconds: int | float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> tuple[bool, dict]:
    started = time.perf_counter()
    command = [sys.executable, *args]
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=_subprocess_env(),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started, 3)
        stdout = _timeout_text(exc.stdout)
        stderr = _timeout_text(exc.stderr, f"command timed out after {timeout_seconds}s")
        return False, {
            "command": command,
            "exit_code": 124,
            "duration_seconds": duration,
            "timeout_seconds": timeout_seconds,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }
    return proc.returncode == 0, {
        "command": command,
        "exit_code": proc.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "timeout_seconds": timeout_seconds,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _timeout_text(value: str | bytes | None, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
