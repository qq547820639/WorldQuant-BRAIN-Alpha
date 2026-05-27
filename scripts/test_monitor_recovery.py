#!/usr/bin/env python
"""
Automated Test Monitor & Recovery — solves frequent unexpected test interruptions.

Features:
  1. Real-time stdout/stderr streaming with heartbeat-based hang detection
  2. Automatic safe-kill sequence: SIGINT (Ctrl+C) → SIGTERM → SIGKILL
  3. Auto-retry failed/hung test cases with configurable max retries
  4. Detailed diagnostic report (cause, timestamp, stack trace, retry log)

Usage:
  py scripts/test_monitor_recovery.py [TARGET] [OPTIONS]

Examples:
  # Monitor a single test file
  py scripts/test_monitor_recovery.py tests/qa_full_chain_backend.py

  # Monitor with custom timeout and retries
  py scripts/test_monitor_recovery.py tests/qa_e2e_new_user_walkthrough.py -t 180 -r 2

  # Run individual tests from a file
  py scripts/test_monitor_recovery.py tests/qa_full_chain_frontend.py --collect-only
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

# ── Windows-specific signal handling ───────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    # Windows doesn't have SIGALRM; we use threading.Timer instead
    SIGALRM_AVAILABLE = False
else:
    import signal as _signal
    SIGALRM_AVAILABLE = True


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    """Single test case execution result."""
    test_id: str
    status: str = "pending"  # pending | running | passed | failed | hung | killed | error
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_message: str = ""
    stack_trace: str = ""
    retry_count: int = 0
    kill_signal: str = ""  # INT, TERM, KILL, or ""
    last_heartbeat: float = 0.0
    hang_detected: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def failed(self) -> bool:
        return self.status in ("failed", "hung", "killed", "error")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start_time_iso"] = datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat()
        d["end_time_iso"] = datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None
        return d


@dataclass
class SessionReport:
    """Full monitoring session report."""
    target: str = ""
    started_at: str = ""
    finished_at: str = ""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    hung: int = 0
    killed: int = 0
    retried: int = 0
    total_retries: int = 0
    total_duration: float = 0.0
    max_retries_per_test: int = 3
    per_test_timeout: int = 120
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append(f"  TEST MONITOR REPORT — {self.target}")
        lines.append(f"  Started:  {self.started_at}")
        lines.append(f"  Finished: {self.finished_at}")
        lines.append(f"  Duration: {self.total_duration:.1f}s")
        lines.append("-" * 70)
        lines.append(f"  Total:   {self.total_tests}")
        lines.append(f"  Passed:  {self.passed}")
        lines.append(f"  Failed:  {self.failed}")
        lines.append(f"  Hung:    {self.hung}")
        lines.append(f"  Killed:  {self.killed}")
        lines.append(f"  Retried: {self.retried} tests ({self.total_retries} total retries)")
        lines.append("-" * 70)
        if self.failed > 0:
            lines.append("  FAILURE DETAILS:")
            for r in self.results:
                if r.get("status") in ("failed", "hung", "killed", "error"):
                    lines.append(f"    [{r['status'].upper()}] {r['test_id']}")
                    if r.get("error_message"):
                        lines.append(f"           {r['error_message'][:120]}")
                    if r.get("kill_signal"):
                        lines.append(f"           kill signal: {r['kill_signal']}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Test Discovery
# ═══════════════════════════════════════════════════════════════════════════


def discover_tests(target: str) -> list[str]:
    """Discover test cases in a pytest target file."""
    # If target is a specific test (contains ::), return it directly
    if "::" in target:
        return [target]

    filepath = Path(target)
    if not filepath.exists():
        print(f"[!] Target not found: {target}")
        return [target]  # Let pytest handle the error

    # Ask pytest to list test IDs (quietly)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(filepath), "--collect-only", "-q", "--no-header", "-p", "no:warnings", "-p", "no:cacheprovider"],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        lines = result.stdout.strip().split("\n")
        # Filter: keep lines that look like test IDs (contain "::")
        test_ids = [l.strip() for l in lines if "::" in l and not l.startswith("=")]
        if test_ids:
            print(f"[*] Discovered {len(test_ids)} test cases in {target}")
            return test_ids
    except subprocess.TimeoutExpired:
        print(f"[!] Test discovery timed out, running as single batch")
    except Exception as e:
        print(f"[!] Test discovery failed: {e}")

    # Fallback: run the whole file as one batch
    return [target]


# ═══════════════════════════════════════════════════════════════════════════
# Process Execution with Heartbeat
# ═══════════════════════════════════════════════════════════════════════════


def _stream_reader(stream, output_list: list, lock: threading.Lock):
    """Read lines from a stream in a background thread."""
    try:
        for line in iter(stream.readline, ""):
            with lock:
                output_list.append(line)
    except Exception:
        pass


def run_test_with_watchdog(
    test_id: str,
    timeout: int = 120,
    collect_output: bool = True,
) -> tuple[subprocess.Popen, threading.Thread, threading.Thread, list, list, list]:
    """
    Launch a test as subprocess with stdout/stderr streaming threads.
    Returns (process, stdout_thread, stderr_thread, stdout_lines, stderr_lines, heartbeat_times).
    """
    project_root = str(Path(__file__).resolve().parents[1])
    env = os.environ.copy()
    env["BRAIN_ALPHA_OPS_HOME"] = project_root
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        sys.executable, "-m", "pytest", test_id,
        "-v", "--tb=long", "--no-header",
        "-p", "no:warnings", "-p", "no:cacheprovider",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=project_root,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    heartbeat_times: list[float] = []
    lock = threading.Lock()

    # Capture stdout with heartbeat tracking
    def stdout_reader():
        try:
            for line in iter(proc.stdout.readline, ""):
                with lock:
                    stdout_lines.append(line)
                    heartbeat_times.append(time.time())
        except Exception:
            pass

    def stderr_reader():
        try:
            for line in iter(proc.stderr.readline, ""):
                with lock:
                    stderr_lines.append(line)
        except Exception:
            pass

    t_stdout = threading.Thread(target=stdout_reader, daemon=True)
    t_stderr = threading.Thread(target=stderr_reader, daemon=True)
    t_stdout.start()
    t_stderr.start()

    return proc, t_stdout, t_stderr, stdout_lines, stderr_lines, heartbeat_times


def kill_process_tree(proc: subprocess.Popen, signal_name: str) -> bool:
    """Attempt to kill a process. Returns True if killed, False if already dead."""
    if proc.poll() is not None:
        return False  # Already exited

    try:
        if IS_WINDOWS:
            # Windows: CTRL_BREAK_EVENT for graceful, TerminateProcess for force
            if signal_name == "INT":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.kill()  # SIGTERM equivalent on Windows
        else:
            sig = getattr(signal, f"SIG{signal_name}", signal.SIGTERM)
            proc.send_signal(sig)
        return True
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


def safe_shutdown_server():
    """Attempt to cleanly shut down any lingering web server."""
    try:
        from brain_alpha_ops import web
        web.shutdown_server()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Core Monitor Logic
# ═══════════════════════════════════════════════════════════════════════════


def execute_test_with_recovery(
    test_id: str,
    timeout: int = 120,
    max_retries: int = 3,
    hang_threshold: float = 30.0,
) -> TestResult:
    """
    Execute a single test with hang detection, kill sequence, and auto-retry.

    Kill escalation (with 3s cooldown between each):
      1. SIGINT (CTRL_BREAK on Windows) — asks test to gracefully stop
      2. SIGTERM — force terminate
      3. SIGKILL — immediate kill
    """
    result = TestResult(test_id=test_id)
    result.retry_count = 0

    for attempt in range(1, max_retries + 1):
        result.retry_count = attempt
        result.start_time = time.time()

        print(f"  [{attempt}/{max_retries}] Running: {test_id.split('::')[-1] if '::' in test_id else test_id}")

        # Clean slate
        safe_shutdown_server()
        time.sleep(0.3)

        proc, t_out, t_err, stdout_lines, stderr_lines, heartbeats = run_test_with_watchdog(
            test_id, timeout=timeout
        )

        result.last_heartbeat = time.time()
        hang_count = 0
        escalated = False

        # Watchdog loop
        while proc.poll() is None:
            elapsed = time.time() - result.start_time

            # Check heartbeat (output received recently?)
            if heartbeats:
                result.last_heartbeat = max(heartbeats)
            time_since_heartbeat = time.time() - result.last_heartbeat

            # Hang detection
            if time_since_heartbeat > hang_threshold:
                hang_count += 1
                if not result.hang_detected:
                    result.hang_detected = True
                    print(f"    [!] Hang detected: no output for {time_since_heartbeat:.0f}s")
                    # Dump current output for diagnosis
                    with threading.Lock():
                        tail = "".join(stdout_lines[-5:]) + "".join(stderr_lines[-5:])
                    if tail.strip():
                        print(f"    [!] Last output:\n{tail[:300]}")

            # Timeout exceeded → kill sequence
            if elapsed > timeout:
                if not escalated:
                    print(f"    [!] Timeout ({elapsed:.0f}s > {timeout}s), sending INT...")
                    kill_process_tree(proc, "INT")
                    escalated = True
                elif elapsed > timeout + 5:
                    print(f"    [!] INT failed, sending TERM...")
                    kill_process_tree(proc, "TERM")
                    result.kill_signal = "TERM"
                elif elapsed > timeout + 10:
                    print(f"    [!] TERM failed, sending KILL...")
                    kill_process_tree(proc, "KILL")
                    result.kill_signal = "KILL"

            time.sleep(0.5)

        # Test completed (or killed)
        t_out.join(timeout=1)
        t_err.join(timeout=1)
        safe_shutdown_server()

        result.end_time = time.time()
        result.duration = result.end_time - result.start_time
        result.return_code = proc.returncode
        result.stdout = "".join(stdout_lines[-200:])  # Keep last 200 lines
        result.stderr = "".join(stderr_lines[-100:])

        # Determine status
        if proc.returncode == 0:
            result.status = "passed"
            print(f"    [PASS] {result.duration:.1f}s")
            break
        elif proc.returncode is None or result.kill_signal == "KILL":
            result.status = "killed"
            result.error_message = f"Killed after {result.duration:.0f}s (signal: {result.kill_signal})"
            print(f"    [KILL] attempt {attempt} failed, {'retrying...' if attempt < max_retries else 'giving up'}")
        elif result.hang_detected:
            result.status = "hung"
            result.error_message = f"Hung for >{hang_threshold}s, killed after {result.duration:.0f}s"
            print(f"    [HUNG] attempt {attempt} failed, {'retrying...' if attempt < max_retries else 'giving up'}")
        else:
            # Parse error from output
            result.status = "failed"
            error_lines = [l for l in result.stdout.split("\n") + result.stderr.split("\n")
                          if "Error" in l or "FAIL" in l or "Traceback" in l]
            result.error_message = "\n".join(error_lines[:5]) if error_lines else f"Exit code {proc.returncode}"
            print(f"    [FAIL] attempt {attempt} failed, {'retrying...' if attempt < max_retries else 'giving up'}")

    # After all retries, extract stack trace if failed
    if result.failed:
        result.stack_trace = _extract_stack(result.stdout + result.stderr)

    return result


def _extract_stack(output: str) -> str:
    """Extract the most relevant stack trace from test output."""
    lines = output.split("\n")
    trace_lines = []
    in_trace = False
    for line in lines:
        if "Traceback (most recent call last)" in line:
            in_trace = True
            trace_lines = [line]
        elif in_trace:
            trace_lines.append(line)
            if not line.startswith(" ") and not line.startswith("\t") and "Error" not in line:
                if len(trace_lines) > 1:
                    break
    return "\n".join(trace_lines[-30:]) if trace_lines else ""


# ═══════════════════════════════════════════════════════════════════════════
# Session Runner
# ═══════════════════════════════════════════════════════════════════════════


def run_session(
    target: str,
    timeout: int = 120,
    max_retries: int = 3,
    report_path: str | None = None,
) -> SessionReport:
    """
    Run a complete monitoring session for a test target.
    Returns a SessionReport with all results.
    """
    project_root = str(Path(__file__).resolve().parents[1])
    os.environ["BRAIN_ALPHA_OPS_HOME"] = project_root

    report = SessionReport(
        target=target,
        started_at=datetime.now(timezone.utc).isoformat(),
        per_test_timeout=timeout,
        max_retries_per_test=max_retries,
    )

    print(f"\n{'='*70}")
    print(f"  TEST MONITOR & RECOVERY")
    print(f"  Target:     {target}")
    print(f"  Timeout:    {timeout}s per test")
    print(f"  Max Retry:  {max_retries}")
    print(f"{'='*70}\n")

    # Discover tests
    test_ids = discover_tests(target)
    report.total_tests = len(test_ids)
    print(f"\n[*] {len(test_ids)} test(s) to execute\n")

    session_start = time.time()

    for i, test_id in enumerate(test_ids, 1):
        print(f"\n{'─'*50}")
        print(f"  [{i}/{len(test_ids)}] {test_id}")
        print(f"{'─'*50}")

        result = execute_test_with_recovery(test_id, timeout=timeout, max_retries=max_retries)
        report.results.append(result.to_dict())

        if result.passed:
            report.passed += 1
        else:
            report.failed += 1
            if result.status == "hung":
                report.hung += 1
            elif result.status == "killed":
                report.killed += 1

        if result.retry_count > 1:
            report.retried += 1
            report.total_retries += result.retry_count - 1

    report.total_duration = time.time() - session_start
    report.finished_at = datetime.now(timezone.utc).isoformat()

    # Print summary
    print(f"\n{report.summary()}")

    # Save report
    if report_path is None:
        report_path = str(Path(project_root) / "data" / "monitor_report.json")
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[*] Report saved: {report_path}")

    return report


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Automated test monitor with hang detection, safe-kill, and auto-retry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py scripts/test_monitor_recovery.py tests/qa_full_chain_backend.py
  py scripts/test_monitor_recovery.py tests/qa_e2e_new_user_walkthrough.py -t 180 -r 2
  py scripts/test_monitor_recovery.py tests/qa_full_chain_frontend.py --collect-only
        """,
    )
    parser.add_argument("target", help="Test file or specific test (file::TestClass::test_name)")
    parser.add_argument("-t", "--timeout", type=int, default=120, help="Per-test timeout in seconds (default: 120)")
    parser.add_argument("-r", "--max-retries", type=int, default=3, help="Max retries per test (default: 3)")
    parser.add_argument("-o", "--output", help="Report output path (default: data/monitor_report.json)")
    parser.add_argument("--collect-only", action="store_true", help="Only discover and list tests, don't run")
    args = parser.parse_args()

    if args.collect_only:
        test_ids = discover_tests(args.target)
        print(f"\nDiscovered {len(test_ids)} test(s):")
        for tid in test_ids:
            print(f"  {tid}")
        return 0

    report = run_session(
        target=args.target,
        timeout=args.timeout,
        max_retries=args.max_retries,
        report_path=args.output,
    )

    return 1 if report.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
