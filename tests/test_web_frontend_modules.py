from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

from scripts.check_frontend_syntax import _node_path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "brain_alpha_ops" / "web"
WEB_JS = ROOT / "brain_alpha_ops" / "web" / "js"
TEMPLATE_PATH = WEB_DIR / "index_template.html"

MODULE_TEST_COVERAGE = {
    "js/api-client.js": "api request, csrf header, and error mapping",
    "js/app.js": "ux orchestration, workflow nav, empty states, busy guards",
    "js/components/modal.js": "confirm dialog visibility, focus, and resolution",
    "js/components/progress.js": "progress bar clamp and status text rendering",
    "js/components/spinner.js": "loading overlay visibility and message rendering",
    "js/components/table.js": "table empty/data rendering, badges, score formatting",
    "js/components/toast.js": "toast roles, escaping, and removal contract",
    "js/state.js": "nested state set/merge, listeners, cache, check freshness",
    "js/utils.js": "escaping, labels, risk/state navigation rendering",
    "js/view-model.js": "identity, normalization, dedupe, runtime array selection",
    "js/views/charts.js": "offline canvas fallback and empty dataset rendering",
    "js/views/detail.js": "detail modal rendering, escaping, and check suggestions",
    "js/views/monitor.js": "legacy monitor tiles and backtest slot rendering",
    "js/views/production.js": "production guard and global action exports",
}


def _run_node_contract(script: str) -> str:
    node = _node_path()
    assert node, "bundled Node.js is required for frontend module contract tests"
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "frontend_contract_test.js"
        script_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [node, str(script_path), str(ROOT)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=90,
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def test_every_frontend_module_has_a_contract_test_entry():
    actual_modules = {
        "js/" + path.relative_to(WEB_JS).as_posix()
        for path in WEB_JS.rglob("*.js")
    }
    assert actual_modules == set(MODULE_TEST_COVERAGE)

    inlined_sources = set(re.findall(r"<!--\s*inline:(js/.+?\.js)\s*-->", TEMPLATE_PATH.read_text(encoding="utf-8")))
    assert inlined_sources.issubset(MODULE_TEST_COVERAGE)
    assert "js/views/monitor.js" not in inlined_sources, "legacy monitor is tested but not shipped in the inline bundle"


def test_frontend_runtime_modules_render_state_and_interaction_contracts():
    script = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = process.argv[2];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function createHarness() {
  const elements = {};
  const timers = [];

  class ClassList {
    constructor(el) {
      this.el = el;
      this.tokens = new Set();
    }
    _sync() { this.el.className = Array.from(this.tokens).join(" "); }
    add() { Array.from(arguments).forEach(token => { if (token) this.tokens.add(String(token)); }); this._sync(); }
    remove() { Array.from(arguments).forEach(token => this.tokens.delete(String(token))); this._sync(); }
    contains(token) { return this.tokens.has(String(token)); }
    toggle(token, force) {
      const shouldAdd = force === undefined ? !this.contains(token) : Boolean(force);
      if (shouldAdd) this.tokens.add(String(token));
      else this.tokens.delete(String(token));
      this._sync();
      return shouldAdd;
    }
  }

  class Element {
    constructor(tagName) {
      this.tagName = String(tagName || "div").toUpperCase();
      this.children = [];
      this.parentNode = null;
      this.parentElement = null;
      this.attributes = {};
      this.dataset = {};
      this.style = {};
      this.className = "";
      this.classList = new ClassList(this);
      this.innerHTML = "";
      this.textContent = "";
      this.value = "";
      this.disabled = false;
      this.eventListeners = {};
      this.clientWidth = 420;
      this.clientHeight = 220;
      this.drawOps = [];
    }
    setAttribute(name, value) {
      value = String(value);
      this.attributes[name] = value;
      if (name === "id") {
        this.id = value;
        elements[value] = this;
      }
      if (name === "class") {
        this.className = value;
        this.classList.tokens = new Set(value.split(/\s+/).filter(Boolean));
      }
      if (name.indexOf("data-") === 0) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
        this.dataset[key] = value;
      }
    }
    getAttribute(name) { return this.attributes[name] || ""; }
    appendChild(child) {
      child.parentNode = this;
      child.parentElement = this;
      this.children.push(child);
      return child;
    }
    removeChild(child) {
      this.children = this.children.filter(item => item !== child);
      child.parentNode = null;
      child.parentElement = null;
      return child;
    }
    addEventListener(type, fn) {
      if (!this.eventListeners[type]) this.eventListeners[type] = [];
      this.eventListeners[type].push(fn);
    }
    removeEventListener(type, fn) {
      this.eventListeners[type] = (this.eventListeners[type] || []).filter(item => item !== fn);
    }
    click() {
      (this.eventListeners.click || []).slice().forEach(fn => fn({ target: this, preventDefault() {}, stopPropagation() {} }));
    }
    focus() { document.activeElement = this; }
    querySelector(selector) {
      if (selector[0] === "#") return elements[selector.slice(1)] || null;
      if (selector[0] === ".") {
        const wanted = selector.slice(1);
        const stack = this.children.slice();
        while (stack.length) {
          const item = stack.shift();
          if (item.classList.contains(wanted)) return item;
          stack.push.apply(stack, item.children);
        }
      }
      return null;
    }
    getBoundingClientRect() {
      return { width: this.clientWidth || 360, height: this.clientHeight || 200, top: 0, left: 0 };
    }
    getContext(type) {
      if (this.tagName !== "CANVAS" || type !== "2d") return null;
      const canvas = this;
      const ctx = {
        setTransform() { canvas.drawOps.push("setTransform"); },
        clearRect() { canvas.drawOps.push("clearRect"); },
        fillRect() { canvas.drawOps.push("fillRect"); },
        fillText(text) { canvas.drawOps.push("text:" + text); },
        beginPath() { canvas.drawOps.push("beginPath"); },
        moveTo() { canvas.drawOps.push("moveTo"); },
        lineTo() { canvas.drawOps.push("lineTo"); },
        stroke() { canvas.drawOps.push("stroke"); },
        arc() { canvas.drawOps.push("arc"); },
        closePath() { canvas.drawOps.push("closePath"); },
        fill() { canvas.drawOps.push("fill"); },
      };
      return ctx;
    }
  }

  const document = {
    elements,
    readyState: "loading",
    activeElement: null,
    documentElement: new Element("html"),
    body: null,
    createElement(tag) { return new Element(tag); },
    getElementById(id) { return elements[id] || null; },
    querySelector(selector) {
      if (selector[0] === "#") return elements[selector.slice(1)] || null;
      return this.body ? this.body.querySelector(selector) : null;
    },
    addEventListener() {},
    contains(el) { return Boolean(el); },
    register(id, tag) {
      const el = new Element(tag || "div");
      el.setAttribute("id", id);
      return el;
    },
  };
  document.body = new Element("body");
  document.activeElement = document.body;

  const context = {
    console,
    URL,
    document,
    setTimeout(fn) { timers.push(fn); if (typeof fn === "function") fn(); return timers.length; },
    clearTimeout() {},
    setInterval() { return 1; },
    clearInterval() {},
    localStorage: { getItem() { return null; }, setItem() {} },
    location: { origin: "http://127.0.0.1:8765" },
    matchMedia() { return { matches: false }; },
    navigator: { clipboard: { writeText: async () => {} } },
    getComputedStyle() { return { display: "block" }; },
    confirm() { return true; },
  };
  context.window = context;
  return { context: vm.createContext(context), document, Element };
}

function load(context, relPath) {
  const source = fs.readFileSync(path.join(root, "brain_alpha_ops", "web", relPath), "utf8");
  vm.runInContext(source, context, { filename: relPath });
}

(async function main() {
  const { context, document, Element } = createHarness();
  [
    "toastContainer", "spinnerOverlay", "spinnerText", "confirmOverlay", "confirmText",
    "confirmYes", "confirmNo", "progressFill", "progressMeta", "tableRows",
    "detailModal", "detailCloseButton", "modalTitle", "detail", "opsMonitor",
    "insight", "backtestPanel", "controlButton", "status"
  ].forEach(id => document.register(id, id === "confirmYes" || id === "confirmNo" || id === "detailCloseButton" || id === "controlButton" ? "button" : "div"));
  const modalPanel = new Element("div");
  modalPanel.classList.add("modal-panel");
  document.getElementById("detailModal").appendChild(modalPanel);
  document.getElementById("confirmOverlay").classList.add("hidden");
  document.getElementById("spinnerOverlay").classList.add("hidden");

  load(context, "js/utils.js");
  load(context, "js/state.js");
  load(context, "js/api-client.js");
  load(context, "js/view-model.js");
  load(context, "js/components/toast.js");
  load(context, "js/components/spinner.js");
  load(context, "js/components/modal.js");
  load(context, "js/components/progress.js");
  load(context, "js/components/table.js");

  assert(context.Utils.escapeHtml("<b>&") === "&lt;b&gt;&amp;", "utils escapeHtml must escape markup");
  assert(context.Utils.phaseName("cloud_sync") === "云端数据同步", "utils phaseName must translate backend phases");
  const riskHtml = context.Utils.renderRiskExplanation({ title: "<risk>", summary: "<bad>", severity: "blocking<script>", visual: { value: 0.91, threshold: 0.9 }, reasons: ["<x>"], recommended_actions: ["fix"] });
  assert(riskHtml.includes("&lt;risk&gt;") && !riskHtml.includes("<script>"), "risk rendering must escape text and sanitize classes");

  let apiRequest = null;
  context.fetch = async function(url, options) {
    apiRequest = { url, options };
    return { json: async () => ({ ok: true, value: 42 }) };
  };
  const apiOk = await context.ApiClient.post("/api/demo?x=1", { alpha: "A1" });
  assert(apiOk.value === 42, "api-client must return successful payload");
  assert(apiRequest.url === "/api/demo?x=1", "api-client must preserve local api path");
  assert(apiRequest.options.headers["X-Brain-Alpha-CSRF"], "api-client must send csrf header");
  context.fetch = async function() { return { json: async () => ({ ok: false, error_code: "SUBMIT_BLOCKED", error: "raw" }) }; };
  let rejected = false;
  try { await context.ApiClient.get("/api/fail"); } catch (err) { rejected = err.code === "SUBMIT_BLOCKED" && err.message.includes("提交被安全门禁阻断"); }
  assert(rejected, "api-client must map backend error codes to user-facing messages");

  let notified = "";
  context.AppState.onUpdate(path => { notified = path; });
  context.AppState.set("currentResult.summary.produced_count", 7);
  assert(context.AppState.get("currentResult.summary.produced_count") === 7 && notified === "currentResult.summary.produced_count", "state set/get/listener contract failed");
  context.AppState.merge("currentResult.summary", { passed_count: 3 });
  assert(context.AppState.get("currentResult.summary.passed_count") === 3, "state merge contract failed");
  context.AppState.set("checkResults.A1", { passed: true, checked_at: new Date().toISOString(), checks: [{ name: "official_pre_submit_check", passed: true }] });
  assert(context.AppState.isSubmittable({ alpha_id: "A1" }), "state submittable helper must honor fresh official checks");

  assert(context.ViewModel.normalizedExpression(" rank( x ) ") === "rank( x )", "view-model normalization failed");
  assert(context.ViewModel.uniqueCandidates([{ alpha_id: "A1" }, { alpha_id: "A1" }]).length === 1, "view-model candidate dedupe failed");
  assert(context.ViewModel.chooseRuntimeArray([], [{ id: 1 }], [{ id: 2 }])[0].id === 1, "view-model runtime array choice failed");

  const toast = context.Toast.toast("<unsafe>", "error", 0);
  assert(toast.getAttribute("role") === "alert" && toast.innerHTML.includes("&lt;unsafe&gt;"), "toast must render safe alert markup");
  context.Spinner.showSpinner("Working");
  assert(!document.getElementById("spinnerOverlay").classList.contains("hidden") && document.getElementById("spinnerText").textContent === "Working", "spinner show contract failed");
  context.Spinner.hideSpinner();
  assert(document.getElementById("spinnerOverlay").classList.contains("hidden"), "spinner hide contract failed");

  context.Progress.renderProgress("progress", { percent: 150, message: "Sync", scanned: 2, total: 4, added: 1, skipped: 3 });
  assert(document.getElementById("progressFill").style.width === "100%", "progress must clamp fill width");
  assert(document.getElementById("progressMeta").textContent.includes("(2/4)") && document.getElementById("progressMeta").textContent.includes("已跳过 3"), "progress meta rendering failed");

  const confirmed = context.Modal.confirmAction("Continue?", "Yes", "No");
  assert(!document.getElementById("confirmOverlay").classList.contains("hidden"), "modal must show confirm overlay");
  document.getElementById("confirmYes").click();
  assert(await confirmed === true, "modal must resolve true from yes button");
  assert(document.getElementById("confirmOverlay").classList.contains("hidden"), "modal must hide after resolution");

  context.Table.render("tableRows", [{ accessor: "name" }, { accessor: row => row.raw.html, render: value => value, trustedHtml: false }], [{ kind: "candidate", id: "1", raw: { name: "<Alpha>", html: "<button>bad</button>" } }]);
  assert(document.getElementById("tableRows").innerHTML.includes("&lt;Alpha&gt;") && document.getElementById("tableRows").innerHTML.includes("&lt;button&gt;bad&lt;/button&gt;"), "table must escape untrusted values");
  context.Table.render("tableRows", [{ accessor: "name" }], [], { emptyText: "No rows" });
  assert(document.getElementById("tableRows").innerHTML.includes("No rows"), "table empty state rendering failed");

  ["chartFallback", "scoreTrendChart", "sharpeDistChart", "gatePieChart", "turnoverChart"].forEach(id => {
    const el = document.register(id, id.endsWith("Chart") ? "canvas" : "div");
    if (el.tagName === "CANVAS") {
      el.parentElement = { clientWidth: 360 };
      el.clientWidth = 360;
      el.clientHeight = 210;
    }
  });
  context.AppScoring = {
    candidateDisplayScore(candidate) { return (candidate.scorecard || {}).total_score || 0; },
    extractOfficialMetrics(candidate) { return candidate.official_metrics || {}; },
  };
  load(context, "js/views/charts.js");
  context.ChartView.renderCharts({ candidates: [{ alpha_id: "A1", scorecard: { total_score: 88, sharpe: 1.2, turnover: 0.18 }, gate: { submission_ready: true } }] });
  assert(document.getElementById("chartFallback").textContent.includes("内置离线图表"), "charts must expose offline fallback guidance");
  assert(document.getElementById("scoreTrendChart").drawOps.length > 0, "charts must draw to native canvas fallback");

  load(context, "js/views/detail.js");
  context.DetailView.renderCheckDetail({ alpha_id: "A1", passed: false, is_stale: false, checks: [{ name: "official_pre_submit_check", passed: false, suggestion: "Fix <bad>" }] });
  assert(document.getElementById("detail").innerHTML.includes("Fix &lt;bad&gt;"), "detail check suggestions must be escaped");
  assert(document.getElementById("detailModal").getAttribute("aria-hidden") === "false", "detail modal must become visible");

  load(context, "js/views/monitor.js");
  context.AppState.set("currentResult.candidates", [{ alpha_id: "A1", lifecycle_status: "submission_ready" }]);
  context.AppState.set("currentResult.summary", { stats: { produced_count: 5, passed_count: 1 }, dataset_id: "D1" });
  context.MonitorView.renderOpsMonitor();
  assert(document.getElementById("opsMonitor").innerHTML.includes("monitor-tile") && document.getElementById("opsMonitor").innerHTML.includes("D1"), "monitor must render stat tiles");
  context.MonitorView.renderBacktests([{ status: "running", alpha_id: "A1", sharpe: 1.2, fitness: 0.7 }]);
  assert(document.getElementById("backtestPanel").innerHTML.includes("monitor-slot") && document.getElementById("backtestPanel").innerHTML.includes("A1"), "monitor must render backtest slots");

  context.Toast.toast = function(message, type) { context.lastToast = { message, type }; };
  context.operationBlockReason = function(action) { return action === "production" ? "blocked by test" : ""; };
  context.renderBusyControls = function() { context.busyRendered = true; };
  context.collectPayload = function() { return {}; };
  load(context, "js/views/production.js");
  await context.startProduction();
  assert(context.lastToast.message === "blocked by test" && context.lastToast.type === "warning", "production module must honor operation guard before api calls");
  assert(typeof context.toggleRun === "function" && typeof context.connectSSE === "function" && typeof context.disconnectSSE === "function", "production module exports must remain available");

  console.log("frontend module contracts ok");
})().catch(err => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
"""
    assert "frontend module contracts ok" in _run_node_contract(script)


def test_app_ux_orchestrator_has_tested_navigation_empty_and_busy_contracts():
    app_js = (WEB_JS / "app.js").read_text(encoding="utf-8")
    template = (ROOT / "brain_alpha_ops" / "web" / "index_template.html").read_text(encoding="utf-8")

    for label in ["生产候选", "官方回测", "达标检查", "提交队列", "诊断复盘"]:
        assert label in app_js

    assert "function renderWorkflowNav()" in app_js
    assert "workflow-step " in app_js
    assert "aria-current=\"" in app_js
    assert "renderWorkflowNav();" in app_js
    assert "insightGroupHtml('辅助追踪与诊断', trackingCards, { collapsible: true" in app_js

    assert "function emptyStateHtml(view)" in app_js
    assert "function emptyStateActions(view)" in app_js
    assert "emptyStateHtml(view)" in app_js
    assert "table-empty-cell" in app_js
    assert "empty-mobile-card" in app_js
    assert "toggleRun()" in app_js
    assert "syncCloud()" in app_js
    assert "checkBatch('quick')" in app_js

    assert "function operationBlockReason(action)" in app_js
    assert "function renderBusyControls()" in app_js
    assert "setControlState('controlButton'" in app_js
    assert "setControlState('syncButton'" in app_js
    assert "operationGuard" in app_js

    assert 'id="workflowNav" class="workflow-nav"' in template
    assert "control-section primary run-actions" in template
    assert "status-strip" in template
    assert "view-guidance" in template


def test_ux_styles_cover_interaction_feedback_and_responsive_layout():
    template = (ROOT / "brain_alpha_ops" / "web" / "index_template.html").read_text(encoding="utf-8")

    for selector in [
        "button:focus-visible",
        ".workflow-step:hover:not(:disabled)",
        ".workflow-step.active",
        ".insight-item:hover",
        ".filter-chip:focus-visible",
        ".empty-state",
        ".empty-actions",
        ".mobile-card-list:not(.hidden)",
    ]:
        assert selector in template

    assert "@media (max-width: 1380px)" in template
    assert ".workflow-nav { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in template
    assert "@media (max-width: 720px)" in template
    assert ".row, .quick-links, .workflow-nav, .insight, .toolbar, .module-actions, .monitor, .monitor-stats, .monitor-slots, .kv { grid-template-columns: 1fr; }" in template
