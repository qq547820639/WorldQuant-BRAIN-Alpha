"""Diagnose: dump BRAIN /alphas/{alpha_id} full response structure.
Fetches a Round 8 alpha_id and prints the ENTIRE raw JSON.
"""
import os, sys, json, base64, requests
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

username = os.environ.get("BRAIN_USERNAME", "")
password = os.environ.get("BRAIN_PASSWORD", "")
if not username or not password:
    print("ERROR: creds not set")
    sys.exit(1)

session = requests.Session()
resp = session.post(
    "https://api.worldquantbrain.com/authentication",
    headers={"Authorization": f"Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}"},
    timeout=60,
)
print(f"Auth: {resp.status_code}")

# Try to get an alpha_id from Round 8 intermediate results
results_file = Path("experiments/_intermediate_results.json")
alpha_id = None
if results_file.exists():
    data = json.loads(results_file.read_text(encoding="utf-8"))
    for r in data.get("results", []):
        if r.get("status") == "completed":
            aid = r.get("official_alpha_id") or r.get("alpha_id")
            if aid and len(aid) > 10:
                alpha_id = aid
                break

if not alpha_id:
    # Fallback: grab from user's recent alphas
    print("No alpha_id in intermediate results, fetching from user alphas...")
    resp2 = session.get("https://api.worldquantbrain.com/users/self/alphas?limit=3", timeout=60)
    if resp2.status_code == 200:
        alphas = resp2.json()
        if isinstance(alphas, list) and alphas:
            alpha_id = alphas[0].get("alpha_id") or alphas[0].get("id")
        elif isinstance(alphas, dict):
            results = alphas.get("results", [])
            if results:
                alpha_id = results[0].get("id") or results[0].get("alpha_id")

if not alpha_id:
    print("ERROR: could not find any alpha_id")
    sys.exit(1)

print(f"Fetching /alphas/{alpha_id} ...")
resp3 = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}", timeout=60)
print(f"Status: {resp3.status_code}")

if resp3.status_code == 200:
    data = resp3.json()
    raw = json.dumps(data, indent=2, default=str)
    
    # Save full dump
    dump_path = Path("experiments/_alpha_raw.json")
    dump_path.write_text(raw, encoding="utf-8")
    
    # Print key sections
    print(f"\n=== TOP-LEVEL KEYS ===")
    print(list(data.keys()))
    
    print(f"\n=== 'is' (In-Sample) KEYS ===")
    is_d = data.get("is", {})
    if isinstance(is_d, dict):
        for k, v in sorted(is_d.items()):
            print(f"  is.{k}: {v}")
    else:
        print(f"  (not a dict: {type(is_d)}) {str(is_d)[:200]}")
    
    print(f"\n=== 'os' (Out-of-Sample) KEYS ===")
    os_d = data.get("os", {})
    if isinstance(os_d, dict):
        for k, v in sorted(os_d.items()):
            print(f"  os.{k}: {v}")
    else:
        print(f"  (not a dict or missing)")
    
    print(f"\n=== OTHER TOP-LEVEL FIELDS ===")
    skip = {"is", "os", "settings", "regular", "expression"}
    for k, v in data.items():
        if k in skip:
            continue
        if isinstance(v, (str, int, float, bool)):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if not isinstance(v2, (dict, list)):
                    print(f"  {k}.{k2}: {v2}")
    
    print(f"\nFull JSON saved to experiments/_alpha_raw.json")
else:
    print(f"ERROR: {resp3.status_code} {resp3.text[:300]}")
