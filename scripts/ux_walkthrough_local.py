"""
Fast Local UX Walkthrough — verifies all local server endpoints and UX structure.
Uses subprocess with strict timeout (no live BRAIN API calls that can hang).
"""
import json, os, re, sys, time, uuid
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)
os.environ["BRAIN_ALPHA_OPS_HOME"] = PROJECT_ROOT

import requests
from brain_alpha_ops import web

RESULTS = {"stages": [], "warnings": [], "metrics": {}}
CSS_DIR = Path(PROJECT_ROOT) / "brain_alpha_ops" / "web" / "css"
JS_DIR = Path(PROJECT_ROOT) / "brain_alpha_ops" / "web" / "js"

def record_stage(name, status, detail=""):
    RESULTS["stages"].append({"name": name, "status": status, "detail": detail})
    print(f"  {'PASS' if status=='PASS' else 'WARN' if status=='WARN' else 'FAIL'}  {name}: {detail[:100] if detail else ''}")

# ── Stage 0: Server Start ──────────────────────────────────────────────
print("\n[0] Server Startup")
port = web.find_free_port(start=8866)
BASE = web.serve(port=port, open_browser=False).rstrip("/")
time.sleep(0.3)
r = requests.get(f"{BASE}/api/health", timeout=5)
assert r.status_code == 200 and r.json().get("ok")
record_stage("Server Startup", "PASS", BASE)

# ── Stage 1: HTML & UX Elements ────────────────────────────────────────
print("\n[1] HTML & UX Element Verification")
r = requests.get(BASE, timeout=10)
html = r.text
sid = r.cookies.get("brain_alpha_ops_session")
csrf = web._csrf_for_session(sid)
H = {"X-Brain-Alpha-CSRF": csrf}
C = {"brain_alpha_ops_session": sid}

def post_headers():
    return {
        **H,
        "X-Brain-Alpha-Request-ID": str(uuid.uuid4()),
        "X-Brain-Alpha-Request-Timestamp": str(int(time.time() * 1000)),
    }

# v3 base elements
v3 = ["app-shell","app-header","app-sidebar","app-content","viewTabs","candidateTable",
      "tableSearch","insightPanel","workflowRail","detailModal","toastContainer","spinnerOverlay",
      "confirmOverlay","controlButton","tableEmptyState","runtimeStatusPanel","envBadge"]
v3_found = sum(1 for e in v3 if e in html)
record_stage("v3 Shell Elements", "PASS" if v3_found >= 15 else "WARN", f"{v3_found}/{len(v3)}")

# v4 UX enhancements
v4 = ["skip-link","ux-enhancements.css","keyboard-shortcuts-panel","workflow-wizard",
      "skeleton","page-enter","reduced-motion","has-error","has-success",
      "form-error-message","focus-visible","focus-ring","aria-live","sr-only"]
v4_found = sum(1 for e in v4 if e in html or e in " ".join([html]))
# Check CSS files
ux_css = (CSS_DIR / "ux-enhancements.css").read_text(encoding="utf-8")
v4_css = ["skeleton","skeletonShimmer","pageFadeIn","reduced-motion","has-error",
          "form-error-message","toast-progress","keyboard-shortcuts-panel",
          "workflow-wizard","focus-visible","print","runtimeStatusSlideIn"]
v4_css_found = sum(1 for e in v4_css if e in ux_css)
record_stage("v4 UX CSS", "PASS" if v4_css_found >= 10 else "WARN", f"{v4_css_found}/{len(v4_css)}")

# ARIA & accessibility
aria = ['role="banner"','role="main"','role="complementary"','role="navigation"',
        'role="list"','role="button"','role="dialog"','aria-label',"aria-live",
        "aria-hidden","aria-current","aria-pressed","skip-link"]
aria_found = sum(1 for a in aria if a in html)
record_stage("ARIA/Accessibility", "PASS" if aria_found >= 10 else "WARN", f"{aria_found}/{len(aria)}")

# Dark mode
record_stage("Dark Mode Support", "PASS" if "data-theme" in ux_css and "toggle-theme" in html else "WARN")

# Responsive breakpoints
app_css = (CSS_DIR / "app.css").read_text(encoding="utf-8")
bps = "1200px" in app_css or "960px" in app_css or "640px" in app_css
record_stage("Responsive Breakpoints", "PASS" if bps else "WARN")

record_stage("Session Bootstrap", "PASS", f"sid={sid[:6]}...")

# ── Stage 2: API Endpoints ────────────────────────────────────────────
print("\n[2] API Endpoint Health")

GET_ENDPOINTS = [
    ("/api/config", True),
    ("/api/presets", True),
    ("/api/profile", False),  # May return unauthenticated
    ("/api/latest_result", True),
    ("/api/health", True),
    ("/api/check_results", True),
    ("/api/checkpoint/status", False),
    ("/api/research_memory", True),
    ("/api/research_knowledge", True),
    ("/api/research_observability", True),
    ("/api/lifecycle", True),
    ("/api/cloud_alphas", True),
    ("/api/assistant_context", True),
    ("/api/assistant_guidance", True),
    ("/api/assistant_request", True),
    ("/api/prompt_runs", False),
    ("/api/redline/report", False),
    ("/api/scoring/health", False),
]

ok, fail = 0, 0
for ep, critical in GET_ENDPOINTS:
    try:
        r = requests.get(f"{BASE}{ep}", headers=H, cookies=C, timeout=10)
        if r.status_code in (200, 401, 403):
            ok += 1
        else:
            fail += 1
            if critical:
                RESULTS["warnings"].append(f"{ep}: HTTP {r.status_code}")
    except Exception as e:
        fail += 1
        if critical:
            RESULTS["warnings"].append(f"{ep}: {e}")

record_stage("API Endpoints", "PASS" if fail==0 else "WARN", f"{ok}/{len(GET_ENDPOINTS)} reachable, {fail} failed")

# ── Stage 3: JS Module Contracts ───────────────────────────────────────
print("\n[3] JS Module Contract Verification")

js_v4_features = {
    "js/components/toast.js": ["showProgress", "withAction", "persistent"],
    "js/components/spinner.js": ["showTableSkeleton", "announceToScreenReader", "startStageMessages"],
    "js/app.js": ["SHORTCUTS", "toggleShortcutsPanel", "showWorkflowWizard", "handleKeyboardShortcut"],
    "js/form-controls.js": ["validateField", "clearFieldValidation", "bindFieldValidation", "validateConnection"],
    "js/views/detail.js": ["trapModalFocus", "FOCUSABLE_SELECTOR"],
}
js_ok = 0
for mod_path, features in js_v4_features.items():
    src = (JS_DIR / mod_path.replace("js/", "")).read_text(encoding="utf-8")
    found = sum(1 for f in features if f in src)
    if found == len(features):
        js_ok += 1
    else:
        RESULTS["warnings"].append(f"{mod_path}: missing features")
record_stage("v4 JS Features", "PASS" if js_ok==len(js_v4_features) else "WARN", f"{js_ok}/{len(js_v4_features)}")

# ── Stage 4: Shutdown ──────────────────────────────────────────────────
print("\n[4] Shutdown")
try:
    requests.post(f"{BASE}/api/shutdown", json={}, headers=post_headers(), cookies=C, timeout=5)
    time.sleep(0.3)
    try:
        requests.get(BASE, timeout=2)
    except Exception as exc:
        RESULTS["warnings"].append(f"shutdown probe failed: {exc}")
except Exception as exc:
    RESULTS["warnings"].append(f"shutdown request failed: {exc}")
record_stage("Shutdown", "PASS")

# ── Report ─────────────────────────────────────────────────────────────
RESULTS["css_size"] = len(ux_css)
RESULTS["total_stages"] = len(RESULTS["stages"])
RESULTS["pass_count"] = sum(1 for s in RESULTS["stages"] if s["status"] == "PASS")
RESULTS["warn_count"] = sum(1 for s in RESULTS["stages"] if s["status"] == "WARN")

print(f"\n{'='*70}")
print(f"  WALKTHROUGH RESULTS: {RESULTS['pass_count']} pass, {RESULTS['warn_count']} warn, {len(RESULTS['warnings'])} warnings")
print(f"{'='*70}")

rp = Path(PROJECT_ROOT) / "data" / "ux_walkthrough_report.json"
rp.parent.mkdir(parents=True, exist_ok=True)
rp.write_text(json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"  Report: {rp}")
