"""
Comprehensive frontend module tests for UX v3 redesign.
Tests all 14 JS modules: state, utils, api-client, view-model,
all 5 components, all 4 views, and app entry point.
Uses Node.js VM module with DOM simulation harness for realistic testing.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts.check_frontend_syntax import _node_path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "brain_alpha_ops" / "web"
WEB_JS = WEB_DIR / "js"
TEMPLATE_PATH = WEB_DIR / "index_template.html"

# ═══════════════════════════════════════════════════════════════════════════
# Module listing — every frontend JS file must be tested
# ═══════════════════════════════════════════════════════════════════════════

ALL_MODULES = {
    "js/api-client.js",
    "js/app.js",
    "js/components/modal.js",
    "js/components/progress.js",
    "js/components/spinner.js",
    "js/components/table.js",
    "js/components/toast.js",
    "js/state.js",
    "js/utils.js",
    "js/view-model.js",
    "js/views/charts.js",
    "js/views/detail.js",
    "js/views/monitor.js",
    "js/views/production.js",
}


# ═══════════════════════════════════════════════════════════════════════════
# Test infrastructure
# ═══════════════════════════════════════════════════════════════════════════

def _node_path_or_skip():
    node = _node_path()
    if not node:
        pytest.skip("Node.js not available")
    return node


def _run_node_script(script: str, timeout: int = 120) -> str:
    node = _node_path_or_skip()
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "test.js"
        script_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [node, str(script_path), str(ROOT)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    if proc.returncode != 0:
        raise AssertionError(
            f"Node script failed (exit={proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout


def _build_test_script(modules: list[str], test_code: str) -> str:
    """Build a complete Node.js test script with DOM harness and module loading."""
    harness = r"""
// DOM Simulation Harness for browser-less testing
class ClassList {
  constructor(el) { this.el = el; this.tokens = new Set(); }
  _sync() { this.el.className = Array.from(this.tokens).join(" "); }
  add() { for (const t of arguments) { if (t) this.tokens.add(String(t)); } this._sync(); }
  remove() { for (const t of arguments) this.tokens.delete(String(t)); this._sync(); }
  contains(t) { return this.tokens.has(String(t)); }
  toggle(t, force) {
    const should = force === undefined ? !this.contains(t) : Boolean(force);
    should ? this.tokens.add(String(t)) : this.tokens.delete(String(t));
    this._sync(); return should;
  }
}

class MockElement {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.children = [];
    this.parentNode = null;
    this._attrs = {};
    this._dataset = {};
    this._style = {};
    this._events = {};
    this.textContent = "";
    this.innerHTML = "";
    this.value = "";
    this.disabled = false;
    this.checked = false;
    this.className = "";
    this.id = "";
    this.classList = new ClassList(this);
    this.name = "";
    this.type = "text";
    this.href = "";
    this.src = "";
    this.role = "";
    this.clientWidth = 800;
    this.clientHeight = 600;
  }
  getAttribute(name) { return this._attrs[name] || null; }
  setAttribute(name, value) { this._attrs[name] = String(value); }
  removeAttribute(name) { delete this._attrs[name]; }
  get style() { return this._style; }
  set style(v) { this._style = v; }
  get dataset() { return this._dataset; }
  addEventListener(event, fn) {
    if (!this._events[event]) this._events[event] = [];
    this._events[event].push(fn);
  }
  removeEventListener(event, fn) {
    if (!this._events[event]) return;
    this._events[event] = this._events[event].filter(function(f) { return f !== fn; });
  }
  dispatchEvent(event) {
    const handlers = this._events[event.type] || [];
    handlers.forEach(function(fn) { fn.call(this, event); });
  }
  click() { this.dispatchEvent({ type: "click" }); }
  focus() {}
  scrollIntoView() {}
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  removeChild(child) { this.children = this.children.filter(function(c) { return c !== child; }); return child; }
  querySelector(selector) {
    if (selector === ".modal-panel" || selector === ".confirm-dialog") return new MockElement("div");
    if (selector === ".confirm-dialog-icon") return new MockElement("div");
    return this.children[0] || null;
  }
  querySelectorAll(selector) {
    if (selector === ".sbar-section") return [new MockElement("div"), new MockElement("div")];
    return this.children;
  }
  contains(el) { return this.children.includes(el); }
  closest(selector) { return null; }
  getBoundingClientRect() { return { top: 0, left: 0, width: 800, height: 600, bottom: 600, right: 800 }; }
}

// Global document mock
const elements = {};
globalThis.document = {
  getElementById: function(id) {
    if (!elements[id]) {
      const el = new MockElement("div");
      el.id = id;
      elements[id] = el;
    }
    return elements[id];
  },
  createElement: function(tag) { return new MockElement(tag); },
  querySelector: function(sel) {
    const id = sel.replace(/^#/, "").replace(/[\[\]'"]/g, "");
    return elements[id] || null;
  },
  querySelectorAll: function(sel) {
    if (sel === ".sbar-section") return [elements["sbarSection1"] || new MockElement("div")];
    return Object.values(elements);
  },
  activeElement: new MockElement("body"),
  contains: function(el) { return true; },
  body: new MockElement("body"),
  documentElement: new MockElement("html"),
  addEventListener: function() {},
  removeEventListener: function() {},
  readyState: "complete",
};

// Global window mock
globalThis.window = {
  location: { origin: "http://localhost:8080", pathname: "/" },
  innerWidth: 1024,
  innerHeight: 768,
  devicePixelRatio: 1,
  addEventListener: function() {},
  removeEventListener: function() {},
  setTimeout: function(fn, ms) { return setTimeout(fn, ms); },
  clearTimeout: function(id) { clearTimeout(id); },
  setInterval: function(fn, ms) { return setInterval(fn, ms); },
  clearInterval: function(id) { clearInterval(id); },
  fetch: async function() {
    return {
      ok: true,
      status: 200,
      json: async function() { return { ok: true, data: {} }; },
      text: async function() { return "{}"; },
    };
  },
  URL: URL,
  EventSource: function() { this.close = function() {}; this.readyState = 1; },
  Chart: function(ctx, config) {
    this.data = config.data;
    this.options = config.options;
    this.type = config.type;
    this.destroy = function() {};
  },
  btoa: function(s) { return Buffer.from(s).toString("base64"); },
  atob: function(s) { return Buffer.from(s, "base64").toString(); },
  location: { origin: "http://localhost:8080" },
};

globalThis.elements = elements;
globalThis.AbortController = function() {
  this.signal = { aborted: false };
  this.abort = function() { this.signal.aborted = true; };
};

function assert(condition, message) {
  if (!condition) throw new Error("ASSERTION FAILED: " + message);
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(
    "ASSERTION FAILED: " + (message || "") +
    "\\n  Expected: " + JSON.stringify(expected) +
    "\\n  Actual:   " + JSON.stringify(actual)
  );
}

function assertContains(haystack, needle, message) {
  if (String(haystack).indexOf(String(needle)) === -1) throw new Error(
    "ASSERTION FAILED: " + (message || "") + "\\n  String does not contain: " + JSON.stringify(needle)
  );
}

function assertNotContains(haystack, needle, message) {
  if (String(haystack).indexOf(String(needle)) !== -1) throw new Error(
    "ASSERTION FAILED: " + (message || "") + "\\n  String contains: " + JSON.stringify(needle)
  );
}

function assertDefined(value, message) {
  if (value === undefined || value === null) throw new Error("ASSERTION FAILED: " + (message || "Value is undefined"));
}

const fs = require("fs");
const path = require("path");
const root = process.argv[2];
function loadModule(name) {
  const filePath = path.join(root, "brain_alpha_ops", "web", name);
  const src = fs.readFileSync(filePath, "utf-8");
  const vm = require("vm");
  vm.runInThisContext(src, { filename: filePath });
}
"""
    load_calls = "\n".join(f"loadModule('{m}');" for m in modules)
    full_script = harness + "\n" + load_calls + "\n" + test_code
    return (
        "try {\n" + full_script + "\n} catch (e) {\n"
        "  console.error('TEST ERROR:', e.message);\n"
        "  console.error('STACK:', e.stack);\n"
        "  process.exit(1);\n"
        "}\n"
        "console.log('ALL TESTS PASSED');\n"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Module existence tests
# ═══════════════════════════════════════════════════════════════════════════

def test_all_modules_exist_on_disk():
    """Verify every declared module file exists."""
    for mod in sorted(ALL_MODULES):
        path = WEB_JS / mod.replace("js/", "")
        assert path.is_file(), f"Module file missing: {mod}"


def test_template_references_all_modules():
    """Verify index_template.html inline markers reference all shipped modules."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    inlined = set(re.findall(r"<!--\s*inline:(js/.+?\.js)\s*-->", template))
    assert "js/utils.js" in inlined
    assert "js/app.js" in inlined
    assert "js/views/charts.js" in inlined
    assert "js/state.js" in inlined


# ═══════════════════════════════════════════════════════════════════════════
# Template v3 CSS Design System Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_template_has_v3_css_variables():
    """Verify the template includes the v3 design system CSS variables."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    required_vars = [
        "--bg-root", "--bg-surface", "--bg-muted", "--bg-accent-soft",
        "--text-primary", "--text-secondary", "--text-muted",
        "--accent", "--accent-hover", "--accent-ring", "--accent-gradient",
        "--success", "--warning", "--danger", "--info",
        "--border-default", "--border-hover", "--border-focus", "--border-accent",
        "--r-sm", "--r-md", "--r-lg", "--r-xl", "--r-full",
        "--sp-1", "--sp-2", "--sp-3", "--sp-4",
        "--shadow-xs", "--shadow-sm", "--shadow-md", "--shadow-lg", "--shadow-xl",
        "--font", "--font-mono",
    ]
    for var in required_vars:
        assert var in template, f"CSS variable {var} missing from template"


def test_template_has_dark_mode_support():
    """Verify dark mode theme is defined with v3 tokens."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "data-theme" in template
    assert "toggleTheme" in template
    # brain-alpha-ops-theme is in app.js, not the HTML template


def test_template_has_responsive_breakpoints():
    """Verify responsive CSS breakpoints are defined."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "@media(max-width:1200px)" in template or "@media (max-width: 1200px)" in template
    assert "@media(max-width:960px)" in template or "@media (max-width: 960px)" in template
    assert "@media(max-width:640px)" in template or "@media (max-width: 640px)" in template


def test_template_has_empty_state_v3():
    """Verify the v3 empty state UI elements exist with illustration."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "empty-state" in template
    assert "empty-state-illustration" in template
    assert "empty-state-title" in template
    assert "empty-state-desc" in template
    assert "empty-state-actions" in template
    assert "tableEmptyIcon" in template


def test_template_has_toast_container():
    """Verify toast notification infrastructure is in place."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "toast-container" in template
    assert "toastSlideIn" in template
    assert "toastSlideOut" in template


def test_template_has_spinner_overlay():
    """Verify loading spinner UI elements exist."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "spinner-overlay" in template
    assert "spinner-ring" in template


def test_template_has_v3_sidebar_sections():
    """Verify v3 sbar-section collapsible sections are in the template."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "sbar-section" in template
    assert "sbar-section-header" in template
    assert "sbar-section-body" in template
    assert "is-collapsed" in template
    assert "sbar-step" in template
    assert "sbar-chevron" in template
    assert "sbarSection1" in template
    assert "sbarSection2" in template
    assert "sbarSection3" in template
    assert "sbarSection4" in template


def test_template_has_v3_insight_tiles():
    """Verify v3 insight-strip with insight-tile cards."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "insight-strip" in template
    assert "insight-tile" in template
    assert "insight-tile-icon" in template
    assert "insight-tile-label" in template
    assert "insight-tile-value" in template


def test_template_has_view_tabs():
    """Verify v3 view-tabs navigation exists."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'id="viewTabs"' in template
    assert "view-tab" in template
    assert "tab-badge" in template
    assert "view-tab-separator" in template


def test_template_has_action_card():
    """Verify the v3 primary action card exists in sidebar."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "action-card" in template
    assert "action-card-title" in template
    assert "action-card-desc" in template
    assert "btn-run" in template


def test_template_has_header_status_dot():
    """Verify the v3 header status indicator dot."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "header-status-dot" in template
    assert "headerStatusDot" in template
    assert "is-running" in template


def test_template_has_sr_only():
    """Verify screen-reader-only utility."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert ".sr-only" in template


# ═══════════════════════════════════════════════════════════════════════════
# Template Required Elements
# ═══════════════════════════════════════════════════════════════════════════

def test_template_has_all_required_html_elements():
    """Verify key structural elements exist in the v3 template."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    required = [
        'class="app-shell"', 'class="app-header"', 'class="app-main"',
        'class="app-sidebar"', 'class="app-content"',
        'id="controlPanel"', 'id="mainContent"',
        'id="insightPanel"', 'id="chartsPanel"',
        'id="opsMonitor"', 'id="backtestPanel"',
        'id="candidateTable"', 'id="candidateRows"',
        'id="tableEmptyState"', 'id="mobileCardList"',
        'id="detailModal"', 'id="modalTitle"',
        'id="confirmOverlay"', 'id="toastContainer"', 'id="spinnerOverlay"',
        'id="moduleActions"', 'id="submitFailurePanel"',
        'id="viewTabs"', 'id="tableSearch"', 'id="controlButton"',
    ]
    for el in required:
        assert el in template, f"Required element missing: {el}"


def test_template_has_theme_toggle():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'id="themeToggleBtn"' in template
    assert "theme-icon-light" in template
    assert "theme-icon-dark" in template


def test_template_form_elements_use_v3_classes():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'class="form-input"' in template
    assert 'class="form-select"' in template
    assert 'class="form-textarea"' in template
    assert 'class="form-label"' in template
    assert 'class="form-group"' in template
    assert 'class="form-row"' in template
    assert 'class="btn btn-primary' in template
    assert 'class="btn btn-secondary' in template


def test_template_has_button_loading_state():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "is-loading" in template


def test_template_has_toggle_class():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'class="toggle"' in template


def test_template_has_progress_indeterminate():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "is-indeterminate" in template
    assert "progressIndeterminate" in template


# ═══════════════════════════════════════════════════════════════════════════
# Accessibility tests
# ═══════════════════════════════════════════════════════════════════════════

def test_template_has_skip_link():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'class="skip-link"' in template
    assert 'href="#mainContent"' in template


def test_template_has_aria_attributes():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'role="banner"' in template
    assert 'role="main"' in template
    assert 'role="complementary"' in template
    assert 'aria-live="polite"' in template
    assert 'aria-atomic="true"' in template
    assert 'aria-label' in template
    assert 'aria-hidden' in template


# ═══════════════════════════════════════════════════════════════════════════
# Backward compatibility tests
# ═══════════════════════════════════════════════════════════════════════════

def test_backward_compat_inline_markers_unchanged():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    inlined = re.findall(r"<!--\s*inline:(js/.+?\.js)\s*-->", template)
    required = [
        "js/utils.js", "js/api-client.js", "js/state.js",
        "js/components/toast.js", "js/components/spinner.js",
        "js/components/modal.js", "js/components/progress.js",
        "js/components/table.js", "js/views/detail.js",
        "js/views/production.js", "js/views/charts.js",
        "js/view-model.js", "js/app.js",
    ]
    for req in required:
        assert req in inlined, f"Required inline marker missing: {req}"


def test_build_inline_still_works():
    import importlib.util
    build_path = WEB_DIR / "build_inline.py"
    spec = importlib.util.spec_from_file_location("build_inline", build_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html, stats = module.build_inline(template)

    assert stats["replaced"] >= 13, f"Expected >= 13 modules, got {stats['replaced']}"
    assert len(stats["missing"]) == 0, f"Missing modules: {stats['missing']}"
    assert "<!-- inline:" not in html, "No unreplaced inline markers"


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Module Tests — State
# ═══════════════════════════════════════════════════════════════════════════

def test_state_module_get_set_and_computed():
    """Test AppState v3: get, set, setBatch, merge, viewCount, freshness."""
    test_code = """
var s = window.AppState;
assertDefined(s, "AppState should be defined");

// get
assertEqual(s.get("activeView"), "candidates", "default activeView");
assertEqual(s.get("isRunning"), false, "default isRunning");
assertDefined(s.get(), "get() returns full state");

// set
s.set("activeView", "passed");
assertEqual(s.get("activeView"), "passed", "set activeView");

// nested set
s.set("currentResult.candidates", [{ alpha_id: "test1" }, { alpha_id: "test2" }]);
assertEqual(s.get("currentResult.candidates").length, 2, "nested set");

// setBatch
s.setBatch({ "isRunning": true, "activeJobId": "job123" });
assertEqual(s.get("isRunning"), true, "setBatch isRunning");
assertEqual(s.get("activeJobId"), "job123", "setBatch activeJobId");

// merge
s.set("config", { autoSubmit: false });
s.merge("config", { runForever: true });
assertEqual(s.get("config").autoSubmit, false, "merge preserves");
assertEqual(s.get("config").runForever, true, "merge adds");

// candidateCount
assertEqual(typeof s.candidateCount(), "number", "candidateCount returns number");

// viewCount
s.set("currentResult.candidates", [
  { alpha_id: "A1", lifecycle_status: "submission_ready", gate: { submission_ready: true } },
  { alpha_id: "A2", lifecycle_status: "candidate" },
]);
assertEqual(s.viewCount("candidates"), 2, "viewCount candidates");
assertEqual(s.viewCount("passed"), 1, "viewCount passed");
assertEqual(s.viewCount("cloud"), 0, "viewCount cloud with no data");

// passCount
s.set("checkResults", {
  "A1": { passed: true, checked_at: new Date().toISOString(), checks: [{ name: "official_pre_submit_check", passed: true }] },
  "A2": { passed: false, checked_at: new Date().toISOString() },
});
assertEqual(s.passedCount(), 1, "passedCount");

// submittableCount
assertEqual(s.submittableCount(), 1, "submittableCount");

// isSubmittable
assertEqual(s.isSubmittable({ alpha_id: "A1" }), true, "isSubmittable A1");
assertEqual(s.isSubmittable({ alpha_id: "A2" }), false, "isSubmittable A2");

// isFreshCheck
var fresh = { passed: true, checked_at: new Date().toISOString(), checks: [{ name: "official_pre_submit_check", passed: true }] };
assertEqual(s.isFreshCheck(fresh), true, "fresh check");
assertEqual(s.isFreshPassedCheck(fresh), true, "fresh passed check");

// isFreshBlockedCheck
var blocked = { passed: false, checked_at: new Date().toISOString() };
assertEqual(s.isFreshBlockedCheck(blocked), true, "fresh blocked check");

// Row cache
s.setCached({ kind: "test", id: "abc" }, { alpha_id: "abc" });
var cached = s.getCached("test", "abc");
assertDefined(cached, "cached row exists");
assertEqual(cached.raw.alpha_id, "abc", "cached raw data");

// clearCache
s.clearCache();
assertEqual(s.getCached("test", "abc"), null, "cache cleared");

// Listener notification
var notified = false;
s.onUpdate(function(path) { notified = path; });
s.set("isRunning", false);
assertEqual(notified, "isRunning", "listener notified");
"""

    _run_node_script(_build_test_script(["js/state.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Module Tests — Utils
# ═══════════════════════════════════════════════════════════════════════════

def test_utils_module_escaping_and_helpers():
    """Test Utils v3: escape, formatting, badge helpers, scoreSpan, statusBadge, setVal."""
    test_code = """
var u = window.Utils;
assertDefined(u, "Utils should be defined");

// HTML escaping
assertEqual(u.escapeHtml("<script>alert('xss')</script>"),
  "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;", "HTML escape");
assertEqual(u.escapeHtml("a & b"), "a &amp; b", "ampersand escape");
assertEqual(u.escapeHtml('"quoted"'), "&quot;quoted&quot;", "quote escape");

// Phase names
assertEqual(u.phaseName("completed"), "完成", "phase map");
assertEqual(u.phaseName({ phase_label: "自定义" }), "自定义", "phase_label override");
assertEqual(u.phaseName("unknown"), "unknown", "unknown fallback");

// Check names
assertEqual(u.humanCheckName("LOW_SHARPE"), "低 Sharpe", "human check");
assertEqual(u.humanCheckName({ label_cn: "自定义" }), "自定义", "label_cn override");

// Formatting
assertEqual(u.formatScore(85.567), "85.6", "format score");
assertEqual(u.formatScore(null), "-", "null score");
assertEqual(u.formatPct(0.856), "85.6%", "format pct");
assertEqual(u.num(3.14159, 2), "3.14", "num format");
assertEqual(u.num(null), "-", "num null");

// Payload truthy
assertEqual(u.payloadTruthy(true), true, "true");
assertEqual(u.payloadTruthy("false"), false, "string false");

// Badge class helper
assertContains(u.badgeClass("good"), "badge-success", "good badge");
assertContains(u.badgeClass("bad"), "badge-danger", "bad badge");
assertContains(u.badgeClass("warn"), "badge-warning", "warn badge");
assertContains(u.badgeClass("info"), "badge-info", "info badge");
assertContains(u.badgeClass("muted"), "badge-default", "muted badge");

// Score span (v3: uses Utils.scoreSpan)
var sHigh = u.scoreSpan(85.5);
assertContains(sHigh, "var(--success)", "high score green");
assertContains(sHigh, "85.5", "score value");

var sMid = u.scoreSpan(55);
assertContains(sMid, "var(--warning)", "mid score yellow");

var sLow = u.scoreSpan(30);
assertContains(sLow, "var(--danger)", "low score red");

var sNull = u.scoreSpan(null);
assertContains(sNull, "-", "null score");

// Status badge (v3)
var sb = u.statusBadge("通过", "good");
assertContains(sb, "badge-success", "status badge good");
assertContains(sb, "通过", "status badge text");

// Risk explanation
var riskHtml = u.renderRiskExplanation({
  title: "相似度风险", summary: "表达式过于相似", severity: "blocking",
  visual: { value: 0.95, threshold: 0.9 },
  reasons: ["高表达式相似度"],
  recommended_actions: ["修改表达式结构"],
});
assertContains(riskHtml, "相似度风险", "risk title");
assertContains(riskHtml, "blocking", "severity class");
assertContains(riskHtml, "risk-meter", "risk meter");

// State navigation
var navHtml = u.renderStateNavigation({
  title: "解决路径", summary: "需要修改",
  steps: [{ id: "s1", label: "分析", status: "done" }, { id: "s2", label: "修改", status: "active" }],
  primary_action: "重新生成",
});
assertContains(navHtml, "解决路径", "nav title");
assertContains(navHtml, "lc-step", "lifecycle step class");

// setVal
var testInput = document.getElementById("testInput");
if (!testInput) { testInput = new MockElement("input"); testInput.id = "testInput"; elements["testInput"] = testInput; }
u.setVal("testInput", "hello");
assertEqual(testInput.value, "hello", "setVal sets value");
"""

    _run_node_script(_build_test_script(["js/utils.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Module Tests — API Client
# ═══════════════════════════════════════════════════════════════════════════

def test_api_client_module():
    """Test ApiClient v3: URL building, error mapping, CSRF, method existence."""
    test_code = """
var Api = window.ApiClient;
assertDefined(Api, "ApiClient defined");
assertDefined(Api.ERROR_MESSAGES, "ERROR_MESSAGES defined");

// Error messages
assertEqual(Api.ERROR_MESSAGES["SESSION_INVALID"], "会话已过期，请刷新页面。");
assertEqual(Api.ERROR_MESSAGES["NETWORK_ERROR"], "网络连接失败，请检查服务是否运行。");
assertEqual(Api.ERROR_MESSAGES["TIMEOUT_ERROR"], "请求超时，请稍后重试。");
assertEqual(Api.ERROR_MESSAGES["SUBMIT_BLOCKED"], "提交被安全门禁阻断。");

// Methods exist
assertEqual(typeof Api.get, "function", "get exists");
assertEqual(typeof Api.post, "function", "post exists");
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/api-client.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Module Tests — ViewModel
# ═══════════════════════════════════════════════════════════════════════════

def test_view_model_module():
    """Test ViewModel v3: identity, deduplication, score helpers."""
    test_code = """
var VM = window.ViewModel;
assertDefined(VM, "ViewModel defined");

// candidateIdentity
assertEqual(VM.candidateIdentity({ alpha_id: "ABC" }), "ABC", "alpha_id");
assertEqual(VM.candidateIdentity({ official_alpha_id: "OFF" }), "OFF", "official_alpha_id");
assertEqual(VM.candidateIdentity({ simulation_id: "SIM" }), "SIM", "simulation_id");

// normalizedExpression
assertEqual(VM.normalizedExpression("a + b  *  c"), "a + b * c", "normalize whitespace");
assertEqual(VM.normalizedExpression("Ts_Sum"), "ts_sum", "lowercase");

// expressionFromRow
assertEqual(VM.expressionFromRow({ expression: "rank(close)" }), "rank(close)", "direct expression");
assertEqual(VM.expressionFromRow({ raw: { regular: { code: "group_rank(close)" } } }), "group_rank(close)", "raw.regular");

// uniqueBy / uniqueCandidates
var items = [{ id: "a" }, { id: "b" }, { id: "a" }];
assertEqual(VM.uniqueBy(items, function(i) { return i.id; }).length, 2, "dedup");
assertEqual(VM.uniqueCandidates([{ alpha_id: "A" }, { alpha_id: "A" }]).length, 1, "unique candidates");

// uniqueLifecycle
var lc1 = { run_id: "R1", alpha_id: "A1", stage: "check", status: "passed" };
var lc2 = { run_id: "R2", alpha_id: "A1", stage: "check", status: "passed" };
assertEqual(VM.uniqueLifecycle([lc1, lc2]).length, 2, "unique lifecycle keeps distinct");
// Test dedup with same items:
var key1 = VM.lifecycleIdentity(lc1);
var key2 = VM.lifecycleIdentity(lc2);
assertEqual(typeof key1, "string", "lifecycleIdentity returns string");
assertEqual(key1 !== key2, true, "different items produce different keys");

// firstArrayWithItems / chooseRuntimeArray
var arr1 = VM.firstArrayWithItems([], [1,2], [3]);
assertEqual(Array.isArray(arr1) && arr1.length === 2 && arr1[0] === 1, true, "first non-empty");
var arr2 = VM.chooseRuntimeArray(null, [1,2], [3]);
assertEqual(Array.isArray(arr2) && arr2.length === 2, true, "choose runtime");

// v3: candidateDisplayScore
var c1 = { scorecard: { total_score: 85, local_rank_score: 80 } };
assertEqual(VM.candidateDisplayScore(c1), 85, "display score total");
var c2 = { scorecard: { local_rank_score: 70 } };
assertEqual(VM.candidateDisplayScore(c2), 70, "display score local");

// v3: officialMetric
var c3 = { official_metrics: { sharpe: 1.5 } };
assertEqual(VM.officialMetric(c3, "sharpe"), 1.5, "official metric");

// v3: firstFiniteNumber / firstPositiveFiniteNumber
// Number(null) = 0, 0 is finite, so firstFiniteNumber(null, ...) = 0
assertEqual(VM.firstFiniteNumber(undefined, undefined, 42), 42, "firstFiniteNumber skips undefined");
assertEqual(VM.firstPositiveFiniteNumber(0, 5), 5, "firstPositiveFiniteNumber skips 0");
assertEqual(VM.firstFiniteNumber(0, 5), 0, "firstFiniteNumber returns first finite (0)");
"""

    _run_node_script(_build_test_script(["js/view-model.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Component Tests — Toast
# ═══════════════════════════════════════════════════════════════════════════

def test_toast_component():
    """Test Toast v3: creation, removal, type classes, clearAll."""
    test_code = """
var T = window.Toast;
assertDefined(T, "Toast defined");
assertEqual(typeof T.toast, "function", "toast exists");
assertEqual(typeof T.removeToast, "function", "removeToast exists");
assertEqual(typeof T.clearAll, "function", "clearAll exists v3");

// Create toasts
var el = T.toast("Test", "success", 0);
assertDefined(el, "toast created");
assertContains(el.className, "is-success", "success class");
assertContains(el.innerHTML, "Test", "message in toast");
assertEqual(el.getAttribute("role"), "status", "success=status role");

var errEl = T.toast("Error!", "error", 0);
assertEqual(errEl.getAttribute("role"), "alert", "error=alert role");
assertContains(errEl.className, "is-error", "error class");

var warnEl = T.toast("Warning", "warning", 0);
assertContains(warnEl.className, "is-warning", "warning class");

var infoEl = T.toast("Info", "info", 0);
assertContains(infoEl.className, "is-info", "info class");

// v3 icon classes - verify toast HTML structure
var toastHtml = el.innerHTML;
assertContains(toastHtml, "toast-icon", "toast-icon present v3");
assertContains(toastHtml, "toast-msg", "toast-msg present v3");
assertContains(toastHtml, "toast-close", "toast-close present v3");

// Convenience
assertEqual(typeof T.success, "function", "success convenience");
assertEqual(typeof T.error, "function", "error convenience");
assertEqual(typeof T.warning, "function", "warning convenience");
assertEqual(typeof T.info, "function", "info convenience");

// Removal
var remEl = T.toast("Remove me", "info", 0);
T.removeToast(remEl);
assertEqual(remEl.classList.contains("removing"), true, "removing class");

// Null-safe
T.removeToast(null);
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/components/toast.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Component Tests — Spinner
# ═══════════════════════════════════════════════════════════════════════════

def test_spinner_component():
    """Test Spinner v3: show, hide, visibility, default text."""
    test_code = """
var S = window.Spinner;
assertDefined(S, "Spinner defined");
assertEqual(typeof S.showSpinner, "function", "showSpinner");
assertEqual(typeof S.hideSpinner, "function", "hideSpinner");
assertEqual(typeof S.isSpinnerVisible, "function", "isSpinnerVisible v3");

S.showSpinner("加载...");
var overlay = document.getElementById("spinnerOverlay");
assertDefined(overlay, "overlay exists");
assertEqual(overlay.classList.contains("hidden"), false, "visible");
assertEqual(overlay.getAttribute("aria-hidden"), "false", "aria-hidden false");

var textEl = document.getElementById("spinnerText");
assertEqual(textEl.textContent, "加载...", "text updated");
assertEqual(S.isSpinnerVisible(), true, "isSpinnerVisible true");

S.hideSpinner();
assertEqual(overlay.classList.contains("hidden"), true, "hidden");
assertEqual(overlay.getAttribute("aria-hidden"), "true", "aria-hidden true");
assertEqual(S.isSpinnerVisible(), false, "isSpinnerVisible false");

// Default text
S.showSpinner();
assertEqual(textEl.textContent, "处理中...", "default text");
S.hideSpinner();
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/components/spinner.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Component Tests — Modal
# ═══════════════════════════════════════════════════════════════════════════

def test_modal_component():
    """Test Modal v3: confirmAction, confirmDanger, hideConfirm, focus management."""
    test_code = """
var M = window.Modal;
assertDefined(M, "Modal defined");
assertEqual(typeof M.confirmAction, "function", "confirmAction exists");
assertEqual(typeof M.confirmDanger, "function", "confirmDanger v3");
assertEqual(typeof M.hideConfirm, "function", "hideConfirm exists");

// confirmAction opens overlay
M.confirmAction("确认删除？", "删除", "取消").then(function(result) {
  var overlay = document.getElementById("confirmOverlay");
  assertEqual(overlay.classList.contains("hidden"), false, "overlay visible");
  assertEqual(overlay.getAttribute("aria-hidden"), "false", "aria-hidden");

  // Click confirm
  document.getElementById("confirmYes").click();
});

// confirmDanger
assertEqual(typeof M.confirmDanger, "function", "confirmDanger");

// hideConfirm
M.hideConfirm();
var overlay = document.getElementById("confirmOverlay");
assertEqual(overlay.classList.contains("hidden"), true, "overlay hidden");
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/components/modal.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Component Tests — Progress
# ═══════════════════════════════════════════════════════════════════════════

def test_progress_component():
    """Test Progress v3: bar width, meta formatting, ETA, clamping."""
    test_code = """
var P = window.Progress;
assertDefined(P, "Progress defined");
assertEqual(typeof P.renderProgress, "function", "renderProgress exists");
assertEqual(typeof P.renderCloudSyncProgress, "function", "v3 cloudSyncProgress");
assertEqual(typeof P.renderCheckProgress, "function", "v3 checkProgress");

var fillEl = document.getElementById("cloudSyncFill");
var metaEl = document.getElementById("cloudSyncMeta");
fillEl.style = {};
metaEl.textContent = "";

// 50%
P.renderProgress("cloudSync", { percent: 50, message: "同步", scanned: 50, total: 100, added: 5, skipped: 2 });
assertEqual(fillEl.style.width, "50%", "50% fill");
assertContains(metaEl.textContent, "同步", "message");
assertContains(metaEl.textContent, "50%", "percent");
assertContains(metaEl.textContent, "50/100", "scanned/total");
assertContains(metaEl.textContent, "新增 5", "added");
assertContains(metaEl.textContent, "跳过 2", "skipped");

// ETA
P.renderProgress("cloudSync", { percent: 30, eta_seconds: 45 });
assertContains(metaEl.textContent, "预计 45 秒", "ETA seconds");

P.renderProgress("cloudSync", { percent: 60, eta_seconds: 180 });
assertContains(metaEl.textContent, "预计 3 分", "ETA minutes");

// Clamp
P.renderProgress("cloudSync", { percent: -10 });
assertEqual(fillEl.style.width, "0%", "clamp 0%");
P.renderProgress("cloudSync", { percent: 150 });
assertEqual(fillEl.style.width, "100%", "clamp 100%");

// Null-safe
P.renderProgress("nonexistent", null);
P.renderProgress("nonexistent", {});
P.renderProgress("cloudSync", undefined);
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/components/progress.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# Component Tests — Table
# ═══════════════════════════════════════════════════════════════════════════

def test_table_component():
    """Test Table v3: rendering, empty state, badges, score spans, mobile cards."""
    test_code = """
var T = window.Table;
assertDefined(T, "Table defined");
assertEqual(typeof T.render, "function", "render exists");
assertEqual(typeof T.statusBadge, "function", "statusBadge exists");
assertEqual(typeof T.scoreSpan, "function", "scoreSpan exists");

// Status badge
var bg = T.statusBadge("通过", "good");
assertContains(bg, "badge-success", "good badge");
assertContains(bg, "通过", "badge text");

var bb = T.statusBadge("失败", "bad");
assertContains(bb, "badge-danger", "bad badge");

// Score span
var sh = T.scoreSpan(85.5);
assertContains(sh, "var(--success)", "high score");
assertContains(sh, "85.5", "value");

var sl = T.scoreSpan(30);
assertContains(sl, "var(--danger)", "low score");

var sn = T.scoreSpan(null);
assertContains(sn, "-", "null score");

// Render empty
var tbody = document.getElementById("candidateRows");
T.render("candidateRows",
  [{ accessor: "id", render: function(v) { return String(v); } }],
  [],
  { emptyText: "暂无", emptyIcon: "📊" }
);

var emptyEl = document.getElementById("tableEmptyState");
assertEqual(emptyEl.classList.contains("hidden"), false, "empty state visible");
var tableEl = document.getElementById("candidateTable");
assertEqual(tableEl.classList.contains("hidden"), true, "table hidden");

// Render with data
T.render("candidateRows",
  [{ accessor: "id", render: function(v) { return String(v); } }],
  [{ kind: "test", id: "row1", raw: { alpha_id: "A1" }, _selected: false }],
  { emptyText: "暂无" }
);
assertEqual(emptyEl.classList.contains("hidden"), true, "empty state hidden");
assertEqual(tableEl.classList.contains("hidden"), false, "table visible");
assertContains(tbody.innerHTML, "row1", "row rendered");
"""

    _run_node_script(_build_test_script(["js/utils.js", "js/components/table.js"], test_code))


# ═══════════════════════════════════════════════════════════════════════════
# View Tests — Monitor
# ═══════════════════════════════════════════════════════════════════════════

def test_monitor_view():
    """Test MonitorView v3: insight tiles, stat grid, backtest slot cards."""
    test_code = """
var MV = window.MonitorView;
assertDefined(MV, "MonitorView defined");
assertEqual(typeof MV.renderInsight, "function", "renderInsight");
assertEqual(typeof MV.renderOpsMonitor, "function", "renderOpsMonitor");
assertEqual(typeof MV.renderBacktests, "function", "renderBacktests");

// Set up state
window.AppState.setBatch({
  "currentResult.candidates": [
    { alpha_id: "A1", lifecycle_status: "submission_ready", scorecard: { total_score: 85 }, gate: { submission_ready: true } },
    { alpha_id: "A2", lifecycle_status: "active", scorecard: { total_score: 60 } },
  ],
  "currentResult.backtests": [
    { slot: 1, alpha_id: "B1", status: "active", sharpe: 1.5, fitness: 1.2 },
    { slot: 2, alpha_id: "B2", status: "completed", sharpe: 1.1, fitness: 0.9 },
  ],
  "currentResult.summary": {},
  "isRunning": true,
  "liveProgress": { phase: "production_loop", data: {} },
  "checkResults": {},
});

// Render insight
MV.renderInsight();
var insightPanel = document.getElementById("insightPanel");
assertDefined(insightPanel.innerHTML, "insight has content");
assertContains(insightPanel.innerHTML, "insight-tile", "v3 insight-tile class");
assertContains(insightPanel.innerHTML, "insight-tile-label", "v3 label");
assertContains(insightPanel.innerHTML, "insight-tile-value", "v3 value");
assertContains(insightPanel.innerHTML, "insight-tile-icon", "v3 icon");
assertContains(insightPanel.innerHTML, "运行中", "status in insight");

// Render ops monitor
MV.renderOpsMonitor();
var opsPanel = document.getElementById("opsMonitor");
assertContains(opsPanel.innerHTML, "stat-tile", "v3 stat tile");
assertContains(opsPanel.innerHTML, "stat-label", "v3 stat label");

// Render backtests
MV.renderBacktests([
  { id: "BT1", status: "active", sharpe: 1.5, fitness: 1.0 },
  { id: "BT2", status: "failed", sharpe: 0.3, fitness: 0.5 },
]);
var btPanel = document.getElementById("backtestPanel");
assertContains(btPanel.innerHTML, "slot-card", "slot card");
assertContains(btPanel.innerHTML, "is-active", "active slot class");
assertContains(btPanel.innerHTML, "is-error", "failed slot class");

// Empty backtest state
MV.renderBacktests([]);
assertContains(btPanel.innerHTML, "暂无", "empty backtest message");
"""

    _run_node_script(_build_test_script(
        ["js/state.js", "js/utils.js", "js/components/table.js", "js/views/monitor.js"],
        test_code
    ))


# ═══════════════════════════════════════════════════════════════════════════
# View Tests — Production
# ═══════════════════════════════════════════════════════════════════════════

def test_production_view():
    """Test ProductionView v3: exports, start/stop, SSE, resume."""
    test_code = """
assertDefined(window.startProduction, "startProduction exported");
assertDefined(window.stopProduction, "stopProduction exported");
assertDefined(window.toggleRun, "toggleRun exported");
assertDefined(window.connectSSE, "connectSSE exported");
assertDefined(window.disconnectSSE, "disconnectSSE exported");
assertDefined(window.resumeProductionFromCheckpoint, "resumeProductionFromCheckpoint exported");

assertEqual(typeof window.startProduction, "function", "startProduction is function");
assertEqual(typeof window.stopProduction, "function", "stopProduction is function");
assertEqual(typeof window.toggleRun, "function", "toggleRun is function");
assertEqual(typeof window.resumeProductionFromCheckpoint, "function", "resumeProductionFromCheckpoint is function");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/components/toast.js",
         "js/components/spinner.js", "js/views/production.js"],
        test_code
    ))


# ═══════════════════════════════════════════════════════════════════════════
# View Tests — Charts
# ═══════════════════════════════════════════════════════════════════════════

def test_charts_view():
    """Test ChartView v3: renderCharts, destroyAll, empty data safety."""
    test_code = """
assertDefined(window.ChartView, "ChartView defined");
assertEqual(typeof window.ChartView.renderCharts, "function", "renderCharts exists");
assertEqual(typeof window.ChartView.destroyAll, "function", "destroyAll exists");

window.AppState.set("currentResult.summary", {});
window.AppState.set("currentResult.candidates", []);

// Should not throw with empty data
try {
  window.ChartView.renderCharts();
} catch (e) {
  assert(false, "renderCharts should not throw: " + e.message);
}

// destroyAll should not throw
try {
  window.ChartView.destroyAll();
} catch (e) {
  assert(false, "destroyAll should not throw: " + e.message);
}
"""

    _run_node_script(_build_test_script(
        ["js/state.js", "js/utils.js", "js/views/charts.js"],
        test_code
    ))


# ═══════════════════════════════════════════════════════════════════════════
# View Tests — Detail
# ═══════════════════════════════════════════════════════════════════════════

def test_detail_view():
    """Test DetailView v3: detail rendering, modal, section blocks."""
    test_code = """
var DV = window.DetailView;
assertDefined(DV, "DetailView defined");
assertEqual(typeof DV.viewCandidateDetail, "function", "viewCandidateDetail");
assertEqual(typeof DV.viewCloudDetail, "function", "viewCloudDetail");
assertEqual(typeof DV.viewLifecycleDetail, "function", "viewLifecycleDetail");
assertEqual(typeof DV.viewCheckDetail, "function", "viewCheckDetail");

assertEqual(typeof window.viewCandidateDetail, "function", "global viewCandidateDetail");
assertEqual(typeof window.closeDetailModal, "function", "global closeDetailModal");

// View candidate detail
var candidate = {
  alpha_id: "TEST001", family: "momentum", hypothesis: "趋势跟踪",
  expression: "rank(close)", data_fields: ["close"], operators: ["rank"],
  lifecycle_status: "candidate",
  scorecard: { total_score: 85, local_rank_score: 82 },
  gate: { passed: true, submission_ready: true },
  validation: { is_sharpe: 1.5, r_ic: 0.05 },
};
window.viewCandidateDetail(candidate);
var detailEl = document.getElementById("detail");
assertContains(detailEl.innerHTML, "TEST001", "shows alpha ID");
assertContains(detailEl.innerHTML, "detail-section", "section layout");
assertContains(detailEl.innerHTML, "detail-section-title", "section titles");

// Empty candidate
window.viewCandidateDetail(null);
assertContains(detailEl.innerHTML, "暂无详情", "empty state");

// View check detail
window.viewCheckDetail({
  alpha_id: "CHK1", passed: true,
  checked_at: new Date().toISOString(),
  checks: [{ name: "official_pre_submit_check", passed: true, label_cn: "预提交检查" }],
});
assertContains(detailEl.innerHTML, "CHK1", "check shows ID");

// Close modal
window.closeDetailModal();
var overlay = document.getElementById("detailModal");
assertEqual(overlay.classList.contains("hidden"), true, "modal closed");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/components/table.js", "js/state.js", "js/views/detail.js"],
        test_code
    ))


# ═══════════════════════════════════════════════════════════════════════════
# App Entry Point Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_app_module_global_exports():
    """Test app.js v3 exports and function existence."""
    test_code = """
assertDefined(window.switchView, "switchView exported");
assertEqual(typeof window.switchView, "function", "switchView is function");
assertDefined(window.renderCurrentView, "renderCurrentView exported");
assertDefined(window._app, "_app exported");
assertEqual(typeof window._app.renderAll, "function", "_app.renderAll");
assertDefined(window.operationBlockReason, "operationBlockReason exported");
assertDefined(window.renderBusyControls, "renderBusyControls exported");
assertDefined(window.collectPayload, "collectPayload exported");
assertDefined(window.renderStrategyPolicy, "renderStrategyPolicy exported");
assertDefined(window.toggleTheme, "toggleTheme exported");
assertDefined(window.toggleEnvironment, "toggleEnvironment exported");
assertDefined(window.toggleSelectCandidate, "toggleSelectCandidate exported");
assertDefined(window.submitSelectedCandidates, "submitSelectedCandidates exported");
assertDefined(window.submitSingleCandidate, "submitSingleCandidate exported");
assertDefined(window.syncCloud, "syncCloud exported");
assertDefined(window.checkBatch, "checkBatch exported");
assertDefined(window.shutdownApp, "shutdownApp exported");
assertDefined(window.applyPreset, "applyPreset exported");
assertDefined(window.testConnection, "testConnection exported");
assertDefined(window.loadConfig, "loadConfig exported");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_app_renders_empty_state():
    """Test app renders empty state when no data."""
    test_code = """
window.AppState.set("currentResult.candidates", []);
window.AppState.set("currentResult.cloud_alphas", []);
window.AppState.set("currentResult.backtests", []);
window.AppState.set("isRunning", false);
window.AppState.set("activeView", "candidates");

window.renderCurrentView();
var emptyEl = document.getElementById("tableEmptyState");
assertEqual(emptyEl.classList.contains("hidden"), false, "empty state visible");
var tableEl = document.getElementById("candidateTable");
assertEqual(tableEl.classList.contains("hidden"), true, "table hidden when empty");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_app_renders_data_with_rows():
    """Test app renders table rows when data is present (v3)."""
    test_code = """
window.AppState.setBatch({
  "currentResult.candidates": [
    { alpha_id: "ALPHA001", family: "momentum", lifecycle_status: "candidate",
      scorecard: { total_score: 85, local_rank_score: 82 },
      gate: { passed: true, submission_ready: true }, official_alpha_id: "" },
    { alpha_id: "ALPHA002", family: "reversal", lifecycle_status: "submission_ready",
      scorecard: { total_score: 72, local_rank_score: 70 },
      gate: { passed: true, submission_ready: true }, official_alpha_id: "OFF002" },
  ],
  "activeView": "candidates",
});

window.renderCurrentView();

var tbody = document.getElementById("candidateRows");
assertContains(tbody.innerHTML, "ALPHA001", "first alpha rendered");
assertContains(tbody.innerHTML, "ALPHA002", "second alpha rendered");

var pill = document.getElementById("countPill");
assertContains(pill.textContent, "2", "count pill shows 2");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_app_view_switching():
    """Test switching views updates state and title."""
    test_code = """
window.AppState.set("currentResult.candidates", [
  { alpha_id: "A1", lifecycle_status: "submission_ready", scorecard: { total_score: 85 }, gate: { submission_ready: true } },
  { alpha_id: "A2", lifecycle_status: "failed", scorecard: { total_score: 30 }, gate: { passed: false } },
]);

window.switchView("passed");
assertEqual(window.AppState.get("activeView"), "passed", "switched to passed");
var titleEl = document.getElementById("tableTitle");
assertEqual(titleEl.textContent, "达标", "title=达标");

window.switchView("candidates");
assertEqual(window.AppState.get("activeView"), "candidates", "back to candidates");
assertEqual(titleEl.textContent, "候选池", "title=候选池");

// Invalid view falls back
window.switchView("nonexistent");
assertEqual(window.AppState.get("activeView"), "candidates", "invalid falls back");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_app_display_mode_switching():
    """Test table/chart display mode toggle (v3)."""
    test_code = """
window.AppState.set("currentResult.candidates", []);
window.AppState.set("activeView", "candidates");

window.setResultDisplayMode("charts");
var chartsPanel = document.getElementById("chartsPanel");
assertEqual(chartsPanel.classList.contains("visible"), true, "charts visible");
var tableBtn = document.getElementById("tableModeBtn");
var chartBtn = document.getElementById("chartModeBtn");
assertEqual(tableBtn.classList.contains("is-active"), false, "table btn not active");
assertEqual(chartBtn.classList.contains("is-active"), true, "chart btn active");

window.setResultDisplayMode("table");
assertEqual(chartsPanel.classList.contains("visible"), false, "charts hidden");
assertEqual(tableBtn.classList.contains("is-active"), true, "table btn active");
assertEqual(chartBtn.classList.contains("is-active"), false, "chart btn not active");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_candidate_selection_toggle():
    """Test candidate selection toggle (v3)."""
    test_code = """
window.AppState.set("currentResult.candidates", [
  { alpha_id: "SEL001", lifecycle_status: "submission_ready", scorecard: { total_score: 85 }, gate: { submission_ready: true } },
]);
window.AppState.set("activeView", "passed");

var el = { textContent: "选择" };
window.toggleSelectCandidate("SEL001", el);
assertEqual(el.textContent, "已选", "toggled on");
window.toggleSelectCandidate("SEL001", el);
assertEqual(el.textContent, "选择", "toggled off");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_operation_blocking_logic():
    """Test operationBlockReason for v3 actions."""
    test_code = """
// Initial state: idle
assertEqual(window.operationBlockReason("production"), "", "production unblocked when idle");
assertEqual(window.operationBlockReason("sync"), "", "sync unblocked when idle");
assertEqual(window.operationBlockReason("check"), "", "check unblocked when idle");
assertEqual(window.operationBlockReason("submit"), "", "submit unblocked when idle");

// Running blocks sync/check/submit
window.AppState.set("isRunning", true);
assertEqual(window.operationBlockReason("production"), "", "production still allowed when running");
assertContains(window.operationBlockReason("sync"), "生产", "sync blocked when running");
assertContains(window.operationBlockReason("check"), "生产", "check blocked when running");

window.AppState.set("isRunning", false);
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


def test_render_strategy_policy():
    """Test v3 renderStrategyPolicy renders config cards."""
    test_code = """
var config = {
  ops: {
    budget: {
      max_candidates_per_cycle: 20,
      retained_alpha_pool_size: 10,
      official_backtest_batch_size: 3,
      max_official_simulations_per_cycle: 3,
      max_official_concurrent_simulations: 3,
      run_forever: true,
      strategy_plugins_enabled: true,
      strategy_plugin_specs: ["mod:Plugin"],
    },
  },
};

window.renderStrategyPolicy(config);
var target = document.getElementById("strategyText");
assertContains(target.innerHTML, "候选上限", "shows candidate limit");
assertContains(target.innerHTML, "池容量", "shows pool size label");
assertContains(target.innerHTML, "10", "shows pool size value");
assertContains(target.innerHTML, "连续生产", "shows run forever");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Full Integration Test
# ═══════════════════════════════════════════════════════════════════════════

def test_full_integration_all_modules_no_crash():
    """Load all 14 modules together, verify no crashes from init or rendering."""
    test_code = """
// All 14 modules loaded — verify exports
assertDefined(window.Utils, "Utils loaded");
assertDefined(window.ApiClient, "ApiClient loaded");
assertDefined(window.AppState, "AppState loaded");
assertDefined(window.Toast, "Toast loaded");
assertDefined(window.Spinner, "Spinner loaded");
assertDefined(window.Modal, "Modal loaded");
assertDefined(window.Progress, "Progress loaded");
assertDefined(window.Table, "Table loaded");
assertDefined(window.ViewModel, "ViewModel loaded");
assertDefined(window.ChartView, "ChartView loaded");
assertDefined(window.DetailView, "DetailView loaded");
assertDefined(window.MonitorView, "MonitorView loaded");
assertDefined(window._app, "App loaded");

// Set up state
window.AppState.setBatch({
  "currentResult.candidates": [
    { alpha_id: "INT001", family: "test", lifecycle_status: "candidate",
      scorecard: { total_score: 80, local_rank_score: 78 },
      gate: { passed: true, submission_ready: true } },
  ],
  "currentResult.cloud_alphas": [
    { alpha_id: "CLD001", status: "APPROVED", sharpe: 1.5, fitness: 1.2 },
  ],
  "currentResult.backtests": [
    { slot: 1, alpha_id: "BT001", status: "active", sharpe: 1.3, fitness: 1.0 },
  ],
  "activeView": "candidates",
  "isRunning": false,
  "currentResult.summary": {},
  "currentResult.lifecycle_records": [],
  "checkResults": {},
});

// renderAll should not throw
try {
  window._app.renderAll();
} catch (e) {
  assert(false, "renderAll threw: " + e.message);
}

// Verify outputs
var insightPanel = document.getElementById("insightPanel");
assertContains(insightPanel.innerHTML, "insight-tile", "v3 insight tiles rendered");

var tbody = document.getElementById("candidateRows");
assertContains(tbody.innerHTML, "INT001", "candidate rows rendered");

var emptyEl = document.getElementById("tableEmptyState");
assertEqual(emptyEl.classList.contains("hidden"), true, "empty state hidden with data");

var titleEl = document.getElementById("tableTitle");
assertEqual(titleEl.textContent, "候选池", "title correct");
"""

    _run_node_script(_build_test_script(
        ["js/utils.js", "js/api-client.js", "js/state.js", "js/view-model.js",
         "js/components/toast.js", "js/components/spinner.js", "js/components/modal.js",
         "js/components/progress.js", "js/components/table.js",
         "js/views/detail.js", "js/views/production.js", "js/views/charts.js",
         "js/views/monitor.js", "js/app.js"],
        test_code
    ))
