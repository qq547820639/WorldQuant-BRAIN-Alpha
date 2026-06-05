"""Launch BrainAlphaProd.exe and monitor output."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
EXE_PATH = ROOT / "dist" / "BrainAlphaProd.exe"
LOG_PATH = ROOT / "data" / "prod_monitor.log"

SAFE_CHILD_ENV_KEYS = {
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "PATHEXT",
    "PYTHONIOENCODING",
    "PYTHONNOUSERSITE",
    "PYTHONUTF8",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "USERNAME",
    "VIRTUAL_ENV",
    "WINDIR",
}
SENSITIVE_CHILD_ENV_KEYS = {
    "BRAIN_USERNAME",
    "BRAIN_PASSWORD",
    "BRAIN_TOKEN",
    "BRAIN_ALPHA_OPS_ADMIN_TOKEN",
}


def sanitized_child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source is None else source
    return {
        key: value
        for key, value in source.items()
        if key in SAFE_CHILD_ENV_KEYS and key not in SENSITIVE_CHILD_ENV_KEYS
    }


def main(argv: list[str] | None = None) -> int:
    _argv = argv or []
    if _argv:
        print(f"[MONITOR] ERROR: unsupported arguments: {' '.join(_argv)}")
        return 2

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"[MONITOR] Launching: {EXE_PATH}")
    print(f"[MONITOR] Log: {LOG_PATH}")

    with LOG_PATH.open("w", encoding="utf-8") as log:
        log.write("=== BRAIN Alpha Production Run ===\n")
        log.write(f"=== Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
        log.flush()

        proc = subprocess.Popen(
            [str(EXE_PATH)],
            env=sanitized_child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )

        print(f"[MONITOR] PID: {proc.pid}")
        last_report = time.time()
        line_count = 0

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line_count += 1
                log.write(line)
                log.flush()

                now = time.time()
                if now - last_report > 10:
                    print(f"[MONITOR] Running... {line_count} lines, last: {line.rstrip()[:100]}")
                    last_report = now

                if "DONE" in line or "run_completed" in line.lower():
                    print("[MONITOR] PIPELINE COMPLETED!")
                    break
                if "FAILED" in line or "error" in line.lower():
                    print(f"[MONITOR] ALERT: {line.rstrip()[:150]}")
        except KeyboardInterrupt:
            print("[MONITOR] Interrupted. Terminating...")
            proc.terminate()

        proc.wait()
        print(f"[MONITOR] Exit code: {proc.returncode}")
        print(f"[MONITOR] Total lines: {line_count}")
        print(f"[MONITOR] Full log: {LOG_PATH}")
        return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
