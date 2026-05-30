from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

from scripts.check_frontend_syntax import _node_path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "brain_alpha_ops" / "web"
WEB_JS = ROOT / "brain_alpha_ops" / "web" / "js"
WEB_CSS = ROOT / "brain_alpha_ops" / "web" / "css"
TEMPLATE_PATH = WEB_DIR / "index_template.html"

MODULE_TEST_COVERAGE = {
    "js/api-client.js": "api request, csrf header, and error mapping",
    "js/app.js": "ux orchestration, workflow nav, busy guards, and app actions",
    "js/app-runtime.js": "runtime progress, operation locks, busy controls, and async job feedback",
    "js/components/modal.js": "confirm dialog visibility, focus, and resolution",
    "js/components/progress.js": "progress bar clamp and status text rendering",
    "js/components/spinner.js": "loading overlay visibility and message rendering",
    "js/components/table.js": "table empty/data rendering, badges, score formatting",
    "js/components/toast.js": "toast roles, escaping, and removal contract",
    "js/state.js": "nested state set/merge, listeners, cache, check freshness",
    "js/utils.js": "escaping, labels, risk/state navigation rendering",
    "js/form-controls.js": "form value writes, config hydration, and payload assembly",
    "js/header-status.js": "header connection status and profile summary rendering",
    "js/loading-feedback.js": "page-load progress, startup refreshes, and redline status hydration",
    "js/strategy-panel.js": "strategy policy summary and plugin-control state",
    "js/result-state.js": "result snapshot merging and cloud sync preservation",
    "js/result-table.js": "main result table, mobile cards, and empty-state rendering",
    "js/view-model.js": "identity, normalization, dedupe, runtime array selection",
    "js/view-registry.js": "view ordering, labels, navigation groups, and empty-state hints",
    "js/view-renderers.js": "result row sources, filters, and column renderer definitions",
    "js/workflow-assist.js": "keyboard shortcuts, quick-start wizard, and view transition wrapper",
    "js/cloud-sync.js": "production cloud snapshot loading, sync polling, and state hydration",
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
    querySelectorAll(selector) {
      if (selector === "[data-style-width]" || selector === "[data-style-left]") return [];
      return this.children;
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
    "insight", "backtestPanel", "controlButton", "status", "checkpointSummary"
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
  load(context, "js/view-registry.js");
  load(context, "js/view-renderers.js");
  load(context, "js/result-state.js");
  load(context, "js/result-table.js");
  load(context, "js/workflow-assist.js");
  load(context, "js/form-controls.js");
  load(context, "js/strategy-panel.js");
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
  assert(apiRequest.options.headers["X-Brain-Alpha-Request-ID"], "api-client must send replay request id on POST");
  assert(apiRequest.options.headers["X-Brain-Alpha-Request-Timestamp"], "api-client must send replay timestamp on POST");
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
  const viewRows = context.ViewRenderers.getRowsForView("passed", { candidates: [{ alpha_id: "A1", lifecycle_status: "submission_ready", gate: { submission_ready: true } }] });
  assert(viewRows.length === 1 && viewRows[0].kind === "passed", "view-renderers row source failed");
  const resultBatch = context.ResultState.buildResultBatch({ summary: { cloud_sync: { status: "empty" } }, candidates: [{ alpha_id: "A1" }] }, { currentSummary: {}, currentCandidates: [], liveCloudSyncProgress: () => ({ status: "running", scanned: 3 }) });
  assert(resultBatch["currentResult.summary"].cloud_sync.scanned === 3, "result-state must preserve active cloud progress over empty snapshots");
  const assist = context.AppEnhancements.create({
    $: id => document.getElementById(id),
    activeView: () => "candidates",
    state: context.AppState,
    registry: context.ViewRegistry,
    viewOrder: context.ViewRegistry.VIEW_ORDER,
    invokeWindowAction(name) { context.lastAssistAction = name; },
    renderCurrentView() { context.assistRendered = true; },
  });
  assert(assist.SHORTCUTS.length >= 4 && typeof assist.handleKeyboardShortcut === "function", "workflow assist must expose shortcut contracts");
  let switchedView = "";
  assist.wrapSwitchView(view => { switchedView = view; })("cloud");
  assert(switchedView === "cloud", "workflow assist must wrap view transitions");
  document.register("region", "select").value = "USA";
  document.register("universe", "select").value = "TOP3000";
  document.register("delay", "input").value = "1";
  document.register("neutralization", "select").value = "SUBINDUSTRY";
  document.register("instrumentType", "select").value = "EQUITY";
  document.register("alphaType", "select").value = "PYRAMID";
  document.register("decay", "input").value = "10";
  document.register("truncation", "input").value = "0.05";
  document.register("pasteurization", "select").value = "ON";
  document.register("nanHandling", "select").value = "ON";
  document.register("unitHandling", "select").value = "NONE";
  document.register("language", "select").value = "FASTEXPR";
  document.register("preset", "select").value = "atom_preset";
  document.register("environment", "select").value = "production";
  document.register("baseUrl", "input").value = "https://api.worldquantbrain.com";
  document.register("syncRange", "select").value = "7d";
  document.register("autoSubmitToggle", "input").type = "checkbox";
  document.getElementById("autoSubmitToggle").checked = true;
  document.register("useAssistantGuidance", "input").type = "checkbox";
  document.getElementById("useAssistantGuidance").checked = true;
  document.register("assistantGuidanceMinConfidence", "input").value = "0.7";
  document.register("assistantGuidanceScoreAdjustment", "input").type = "checkbox";
  document.getElementById("assistantGuidanceScoreAdjustment").checked = true;
  document.register("assistantGuidanceScoreMinConfidence", "input").value = "0.75";
  document.register("assistantGuidanceScoreMinOutcomeCount", "input").value = "2";
  document.register("assistantGuidanceScoreBonusCap", "input").value = "2.5";
  document.register("assistantGuidanceScorePenaltyCap", "input").value = "3.5";
  document.register("strategyPluginsEnabled", "input").type = "checkbox";
  document.getElementById("strategyPluginsEnabled").checked = true;
  document.register("strategyPluginSpecs", "textarea").value = "brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin";
  const formPayload = context.FormControls.collectPayload();
  assert(formPayload.settings.region === "USA", "form-controls must collect settings payload");
  assert(formPayload.settings.type === "PYRAMID", "form-controls must send backend alpha type key");
  assert(!Object.prototype.hasOwnProperty.call(formPayload.settings, "alphaType"), "form-controls must not emit stale alphaType key");
  assert(formPayload.settings.unitHandling === "NONE", "form-controls must preserve canonical unit handling NONE");
  assert(formPayload.autoSubmit === true, "form-controls must collect auto submit toggle");
  assert(formPayload.syncRange === "7d", "form-controls must collect cloud sync range");
  assert(formPayload.useAssistantGuidance === true, "form-controls must emit canonical guidance key");
  assert(formPayload.assistantGuidanceMinConfidence === 0.7, "form-controls must collect guidance confidence");
  assert(formPayload.assistantGuidanceScoreAdjustment === true, "form-controls must collect scoring adjustment flag");
  assert(formPayload.assistantGuidanceScoreMinConfidence === 0.75, "form-controls must collect scoring confidence");
  assert(formPayload.assistantGuidanceScoreMinOutcomeCount === 2, "form-controls must collect scoring sample floor");
  assert(formPayload.assistantGuidanceScoreBonusCap === 2.5, "form-controls must collect scoring bonus cap");
  assert(formPayload.assistantGuidanceScorePenaltyCap === 3.5, "form-controls must collect scoring penalty cap");
  assert(formPayload.strategyPluginsEnabled === true, "form-controls must emit canonical plugin flag");
  assert(formPayload.strategyPluginSpecs.indexOf("ConservativeMeanReversionPlugin") !== -1, "form-controls must collect plugin specs");
  [
    "use_assistant_guidance",
    "assistant_guidance_min_confidence",
    "assistant_guidance_score_adjustment",
    "assistant_guidance_score_min_confidence",
    "strategy_plugins_enabled",
  ].forEach(key => assert(!Object.prototype.hasOwnProperty.call(formPayload, key), "form-controls must not emit stale snake_case key " + key));
  assert(context.FormControls.applyPreset({ atom_preset: { settings: { type: "ATOM", unitHandling: "RAW" } } }), "preset application should accept backend type key");
  assert(document.getElementById("alphaType").value === "ATOM", "preset type must update alphaType control");
  assert(document.getElementById("unitHandling").value === "RAW", "preset unit handling must update control");
  context.FormControls.applyConfig({
    environment: "production",
    auto_submit: false,
    ops: {
      official_api: { base_url: "https://api.worldquantbrain.com" },
      settings: {
        region: "EUR",
        universe: "TOP1000",
        delay: 0,
        neutralization: "MARKET",
        instrumentType: "EQUITY",
        type: "REGULAR",
        decay: 5,
        truncation: 0.08,
        pasteurization: "OFF",
        nanHandling: "OFF",
        unitHandling: "VERIFY",
        language: "FASTEXPR",
      },
      budget: {
        cloud_sync_range: "all",
        use_assistant_guidance: false,
        assistant_guidance_min_confidence: 0.8,
        strategy_plugins_enabled: true,
        strategy_plugin_specs: ["pkg:PluginA", "pkg:PluginB"],
      },
      scoring: {
        assistant_guidance_score_adjustment_enabled: false,
        assistant_guidance_score_min_confidence: 0.85,
        assistant_guidance_score_min_outcome_count: 4,
        assistant_guidance_score_bonus_cap: 1.5,
        assistant_guidance_score_penalty_cap: 2.5,
      },
    },
  });
  assert(document.getElementById("region").value === "EUR", "applyConfig must hydrate settings.region");
  assert(document.getElementById("alphaType").value === "REGULAR", "applyConfig must hydrate settings.type into alphaType");
  assert(document.getElementById("syncRange").value === "all", "applyConfig must hydrate cloud sync range");
  assert(document.getElementById("autoSubmitToggle").checked === false, "applyConfig must hydrate auto_submit");
  assert(document.getElementById("useAssistantGuidance").checked === false, "applyConfig must hydrate guidance flag");
  assert(document.getElementById("assistantGuidanceMinConfidence").value === "0.8", "applyConfig must hydrate guidance confidence");
  assert(document.getElementById("assistantGuidanceScoreAdjustment").checked === false, "applyConfig must hydrate scoring adjustment flag");
  assert(document.getElementById("assistantGuidanceScoreMinOutcomeCount").value === "4", "applyConfig must hydrate scoring sample floor");
  assert(document.getElementById("strategyPluginsEnabled").checked === true, "applyConfig must hydrate plugin flag");
  assert(document.getElementById("strategyPluginSpecs").value === "pkg:PluginA\npkg:PluginB", "applyConfig must hydrate plugin specs one per line");

  const toast = context.Toast.toast("<unsafe>", "error", 0);
  assert(toast.getAttribute("role") === "alert" && toast.innerHTML.includes("&lt;unsafe&gt;"), "toast must render safe alert markup");
  context.Spinner.showSpinner("Working");
  assert(!document.getElementById("spinnerOverlay").classList.contains("hidden") && document.getElementById("spinnerText").textContent === "Working", "spinner show contract failed");
  context.Spinner.hideSpinner();
  assert(document.getElementById("spinnerOverlay").classList.contains("hidden"), "spinner hide contract failed");

  context.Progress.renderProgress("progress", { percent: 150, message: "Sync", scanned: 2, total: 4, added: 1, skipped: 3, eta_seconds: 65 });
  assert(document.getElementById("progressFill").style.width === "100%", "progress must clamp fill width");
  assert(context.Utils.renderSafeHtmlFragment('<img src=x onerror=alert(1)>', 'badge').includes("&lt;img"), "safe fragment helper must reject dangerous tags");
  assert(context.Utils.renderSafeHtmlFragment(context.Utils.statusBadge("OK", "good"), "badge").includes("badge-success"), "safe fragment helper must allow whitelisted badges");
  assert(document.getElementById("progressMeta").textContent.includes("2/4") && document.getElementById("progressMeta").textContent.includes("跳过 3"), "progress meta rendering failed");
  assert(document.getElementById("progressMeta").textContent.includes("预计剩余"), "progress meta must render ETA countdown text");

  const confirmed = context.Modal.confirmAction("Continue?", "Yes", "No");
  assert(!document.getElementById("confirmOverlay").classList.contains("hidden"), "modal must show confirm overlay");
  document.getElementById("confirmYes").click();
  assert(await confirmed === true, "modal must resolve true from yes button");
  assert(document.getElementById("confirmOverlay").classList.contains("hidden"), "modal must hide after resolution");

  context.Table.render("tableRows", [{ accessor: "name" }, { accessor: row => row.raw.html, render: value => value, trustedHtml: true }], [{ kind: "candidate", id: "1", raw: { name: "<Alpha>", html: "<button>bad</button>" } }]);
  assert(document.getElementById("tableRows").innerHTML.includes("&lt;Alpha&gt;") && document.getElementById("tableRows").innerHTML.includes("&lt;button&gt;bad&lt;/button&gt;"), "table must escape untrusted values");
  context.Table.render("tableRows", [{ accessor: row => row.raw.status, render: value => context.Utils.statusBadge(value, "good"), htmlType: "badge" }], [{ kind: "candidate", id: "2", raw: { status: "OK" } }]);
  assert(document.getElementById("tableRows").innerHTML.includes("badge-success"), "table must render whitelisted badge fragments");
  context.Table.render("tableRows", [{ accessor: row => row.raw.html, render: value => value, htmlType: "badge" }], [{ kind: "candidate", id: "3", raw: { html: '<span class="badge badge-success" onclick="alert(1)">bad</span>' } }]);
  assert(document.getElementById("tableRows").innerHTML.includes("&lt;span") && !document.getElementById("tableRows").innerHTML.includes('<span class="badge badge-success" onclick='), "table must reject malformed whitelisted fragments");
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
  assert(document.getElementById("chartFallback").textContent.includes("Chart.js 未加载"), "charts must expose offline fallback guidance");
  assert(document.getElementById("chartFallback").textContent.includes("本地 canvas"), "charts must explain local canvas fallback");
  assert(document.getElementById("scoreTrendChart").drawOps.length > 0, "charts should draw native fallback without Chart.js");
  assert(document.getElementById("gatePieChart").drawOps.includes("arc"), "native fallback should render a gate pie chart");

  load(context, "js/views/detail.js");
  context.DetailView.viewCheckDetail({ alpha_id: "A1", passed: false, is_stale: false, checks: [{ name: "official_pre_submit_check", passed: false, suggestion: "Fix <bad>" }] });
  assert(document.getElementById("detail").innerHTML.includes("Fix &lt;bad&gt;"), "detail check suggestions must be escaped");
  assert(document.getElementById("detailModal").getAttribute("aria-hidden") === "false", "detail modal must become visible");

  load(context, "js/views/monitor.js");
  context.AppState.set("currentResult.candidates", [{ alpha_id: "A1", lifecycle_status: "submission_ready" }]);
  context.AppState.set("currentResult.summary", { stats: { produced_count: 5, passed_count: 1 }, dataset_id: "D1" });
  context.MonitorView.renderOpsMonitor();
  assert(document.getElementById("opsMonitor").innerHTML.includes("stat-tile") && document.getElementById("opsMonitor").innerHTML.includes("D1"), "monitor must render stat tiles");
  context.MonitorView.renderBacktests([{ status: "running", alpha_id: "A1", sharpe: 1.2, fitness: 0.7 }]);
  assert(document.getElementById("backtestPanel").innerHTML.includes("slot-card") && document.getElementById("backtestPanel").innerHTML.includes("A1"), "monitor must render backtest slots");

  context.Toast.toast = function(message, type) { context.lastToast = { message, type }; };
  context.Toast.warning = function(message) { context.lastToast = { message, type: "warning" }; };
  context.operationBlockReason = function(action) { return action === "production" ? "blocked by test" : ""; };
  context.renderBusyControls = function() { context.busyRendered = true; };
  context.collectPayload = function() { return {}; };
  load(context, "js/views/production.js");
  context.fetch = async function(url) {
    if (url === "/api/checkpoint/status") {
      return { json: async () => ({ ok: true, checkpoint_count: 1, history_count: 2, resume_available: true, latest: { run_id: "run_1", phase_completed: "redline" }, latest_history: { run_id: "run_1", status: "completed" }, latest_comparison: { deltas: { best_score: 10.5, submission_ready: 2 } } }) };
    }
    return { json: async () => ({ ok: true }) };
  };
  await context.loadCheckpointStatus();
  assert(document.getElementById("checkpointSummary").textContent.includes("断点可续跑") && document.getElementById("checkpointSummary").textContent.includes("历史 2"), "production module must render checkpoint and history status");
  assert(document.getElementById("checkpointSummary").textContent.includes("10.5"), "production module must render score delta");
  await context.startProduction();
  assert(context.lastToast.message === "blocked by test" && context.lastToast.type === "warning", "production module must honor operation guard before api calls");
  assert(typeof context.toggleRun === "function" && typeof context.connectSSE === "function" && typeof context.disconnectSSE === "function" && typeof context.loadCheckpointStatus === "function", "production module exports must remain available");

  console.log("frontend module contracts ok");
})().catch(err => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
"""
    assert "frontend module contracts ok" in _run_node_contract(script)


def test_app_ux_orchestrator_has_tested_navigation_empty_and_busy_contracts():
    app_js = (WEB_JS / "app.js").read_text(encoding="utf-8")
    app_runtime_js = (WEB_JS / "app-runtime.js").read_text(encoding="utf-8")
    view_registry_js = (WEB_JS / "view-registry.js").read_text(encoding="utf-8")
    view_renderers_js = (WEB_JS / "view-renderers.js").read_text(encoding="utf-8")
    result_table_js = (WEB_JS / "result-table.js").read_text(encoding="utf-8")
    strategy_panel_js = (WEB_JS / "strategy-panel.js").read_text(encoding="utf-8")
    template = (ROOT / "brain_alpha_ops" / "web" / "index_template.html").read_text(encoding="utf-8")

    for label in ["生产流程", "数据审计", "研究工具", "达标检查", "可提交"]:
        assert label in (app_js + view_registry_js + view_renderers_js)

    assert "function renderViewTabs()" in app_js
    assert "function renderTaskRail()" in app_js
    assert "VIEW_GROUPS" in view_registry_js
    assert "view-tab-group" in app_js
    assert "tab-marker" in app_js
    assert "view-tab-row" in app_js
    assert "workflow-rail" in template
    assert "workflowStepProduce" in template
    assert "workflowStepCheck" in template
    assert "workflowStepSubmit" in template
    assert "workflowStepCloud" in template
    assert "workflowStatusText" in app_js
    assert "workflowCandidateCount" in app_js
    assert 'role="tab"' in app_js
    assert 'aria-selected="' in app_js
    assert 'aria-controls="mainContent"' in app_js
    assert "renderViewTabs();" in app_js
    assert "renderInsight" in app_js

    assert "function getEmptyDescription(view)" in result_table_js
    assert "function getEmptyActionsHtml(view)" in result_table_js
    assert "tableEmptyState" in result_table_js
    assert "tableEmptyDescription" in result_table_js
    assert "tableEmptyActions" in result_table_js
    assert "tableEmptyIcon" in result_table_js
    assert "clear-search" in result_table_js
    assert 'data-action="toggle-run"' in template
    assert 'data-action="sync-cloud"' in template
    assert 'data-action="check-batch"' in template
    assert "function installStaticActionHandlers()" in app_js
    assert "function getRowsForView" in view_renderers_js
    assert "function getColumnsForView" in view_renderers_js
    assert "function buildCandidateRows" in view_renderers_js

    assert "function operationBlockReason(action)" in app_runtime_js
    assert "function renderBusyControls()" in app_runtime_js
    assert "function syncStrategyPluginControls()" in app_js
    assert "function syncPluginControls()" in strategy_panel_js
    assert "function renderPolicy(config)" in strategy_panel_js
    assert "setControlState('controlButton'" in app_runtime_js
    assert "setControlState('syncButton'" in app_runtime_js
    assert "setControlState('sideSyncButton'" in app_runtime_js
    assert "setControlState('sideCheckButton'" in app_runtime_js
    assert "sideTaskReason" in app_runtime_js
    assert "operationGuard" in app_runtime_js
    assert "function syncStartupState(snapshot)" in app_js
    assert "window.LoadingFeedback" in (WEB_JS / "loading-feedback.js").read_text(encoding="utf-8")

    assert 'id="viewTabs"' in template
    assert "action-card" in template
    assert "task-console-actions" in template
    assert 'id="sideSyncButton"' in template
    assert 'id="sideCheckButton"' in template
    assert 'id="sideSubmitButton"' in template
    assert 'id="strategyPluginSpecsGroup"' in template
    assert 'data-change-action="toggle-strategy-plugins"' in template
    assert 'id="strategyPluginSpecsHelp"' in template
    assert "status-bar" in template
    assert "status-pill" in template
    assert "panelHint" in template


def test_ux_styles_cover_interaction_feedback_and_responsive_layout():
    template = (ROOT / "brain_alpha_ops" / "web" / "index_template.html").read_text(encoding="utf-8")
    css = (WEB_CSS / "app.css").read_text(encoding="utf-8")

    for selector in [
        ".btn:focus-visible",
        ".view-tab:hover",
        ".view-tab.is-active",
        ".insight-tile:hover",
        ".filter-chip:focus-visible",
        ".workflow-step:hover",
        ".workflow-step.is-active",
        ".workflow-actions",
        ".task-console-actions",
        ".task-console-reason",
        ".status-pill",
        ".data-table-wrap.is-empty",
        ".empty-state",
        ".empty-state-actions",
        ".form-group.is-disabled",
        ".policy-card.is-wide",
        ".mobile-cards{display:none",
    ]:
        assert selector in css

    assert '<!-- inline-css:css/app.css -->' in template
    assert "@media(max-width:1200px)" in css
    assert "overflow-x:visible;overflow-y:visible" in css
    assert ".form-select{padding-right:34px;text-overflow:ellipsis}" in css
    assert ".sidebar-body > .action-card" in css
    assert ".app-content{order:1;min-height:auto}" in css
    assert ".app-sidebar{order:2;position:static;max-height:none}" in css
    assert "@media(max-width:640px)" in css
    assert ".view-tab{min-width:128px;max-width:160px}" in css
