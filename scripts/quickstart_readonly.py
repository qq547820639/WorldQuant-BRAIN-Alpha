"""Read-only quickstart — starts the web server, tests connectivity, and runs a
single synthetic prefilter cycle with auto_submit disabled.  No real BRAIN
submissions are made."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

PROJECT_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("BRAIN_ALPHA_OPS_HOME", PROJECT_ROOT)


def _http_json(url: str, *, method: str = "GET", data: bytes | None = None, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main() -> int:
    print("=" * 60)
    print("  BRAIN Alpha Ops — Read-Only Quickstart")
    print("=" * 60)

    # ── Step 1: Start web server ────────────────────────────────────
    print("\n[1/4] Starting web server …")
    from brain_alpha_ops.web import serve, shutdown_server

    url = serve(open_browser=False)
    print(f"  Server running at {url}")
    time.sleep(0.5)

    # ── Step 2: Health check ────────────────────────────────────────
    print("\n[2/4] Health check …")
    try:
        health = _http_json(f"{url}/api/health")
        assert health.get("ok"), f"health check failed: {health}"
        print("  PASS — server is healthy")
    except Exception as exc:
        print(f"  FAIL — {exc}")
        shutdown_server()
        return 1

    # ── Step 3: Connection test (no credentials → expects graceful error) ─
    print("\n[3/4] Connection test (no real credentials) …")
    try:
        conn_result = _http_json(f"{url}/api/test_connection", method="POST", data=b"{}")
        status = conn_result.get("status", "unknown")
        print(f"  Result: {status} (expected: not_connected without credentials)")
    except Exception as exc:
        print(f"  Result: connection_test_unavailable — {exc}")

    # ── Step 4: Synthetic prefilter cycle (auto_submit=false) ───────
    print("\n[4/4] Synthetic prefilter cycle (auto_submit=false) …")
    try:
        cycle_payload = json.dumps({"auto_submit": False}).encode()
        cycle_result = _http_json(f"{url}/api/run_cycle", method="POST", data=cycle_payload)
        print(f"  Cycle result: {json.dumps(cycle_result, indent=2)[:500]}")
    except Exception as exc:
        print(f"  Cycle unavailable — {exc}")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Quickstart complete.  No real BRAIN submissions were made.")
    print("=" * 60)

    shutdown_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
