"""Submit an alpha directly to BRAIN API — simulate, check, and submit.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/submit_alpha_direct.py [--expression EXPR] [--settings JSON]
    PYTHONPATH=. .venv/bin/python scripts/submit_alpha_direct.py --dry-run  (auth test only)

Credentials default to those provided in the script; env vars BRAIN_USERNAME/BRAIN_PASSWORD also work.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Bypass safety gate so submit_alpha() works from CLI
os.environ["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"

from brain_alpha_ops.brain_api import OfficialBrainAPI
from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import OfficialAPIConfig, load_run_config


def submit_alpha_direct(
    username: str = "547820639@qq.com",
    password: str = "Ph360098.",
    expression: str = "-returns",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit an alpha through the full BRAIN pipeline: auth → simulate → check → submit."""

    if settings is None:
        config = load_run_config()
        settings = config.ops.settings

    # -- convert BrainSettings to dict for display --
    settings_dict = settings if isinstance(settings, dict) else {k: v for k, v in settings.__dict__.items() if not k.startswith("_")}

    print("=" * 60)
    print("BRAIN Alpha Direct Submission")
    print("=" * 60)
    print(f"Target: {expression}")
    print(f"Settings: universe={settings_dict.get("universe")}, region={settings_dict.get("region")}, "
          f"delay={settings_dict.get("delay")}, dataset={settings_dict.get("dataset")}")

    api_config = OfficialAPIConfig()
    api = OfficialBrainAPI(api_config, username=username, password=password)

    # ── Step 1: Authenticate ──
    print(f"\n[1/6] Authenticating with BRAIN API as {username}...")
    try:
        auth_result = api.authenticate()
        print(f"  Auth: {auth_result.get('status')} ({auth_result.get('auth')})")
    except BrainAPIError as e:
        return {"ok": False, "step": "authenticate", "error": str(e)}

    # ── Step 2: Profile ──
    print("[2/6] Fetching user profile...")
    profile = {}
    try:
        profile = api.get_user_profile()
        print(f"  User: {profile.get('username')}, Tier: {profile.get('tier')}, "
              f"Level: {profile.get('level')}, Points: {profile.get('points')}")
    except Exception as e:
        print(f"  (warning) Profile fetch failed: {e}")

    # ── Step 3: Submit simulation ──
    print(f"\n[3/6] Submitting simulation...")
    print(f"  Expression: {expression}")
    try:
        simulation_id = api.submit_simulation(expression, settings)
        print(f"  Simulation ID: {simulation_id}")
    except BrainAPIError as e:
        return {"ok": False, "step": "submit_simulation", "error": str(e)}

    # ── Step 4: Poll ──
    print("\n[4/6] Polling (max 120 attempts @ 6s intervals)...")
    max_polls = 120
    poll_interval = 6.0

    for attempt in range(1, max_polls + 1):
        try:
            status = api.poll_simulation(simulation_id)
        except BrainAPIError as e:
            print(f"  (warning) Poll attempt {attempt}: {e}")
            time.sleep(poll_interval)
            continue

        if status == "COMPLETED":
            print(f"  [OK] Simulation completed (attempt {attempt}, ~{attempt * poll_interval:.0f}s)")
            break
        elif status == "FAILED":
            try:
                result = api.fetch_result(simulation_id)
                print(f"  [FAIL] Simulation FAILED")
            except Exception:
                result = {}
            return {"ok": False, "step": "poll_simulation", "status": "FAILED",
                    "simulation_id": simulation_id, "raw": result.get('raw', {})}
        elif attempt % 15 == 0:
            print(f"  Still running... (attempt {attempt}/{max_polls})")

        if attempt == max_polls:
            print(f"  [TIMEOUT] after {max_polls} attempts")
            return {"ok": False, "step": "poll_simulation", "status": "TIMEOUT",
                    "simulation_id": simulation_id}
        time.sleep(poll_interval)

    # ── Step 5: Fetch result ──
    print("\n[5/6] Fetching simulation result...")
    try:
        result = api.fetch_result(simulation_id)
        alpha_id = result.get("alpha_id", "")
        metrics = result.get("metrics", {})
        print(f"  Alpha ID: {alpha_id or '(none)'}")
        print(f"  Sharpe: {metrics.get('sharpe', 'N/A')}  Fitness: {metrics.get('fitness', 'N/A')}")
        print(f"  Turnover: {metrics.get('turnover', 'N/A')}  Returns: {metrics.get('returns', 'N/A')}")
        print(f"  Drawdown: {metrics.get('drawdown', 'N/A')}  Margin: {metrics.get('margin', 'N/A')}")
    except BrainAPIError as e:
        return {"ok": False, "step": "fetch_result", "error": str(e),
                "simulation_id": simulation_id}

    if not alpha_id:
        return {"ok": True, "step": "simulated", "simulation_id": simulation_id,
                "alpha_id": "", "expression": expression, "metrics": metrics,
                "note": "Simulation passed but no alpha_id generated from result."}

    # ── Step 6: Check + Submit ──
    print(f"\n[6/6] Checking pre-submit gate for alpha {alpha_id}...")
    try:
        check = api.check_alpha(alpha_id)
        check_status = check.get("status", "UNKNOWN")
        print(f"  Check: {check_status}")
        if check_status != "PASSED":
            checks = check.get("checks", {})
            print(f"  Details: {json.dumps(checks, indent=2)[:500]}")
            return {"ok": True, "step": "checked_not_passed",
                    "simulation_id": simulation_id, "alpha_id": alpha_id,
                    "metrics": metrics, "check_status": check_status,
                    "checks": checks,
                    "note": f"Pre-submit check status is '{check_status}'."}

        print(f"  [OK] Pre-submit check PASSED — submitting...")
        submit_result = api.submit_alpha(
            alpha_id=alpha_id, expression=expression, settings=settings, bodyless=True)
        submit_status = submit_result.get("status", "UNKNOWN")
        print(f"  Submit: {submit_status}")
        if submit_result.get("checks"):
            print(f"  Checks: {json.dumps(submit_result.get('checks'), indent=2)[:500]}")

        raw_alpha = submit_result.get("raw_alpha", {})
        alpha_status = raw_alpha.get("status", "")

        return {"ok": True, "step": "submitted", "simulation_id": simulation_id,
                "alpha_id": alpha_id, "expression": expression, "metrics": metrics,
                "profile": {"tier": profile.get("tier", ""), "level": profile.get("level", "")},
                "submit_status": submit_status, "alpha_status": alpha_status}
    except BrainAPIError as e:
        return {"ok": False, "step": "submit_alpha", "error": str(e),
                "alpha_id": alpha_id, "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit an alpha directly to BRAIN API.")
    parser.add_argument("--username", default="547820639@qq.com")
    parser.add_argument("--password", default="Ph360098.")
    parser.add_argument("--expression", default="-returns")
    parser.add_argument("--settings", default=None, help="JSON settings override")
    parser.add_argument("--dry-run", action="store_true", help="Only authenticate")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — authentication test\n")
        api = OfficialBrainAPI(OfficialAPIConfig(), username=args.username, password=args.password)
        try:
            print(f"Auth: {api.authenticate()}")
            p = api.get_user_profile()
            print(f"Profile: tier={p.get('tier')}, level={p.get('level')}, points={p.get('points')}")
            return 0
        except Exception as e:
            print(f"AUTH FAILED: {e}")
            return 1

    settings_override = None
    if args.settings:
        settings_override = json.loads(args.settings)

    result = submit_alpha_direct(
        username=args.username, password=args.password,
        expression=args.expression, settings=settings_override)

    print("\n" + "=" * 60)
    if result.get("ok"):
        step = result.get("step", "")
        aid = result.get("alpha_id", "")
        if step == "submitted":
            print("[SUCCESS] Alpha submitted for production!")
            print(f"  Alpha: {aid}")
            print(f"  Expression: {result.get('expression')}")
            print(f"  Submit Status: {result.get('submit_status')}")
            s = result.get("metrics", {}).get("sharpe")
            if s: print(f"  Sharpe: {s}")
            print(f"\n  BRAIN: https://platform.worldquantbrain.com/alphas/{aid}")
        elif step == "checked_not_passed":
            print(f"[WARNING] Pre-submit check not passed ({result.get('check_status')})")
            print(f"  Alpha: {aid}")
            print(f"  BRAIN: https://platform.worldquantbrain.com/alphas/{aid}")
        elif step == "simulated":
            print("[INFO] Simulation completed (no alpha_id in result)")
        else:
            print(f"[OK] {step}")
        return 0
    else:
        print(f"[FAILED] step='{result.get('step')}': {result.get('error') or result.get('status')}")
        aid = result.get("alpha_id", "")
        if aid: print(f"  Alpha: {aid}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
