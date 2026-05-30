#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function usage() {
  return [
    "Usage: node scripts/browser_react_artifact_smoke.mjs --url <local-react-dist-url>",
    "",
    "Options:",
    "  --devtools-url <url>   Chrome DevTools HTTP URL, default http://127.0.0.1:9224",
    "  --output-dir <dir>     Artifact directory, default output/react-artifact-smoke",
    "  --json                 Print JSON only",
  ].join("\n");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}: ${await response.text()}`);
  }
  return response.json();
}

async function closeTarget(devtoolsUrl, targetId) {
  if (!targetId) return;
  try {
    await fetch(`${devtoolsUrl.replace(/\/$/, "")}/json/close/${encodeURIComponent(targetId)}`);
  } catch {
    // Best-effort cleanup only.
  }
}

class CdpSession {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.eventWaiters = new Map();
    this.consoleMessages = [];
    this.networkFailures = [];
    this.responses = [];
    this.mockRequests = [];
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    this.ws.addEventListener("message", (event) => this.handleMessage(event));
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Timed out connecting to ${this.wsUrl}`)), 5000);
      this.ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      this.ws.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error(`Unable to connect to ${this.wsUrl}`));
      }, { once: true });
    });
  }

  resetObservations() {
    this.consoleMessages = [];
    this.networkFailures = [];
    this.responses = [];
    this.mockRequests = [];
  }

  handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.id && this.pending.has(message.id)) {
      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(`${message.error.message || "CDP error"} (${message.error.code})`));
      else resolve(message.result || {});
      return;
    }
    if (message.method === "Runtime.consoleAPICalled") {
      this.consoleMessages.push({
        type: message.params?.type || "",
        text: (message.params?.args || []).map((arg) => arg.value || arg.description || "").join(" ").slice(0, 500),
      });
    }
    if (message.method === "Network.loadingFailed") {
      this.networkFailures.push({
        url: message.params?.requestId || "",
        errorText: message.params?.errorText || "",
        blockedReason: message.params?.blockedReason || "",
      });
    }
    if (message.method === "Network.responseReceived") {
      const response = message.params?.response || {};
      this.responses.push({
        url: response.url || "",
        status: response.status || 0,
        type: message.params?.type || "",
        mimeType: response.mimeType || "",
      });
    }
    if (message.method === "Fetch.requestPaused") {
      this.fulfillMockRequest(message.params).catch((error) => {
        this.consoleMessages.push({ type: "error", text: `mock request failed: ${String(error)}` });
      });
      return;
    }
    if (message.method && this.eventWaiters.has(message.method)) {
      const waiters = this.eventWaiters.get(message.method);
      this.eventWaiters.delete(message.method);
      waiters.forEach((resolve) => resolve(message.params || {}));
    }
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (!this.pending.has(id)) return;
        this.pending.delete(id);
        reject(new Error(`Timed out waiting for ${method}`));
      }, 15000);
    });
  }

  waitForEvent(method, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${method}`)), timeout);
      const wrappedResolve = (params) => {
        clearTimeout(timer);
        resolve(params);
      };
      const waiters = this.eventWaiters.get(method) || [];
      waiters.push(wrappedResolve);
      this.eventWaiters.set(method, waiters);
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(`Runtime evaluation failed: ${JSON.stringify(result.exceptionDetails)}`);
    }
    return result.result ? result.result.value : undefined;
  }

  async fulfillMockRequest(params) {
    const requestId = params.requestId;
    const request = params.request || {};
    const payload = mockApiPayload(request.url || "", request.method || "GET");
    if (!payload) {
      await this.send("Fetch.continueRequest", { requestId });
      return;
    }
    const url = new URL(request.url || "");
    this.mockRequests.push({
      method: request.method || "GET",
      path: url.pathname,
      status: payload.status || 200,
      body: request.postData || "",
    });
    await this.send("Fetch.fulfillRequest", {
      requestId,
      responseCode: payload.status || 200,
      responseHeaders: [
        { name: "Content-Type", value: payload.contentType || "application/json; charset=utf-8" },
        { name: "Cache-Control", value: "no-store" },
      ],
      body: Buffer.from(payload.body || JSON.stringify(payload.json || {}), "utf8").toString("base64"),
    });
  }

  close() {
    if (this.ws) this.ws.close();
  }
}

function mockApiPayload(rawUrl, method) {
  const url = new URL(rawUrl);
  const pathname = url.pathname;
  const ok = (json) => ({ status: 200, json });
  if (method === "GET" && pathname === "/api/status") {
    return ok({
      ok: true,
      status: "idle",
      progress: {
        candidates_generated: 12,
        backtests_completed: 4,
        backtests_pending: 1,
        submissions: 0,
      },
    });
  }
  if (method === "GET" && pathname === "/api/snapshot/cloud") {
    return ok({
      ok: true,
      count: 2,
      submitted_count: 1,
      passed_unsubmitted_count: 1,
      is_stale: false,
      summary: {
        count: 2,
        total: 2,
        returned_count: 2,
        submitted_count: 1,
        passed_unsubmitted_count: 1,
        is_stale: false,
        source: "mock",
      },
      alphas: [
        {
          id: "cloud_1",
          alpha_id: "ALPHA_CLOUD_1",
          status: "ACTIVE",
          pass_fail: "PASS",
          sharpe: 1.42,
          fitness: 1.16,
          turnover: 0.08,
          expression: "rank(close)",
          updated_at: "2026-05-30T00:00:00Z",
        },
        {
          id: "cloud_2",
          alpha_id: "ALPHA_CLOUD_2",
          status: "REVIEW",
          pass_fail: "FAIL",
          sharpe: 0.82,
          fitness: 0.71,
          turnover: 0.12,
          code: "decay_linear(volume, 5)",
          updated_at: "2026-05-30T00:10:00Z",
        },
      ],
      sample_alphas: [
        { alpha_id: "ALPHA_RT_001", pass_fail: "PASS", sharpe: 1.42, fitness: 1.16 },
        { alpha_id: "ALPHA_RT_002", pass_fail: "FAIL", sharpe: 0.82, fitness: 0.71 },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/lifecycle") {
    return ok({
      ok: true,
      records: [
        {
          alpha_id: "ALPHA_LIFE_1",
          status: "submission_ready",
          stage: "ready",
          message: "Ready for submission",
          timestamp: "2026-05-30T00:11:00Z",
        },
        {
          alpha_id: "ALPHA_LIFE_2",
          status: "submitted",
          stage: "submitted",
          note: "Queued for downstream sync",
          timestamp: "2026-05-30T00:12:00Z",
        },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/snapshot/memory") {
    return ok({
      ok: true,
      total_candidates: 1005,
      families: [{ name: "momentum", count: 40, success_rate: 0.31 }],
      fields: [{ name: "close", count: 25, success_rate: 0.28 }],
      operators: [{ name: "rank", count: 18, success_rate: 0.42 }],
      failure_patterns: [{ reason: "self_correlation", count: 3 }],
      recommendations: ["Review turnover constraints", "Refresh research cache"],
      total_lifecycle_records: 42,
      total_check_records: 12,
    });
  }
  if (method === "GET" && pathname === "/api/research_memory") {
    return ok({
      ok: true,
      total_candidates: 1005,
      total_lifecycle_records: 42,
      total_check_records: 12,
      families: [{ name: "momentum", count: 40, success_rate: 0.31 }],
      fields: [{ name: "close", count: 25, success_rate: 0.28 }],
      operators: [{ name: "rank", count: 18, success_rate: 0.42 }],
      failure_patterns: [{ reason: "self_correlation", count: 3 }],
      recommendations: ["Review turnover constraints", "Refresh research cache"],
    });
  }
  if (method === "GET" && pathname === "/api/research_knowledge") {
    return ok({
      ok: true,
      counts: { rules: 3, findings: 2, failures: 1 },
      items: [
        {
          kind: "rule",
          title: "Promote stable momentum",
          confidence: 0.94,
          evidence: [{ id: "run_1" }, { id: "run_2" }],
          source_run_id: "run_2",
          body: "Use rank(close) with turnover guard.",
          updated_at: "2026-05-30T00:13:00Z",
        },
        {
          kind: "finding",
          knowledge_id: "knowledge_2",
          confidence: 0.81,
          evidence: [{ id: "run_3" }],
          expression_pattern: "decay_linear(volume, 5)",
          category: "turnover",
          created_at: "2026-05-30T00:14:00Z",
        },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/research_observability") {
    return ok({
      ok: true,
      health: {
        risk_level: "medium",
        blocking_flags: ["duplicate_expression_history"],
        warning_flags: ["retryable_official_errors_present"],
        health_flags: ["stable_cache"],
      },
      errors: {
        total: 2,
        recent_errors: [
          { error_code: "rate_limit", detail: "Retry later", timestamp: "2026-05-30T00:15:00Z" },
        ],
      },
      backtests: {
        failure_patterns: [{ reason: "sharpe_decay", count: 4 }],
      },
      checks: {
        failure_patterns: [{ reason: "self_correlation", count: 1 }],
      },
      recommendations: ["Reduce request rate", "Inspect duplicate expressions"],
    });
  }
  if (method === "GET" && pathname === "/api/prompt_runs") {
    return ok({
      ok: true,
      count: 2,
      items: [
        {
          timestamp: "2026-05-30T00:16:00Z",
          prompt_digest: "prompt_digest_1",
          context_digest: "context_digest_1",
          model: "gpt-4.1-mini",
          temperature: 0.2,
          response_digest: "response_digest_1",
          parse_status: "ok",
        },
        {
          timestamp: "2026-05-30T00:17:00Z",
          prompt_digest: "prompt_digest_2",
          context_digest: "context_digest_2",
          model: "gpt-4.1-mini",
          temperature: 0.3,
          response_digest: "response_digest_2",
          parse_status: "recorded",
        },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/sqlite_indexes") {
    return ok({
      ok: true,
      expression_index: {
        total_expression_records: 24,
        duplicate_expression_count: 2,
        duplicates: [
          { expression_canonical: "rank(close)", count: 4, success_rate: 0.5, detail: "duplicate cluster" },
        ],
        frequent_expressions: [
          { expression_canonical: "decay_linear(volume, 5)", count: 6, avg_score: 71 },
        ],
        fields: [{ name: "close", count: 8, success_rate: 0.44 }],
        operators: [{ name: "rank", count: 10, score: 0.9 }],
        windows: [{ window: 5, count: 4, score: 0.88 }],
      },
      record_index: {
        ok: true,
        row_count: 128,
        db_path: "/tmp/mock.sqlite",
        latest_timestamp: "2026-05-30T00:18:00Z",
      },
    });
  }
  if (method === "GET" && pathname === "/api/latest_result") {
    const candidate = {
      alpha_id: "ALPHA_RT_001",
      submission: {
        anti_overfit_report: {
          recommendation: "pass",
          score: 92,
          tests: [{ name: "overfit_gap", passed: true }],
          generated_at: "2026-05-30T00:19:00Z",
        },
        rolling_validation_report: {
          status: "pass",
          score: 88,
          sample_size: 24,
          tests: [{ name: "window_stability", passed: true }],
          generated_at: "2026-05-30T00:19:30Z",
        },
      },
      updated_at: "2026-05-30T00:20:00Z",
    };
    return ok({
      ok: true,
      source: "run_history",
      job_id: "run_1",
      status: "completed",
      summary: { candidates: [candidate] },
      result: { candidates: [candidate] },
    });
  }
  if (method === "GET" && pathname === "/api/candidates") {
    return ok({
      ok: true,
      candidates: candidateFixtures(1005),
    });
  }
  if (method === "GET" && pathname === "/api/check_results") {
    return ok({
      ok: true,
      items: [
        { alpha_id: "ALPHA_RT_001", official_alpha_id: "OFFICIAL_RT_001", passed: true, submittable: true, is_stale: false },
        { alpha_id: "ALPHA_RT_006", passed: true, submittable: true, is_stale: true },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/config") {
    return ok({ ok: true, config: configFixture() });
  }
  if (method === "GET" && pathname === "/api/config_schema") {
    return ok({
      ok: true,
      schema: {
        settings_options: {
          region: ["USA", "CHN", "EUR", "GLB"],
          universe: ["TOP3000", "TOP1000", "TOP500"],
          delay: [0, 1],
          neutralization: ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"],
        },
      },
    });
  }
  if (method === "POST" && pathname === "/api/config") {
    return ok({ ok: true, config: configFixture() });
  }
  if (method === "POST" && pathname === "/api/generate_candidates") {
    return ok({ ok: true, job_id: "task_react_smoke_generate" });
  }
  if (method === "POST" && pathname === "/api/scoring/evaluate") {
    return ok({ ok: true, job_id: "task_react_smoke_score" });
  }
  if (method === "POST" && pathname === "/api/scoring/attribution") {
    return ok({
      ok: true,
      attribution: { name: "total", score: 82, weight: 1, children: [] },
      hard_gates: [{ name: "sharpe", passed: true, value: 1.42, threshold: 1.25 }],
      soft_gates: [{ name: "turnover", passed: true, value: 0.08, threshold: 0.7 }],
      top_failures: [],
      improvement_hints: ["Keep monitoring self-correlation."],
    });
  }
  if (method === "POST" && pathname === "/api/check") {
    return ok({ ok: true, alpha_id: "ALPHA_RT_001", checks: [{ name: "mock_check", passed: true }] });
  }
  if (method === "POST" && pathname === "/api/submit") {
    return ok({ ok: true, alpha_id: "ALPHA_RT_001", submitted: true });
  }
  if (method === "POST" && pathname === "/api/check_batch") {
    return ok({ ok: true, job_id: "task_react_smoke_batch_check" });
  }
  if (method === "POST" && pathname === "/api/submit_batch") {
    return ok({ ok: true, job_id: "task_react_smoke_batch_submit" });
  }
  if (method === "GET" && pathname === "/sse") {
    return {
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      body: [
        "data: {\"type\":\"complete\",\"ok\":true,\"result\":{\"total_score\":82,\"passed_gate\":true}}",
        "",
        "",
      ].join("\n"),
    };
  }
  return null;
}

function candidateFixtures(count) {
  const ids = ["ALPHA_RT_001", "ALPHA_RT_002"];
  for (let index = 3; index <= count; index += 1) {
    ids.push(`ALPHA_RT_${String(index).padStart(3, "0")}`);
  }
  return ids.map((alphaId, index) => candidateFixture(alphaId, index));
}

function candidateFixture(alphaId, index = 0) {
  const topCandidate = alphaId === "ALPHA_RT_001";
  const runnerUp = alphaId === "ALPHA_RT_002";
  const score = topCandidate ? 82 : runnerUp ? 67 : 45 - (index % 20) * 0.5;
  const lifecycleStatus = topCandidate
    ? "submission_ready"
    : runnerUp
      ? "running_backtest"
      : index === 2
        ? "backtest_rework"
        : index === 3
          ? "blocked"
          : index === 4
            ? "submitted"
            : "pending_backtest";
  return {
    alpha_id: alphaId,
    official_alpha_id: alphaId === "ALPHA_RT_001" ? "OFFICIAL_RT_001" : "",
    simulation_id: `SIM_${alphaId}`,
    expression: `rank(ts_mean(close, ${10 + (index % 12)})) - group_neutralize(volume, industry)`,
    family: index % 3 === 0 ? "value" : "momentum",
    lifecycle_status: lifecycleStatus,
    scorecard: {
      total_score: score,
      prior_score: 24,
      empirical_score: 38,
      checklist_score: 20,
    },
    official_metrics: {
      sharpe: topCandidate ? 1.42 : runnerUp ? 0.88 : 0.7 + (index % 30) / 100,
      fitness: topCandidate ? 1.16 : runnerUp ? 0.74 : 0.6 + (index % 25) / 100,
      turnover: 0.08,
      returns: 0.12,
      drawdown: 0.04,
      self_correlation: 0.22,
      weight_concentration: 0.05,
    },
    gate: { passed: topCandidate, submission_ready: topCandidate },
    stage: lifecycleStatus === "submitted" ? "submitted" : "",
  };
}

function configFixture() {
  return {
    environment: "production",
    auto_submit: false,
    ops: {
      settings: {
        region: "USA",
        universe: "TOP3000",
        delay: 1,
        decay: 10,
        neutralization: "SUBINDUSTRY",
        dataset: "fundamental_v0",
      },
      budget: {
        max_candidates_per_cycle: 20,
        max_cycles: 10,
        retained_alpha_pool_size: 10,
        official_backtest_batch_size: 3,
        require_cloud_sync: true,
      },
      thresholds: {
        min_sharpe: 1.25,
        min_fitness: 1,
        min_turnover: 0.01,
        platform_max_turnover: 0.7,
        max_self_correlation: 0.7,
        max_weight_concentration: 0.1,
      },
      scoring: {
        prior_layer_weight: 0.3,
        empirical_layer_weight: 0.45,
        checklist_layer_weight: 0.25,
        market_regime: "neutral",
      },
    },
  };
}

function metricsExpression() {
  return `(() => {
    const text = document.body ? document.body.innerText : "";
    const root = document.getElementById("root");
    const resources = performance.getEntriesByType("resource")
      .map((entry) => ({ name: entry.name, transferSize: entry.transferSize || 0 }))
      .filter((entry) => /\\/assets\\//.test(entry.name));
    return {
      title: document.title,
      readyState: document.readyState,
      url: location.href,
      rootExists: Boolean(root),
      rootChildCount: root ? root.childElementCount : 0,
      rootTextLength: root ? root.innerText.length : 0,
      hasHeading: /BRAIN Alpha Ops/.test(text),
      hasVersionLabel: /Research Console v0\\.3/.test(text),
      roles: {
        tablist: document.querySelectorAll('[role="tablist"]').length,
        tab: document.querySelectorAll('[role="tab"]').length,
        selectedTabs: document.querySelectorAll('[role="tab"][aria-selected="true"]').length,
        tabpanel: document.querySelectorAll('[role="tabpanel"]').length,
        liveRegions: document.querySelectorAll('[aria-live]').length,
      },
      meta: {
        csrf: document.querySelector('meta[name="brain-alpha-csrf"]')?.content || "",
        stream: document.querySelector('meta[name="brain-alpha-stream"]')?.content || "",
      },
      resources,
      bodyWidth: document.body ? document.body.scrollWidth : 0,
      viewportWidth: window.innerWidth,
      pageOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
    };
  })()`;
}

function interactionExpression() {
  return `(async () => {
    const waitFrames = async (count = 2) => {
      for (let index = 0; index < count; index += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
    };
    const setValue = (element, value) => {
      if (!element) return;
      const prototype = element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : element instanceof HTMLSelectElement
          ? HTMLSelectElement.prototype
          : HTMLInputElement.prototype;
      const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
      if (descriptor?.set) descriptor.set.call(element, value);
      else element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const setChecked = (element, value) => {
      if (!element) return;
      const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "checked");
      if (descriptor?.set) descriptor.set.call(element, value);
      else element.checked = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const setJsonFile = async (input, name, value) => {
      if (!input) return false;
      const file = new File([JSON.stringify(value)], name, { type: "application/json" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      Object.defineProperty(input, "files", { configurable: true, value: transfer.files });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await waitFrames(12);
      return true;
    };
    const clickTab = async (id) => {
      document.getElementById("app-tab-" + id).click();
      await waitFrames(8);
    };
    const panelText = () => document.querySelector('[role="tabpanel"]')?.innerText || "";
    const bodyText = () => document.body?.innerText || "";
    const labelControl = (labelText) => {
      const labels = Array.from(document.querySelectorAll("label"));
      const label = labels.find((node) => (node.innerText || "").includes(labelText));
      return label ? label.querySelector("input, textarea, select") : null;
    };
    const buttonByText = (text) => Array.from(document.querySelectorAll("button"))
      .find((button) => (button.textContent || "").trim() === text);
    const buttonContaining = (text) => Array.from(document.querySelectorAll("button"))
      .find((button) => (button.textContent || "").includes(text));
    const waitUntil = async (predicate, attempts = 80) => {
      for (let index = 0; index < attempts; index += 1) {
        if (predicate()) return true;
        await waitFrames(1);
      }
      return false;
    };
    const parseShowingStatus = () => {
      const match = panelText().match(/Showing (\\d+)-(\\d+) of (\\d+) candidates/);
      return match ? { start: Number(match[1]), end: Number(match[2]), total: Number(match[3]), text: match[0] } : null;
    };
    const visibleVirtualRowIndexes = () => Array.from(document.querySelectorAll('[data-virtualized-candidate-table="true"] tbody tr[aria-rowindex]'))
      .map((row) => Number(row.getAttribute("aria-rowindex") || "0"))
      .filter(Boolean);
    const hasToast = (message) => bodyText().includes(message);
    const toastAction = (label) => Array.from(document.querySelectorAll('[role="status"] button, [role="alert"] button'))
      .find((button) => (button.textContent || "").trim() === label);
    const controlValue = (label) => labelControl(label)?.value || "";
    const controlChecked = (label) => Boolean(labelControl(label)?.checked);

    await clickTab("dashboard");
    await waitUntil(() => /Cloud Alphas/i.test(panelText()) || /Dashboard data needs attention/i.test(panelText()));
    const report = {};

    report.dashboard = {
      selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
      hasCloudKpi: /Cloud Alphas/i.test(panelText()),
      hasMemoryKpi: /Total Candidates/i.test(panelText()),
      hasDashboardError: /Dashboard data needs attention/i.test(panelText()),
      textSample: panelText().slice(0, 240),
    };

    await clickTab("candidates");
    const candidateLoadStartedAt = performance.now();
    await waitUntil(() => /Showing \\d+-\\d+ of 1005 candidates/.test(panelText()), 160);
    const largeListLoadMs = Math.round(performance.now() - candidateLoadStartedAt);
    const virtualViewport = document.querySelector('[data-virtualized-candidate-table="true"]');
    const candidateTable = document.querySelector('table[aria-label="Candidate results"]');
    const largeListAriaRowCount = Number(candidateTable?.getAttribute("aria-rowcount") || "0");
    const initialStatus = parseShowingStatus();
    const initialRowIndexes = visibleVirtualRowIndexes();
    const scrollStartedAt = performance.now();
    if (virtualViewport) {
      virtualViewport.scrollTop = Math.max(0, virtualViewport.scrollHeight - virtualViewport.clientHeight - 120);
      virtualViewport.dispatchEvent(new Event("scroll", { bubbles: true }));
    }
    await waitFrames(12);
    const scrolledRowIndexes = visibleVirtualRowIndexes();
    const scrollInteractionMs = Math.round(performance.now() - scrollStartedAt);
    const filterInput = document.querySelector('input[aria-label="Filter candidates"]');
    const countInput = document.querySelector('input[type="number"][max="100"]');
    if (filterInput) setValue(filterInput, "ALPHA_RT_001\\u0007" + "x".repeat(260));
    await waitFrames(6);
    const filterSanitized = Boolean(filterInput && !filterInput.value.includes("\\u0007") && filterInput.value.length <= 200);
    if (filterInput) setValue(filterInput, "ALPHA_RT_001");
    await waitUntil(() => /Showing 1-1 of 1 candidates/.test(panelText()) || /ALPHA_RT_001/.test(panelText()));
    if (countInput) setValue(countInput, "1010");
    await waitFrames(6);
    const clampedCount = countInput?.value || "";
    if (countInput) setValue(countInput, "7");
    await waitFrames(3);
    const generateButton = buttonByText("Generate");
    if (generateButton) generateButton.click();
    await waitFrames(10);
    report.candidates = {
      selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
      hasFilter: Boolean(filterInput),
      filterValue: filterInput?.value || "",
      countClampedTo: clampedCount,
      countSubmittedAs: countInput?.value || "",
      hasCandidate: /ALPHA_RT_001/.test(panelText()),
      hasVirtualTable: Boolean(document.querySelector('[data-virtualized-candidate-table="true"]')),
      largeListStatus: initialStatus,
      largeListAriaRowCount,
      renderedInitialRows: initialRowIndexes.length,
      renderedAfterScrollRows: scrolledRowIndexes.length,
      rowWindowChangedAfterScroll: Boolean(initialRowIndexes[0] && scrolledRowIndexes[0] && scrolledRowIndexes[0] > initialRowIndexes[0]),
      filterSanitized,
      largeListLoadMs,
      scrollInteractionMs,
      generateClicked: Boolean(generateButton),
    };

    const queueViews = [
      ["pending_backtest", /Waiting for backtest/i, 1000],
      ["running_backtest", /Backtesting/i, 1],
      ["backtest_rework", /Backtest rework/i, 1],
      ["passed", /Passed candidates/i, 1],
      ["submittable", /Ready to submit/i, 1],
      ["submitted", /Submitted candidates/i, 1],
      ["failed", /Blocked candidates/i, 1],
    ];
    report.queueViews = [];
    for (const [id, titlePattern, expectedTotal] of queueViews) {
      await clickTab(id);
      await waitUntil(() => titlePattern.test(panelText()), 80);
      await waitUntil(() => parseShowingStatus()?.total === expectedTotal || panelText().includes("No candidates"), 120);
      report.queueViews.push({
        id,
        selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
        titleVisible: titlePattern.test(panelText()),
        status: parseShowingStatus(),
        hasVirtualTable: Boolean(document.querySelector('[data-virtualized-candidate-table="true"]')),
      });
    }

    const snapshotViews = [
      ["cloud", /Cloud data/i, /ALPHA_CLOUD_1/],
      ["lifecycle", /Lifecycle/i, /Ready for submission/],
      ["research_memory", /Research memory/i, /momentum/],
      ["research_knowledge", /Knowledge base/i, /Promote stable momentum/],
      ["research_observability", /Observability/i, /duplicate_expression_history/],
      ["prompt_runs", /Prompt runs/i, /prompt_digest_1/],
      ["sqlite_indexes", /SQLite indexes/i, /record_index/],
      ["robustness", /Robustness/i, /ALPHA_RT_001/],
    ];
    report.snapshotViews = [];
    for (const [id, titlePattern, rowPattern] of snapshotViews) {
      await clickTab(id);
      await waitUntil(() => titlePattern.test(panelText()), 80);
      await waitUntil(() => rowPattern.test(panelText()) || /rows/.test(panelText()), 120);
      report.snapshotViews.push({
        id,
        selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
        titleVisible: titlePattern.test(panelText()),
        rowVisible: rowPattern.test(panelText()),
        hasTable: Boolean(document.querySelector('table[aria-label$=" rows"]')),
      });
    }

    await clickTab("candidates");
    const refreshedFilterInput = document.querySelector('input[aria-label="Filter candidates"]');
    if (refreshedFilterInput) setValue(refreshedFilterInput, "ALPHA_RT_001");
    await waitUntil(() => /ALPHA_RT_001/.test(panelText()), 80);
    const scoreButton = buttonByText("Score");
    if (scoreButton) scoreButton.click();
    await waitFrames(12);
    report.scoring = {
      selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
      hasAlphaExpression: /Alpha Expression/.test(panelText()),
      hasCandidateId: /ALPHA_RT_001/.test(panelText()),
      hasScorecard: /Scorecard/.test(panelText()),
    };

    await clickTab("submission");
    const alphaInput = document.querySelector('input[placeholder^="e.g. alpha"]');
    if (alphaInput) setValue(alphaInput, "BAD ID!");
    await waitFrames(4);
    const invalidMessage = panelText();
    if (alphaInput) setValue(alphaInput, "ALPHA_RT_001");
    await waitFrames(4);
    const preCheck = buttonByText("Pre-Submit Check");
    const validAlphaAccepted = Boolean(preCheck && !preCheck.disabled);
    if (preCheck) preCheck.click();
    await waitUntil(() => /Pre-submit check completed|mock_check/.test(panelText()) || hasToast("Check completed for ALPHA_RT_001"));
    const preCheckCompleted = /Pre-submit check completed|mock_check/.test(panelText()) || hasToast("Check completed for ALPHA_RT_001");
    const submitButton = buttonByText("Submit Alpha");
    if (submitButton) submitButton.click();
    await waitUntil(() => hasToast("Confirm submission before proceeding"), 40);
    const submitWithoutConfirmWarned = hasToast("Confirm submission before proceeding");
    const confirmCheckbox = document.querySelector('input[type="checkbox"][aria-describedby="confirm-submit-help"]');
    if (confirmCheckbox) confirmCheckbox.click();
    await waitFrames(12);
    const confirmedSubmitButton = buttonByText("Submit Alpha");
    if (confirmedSubmitButton) confirmedSubmitButton.click();
    await waitUntil(() => hasToast("submitted successfully"), 120);
    const receiptAction = toastAction("View receipt");
    const receiptActionAvailable = Boolean(receiptAction);
    if (receiptAction) receiptAction.click();
    await waitFrames(12);
    const receiptRegion = Array.from(document.querySelectorAll('[role="status"]'))
      .find((node) => /Latest submission receipt/.test(node.textContent || ""));
    await waitUntil(() => Boolean(receiptRegion && document.activeElement && receiptRegion.contains(document.activeElement)), 60);
    const receiptFocused = Boolean(receiptRegion && document.activeElement && receiptRegion.contains(document.activeElement));
    const receiptRegionExists = Boolean(receiptRegion);
    const receiptActiveElementText = (document.activeElement?.textContent || "").slice(0, 160);
    const receiptActiveElementTag = document.activeElement?.tagName || "";

    const candidateJson = document.querySelector('textarea[aria-describedby="candidate-json-validation"]');
    const checkJsonValidation = async (name, value, expectedText) => {
      setValue(candidateJson, value);
      const rejected = await waitUntil(() => panelText().includes(expectedText), 50);
      return {
        name,
        hasControl: Boolean(candidateJson),
        rejected,
        batchCheckDisabled: Boolean(buttonByText("Batch Check")?.disabled),
        batchSubmitDisabled: Boolean(buttonByText("Batch Submit")?.disabled),
      };
    };
    const jsonValidationChecks = [];
    jsonValidationChecks.push(await checkJsonValidation("invalid-json", "{", "Candidate JSON is not valid JSON."));
    jsonValidationChecks.push(await checkJsonValidation("non-array", "{}", "Candidate JSON must be an array."));
    jsonValidationChecks.push(await checkJsonValidation("non-object-row", "[1]", "Every candidate row must be an object."));
    jsonValidationChecks.push(await checkJsonValidation("invalid-alpha-id", '[{"alpha_id":"BAD ID!"}]', "Candidate row 1 alpha_id: Alpha ID may only contain"));
    setValue(candidateJson, '[{"simulation_id":"SIM_ONLY_001","expression":"rank(close)"}]');
    await waitFrames(8);
    const batchSubmitBlockedWithoutAlpha = Boolean(buttonByText("Batch Submit")?.disabled) && /At least one candidate row/.test(panelText());
    setValue(candidateJson, '[{"official_alpha_id":"OFFICIAL_RT_001","simulation_id":"SIM_RT_001","expression":"rank(close)"}]');
    await waitUntil(() => Boolean(buttonByText("Batch Check") && !buttonByText("Batch Check").disabled), 50);
    const batchCheck = buttonByText("Batch Check");
    const batchSubmit = buttonByText("Batch Submit");
    if (batchCheck) batchCheck.click();
    await waitUntil(() => hasToast("Batch check started") || hasToast("Batch check completed"), 80);
    if (batchSubmit) batchSubmit.click();
    await waitUntil(() => hasToast("Batch submission completed"), 120);
    const batchStatusAction = toastAction("View status");
    if (batchStatusAction) batchStatusAction.click();
    await waitUntil(() => Boolean(document.activeElement && (document.activeElement.textContent || "").includes("Batch submission")), 60);
    const batchStatusFocused = Boolean(document.activeElement && (document.activeElement.textContent || "").includes("Batch submission"));

    report.submission = {
      selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
      hasAlphaInput: Boolean(alphaInput),
      invalidAlphaRejected: /Alpha ID may only contain/.test(invalidMessage),
      validAlphaAccepted,
      hasConfirmCheckbox: Boolean(confirmCheckbox),
      preCheckCompleted,
      submitWithoutConfirmWarned,
      receiptActionAvailable,
      receiptRegionExists,
      receiptActiveElementText,
      receiptActiveElementTag,
      submissionActionFocusedReceipt: receiptFocused,
      jsonValidationChecks,
      batchSubmitBlockedWithoutAlpha,
      batchCheckClicked: Boolean(batchCheck),
      batchSubmitClicked: Boolean(batchSubmit),
      batchSubmissionActionFocusedStatus: batchStatusFocused,
    };

    await clickTab("config");
    await waitFrames(12);
    await waitUntil(() => Boolean(labelControl("Dataset")), 80);
    const datasetInput = labelControl("Dataset");
    const initialSaveDisabled = Boolean(buttonByText("Save")?.disabled);
    const exportProbe = { objectUrlCreated: false, revoked: false, downloaded: "", blobType: "", toastShown: false, error: "" };
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const originalAnchorClick = HTMLAnchorElement.prototype.click;
    try {
      URL.createObjectURL = (blob) => {
        exportProbe.objectUrlCreated = true;
        exportProbe.blobType = blob?.type || "";
        return "blob:react-config-export";
      };
      URL.revokeObjectURL = (url) => {
        exportProbe.revoked = url === "blob:react-config-export";
      };
      HTMLAnchorElement.prototype.click = function click() {
        exportProbe.downloaded = this.download || "";
      };
      const exportButton = buttonByText("Export");
      if (exportButton) exportButton.click();
      await waitUntil(() => hasToast("Configuration exported"), 40);
      exportProbe.toastShown = hasToast("Configuration exported");
    } catch (error) {
      exportProbe.error = String(error);
    } finally {
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      HTMLAnchorElement.prototype.click = originalAnchorClick;
    }

    const importInput = document.querySelector('input[type="file"][aria-label="Import configuration JSON"]');
    await setJsonFile(importInput, "invalid-config.json", {
      settings: { region: "MARS", universe: "TOP3000", delay: 1, neutralization: "SUBINDUSTRY", dataset: "fundamental_v0" },
    });
    await waitUntil(() => hasToast("Region is not supported."), 50);
    const invalidImportRejected = hasToast("Region is not supported.");
    const validImportApplied = await setJsonFile(importInput, "valid-config.json", {
      environment: "production",
      autoSubmit: true,
      settings: {
        region: "CHN",
        universe: "TOP1000",
        delay: 0,
        decay: 6,
        neutralization: "MARKET",
        dataset: "imported_v2",
      },
      candidates: 33,
      cycles: 12,
      poolSize: 44,
      backtestBatchSize: 5,
      requireCloudSync: false,
      minSharpe: 1.11,
      minFitness: 1.02,
      minTurnover: 0.02,
      platformMaxTurnover: 0.61,
      maxSelfCorrelation: 0.55,
      maxWeightConcentration: 0.09,
    });
    await waitUntil(() => controlValue("Dataset") === "imported_v2" && hasToast("Configuration imported"), 80);
    const validImportDatasetApplied = controlValue("Dataset") === "imported_v2";

    const selectChanges = [
      ["Region", "USA"],
      ["Universe", "TOP500"],
      ["Delay", "1"],
      ["Neutralization", "SECTOR"],
    ].map(([label, value]) => {
      const control = labelControl(label);
      setValue(control, value);
      return { label, hasControl: Boolean(control), value: control?.value || "" };
    });
    await waitFrames(6);
    const cloudBefore = controlChecked("Cloud Sync Required");
    setChecked(labelControl("Cloud Sync Required"), !cloudBefore);
    const autoSubmitBefore = controlChecked("Auto Submit");
    setChecked(labelControl("Auto Submit"), !autoSubmitBefore);
    await waitFrames(6);

    const checkConfigInvalid = async (label, invalidValue, validValue, expectedText) => {
      const control = labelControl(label);
      setValue(control, invalidValue);
      const rejected = await waitUntil(() => panelText().includes(expectedText), 50);
      const saveDisabled = Boolean(buttonByText("Save")?.disabled);
      setValue(control, validValue);
      await waitUntil(() => !panelText().includes(expectedText), 50);
      return { label, hasControl: Boolean(control), rejected, saveDisabled };
    };
    const validationChecks = [];
    validationChecks.push(await checkConfigInvalid("Dataset", "bad value!", "fundamental_v1", "Dataset may only contain"));
    validationChecks.push(await checkConfigInvalid("Decay", "-1", "6", "Decay must be a non-negative integer."));
    validationChecks.push(await checkConfigInvalid("Max Candidates/Cycle", "0", "33", "Max candidates per cycle must be between 1 and 1000."));
    validationChecks.push(await checkConfigInvalid("Max Cycles", "0", "12", "Max cycles must be between 1 and 10000."));
    validationChecks.push(await checkConfigInvalid("Pool Size", "0", "44", "Pool size must be between 1 and 5000."));
    validationChecks.push(await checkConfigInvalid("Backtest Batch Size", "101", "5", "Backtest batch size must be between 1 and 100."));
    validationChecks.push(await checkConfigInvalid("Min Sharpe", "-0.1", "1.11", "Min Sharpe must be a non-negative number."));
    validationChecks.push(await checkConfigInvalid("Min Fitness", "-0.1", "1.02", "Min Fitness must be a non-negative number."));
    validationChecks.push(await checkConfigInvalid("Min Turnover", "-0.1", "0.02", "Min Turnover must be between 0 and 1."));
    validationChecks.push(await checkConfigInvalid("Max Turnover", "1.2", "0.61", "Max Turnover must be between 0 and 1."));
    validationChecks.push(await checkConfigInvalid("Max Self Correlation", "2", "0.55", "Max Self Correlation must be between 0 and 1."));
    validationChecks.push(await checkConfigInvalid("Max Weight Concentration", "2", "0.09", "Max Weight Concentration must be between 0 and 1."));
    setValue(labelControl("Min Turnover"), "0.8");
    setValue(labelControl("Max Turnover"), "0.2");
    const turnoverRelationRejected = await waitUntil(() => panelText().includes("Min turnover cannot exceed max turnover."), 50);
    const turnoverRelationSaveDisabled = Boolean(buttonByText("Save")?.disabled);
    setValue(labelControl("Min Turnover"), "0.02");
    setValue(labelControl("Max Turnover"), "0.61");
    await waitUntil(() => !panelText().includes("Min turnover cannot exceed max turnover."), 50);
    if (datasetInput) setValue(datasetInput, "fundamental_v1");
    await waitFrames(4);
    const saveEnabledAfterValidEdit = Boolean(buttonByText("Save") && !buttonByText("Save").disabled);
    const saveButton = buttonByText("Save");
    if (saveButton) saveButton.click();
    await waitUntil(() => hasToast("Configuration saved"), 80);
    report.config = {
      selected: document.querySelector('[role="tab"][aria-selected="true"]')?.id || "",
      hasDatasetInput: Boolean(datasetInput),
      initialSaveDisabled,
      invalidDatasetRejected: validationChecks.some((item) => item.label === "Dataset" && item.rejected),
      validDatasetEnablesSave: saveEnabledAfterValidEdit,
      saveClicked: Boolean(saveButton),
      saveToastShown: hasToast("Configuration saved"),
      hasImportExport: Boolean(buttonByText("Import")) && Boolean(buttonByText("Export")),
      exportProbe,
      invalidImportRejected,
      validImportApplied: Boolean(validImportApplied && validImportDatasetApplied),
      importToastShown: hasToast("Configuration imported"),
      selectChanges,
      checkboxesToggled: controlChecked("Cloud Sync Required") !== cloudBefore && controlChecked("Auto Submit") !== autoSubmitBefore,
      validationChecks,
      turnoverRelation: { rejected: turnoverRelationRejected, saveDisabled: turnoverRelationSaveDisabled },
    };
    return report;
  })()`;
}

function validateMetrics(metrics, session) {
  const failures = [];
  if (metrics.title !== "BRAIN Alpha Ops") failures.push("page title mismatch");
  if (metrics.readyState !== "complete") failures.push("document did not finish loading");
  if (!metrics.rootExists) failures.push("missing React root");
  if (metrics.rootChildCount < 1) failures.push("React root did not render children");
  if (!metrics.hasHeading) failures.push("missing app heading");
  if (!metrics.hasVersionLabel) failures.push("missing app version label");
  if (metrics.roles.tablist !== 1) failures.push("expected one tablist");
  if (metrics.roles.tab !== 20) failures.push("expected twenty React tabs");
  if (metrics.roles.selectedTabs !== 1) failures.push("expected one selected tab");
  if (metrics.roles.tabpanel !== 1) failures.push("expected one tabpanel");
  if (!metrics.meta.csrf || !metrics.meta.stream) failures.push("missing CSRF or stream meta token placeholder");
  if (metrics.resources.length < 2) failures.push("expected JS and CSS assets to load");
  if (metrics.pageOverflowX) failures.push("page overflows horizontally");
  const severeConsole = session.consoleMessages.filter((message) => ["error", "assert"].includes(message.type));
  const failedNonApiResponses = session.responses.filter((response) => response.status >= 400 && !/\/api\//.test(response.url));
  if (severeConsole.length) failures.push("browser console reported errors");
  if (failedNonApiResponses.length) failures.push("document or asset responses returned HTTP errors");
  if (session.networkFailures.length) failures.push("browser reported network loading failures");
  return failures;
}

function validateInteractions(interactions, session) {
  const failures = [];
  const posted = (path) => session.mockRequests.some((request) => request.method === "POST" && request.path === path);
  const postedPayload = (path) => {
    const request = [...session.mockRequests].reverse().find((entry) => entry.method === "POST" && entry.path === path && entry.body);
    if (!request) return null;
    try {
      return JSON.parse(request.body);
    } catch {
      return null;
    }
  };
  if (!interactions.dashboard?.hasCloudKpi || !interactions.dashboard?.hasMemoryKpi) {
    failures.push("dashboard did not render mocked KPI data");
  }
  if (interactions.dashboard?.hasDashboardError) failures.push("dashboard rendered an unexpected data error");
  if (!interactions.candidates?.hasFilter || !interactions.candidates?.hasCandidate) {
    failures.push("candidate tab did not render filterable candidate data");
  }
  if (interactions.candidates?.countClampedTo !== "100") failures.push("candidate generate count did not clamp to 100");
  if (interactions.candidates?.countSubmittedAs !== "7" || !posted("/api/generate_candidates")) {
    failures.push("candidate generate action did not submit the edited count flow");
  }
  const generatePayload = postedPayload("/api/generate_candidates");
  if (!generatePayload || generatePayload.count !== 7) failures.push("candidate generate POST body did not include count 7");
  if (!interactions.candidates?.hasVirtualTable) failures.push("candidate table virtualization marker is missing");
  const largeListTotal = interactions.candidates?.largeListStatus?.total || 0;
  if (largeListTotal < 1000) {
    failures.push("candidate browser smoke did not load a 1000+ row list");
  }
  if ((interactions.candidates?.largeListAriaRowCount || 0) < 1001) {
    failures.push("candidate table did not expose large-list aria row count");
  }
  if (
    !interactions.candidates?.renderedInitialRows ||
    interactions.candidates.renderedInitialRows >= largeListTotal
  ) {
    failures.push("candidate table rendered the whole large list instead of a virtual window");
  }
  if (!interactions.candidates?.rowWindowChangedAfterScroll) {
    failures.push("candidate virtual window did not move after scrolling");
  }
  if (!interactions.candidates?.filterSanitized) failures.push("candidate filter did not sanitize control characters or length");
  if ((interactions.candidates?.largeListLoadMs || 0) > 8000) failures.push("candidate large-list browser load exceeded 8s");
  if ((interactions.candidates?.scrollInteractionMs || 0) > 2000) failures.push("candidate virtual scroll interaction exceeded 2s");
  const queueExpectations = {
    pending_backtest: 1000,
    running_backtest: 1,
    backtest_rework: 1,
    passed: 1,
    submittable: 1,
    submitted: 1,
    failed: 1,
  };
  for (const [id, expectedTotal] of Object.entries(queueExpectations)) {
    const view = (interactions.queueViews || []).find((item) => item.id === id);
    if (!view?.titleVisible || view?.selected !== `app-tab-${id}` || view?.status?.total !== expectedTotal || !view?.hasVirtualTable) {
      failures.push(`candidate queue view ${id} did not render the expected filtered rows`);
    }
  }
  if (interactions.snapshotViews?.length !== 8) {
    failures.push("snapshot tabs did not render the expected eight data views");
  }
  for (const item of interactions.snapshotViews || []) {
    if (!item.titleVisible || item.selected !== `app-tab-${item.id}` || !item.hasTable || !item.rowVisible) {
      failures.push(`snapshot view ${item.id} did not render the expected snapshot data`);
    }
  }
  if (!interactions.scoring?.hasAlphaExpression || !interactions.scoring?.hasCandidateId || !interactions.scoring?.hasScorecard) {
    failures.push("score action did not open candidate scoring details");
  }
  if (!interactions.submission?.invalidAlphaRejected || !interactions.submission?.validAlphaAccepted) {
    failures.push("submission alpha-id validation did not behave as expected");
  }
  if (!interactions.submission?.hasConfirmCheckbox) failures.push("submission confirmation checkbox is missing");
  if (!interactions.submission?.preCheckCompleted || !posted("/api/check")) {
    failures.push("submission pre-check did not complete through the browser UI");
  }
  if (!interactions.submission?.submitWithoutConfirmWarned) failures.push("submission did not warn before unconfirmed submit");
  if (!interactions.submission?.submissionActionFocusedReceipt || !posted("/api/submit")) {
    failures.push("submission success toast action did not focus the receipt");
  }
  if (!interactions.submission?.jsonValidationChecks?.every((item) => item.hasControl && item.rejected && item.batchCheckDisabled && item.batchSubmitDisabled)) {
    failures.push("submission candidate JSON browser validation did not reject every malformed case");
  }
  if (!interactions.submission?.batchSubmitBlockedWithoutAlpha) {
    failures.push("batch submit did not require alpha_id or official_alpha_id");
  }
  if (!interactions.submission?.batchCheckClicked || !posted("/api/check_batch")) {
    failures.push("batch check browser flow did not post to the API");
  }
  if (!interactions.submission?.batchSubmitClicked || !posted("/api/submit_batch")) {
    failures.push("batch submit browser flow did not post to the API");
  }
  if (!interactions.submission?.batchSubmissionActionFocusedStatus) {
    failures.push("batch submission toast action did not focus the status panel");
  }
  const batchSubmitPayload = postedPayload("/api/submit_batch");
  if (!batchSubmitPayload?.alpha_ids?.includes("OFFICIAL_RT_001")) {
    failures.push("batch submit POST body did not include the validated official alpha ID");
  }
  if (!interactions.config?.initialSaveDisabled || !interactions.config?.invalidDatasetRejected || !interactions.config?.validDatasetEnablesSave) {
    failures.push("config edit validation/save state did not behave as expected");
  }
  if (!interactions.config?.saveToastShown || !posted("/api/config")) {
    failures.push("config save flow did not complete through the browser UI");
  }
  if (!interactions.config?.hasImportExport) failures.push("config import/export controls are missing");
  if (
    !interactions.config?.exportProbe?.objectUrlCreated ||
    !interactions.config?.exportProbe?.revoked ||
    !/^brain-alpha-config-\d{4}-\d{2}-\d{2}\.json$/.test(interactions.config.exportProbe.downloaded || "") ||
    interactions.config.exportProbe.blobType !== "application/json" ||
    !interactions.config.exportProbe.toastShown
  ) {
    failures.push("config export browser flow did not create a downloadable JSON file");
  }
  if (!interactions.config?.invalidImportRejected || !interactions.config?.validImportApplied || !interactions.config?.importToastShown) {
    failures.push("config import browser flow did not validate and apply JSON files");
  }
  if (!interactions.config?.selectChanges?.every((item) => item.hasControl && item.value)) {
    failures.push("config select controls did not accept valid browser edits");
  }
  if (!interactions.config?.checkboxesToggled) failures.push("config checkbox controls did not toggle in the browser");
  if (!interactions.config?.validationChecks?.every((item) => item.hasControl && item.rejected && item.saveDisabled)) {
    failures.push("config browser validation did not reject every invalid editable field");
  }
  if (!interactions.config?.turnoverRelation?.rejected || !interactions.config?.turnoverRelation?.saveDisabled) {
    failures.push("config turnover cross-field validation did not run in the browser");
  }
  return failures;
}

async function configureSession(session) {
  await session.send("Page.enable");
  await session.send("Runtime.enable");
  await session.send("Network.enable");
  await session.send("Network.setCacheDisabled", { cacheDisabled: true });
  await session.send("Fetch.enable", {
    patterns: [
      { urlPattern: "*://*/api/*", requestStage: "Request" },
      { urlPattern: "*://*/sse*", requestStage: "Request" },
    ],
  });
}

async function runViewport(session, url, viewport, outputDir) {
  session.resetObservations();
  await session.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: Boolean(viewport.mobile),
  });

  const loaded = session.waitForEvent("Page.loadEventFired", 30000);
  const navigationUrl = new URL(url);
  navigationUrl.searchParams.set("__react_artifact_smoke", `${viewport.name}-${Date.now()}`);
  await session.send("Page.navigate", { url: navigationUrl.toString() });
  await loaded;
  await session.evaluate("new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
  const metrics = await session.evaluate(metricsExpression());
  const interactions = await session.evaluate(interactionExpression());
  const screenshot = await session.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const screenshotPath = path.join(outputDir, `react-artifact-smoke-${viewport.name}.png`);
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));

  const failures = [...validateMetrics(metrics, session), ...validateInteractions(interactions, session)];
  return {
    name: viewport.name,
    ok: failures.length === 0,
    failures,
    screenshot: screenshotPath,
    metrics,
    interactions,
    consoleMessages: [...session.consoleMessages],
    networkFailures: [...session.networkFailures],
    failedNonApiResponses: session.responses.filter((response) => response.status >= 400 && !/\/api\//.test(response.url)),
    apiResponses: session.responses.filter((response) => /\/api\//.test(response.url)),
    mockRequests: [...session.mockRequests],
  };
}

async function main() {
  if (hasFlag("--help") || hasFlag("-h")) {
    console.log(usage());
    return 0;
  }
  const url = argValue("--url");
  if (!url) {
    console.error(usage());
    return 2;
  }
  const devtoolsUrl = argValue("--devtools-url", "http://127.0.0.1:9224").replace(/\/$/, "");
  const outputDir = argValue("--output-dir", "output/react-artifact-smoke");
  fs.mkdirSync(outputDir, { recursive: true });

  let target = null;
  let session = null;
  try {
    target = await fetchJson(`${devtoolsUrl}/json/new?about:blank`, { method: "PUT" });
    session = new CdpSession(target.webSocketDebuggerUrl);
    await session.connect();
    await configureSession(session);
    const viewports = [
      { name: "desktop-1366x900", width: 1366, height: 900, mobile: false },
      { name: "mobile-390x844", width: 390, height: 844, mobile: true },
    ];
    const runs = [];
    for (const viewport of viewports) {
      runs.push(await runViewport(session, url, viewport, outputDir));
    }
    const result = {
      ok: runs.every((run) => run.ok),
      schema_version: "browser_react_artifact_smoke.v1",
      url,
      devtoolsUrl,
      generated_at: new Date().toISOString(),
      runs,
    };
    const resultPath = path.join(outputDir, "browser-react-artifact-smoke.json");
    fs.writeFileSync(resultPath, JSON.stringify(result, null, 2), "utf-8");
    if (hasFlag("--json")) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      console.log(`${result.ok ? "PASS" : "FAIL"} React artifact browser smoke`);
      console.log(`Report: ${resultPath}`);
      for (const run of runs) {
        console.log(`- ${run.name}: ${run.ok ? "PASS" : `FAIL ${run.failures.join("; ")}`}`);
      }
    }
    return result.ok ? 0 : 1;
  } finally {
    if (session) session.close();
    if (target) await closeTarget(devtoolsUrl, target.id);
  }
}

main().then((code) => {
  process.exitCode = code;
}).catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
