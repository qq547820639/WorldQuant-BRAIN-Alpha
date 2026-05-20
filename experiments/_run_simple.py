"""Experiment runner: generate N candidates, submit to BRAIN, collect results.
Pure orchestration — all business logic imported from brain_alpha_ops.
"""
import os, sys, json, time, re, base64
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

import requests
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.research.validated_generator import generate_validated_candidates
from brain_alpha_ops.brain_api.official import normalize_metrics, build_simulation_payload
from experiments.validate_scoring import ExperimentResult


def _brains_auth(session: requests.Session) -> int:
    """Return status code after authenticating to BRAIN API."""
    u = os.environ.get("BRAIN_USERNAME", "")
    p = os.environ.get("BRAIN_PASSWORD", "")
    auth = base64.b64encode(f"{u}:{p}".encode()).decode()
    resp = session.post(
        "https://api.worldquantbrain.com/authentication",
        headers={"Authorization": f"Basic {auth}"},
        timeout=60,
    )
    return resp.status_code


def run_resilient(candidate_count: int = 100):
    config = load_run_config()
    config.auto_submit = False
    config.ops.budget.run_forever = False
    config.ops.budget.max_cycles = 1

    print("=== Step 1: Generate (validated) ===")
    print(f"  Generator: validated_generator (64 templates, 13 families)")
    print(f"  Target: {candidate_count} candidates")

    # Round 10: scaled-up production
    all_exprs: dict[str, dict] = {}
    for bn in range(4):
        batch = generate_validated_candidates(
            themes=None, count=candidate_count,
            max_attempts=candidate_count * 30, diversity_threshold=0.68,
        )
        new = 0
        for c in batch:
            if c["expression"] not in all_exprs:
                all_exprs[c["expression"]] = c
                new += 1
        print(f"  Batch {bn+1}: {len(batch)} gen, {new} new (pool {len(all_exprs)})")
    validated = list(all_exprs.values())
    print(f"  [Pool] {len(validated)} unique across 4 batches (prefilter built-in)")

    results = []
    for i, c in enumerate(validated):
        results.append(ExperimentResult(
            index=i + 1, expression=c["expression"],
            fields=[], operators=[], family=c.get("theme", ""), dataset_id="",
            simulation_status="pre_submit",
        ))
    print(f"  [OK] {len(results)} candidates ready\n")

    # ── Step 2: Simulate ──
    print(f"=== Step 2: Simulate ({len(results)} candidates) ===")

    session = requests.Session()
    status = _brains_auth(session)
    print(f"Auth: {status}")

    from dataclasses import asdict
    brain_settings = asdict(config.ops.settings)
    
    results_file = Path("experiments/_intermediate_results.json")
    
    completed = 0
    failed = 0
    AUTH_EVERY_N = 5

    def _submit_one(result):
        """Submit one candidate with adaptive retry. Returns (success, sim_id)."""
        nonlocal session
        for retry in range(5):
            try:
                body = build_simulation_payload(result.expression, brain_settings)
                resp = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=60)
                if resp.status_code in (200, 201):
                    sim_url = resp.headers.get("Location", "") or resp.json().get("id", "")
                    sim_id = sim_url.split("/")[-1] if "/" in sim_url else sim_url
                    print(f"  Submitted #{result.index}: {sim_id[:30]}...")
                    return True, sim_id
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "30"))
                    print(f"  #{result.index} 429 wait {retry_after}s...", end=" ", flush=True)
                    time.sleep(retry_after)
                    continue
                if resp.status_code >= 500:
                    print(f"  #{result.index} 5xx wait 30s...", end=" ", flush=True)
                    time.sleep(30)
                    continue
                result.simulation_status = "error"
                result.simulation_error = f"submit HTTP {resp.status_code}"
                print(f"  #{result.index} SUBMIT FAIL: {resp.status_code}")
                return False, None
            except (requests.exceptions.ConnectionError, ConnectionError, OSError) as e:
                wait = (retry + 1) * 30
                print(f"  #{result.index} net-err wait {wait}s...", end=" ", flush=True)
                time.sleep(wait)
                if retry >= 2:
                    try:
                        session = requests.Session()
                        s = _brains_auth(session)
                        print(f"[re-auth:{s}]", end=" ", flush=True)
                    except Exception:
                        pass
                continue
            except Exception:
                wait = 30
                print(f"  #{result.index} err wait {wait}s...", end=" ", flush=True)
                time.sleep(wait)
                continue
        result.simulation_status = "error"
        result.simulation_error = "429 exhausted"
        print(f"  #{result.index} SUBMIT FAIL: retries exhausted")
        return False, None

    def _poll_result(result, sim_id):
        """Poll one simulation. Returns True if done (completed/failed/timeout)."""
        try:
            resp = session.get(f"https://api.worldquantbrain.com/simulations/{sim_id}", timeout=30)
            if resp.status_code == 429:
                return False  # not done, will retry
            data = resp.json()
            status = data.get("status", "").upper()
            if status in ("COMPLETED", "COMPLETE", "DONE") or data.get("alpha"):
                result.simulation_status = "completed"
                alpha_id = data.get("alpha", "")
                if alpha_id:
                    time.sleep(2)
                    alpha_resp = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}", timeout=60)
                    if alpha_resp.status_code == 200:
                        raw = alpha_resp.json()
                        m = normalize_metrics(raw)
                        result.sharpe = m["sharpe"]
                        result.fitness = m["fitness"]
                        result.turnover = m["turnover"]
                        result.official_alpha_id = alpha_id
                        # Store full metrics for pipeline audit
                        result.full_metrics = m
                return True
            if status in ("FAILED", "ERROR"):
                result.simulation_status = "failed"
                result.brain_failure_detail = str(data.get("message", ""))[:200]
                return True
            return False  # still running
        except Exception:
            return False

    # ── Batch concurrent loop ──
    batch_total = 0
    poll_attempts = config.ops.official_api.poll_attempts
    poll_interval = config.ops.official_api.poll_interval_seconds
    concurrent = config.ops.budget.max_official_concurrent_simulations
    for batch_start in range(0, len(results), concurrent):
        batch_end = min(batch_start + concurrent, len(results))
        batch = results[batch_start:batch_end]

        # Re-auth periodically
        if batch_start > 0 and batch_start % (AUTH_EVERY_N * concurrent) == 0:
            session = requests.Session()
            s = _brains_auth(session)
            print(f"  [re-auth] {s}", flush=True)

        # A: Submit all in batch
        pending = {}  # sim_id -> result
        for r in batch:
            if r.simulation_status == "error":
                failed += 1; continue
            success, sim_id = _submit_one(r)
            if success:
                pending[sim_id] = r
            else:
                failed += 1

        # B: Poll all in batch until done
        poll_count = 0
        while pending and poll_count < poll_attempts:
            time.sleep(poll_interval)
            poll_count += 1
            done = []
            for sim_id, r in list(pending.items()):
                if _poll_result(r, sim_id):
                    done.append(sim_id)
                    if r.simulation_status == "completed":
                        completed += 1
                        print(f"  #{r.index} OK (sharpe={r.sharpe:.3f})")
                    else:
                        failed += 1
                        print(f"  #{r.index} FAIL: {(r.brain_failure_detail or '')[:80]}")
            for sim_id in done:
                del pending[sim_id]
            if not pending:
                break

        for r in pending.values():
            r.simulation_status = "timeout"
            r.simulation_error = "poll timeout"
            failed += 1
            print(f"  #{r.index} TIMEOUT")

        batch_total = sum(1 for r in results if r.simulation_status in ("completed", "failed", "error", "timeout"))
        print(f"  Batch {batch_start//concurrent+1}: {batch_total}/{len(results)} done")

        # Save intermediate — include full metrics for pipeline audit
        with open(results_file, "w") as f:
            json.dump({
                "completed": completed, "failed": failed, "total": len(results),
                "results": [{"index": r.index, "expression": r.expression[:100], "status": r.simulation_status,
                    "sharpe": getattr(r, "sharpe", None), "fitness": getattr(r, "fitness", None),
                    "turnover": getattr(r, "turnover", None),
                    "full_metrics": getattr(r, "full_metrics", None),
                    "error": getattr(r, "simulation_error", "") or getattr(r, "brain_failure_detail", "")}
                    for r in results]
            }, f, indent=2, default=str)
    
    print(f"\n=== Done: {completed} completed, {failed} failed ===")
    print(f"Run post-experiment analysis: python experiments/post_experiment_analysis.py")
    return completed, failed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=int, default=100)
    args = parser.parse_args()
    run_resilient(args.candidates)
