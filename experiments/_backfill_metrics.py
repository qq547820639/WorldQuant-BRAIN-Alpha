"""Backfill: fetch full BRAIN metrics for all Round 8 completed alphas.
Parses experiment log for alpha_ids, fetches /alphas/{id}, extracts is.* + is.checks.
Output: _intermediate_results_full.json ready for pipeline audit.
"""
import os, sys, json, base64, re, time, requests
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

username = os.environ.get("BRAIN_USERNAME", "")
password = os.environ.get("BRAIN_PASSWORD", "")
if not username or not password:
    print("ERROR: creds not set")
    sys.exit(1)

# ── Auth ──
session = requests.Session()
resp = session.post(
    "https://api.worldquantbrain.com/authentication",
    headers={"Authorization": f"Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}"},
    timeout=60,
)
print(f"Auth: {resp.status_code}")

# ── Parse experiment log for alpha_ids ──
log_path = Path("experiments/experiment_r5.log")
if not log_path.exists():
    print("ERROR: no experiment log")
    sys.exit(1)

log_text = log_path.read_text(encoding="utf-8", errors="replace")
log_lines = log_text.split("\n")

alpha_map = {}  # index -> {sharpe, alpha_id}
for line in log_lines:
    m = re.search(r"Submitted #(\d+):\s*(\S+)", line)
    if m:
        idx = int(m.group(1))
        aid = m.group(2).rstrip("...")
        alpha_map[idx] = {"alpha_id": aid}
    
    m2 = re.search(r"#(\d+)\s+OK\s+\(sharpe=(-?[\d.]+)\)", line)
    if m2:
        idx = int(m2.group(1))
        if idx in alpha_map:
            alpha_map[idx]["sharpe"] = float(m2.group(2))

# Read intermediate results for base data
ir_path = Path("experiments/_intermediate_results.json")
base_data = {}
if ir_path.exists():
    base_data = json.loads(ir_path.read_text(encoding="utf-8"))

print(f"\nParsed {len(alpha_map)} alpha_ids from log")
completed_map = {idx: v for idx, v in alpha_map.items() if "sharpe" in v}
print(f"Completed: {len(completed_map)}")

# ── Fetch full metrics for each completed alpha ──
from brain_alpha_ops.brain_api.official import normalize_metrics

results = []
for idx, info in sorted(completed_map.items()):
    aid = info["alpha_id"]
    print(f"  Fetching #{idx}: {aid[:20]}...", end=" ", flush=True)
    
    for retry in range(3):
        try:
            # Step 1: GET /simulations/{sim_id} → get alpha_id
            sim_resp = session.get(f"https://api.worldquantbrain.com/simulations/{aid}", timeout=60)
            if sim_resp.status_code == 429:
                time.sleep(15)
                continue
            if sim_resp.status_code not in (200, 201):
                print(f"S{sim_resp.status_code}", end=" ", flush=True)
                time.sleep(3)
                continue
            
            sim_data = sim_resp.json() or {}
            real_alpha = sim_data.get("alpha", "")
            if not real_alpha:
                print("noA", end=" ", flush=True)
                break
            
            # Step 2: GET /alphas/{alpha_id} → get is.checks  
            r = session.get(f"https://api.worldquantbrain.com/alphas/{real_alpha}", timeout=60)
            if r.status_code == 429:
                time.sleep(15)
                continue
            if r.status_code not in (200, 201):
                print(f"A{r.status_code}", end=" ", flush=True)
                time.sleep(2)
                continue
            raw = r.json() or {}
            m = normalize_metrics(raw)
            expression = raw.get("regular", {}).get("code", "")[:100]
            results.append({
                "index": idx,
                "expression": expression,
                "status": "completed",
                "sharpe": m["sharpe"],
                "fitness": m["fitness"],
                "turnover": m["turnover"],
                "full_metrics": m,
                "error": "",
            })
            print(f"P={m['brain_pass']} F={len(m['brain_failed_names'])}")
            break
        except Exception:
            print("err", end=" ", flush=True)
        except Exception:
            print("err", end=" ", flush=True)
            time.sleep(10)
    else:
        print("SKIP")
        results.append({
            "index": idx,
            "expression": "",
            "status": "completed",
            "sharpe": info.get("sharpe", 0),
            "fitness": 0, "turnover": 0,
            "full_metrics": None,
            "error": "fetch failed",
        })
    
    time.sleep(2)  # rate limit

# ── Save augmented results ──
completed_count = sum(1 for r in results if r.get("status") == "completed")
failed_count = base_data.get("failed", 0)
total = max(base_data.get("total", 0), len(results))

output = {
    "completed": completed_count,
    "failed": failed_count,
    "total": total,
    "results": results,
    "_note": "full_metrics backfilled from BRAIN API post-hoc",
}

out_path = Path("experiments/_intermediate_results_full.json")
out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

print(f"\nSaved {len(results)} results with full_metrics to {out_path}")
print(f"  brain_pass count: {sum(1 for r in results if r.get('full_metrics',{}).get('brain_pass'))}")
print(f"\nReady for: python experiments/_pipeline_audit.py")
