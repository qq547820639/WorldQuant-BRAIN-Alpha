"""Launch BrainAlphaProd.exe and monitor output."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parent
EXE_PATH = ROOT / "dist" / "BrainAlphaProd.exe"
LOG_PATH = ROOT / "data" / "prod_monitor.log"

# Legacy whitelist retained for backward compatibility with tests/external
# callers.  sanitized_child_env() now uses a blacklist
# (DANGEROUS_CHILD_ENV_KEYS + SENSITIVE_CHILD_ENV_KEYS) so that BRAIN_*
# business env vars and BRAIN_ALPHA_OPS_* vars are preserved.
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

# Credentials that must never be passed to the child process.
SENSITIVE_CHILD_ENV_KEYS = {
    "BRAIN_ALPHA_FORCE_REAL_SUBMIT",
    "BRAIN_ALPHA_OPS_ADMIN_TOKEN",
    "BRAIN_PASSWORD",
    "BRAIN_TOKEN",
    "BRAIN_USERNAME",
}

# Dangerous system env vars that may leak secrets or break the frozen child.
# Used as a blacklist: anything NOT here (and not in SENSITIVE_CHILD_ENV_KEYS)
# is passed through, preserving BRAIN_* business env and BRAIN_ALPHA_OPS_*.
DANGEROUS_CHILD_ENV_KEYS = {
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_CLIENT_SECRET",
    "CI_TOKEN",
    "DATABASE_URL",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "HISTFILE",
    "JWT_SECRET",
    "PGPASSWORD",
    "PG_PASSWORD",
    "PIP_INDEX_URL",
    "PIP_USER",
    "PYTHONHOME",
    "PYTHONPATH",
    "REDIS_URL",
    "SECRET_KEY",
    "SLACK_TOKEN",
}


def sanitized_child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return a child-process env dict with dangerous/sensitive keys stripped.

    Uses a blacklist approach so that BRAIN_* business env vars and
    BRAIN_ALPHA_OPS_* vars (except those in SENSITIVE_CHILD_ENV_KEYS) are
    preserved and forwarded to the child process.
    """
    source = os.environ if source is None else source
    stripped = SENSITIVE_CHILD_ENV_KEYS | DANGEROUS_CHILD_ENV_KEYS
    return {
        key: value
        for key, value in source.items()
        if key not in stripped
    }


# Phrases containing "error" or "failed" that are NOT actual errors.
_ERROR_FALSE_POSITIVES = (
    "no_error",
    "no_errors",
    "0 errors",
    "0 error",
    "error_count=0",
    "error_count = 0",
    "errors=0",
    "errors = 0",
    "no failed",
    "no_failed",
    "0 failed",
    "0 failures",
)

# Structured text completion markers (replaces loose `\bDONE\b` word match).
_COMPLETION_TEXT_MARKERS = (
    "run_completed",
    "pipeline_done",
    "pipeline_completed",
)
_COMPLETION_EVENT_VALUES = frozenset(
    {"pipeline_done", "pipeline_completed", "run_completed", "completed", "done"}
)


def _is_completion_marker(line: str) -> bool:
    """Return True if *line* is a structured pipeline-completion marker."""
    stripped = line.strip()
    if not stripped:
        return False
    lower = stripped.lower()
    for marker in _COMPLETION_TEXT_MARKERS:
        if marker in lower:
            return True
    # JSON line with an `event` or `status` field indicating completion.
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return False
        if isinstance(payload, dict):
            event = str(payload.get("event", "")).lower()
            if event in _COMPLETION_EVENT_VALUES:
                return True
            status = str(payload.get("status", "")).lower()
            if status in _COMPLETION_EVENT_VALUES:
                return True
    return False


def _is_error_line(line: str) -> bool:
    """Return True if *line* indicates a genuine error/failure."""
    lower = line.lower()
    if not re.search(r"\b(failed|error)\b", lower):
        return False
    for phrase in _ERROR_FALSE_POSITIVES:
        if phrase in lower:
            return False
    return True


def _reader_thread(stream, out_queue: "queue.Queue[str | None]") -> None:
    """Read lines from *stream* and push them to *out_queue*.

    Pushes ``None`` on EOF so the consumer can distinguish EOF from a
    temporary lack of output.  Portable alternative to ``select.select``
    on pipes (which does not work on Windows).  Daemon thread so it never
    blocks process exit.
    """
    try:
        for line in iter(stream.readline, ""):
            out_queue.put(line)
    finally:
        out_queue.put(None)


# Kill child if no output for this many seconds.
IDLE_TIMEOUT_SECONDS = 60.0
# Poll interval for the output queue.
_POLL_INTERVAL_SECONDS = 1.0


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("[MONITOR] Skipped — launch monitor is Windows-only (BrainAlphaProd.exe).")
        return 0
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
        last_output = time.time()
        line_count = 0

        assert proc.stdout is not None
        out_queue: "queue.Queue[str | None]" = queue.Queue()
        reader = threading.Thread(
            target=_reader_thread,
            args=(proc.stdout, out_queue),
            daemon=True,
        )
        reader.start()

        try:
            while True:
                try:
                    item = out_queue.get(timeout=_POLL_INTERVAL_SECONDS)
                except queue.Empty:
                    # No output this interval — check for hang or child exit.
                    if proc.poll() is not None:
                        # Child exited; drain any remaining queued lines.
                        while True:
                            try:
                                remaining = out_queue.get_nowait()
                            except queue.Empty:
                                break
                            if remaining is None:
                                break
                            line_count += 1
                            log.write(remaining)
                            log.flush()
                            if _is_completion_marker(remaining):
                                print("[MONITOR] PIPELINE COMPLETED!")
                            elif _is_error_line(remaining):
                                print(f"[MONITOR] ALERT: {remaining.rstrip()[:150]}")
                        break
                    if time.time() - last_output > IDLE_TIMEOUT_SECONDS:
                        print(
                            f"[MONITOR] ALERT: no output for "
                            f"{IDLE_TIMEOUT_SECONDS:.0f}s, killing child..."
                        )
                        proc.kill()
                        break
                    continue

                if item is None:
                    # EOF from child stdout
                    break

                last_output = time.time()
                line_count += 1
                log.write(item)
                log.flush()

                now = time.time()
                if now - last_report > 10:
                    print(f"[MONITOR] Running... {line_count} lines, last: {item.rstrip()[:100]}")
                    last_report = now

                if _is_completion_marker(item):
                    print("[MONITOR] PIPELINE COMPLETED!")
                    break
                if _is_error_line(item):
                    print(f"[MONITOR] ALERT: {item.rstrip()[:150]}")
        except KeyboardInterrupt:
            print("[MONITOR] Interrupted. Terminating...")
            proc.terminate()
            reader.join(timeout=2.0)

        # Ensure child is reaped.
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=2.0)

        print(f"[MONITOR] Exit code: {proc.returncode}")
        print(f"[MONITOR] Total lines: {line_count}")
        print(f"[MONITOR] Full log: {LOG_PATH}")
        return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
