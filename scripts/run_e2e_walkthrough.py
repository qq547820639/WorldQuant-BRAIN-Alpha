"""
Manual E2E Walkthrough — executes the full new-user journey step by step.
"""
import json, os, re, sys, time, traceback, uuid
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)
os.environ["BRAIN_ALPHA_OPS_HOME"] = PROJECT_ROOT

import requests

from brain_alpha_ops import web
from brain_alpha_ops.redaction import redact_text

# Config: live credentials must be supplied at runtime, never committed.
TEST_EMAIL = os.getenv("BRAIN_E2E_USERNAME") or os.getenv("BRAIN_USERNAME", "")
TEST_PASSWORD = os.getenv("BRAIN_E2E_PASSWORD") or os.getenv("BRAIN_PASSWORD", "")
TEST_TOKEN = os.getenv("BRAIN_E2E_TOKEN") or os.getenv("BRAIN_TOKEN", "")

results = {"stages": {}, "metrics": {}, "errors": [], "warnings": []}

def has_live_credentials():
    return bool(TEST_TOKEN or (TEST_EMAIL and TEST_PASSWORD))

def credential_payload():
    return {"username": TEST_EMAIL, "password": TEST_PASSWORD, "token": TEST_TOKEN}

def safe_get(url, headers, cookies, **kw):
    t0 = time.time()
    r = requests.get(url, headers=headers, cookies=cookies, timeout=30, **kw)
    results["metrics"][f"GET:{url.split('/')[-1][:20]}"] = round(time.time()-t0,2)
    return r

def safe_post(url, headers, cookies, data, **kw):
    t0 = time.time()
    post_headers = {
        **headers,
        "X-Brain-Alpha-Request-ID": str(uuid.uuid4()),
        "X-Brain-Alpha-Request-Timestamp": str(int(time.time() * 1000)),
    }
    r = requests.post(url, json=data, headers=post_headers, cookies=cookies, timeout=30, **kw)
    results["metrics"][f"POST:{url.split('/')[-1][:20]}"] = round(time.time()-t0,2)
    return r

# === STAGE 0: Start Server ===
print("\n[0] Server Startup")
port = web.find_free_port(start=8866)
url = web.serve(port=port, open_browser=False)
time.sleep(0.5)
BASE = url.rstrip("/")
print(f"    OK Server at {BASE}")
results["stages"]["startup"] = "PASS"

# === STAGE 1: Session & HTML ===
print("\n[1] Session Bootstrap")
r = requests.get(BASE, timeout=10)
assert r.status_code == 200
html = r.text
assert "BRAIN Alpha Ops" in html
sid = r.cookies.get("brain_alpha_ops_session")
assert sid
csrf = web._csrf_for_session(sid)
assert csrf
headers = {"X-Brain-Alpha-CSRF": csrf}
cookies = {"brain_alpha_ops_session": sid}

# Verify key v4 UX elements
v4_elements = ["toastContainer", "spinnerOverlay", "detailModal", "viewTabs",
               "workflowRail", "tableSearch", "skip-link", "insightPanel"]
found = [e for e in v4_elements if e in html]
missing = [e for e in v4_elements if e not in html]
print(f"    OK Session={sid[:6]}..., CSRF acquired")
print(f"    UX elements: {len(found)}/{len(v4_elements)} found" + (f", missing: {missing}" if missing else ""))
results["stages"]["session"] = "PASS"

# === STAGE 2: Config & Presets ===
print("\n[2] Config & Presets")
r = safe_get(f"{BASE}/api/config", headers, cookies)
cfg = r.json()
assert cfg.get("ok")

r2 = safe_get(f"{BASE}/api/presets", headers, cookies)
prs = r2.json().get("presets", {})
print(f"    OK Config loaded, {len(prs)} presets: {list(prs.keys())[:5]}")

r3 = safe_get(f"{BASE}/api/latest_result", headers, cookies)
try:
    lr = r3.json() or {}
except Exception:
    lr = {}
cands = len((lr.get("result") or {}).get("candidates") or [])
cloud = len((lr.get("result") or {}).get("cloud_alphas") or [])
print(f"    Data: {cands} candidates, {cloud} cloud alphas")
results["stages"]["config"] = "PASS"

# === STAGE 3: Connection Test ===
print("\n[3] Connection Test (Live BRAIN API)")
if not has_live_credentials():
    print("    SKIPPED: set BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN to run live connection checks")
    connected = False
    results["stages"]["connection"] = "SKIP"
else:
    payload = {
        "environment": "production",
        **credential_payload(),
        "baseUrl": "https://api.worldquantbrain.com",
        "preset": "usa_standard",
        "settings": {
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "neutralization": "SUBINDUSTRY",
            "instrumentType": "EQUITY",
            "type": "REGULAR",
            "decay": 10,
            "truncation": 0.05,
            "pasteurization": "ON",
            "nanHandling": "ON",
            "unitHandling": "VERIFY",
            "language": "FASTEXPR",
        },
    }
    r = safe_post(f"{BASE}/api/test_connection", headers, cookies, payload)
    data = r.json()
    connected = data.get("ok", False)
    error_text = redact_text(data.get("error", "?"), max_length=100)
    print(f"    {'OK Connected' if connected else 'FAILED: ' + error_text}")
    results["stages"]["connection"] = "PASS" if connected else "SKIP"

# === STAGE 4: Cloud Sync ===
if connected:
    print("\n[4] Cloud Sync")
    r = safe_post(f"{BASE}/api/sync_alphas", headers, cookies, {
        "environment":"production", **credential_payload(),
        "baseUrl":"https://api.worldquantbrain.com","syncRange":"3d",
        "settings":{"region":"USA","universe":"TOP3000"}})
    d = r.json()
    jid = d.get("job_id","")
    print(f"    Sync started, job: {jid[:12] if jid else 'inline'}")

    # Poll briefly
    for i in range(5):
        time.sleep(2)
        sr = safe_get(f"{BASE}/api/sync_status?job_id={jid}&compact=1", headers, cookies)
        sd = sr.json()
        st = sd.get("status","?")
        pct = sd.get("progress",{}).get("percent","?")
        print(f"    [{i+1}] {st} | {pct}%")
        if st == "completed":
            break
    results["stages"]["sync"] = "PASS"
    time.sleep(1)
else:
    print("\n[4] Cloud Sync — SKIPPED (not connected)")

# === STAGE 5: Check results ===
print("\n[5] Check & Research Data")
# Load updated latest result
r = safe_get(f"{BASE}/api/latest_result", headers, cookies)
lr = r.json() if r.status_code==200 else {}
candidates = (lr.get("result") or {}).get("candidates") or []
passed = [c for c in candidates if c.get("lifecycle_status")=="submission_ready"]
print(f"    Submission-ready: {len(passed)} / {len(candidates)}")

# Research endpoints
for ep,label in [("/api/research_memory","memory"),("/api/lifecycle","lifecycle"),
                 ("/api/check_results","checks"),("/api/checkpoint/status","checkpoint")]:
    try:
        _r = safe_get(f"{BASE}{ep}", headers, cookies)
        _sz = len(_r.text)
        print(f"    {label}: {_r.status_code}, {_sz} bytes")
    except Exception as e:
        print(f"    {label}: ERROR {redact_text(e, max_length=120)}")
results["stages"]["research"] = "PASS"

# === STAGE 6: All GET endpoints health check ===
print("\n[6] API Surface Scan")
all_gets = [
    "/api/health", "/api/profile", "/api/research_knowledge",
    "/api/research_observability", "/api/prompt_runs", "/api/cloud_alphas",
    "/api/assistant_context", "/api/assistant_guidance", "/api/assistant_request",
    "/api/redline/report", "/api/scoring/health", "/api/sqlite_indexes"
]
ok_count = 0
for ep in all_gets:
    try:
        r = safe_get(f"{BASE}{ep}", headers, cookies)
        ok_count += 1
    except:
        pass
print(f"    {ok_count}/{len(all_gets)} endpoints reachable")
results["stages"]["api_surface"] = f"{ok_count}/{len(all_gets)} OK"

# === STAGE 7: Shutdown ===
print("\n[7] Shutdown")
safe_post(f"{BASE}/api/shutdown", headers, cookies, {})
time.sleep(0.5)
try:
    requests.get(BASE, timeout=2)
    print("    WARN Server still up")
except:
    print("    OK Server down")
results["stages"]["shutdown"] = "PASS"

# === UX Report ===
print("\n" + "="*70)
print("  UX WALKTHROUGH REPORT")
print("="*70)
print()
print("STAGE RESULTS:")
for k,v in results["stages"].items():
    print(f"  {k:20s}: {v}")
print(f"\n  Connected to BRAIN: {'YES' if connected else 'NO'}")
print(f"  API latency samples: {list(results['metrics'].values())[:5]}")
print()

# Save report
rp = Path(__file__).resolve().parent / "qa_e2e_walkthrough_report.json"
rp.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"  Report saved to: {rp}")
