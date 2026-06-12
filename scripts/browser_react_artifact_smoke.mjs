#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

let currentSmokeViewport = "";
let currentSmokeState = createSmokeState();

const SECRET_TEXT_PATTERN = /(?:csrf[_-]?token|session[_-]?id|auth(?:orization)?|access[_-]?token|refresh[_-]?token|stream[_-]?token|id[_-]?token|api[_-]?key|client[_-]?secret|set[_-]?cookie|cookie|password|passwd|pwd|secret|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/i;
const REPORT_FORBIDDEN_TEXT_PATTERN = /(?:csrf[_-]?token|session[_-]?id|auth(?:orization)?|access[_-]?token|refresh[_-]?token|stream[_-]?token|id[_-]?token|api[_-]?key|client[_-]?secret|set[_-]?cookie|cookie|password|passwd|pwd|hunter2|secret-token|operator@example|csrf-secret|session-secret|raw backend|Official context refreshed|candidate family lacks official simulation metrics|fields failed|SESSION_INVALID|invalid local session)/i;
const REPORT_RAW_BACKEND_TEXT_PATTERN = /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|Official context refreshed|candidate family lacks official simulation metrics|fields failed)/gi;
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const VALID_SLICES = ["full", "replay_audit", "scoring_failure_retry"];
const ALLOWED_MUTATING_REQUESTS = new Set([
  "POST /api/run",
  "POST /api/sync_alphas",
  "POST /api/sync_cancel",
  "POST /api/generate_candidates",
  "POST /api/candidates/simulate",
  "POST /api/check_batch",
  "POST /api/scoring/evaluate",
  "POST /api/scoring/attribution",
]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const SENSITIVE_KEY_PATTERN = /(?:^|[_-])(?:username|user[_-]?name|email|password|passwd|pwd|token|csrf|stream|session|cookie|authorization|auth|api[_-]?key|client[_-]?secret|secret)(?:$|[_-])/i;

function createSmokeState() {
  return {
    syncStartCount: 0,
    syncCompactStatusCount: 0,
    scoringEvaluateCount: 0,
    candidateSimulationCount: 0,
    candidateSimulationSucceeded: false,
    checkBatchBeforeSimulationSuccessCount: 0,
    stoppedSyncJobs: new Set(),
  };
}

function resetSmokeState() {
  currentSmokeState = createSmokeState();
}

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function usage() {
  return [
    "Usage: node scripts/browser_react_artifact_smoke.mjs --url <local-react-url>",
    "",
    "Options:",
    "  --devtools-url <url>   Chrome DevTools HTTP URL, default http://127.0.0.1:9224",
    "  --output-dir <dir>     Artifact directory, default output/react-artifact-smoke",
    "  --slice <name>         Optional focused slice: full, replay_audit, or scoring_failure_retry; default full",
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
    this.networkRequests = [];
    this.responses = [];
    this.mockRequests = [];
    this.blockedNonLocalRequests = [];
    this.stepContext = { viewport: "", step: "", startedAt: 0 };
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
    this.networkRequests = [];
    this.responses = [];
    this.mockRequests = [];
    this.blockedNonLocalRequests = [];
    this.stepContext = { viewport: "", step: "", startedAt: 0 };
  }

  handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.id && this.pending.has(message.id)) {
      const { resolve, reject, timer } = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(timer);
      if (message.error) reject(new Error(`${message.error.message || "CDP error"} (${message.error.code})`));
      else resolve(message.result || {});
      return;
    }
    if (message.method === "Runtime.consoleAPICalled") {
      this.consoleMessages.push({
        type: message.params?.type || "",
        text: redactText((message.params?.args || []).map((arg) => arg.value || arg.description || "").join(" ").slice(0, 500)),
      });
    }
    if (message.method === "Network.requestWillBeSent") {
      const request = message.params?.request || {};
      const rawUrl = request.url || "";
      this.networkRequests.push({
        url: redactUrl(rawUrl),
        method: request.method || "",
        type: message.params?.type || "",
        isLocal: isLocalBrowserUrl(rawUrl),
      });
    }
    if (message.method === "Network.loadingFailed") {
      this.networkFailures.push({
        requestId: message.params?.requestId || "",
        errorText: redactText(message.params?.errorText || ""),
        blockedReason: redactText(message.params?.blockedReason || ""),
      });
    }
    if (message.method === "Network.responseReceived") {
      const response = message.params?.response || {};
      const rawUrl = response.url || "";
      this.responses.push({
        url: redactUrl(rawUrl),
        status: response.status || 0,
        type: message.params?.type || "",
        mimeType: response.mimeType || "",
        isApi: isMockedApiUrl(rawUrl),
        isLocal: isLocalBrowserUrl(rawUrl),
      });
    }
    if (message.method === "Fetch.requestPaused") {
      this.fulfillMockRequest(message.params).catch((error) => {
        this.consoleMessages.push({ type: "error", text: redactText(`mock request failed: ${String(error)}`) });
      });
      return;
    }
    if (message.method && this.eventWaiters.has(message.method)) {
      const waiters = this.eventWaiters.get(message.method);
      this.eventWaiters.delete(message.method);
      waiters.forEach((resolve) => resolve(message.params || {}));
    }
  }

  send(method, params = {}, timeoutMs = 15000) {
    const id = this.nextId;
    this.nextId += 1;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!this.pending.has(id)) return;
        this.pending.delete(id);
        reject(new Error(this.diagnosticMessage(`Timed out waiting for ${method}`)));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  waitForEvent(method, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(this.diagnosticMessage(`Timed out waiting for ${method}`))), timeout);
      const wrappedResolve = (params) => {
        clearTimeout(timer);
        resolve(params);
      };
      const waiters = this.eventWaiters.get(method) || [];
      waiters.push(wrappedResolve);
      this.eventWaiters.set(method, waiters);
    });
  }

  async evaluate(expression, timeoutMs = 15000) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    }, timeoutMs);
    if (result.exceptionDetails) {
      throw new Error(`Runtime evaluation failed: ${JSON.stringify(result.exceptionDetails)}`);
    }
    return result.result ? result.result.value : undefined;
  }

  setStepContext(viewport, step, startedAt = Date.now()) {
    this.stepContext = { viewport, step, startedAt };
  }

  clearStepContext() {
    this.stepContext = { viewport: "", step: "", startedAt: 0 };
  }

  lastMockEndpoint() {
    const last = this.mockRequests[this.mockRequests.length - 1];
    if (!last) return "none";
    return `${last.method} ${last.path}${last.search || ""} status=${last.status}`;
  }

  diagnosticMessage(message, stepOverride = "") {
    const context = this.stepContext || {};
    const startedAt = Number(context.startedAt || 0);
    const elapsedMs = startedAt > 0 ? Date.now() - startedAt : 0;
    const viewport = context.viewport || currentSmokeViewport || "unknown";
    const step = stepOverride || context.step || "unknown";
    return `${message} (viewport=${viewport}; step=${step}; elapsed_ms=${elapsedMs}; last_mock_endpoint=${this.lastMockEndpoint()})`;
  }

  async captureScreenshot(filePath) {
    const screenshot = await this.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(filePath, Buffer.from(screenshot.data, "base64"));
    return filePath;
  }

  async fulfillMockRequest(params) {
    const requestId = params.requestId;
    const request = params.request || {};
    const rawUrl = request.url || "";
    if (!isLocalBrowserUrl(rawUrl)) {
      this.blockedNonLocalRequests.push({
        method: request.method || "GET",
        url: redactUrl(rawUrl),
      });
      await this.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: 451,
        responseHeaders: [
          { name: "Content-Type", value: "application/json; charset=utf-8" },
          { name: "Cache-Control", value: "no-store" },
        ],
        body: Buffer.from(JSON.stringify({ ok: false, error_code: "NON_LOCAL_BROWSER_SMOKE_REQUEST_BLOCKED" }), "utf8").toString("base64"),
      });
      return;
    }
    if (!isMockedApiUrl(rawUrl)) {
      await this.send("Fetch.continueRequest", { requestId });
      return;
    }
    const payload = mockApiPayload(rawUrl, request.method || "GET", request.postData || "");
    const url = new URL(rawUrl);
    this.mockRequests.push({
      method: request.method || "GET",
      path: url.pathname,
      search: redactSearchParams(url.search),
      status: payload?.status || 501,
      body: redactRequestBody(request.postData || ""),
      hasCredentialFields: requestHasCredentialFields(request.postData || ""),
      hasCredentialSearch: searchHasCredentialFields(url.search),
    });
    if (!payload) {
      await this.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: 501,
        responseHeaders: [
          { name: "Content-Type", value: "application/json; charset=utf-8" },
          { name: "Cache-Control", value: "no-store" },
        ],
        body: Buffer.from(JSON.stringify({ ok: false, error_code: "UNMOCKED_BROWSER_SMOKE_API" }), "utf8").toString("base64"),
      });
      return;
    }
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

function redactRequestBody(rawBody) {
  if (!rawBody) return "";
  try {
    const parsed = JSON.parse(rawBody);
    return JSON.stringify(redactSecrets(parsed));
  } catch {
    return rawBody.replace(/([^=&\s]+)=([^&\s]+)/g, (match, key) => (
      isSensitiveKey(String(key)) ? `${key}=[redacted]` : match
    ));
  }
}

function redactText(text) {
  if (!text) return "";
  return String(text)
    .replace(/([?&])([^=&\s]+)=([^&\s]+)/g, (match, prefix, key) => (
      isSensitiveKey(String(key)) ? `${prefix}${key}=[redacted]` : match
    ))
    .replace(SECRET_TEXT_PATTERN, "[redacted]")
    .replace(REPORT_RAW_BACKEND_TEXT_PATTERN, "[redacted]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted]");
}

function redactUrl(rawUrl) {
  if (!rawUrl) return "";
  try {
    const parsed = new URL(rawUrl);
    parsed.username = "";
    parsed.password = "";
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (/token|csrf|password|username|session/i.test(key)) {
        parsed.searchParams.set(key, "[redacted]");
      }
    }
    return redactText(parsed.toString());
  } catch {
    return redactText(rawUrl);
  }
}

function redactReportValue(value) {
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.map((item) => redactReportValue(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      redactReportValue(item),
    ]));
  }
  return value;
}

function assertReportRedacted(serialized) {
  if (REPORT_FORBIDDEN_TEXT_PATTERN.test(serialized)) {
    throw new Error("browser smoke report contains sensitive or raw backend text");
  }
}

function isLoopbackHostname(hostname) {
  return LOOPBACK_HOSTS.has(hostname);
}

function isLocalBrowserUrl(rawUrl) {
  if (!rawUrl) return false;
  try {
    const parsed = new URL(rawUrl);
    if (["about:", "data:", "blob:"].includes(parsed.protocol)) return true;
    if (["http:", "https:", "ws:", "wss:"].includes(parsed.protocol)) {
      return isLoopbackHostname(parsed.hostname);
    }
    return false;
  } catch {
    return false;
  }
}

function requireLoopbackHttpUrl(rawUrl, label) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error(`${label} must be a valid loopback URL`);
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !isLoopbackHostname(parsed.hostname)) {
    throw new Error(`${label} must use http(s) on localhost, 127.0.0.1, or ::1`);
  }
  return parsed.toString();
}

function isMockedApiUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return isLocalBrowserUrl(rawUrl) && (parsed.pathname.startsWith("/api/") || parsed.pathname.startsWith("/sse"));
  } catch {
    return false;
  }
}

function isAllowedMutatingRequest(method, pathName) {
  return ALLOWED_MUTATING_REQUESTS.has(`${method} ${pathName}`);
}

function normalizeSensitiveKey(key) {
  return String(key || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function isSensitiveKey(key) {
  const normalized = normalizeSensitiveKey(key);
  return SENSITIVE_KEY_PATTERN.test(normalized);
}

function requestHasCredentialFields(rawBody) {
  if (!rawBody) return false;
  try {
    return objectHasCredentialFields(JSON.parse(rawBody));
  } catch {
    return /([^=&\s]+)=([^&\s]+)/g.test(rawBody) && Array.from(rawBody.matchAll(/([^=&\s]+)=([^&\s]+)/g))
      .some((match) => isSensitiveKey(match[1]));
  }
}

function objectHasCredentialFields(value) {
  if (Array.isArray(value)) return value.some((item) => objectHasCredentialFields(item));
  if (value && typeof value === "object") {
    return Object.entries(value).some(([key, item]) => (
      isSensitiveKey(key) ||
      objectHasCredentialFields(item)
    ));
  }
  return false;
}

function searchHasCredentialFields(rawSearch) {
  if (!rawSearch) return false;
  const params = new URLSearchParams(rawSearch);
  return Array.from(params.keys()).some((key) => isSensitiveKey(key));
}

function redactSearchParams(rawSearch) {
  if (!rawSearch) return "";
  const params = new URLSearchParams(rawSearch);
  for (const key of Array.from(params.keys())) {
    if (isSensitiveKey(key)) params.delete(key);
  }
  const redacted = params.toString();
  return redacted ? `?${redacted}` : "";
}

function redactSecrets(value) {
  if (Array.isArray(value)) return value.map((item) => redactSecrets(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      isSensitiveKey(key) ? "[redacted]" : key,
      isSensitiveKey(key) ? "[redacted]" : redactSecrets(item),
    ]));
  }
  return value;
}

function mockApiPayload(rawUrl, method, rawBody = "") {
  const url = new URL(rawUrl);
  const pathname = url.pathname;
  const ok = (json) => ({ status: 200, json });
  if (MUTATING_METHODS.has(method) && !isAllowedMutatingRequest(method, pathname)) {
    return { status: 405, json: { ok: false, error_code: "UNEXPECTED_BROWSER_SMOKE_WRITE" } };
  }

  if (method === "GET" && pathname === "/api/phase_state") {
    return ok({
      ok: true,
      current_phase: "evaluate",
      operation_mode: "connected",
      connected: true,
      context_fresh: true,
      candidates_count: 3,
      scored_count: 1,
      readiness_passed: false,
      sync: { in_progress: false, scanned: 0, total: 0, elapsed_seconds: 0, stalled: false },
      readiness: { eligible_count: 0, ready: false },
      official_context_cache: {
        ok: true,
        fields_count: 8599,
        operators_count: 67,
        datasets_count: 20,
        manifest: {
          complete: true,
          is_stale: false,
          missing_files: [],
          stale_files: [],
          invalid_files: [],
          record_counts: {
            "official_fields.json": 8599,
            "official_operators.json": 67,
            "official_datasets.json": 20,
          },
        },
      },
      cloud_alpha_cache: {
        ok: true,
        count: 2,
        total: 2,
        source: "mock",
        is_stale: false,
        loaded_at: "2026-06-11T00:00:00Z",
      },
    });
  }
  if (method === "GET" && pathname === "/api/production-validation/status") {
    const jobId = url.searchParams.get("job_id") || "";
    if (jobId === "job_validation_interrupted") {
      return ok({
        ok: false,
        job_id: jobId,
        status: "stopped",
        status_kind: "interrupted",
        terminal: true,
        interrupted: true,
        recoverable: true,
        retryable: true,
        error: "raw backend cancellation",
        user_error: {
          kind: "task_cancelled",
          message: "验证流程已停止，结果未确认完成。",
        },
        progress: {
          phase: "session_invalid",
          status_kind: "interrupted",
          terminal: true,
          interrupted: true,
          percent_complete: 100,
        },
      });
    }
    return ok({
      ok: true,
      job_id: "",
      status: "idle",
      progress: {
        phase: "idle",
        status_message: "等待启动非提交生产验证。",
        submitted_this_run: 0,
        auto_submitted: 0,
      },
    });
  }
  if (method === "GET" && pathname === "/api/candidates") {
    return ok({
      ok: true,
      total: 3,
      candidates: [
        candidateFixture("ALPHA_RT_001", "submission_ready", 82),
        candidateFixture("ALPHA_RT_002", "running_backtest", 67),
        candidateFixture("ALPHA_RT_003", "pending_backtest", 48),
      ],
    });
  }
  if (method === "GET" && pathname === "/api/alpha_lifecycle") {
    if (currentSmokeViewport.includes("mobile")) {
      return ok({
        ok: false,
        error: "raw lifecycle backend failure",
        user_error: {
          kind: "lifecycle_history_unavailable",
          message: "生命周期历史加载失败，请稍后重试。",
        },
      });
    }
    return ok({
      ok: true,
      official_api_called: false,
      submit_allowed: false,
      schema_version: "alpha_lifecycle_history.v1",
      count: 4,
      limit: Number(url.searchParams.get("limit") || 250),
      summary: {
        record_count: 4,
        alpha_count: 3,
        passed_count: 1,
        blocked_count: 1,
        failed_count: 1,
        submitted_count: 0,
        replay_ready: true,
        by_status_category: {
          passed: 1,
          blocked: 1,
          failed: 1,
        },
      },
      alpha_traces: [
        {
          trace_key: "ALPHA_RT_001",
          alpha_id: "ALPHA_RT_001",
          official_alpha_id: "OFFICIAL_RT_001",
          simulation_id: "SIM_ALPHA_RT_001",
          latest_stage: "local_quality",
          latest_status: "FAILED",
          status_category: "failed",
          event_count: 1,
          latest_event_at: "2026-06-12T01:01:00Z",
          last_note: "local validation failed; sensitive detail redacted",
          next_action: "optimize_or_archive",
          failed: true,
          submitted: false,
        },
        {
          trace_key: "ALPHA_RT_002",
          alpha_id: "ALPHA_RT_002",
          simulation_id: "SIM_ALPHA_RT_002",
          latest_stage: "official_validation",
          latest_status: "PASSED",
          status_category: "passed",
          event_count: 2,
          latest_event_at: "2026-06-12T01:05:00Z",
          last_note: "official metrics complete",
          next_action: "continue_validation",
          blocked: true,
          passed: true,
        },
        {
          trace_key: "ALPHA_RT_003",
          alpha_id: "ALPHA_RT_003",
          simulation_id: "SIM_ALPHA_RT_003",
          latest_stage: "submission_blocked",
          latest_status: "BLOCKED",
          status_category: "blocked",
          event_count: 1,
          latest_event_at: "2026-06-12T01:03:00Z",
          last_note: "sensitive detail redacted",
          next_action: "review_blockers",
          blocked: true,
        },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/backtest_slots") {
    return ok({
      ok: true,
      slot_limit: 3,
      active_count: 1,
      queue_summary: {
        slot_limit: 3,
        open_slot_count: 2,
        candidate_count: 3,
        local_valid_count: 1,
        blocked_candidate_count: 2,
        above_simulation_score_count: 1,
        review_candidate_count: 0,
        submit_evidence_blocking_count: 2,
        official_api_called: false,
        top_blocking_reasons: [
          { reason: "local_backtest_failed", count: 1 },
          { reason: "score_below_official_simulation_threshold", count: 1 },
        ],
        top_submit_blocking_reasons: [
          { reason: "missing_official_metrics", count: 2 },
          { reason: "scientific_audit_test_feedback_used", count: 1 },
        ],
        next_action: "raw backend action password=secret",
      },
      slots: [
        { slot: 1, status: "RUNNING", alpha_id: "ALPHA_RT_002" },
        { slot: 2, status: "EMPTY" },
        { slot: 3, status: "COMPLETED", alpha_id: "ALPHA_RT_001" },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/submit_readiness") {
    return ok({
      ok: true,
      ready_to_submit: false,
      candidate_count: 3,
      eligible_count: 0,
      blocked_count: 2,
      job_family_candidate_count: 1,
      latest_job_id: "job_validation_interrupted",
      summary_counts: {
        submission_ready: 0,
        submitted_this_run: 0,
        auto_submitted: 0,
        official_validation_passed: 1,
        officially_simulated: 0,
      },
      threshold_summary: {
        min_sharpe: 1.25,
        min_fitness: 1,
        platform_max_turnover: 0.7,
        max_self_correlation: 0.7,
      },
      top_blocking_reasons: [
        { reason: "missing_official_metrics", count: 2 },
        { reason: "missing_scientific_audit", count: 1 },
      ],
      top_family_blocking_reasons: [
        { reason: "candidate_family_missing_official_metrics", count: 1 },
        { reason: "scientific_audit_submit_boundary_breached", count: 1 },
      ],
      required_next_steps: [
        "run official simulation/check in a trusted environment",
        "resolve local blockers before submit review",
        "raw backend-only submit action",
      ],
      production_gaps: [
        { code: "missing_official_metrics", message: "candidate family lacks official simulation metrics" },
        { message: "raw backend-only submission gap" },
        { code: "latest_candidate_scientific_audit_test_feedback_used" },
      ],
      best_candidate: {
        alpha_id: "ALPHA_RT_002",
        score: 67,
        decision_band: "optimize",
        max_similarity: 0.21,
        local_backtest_passed: false,
        risk_level: "medium",
        blocking_reasons: [
          "missing_official_metrics",
          "decision_band_not_submit_candidate",
          "incomplete_scientific_audit",
        ],
      },
    });
  }
  if (method === "GET" && pathname === "/api/check_results") {
    return ok({
      ok: true,
      count: 2,
      items: [
        { alpha_id: "ALPHA_RT_001", status: "PASS", passed: true, summary: "official checks passed" },
        {
          alpha_id: "ALPHA_RT_002",
          status: "RAW_BACKEND_CHECK_STATUS",
          passed: false,
          summary: "official metrics missing",
          failed_reasons: [
            "missing_scientific_audit",
            "scientific_audit_submit_boundary_breached",
            "raw backend-only check reason",
          ],
        },
      ],
    });
  }
  if (method === "POST" && pathname === "/api/sync_alphas") {
    currentSmokeState.syncStartCount += 1;
    let jobId = "sync_warning";
    if (currentSmokeState.syncStartCount === 1) jobId = "sync_open_ended_scan";
    else if (currentSmokeState.syncStartCount === 2) jobId = "sync_cancelled_terminal";
    return ok({ ok: true, job_id: jobId, task_id: jobId, status_url: `/api/sync_status?job_id=${jobId}` });
  }
  if (method === "GET" && pathname === "/api/sync_status") {
    const jobId = url.searchParams.get("job_id") || "";
    if (!jobId && url.searchParams.get("compact") === "1") {
      currentSmokeState.syncCompactStatusCount += 1;
      if (currentSmokeState.syncCompactStatusCount === 1) {
        return ok({
          ok: false,
          error_code: "SESSION_INVALID",
          error: "invalid local session",
          user_error: {
            kind: "session_invalid",
            message: "本地会话已失效，请重新连接后继续。",
          },
        });
      }
    }
    if (jobId === "sync_open_ended_scan") {
      const wasStopped = currentSmokeState.stoppedSyncJobs.has(jobId);
      return ok({
        ok: true,
        job_id: jobId,
        task_id: jobId,
        status: wasStopped ? "stopped" : "running",
        status_kind: wasStopped ? "interrupted" : "active",
        terminal: wasStopped,
        interrupted: wasStopped,
        recoverable: true,
        retryable: true,
        phase: wasStopped ? "stopped" : "scan",
        status_message: wasStopped
          ? "用户已停止本次官方上下文刷新，结果未确认完成；后台确认状态为已停止。"
          : "Scanning cloud alphas: 10800 / 10800",
        progress: {
          job_id: jobId,
          task_id: jobId,
          phase: wasStopped ? "stopped" : "scan",
          status_code: wasStopped ? "STOPPED" : "SCAN",
          status_kind: wasStopped ? "interrupted" : "active",
          terminal: wasStopped,
          interrupted: wasStopped,
          phase_label: wasStopped ? "已停止" : "扫描云端",
          status_message: wasStopped
            ? "用户已停止本次官方上下文刷新，结果未确认完成；后台确认状态为已停止。"
            : "Scanning cloud alphas: 10800 / 10800",
          percent_complete: 100,
          scanned: 10800,
          total: 10800,
          api_reported_total: 10000,
          pages_fetched: 108,
          expected_pages: 108,
          page_size: 100,
          page_limit: 100,
          next_offset: 10800,
          new_unique_items: 100,
          unique_items: 10800,
          elapsed_seconds: 400,
          eta_seconds: 49,
          eta_deadline_at_ms: Date.now() + 49_000,
        },
      });
    }
    if (jobId === "sync_cancelled_terminal") {
      return ok({
        ok: true,
        job_id: "sync_cancelled_terminal",
        task_id: "sync_cancelled_terminal",
        status: "cancelled",
        status_kind: "interrupted",
        terminal: true,
        interrupted: true,
        recoverable: true,
        retryable: true,
        phase: "cancelled",
        status_message: "用户已停止本次官方上下文刷新，结果未确认完成；后台确认状态为已取消。",
        progress: {
          job_id: "sync_cancelled_terminal",
          task_id: "sync_cancelled_terminal",
          phase: "cancelled",
          status_code: "CANCELLED",
          status_kind: "interrupted",
          terminal: true,
          interrupted: true,
          phase_label: "已取消",
          status_message: "用户已停止本次官方上下文刷新，结果未确认完成；后台确认状态为已取消。",
          percent_complete: 100,
          scanned: 8900,
          total: 10000,
          api_reported_total: 10000,
          elapsed_seconds: 385,
          eta_seconds: 60,
          eta_deadline_at_ms: Date.now() + 60_000,
        },
      });
    }
    if (jobId === "sync_warning") {
      return ok({
        ok: true,
        job_id: "sync_warning",
        task_id: "sync_warning",
        status: "completed_with_warnings",
        status_kind: "warning",
        terminal: true,
        recoverable: true,
        retryable: true,
        phase: "COMPLETED_WITH_WARNINGS",
        status_message: "Official context refreshed.",
        count: 8,
        scanned: 8,
        api_reported_total: 12,
        progress: {
          job_id: "sync_warning",
          task_id: "sync_warning",
          phase: "COMPLETED_WITH_WARNINGS",
          status_code: "COMPLETED_WITH_WARNINGS",
          status_message: "Official context refreshed.",
          context_status: "failed",
          context_error: "fields failed",
          percent_complete: 100,
          scanned: 8,
          api_reported_total: 12,
          pagination_complete: true,
          stop_reason: "completed_with_warnings",
        },
        official_context_cache: {
          ok: true,
          fields_count: 8599,
          operators_count: 67,
          datasets_count: 20,
          manifest: {
            complete: true,
            is_stale: false,
            missing_files: [],
            stale_files: [],
            invalid_files: [],
            record_counts: {
              "official_fields.json": 8599,
              "official_operators.json": 67,
              "official_datasets.json": 20,
            },
          },
        },
        sync_history: [
          {
            job_id: "sync_warning",
            status: "completed_with_warnings",
            status_message: "Official context refreshed.",
            phase: "COMPLETED_WITH_WARNINGS",
            scanned: 8,
            api_reported_total: 12,
            added: 2,
            updated: 1,
            failed: 1,
            context_only: false,
            updated_at_ms: 1781200000000,
          },
        ],
        sync_history_error: "history access limited by local mock",
      });
    }
    return ok({
      ok: true,
      job_id: "",
      task_id: "",
      status: "idle",
      phase: "local_cache",
      progress: {
        phase: "local_cache",
        status_code: "LOCAL_CACHE",
        status_message: "本地官方上下文缓存已加载。",
      },
      official_context_cache: {
        ok: true,
        fields_count: 8599,
        operators_count: 67,
        datasets_count: 20,
        manifest: {
          complete: true,
          is_stale: false,
          missing_files: [],
          stale_files: [],
          invalid_files: [],
          record_counts: {
            "official_fields.json": 8599,
            "official_operators.json": 67,
            "official_datasets.json": 20,
          },
        },
      },
    });
  }
  if (method === "POST" && pathname === "/api/sync_cancel") {
    try {
      const body = JSON.parse(rawBody || "{}");
      if (body.job_id) currentSmokeState.stoppedSyncJobs.add(String(body.job_id));
    } catch {
      // Fall back to the active open-ended job below.
    }
    currentSmokeState.stoppedSyncJobs.add("sync_open_ended_scan");
    return ok({ ok: true, job_id: "sync_open_ended_scan", status: "stopping", stopping_since_ms: Date.now() });
  }
  if (method === "POST" && pathname === "/api/run") {
    return ok({ ok: true, job_id: "job_validation_interrupted", task_id: "job_validation_interrupted", auto_submit: false });
  }
  if (method === "POST" && pathname === "/api/generate_candidates") {
    return ok({ ok: true, job_id: "gen_smoke", task_id: "gen_smoke" });
  }
  if (method === "POST" && pathname === "/api/candidates/simulate") {
    currentSmokeState.candidateSimulationCount += 1;
    const jobId = currentSmokeState.candidateSimulationCount === 1 ? "simulate_queue_zero_smoke" : "simulate_queue_smoke";
    return ok({
      ok: true,
      job_id: jobId,
      task_id: jobId,
      sse_url: `/sse?job_id=${jobId}`,
      status_url: `/api/status?job_id=${jobId}`,
    });
  }
  if (method === "POST" && pathname === "/api/check_batch") {
    if (!currentSmokeState.candidateSimulationSucceeded) {
      currentSmokeState.checkBatchBeforeSimulationSuccessCount += 1;
    }
    return ok({
      ok: true,
      job_id: "check_queue_smoke",
      task_id: "check_queue_smoke",
      sse_url: "/sse?job_id=check_queue_smoke",
      status_url: "/api/status?job_id=check_queue_smoke",
    });
  }
  if (method === "POST" && pathname === "/api/scoring/evaluate") {
    currentSmokeState.scoringEvaluateCount += 1;
    if (currentSmokeState.scoringEvaluateCount === 2) {
      return ok({ ok: true, job_id: "score_failed_smoke", task_id: "score_failed_smoke" });
    }
    return ok({ ok: true, job_id: "score_smoke", task_id: "score_smoke" });
  }
  if (method === "POST" && pathname === "/api/scoring/attribution") {
    return ok({
      ok: true,
      attribution: { name: "total", score: 82, weight: 1, children: [{ name: "official_metrics", score: 50, weight: 0.6 }] },
      hard_gates: [{ gate_name: "official", passed: true, check_items: [{ name: "sharpe", passed: true, actual: 1.42, target: 1.25, direction: ">=" }] }],
      soft_gates: [],
      top_failures: [],
      improvement_hints: ["keep official metrics current"],
    });
  }
  if (method === "POST" && pathname === "/api/cancel") {
    return ok({ ok: true, status: "stopping" });
  }
  if (method === "POST" && (pathname === "/api/submit" || pathname === "/api/submit_batch")) {
    return { status: 410, json: { ok: false, error_code: "WEB_ONLY_SUBMIT_REQUIRED" } };
  }
  if (method === "GET" && pathname === "/api/checkpoint_status") {
    return ok({
      ok: true,
      schema_version: "checkpoint_status.v1",
      checkpoint_count: 1,
      history_count: 3,
      resume_available: false,
      storage_dir: "data",
      latest: {
        run_id: "run_raw_snapshot",
        phase_completed: "official_validation",
        saved_at: "2026-06-05T00:00:00Z",
        error: "raw backend-only checkpoint failure",
      },
      history: [
        {
          run_id: "run_resume",
          status: "completed",
          best_score: 88.5,
          completed_at: "2026-06-05T00:05:00Z",
        },
        {
          run_id: "run_history_raw",
          status: "RAW_BACKEND_CHECK_STATUS",
          best_score: "raw backend metric api_key=secret",
          error: "invalid local session",
          completed_at: "SESSION_INVALID",
        },
      ],
      checkpoints: [
        {
          checkpoint_id: "raw backend title password=secret",
          status: "recorded",
          step: "raw backend metric csrf_token=secret",
          summary: "checkpoint row",
          saved_at: "invalid local session",
        },
      ],
      latest_comparison: {
        deltas: { best_score: 4.5, submission_ready: 1, "raw backend delta password=secret": 2 },
      },
      history_analytics: {
        schema_version: "run_history_analytics.v1",
        trend_status: "RAW_BACKEND_RISK password=secret",
        latest_run_id: "run_resume",
      },
    });
  }
  if (method === "GET" && pathname === "/api/latest_result") {
    return ok({
      ok: true,
      result: {
        replay_audit: {
          schema_version: "run-history-replay-audit-v1",
          source: "run_history",
          path: "/Volumes/Extra/raw backend path password=secret/run_history.json",
          local_only: true,
          official_api_called: false,
          submit_allowed: false,
          real_submit_performed: false,
          recovered_candidate_count: 3,
          total_candidate_count: 5,
          lifecycle_row_count: 4,
          lifecycle_rows_used_count: 2,
          candidates_with_production_decision: 3,
          production_decision_counts: {
            optimize: 2,
            needs_human_confirmation: 1,
            "raw backend action password=secret": 7,
          },
          candidates_with_scientific_audit: 2,
          candidates_missing_scientific_audit: 1,
          scientific_submit_boundary_intact: true,
          scientific_audit_summary_available: true,
          workflow_plan_available: true,
          workflow_queue_counts: { rework: 1, review: 2 },
          readiness_blocker_counts: { missing_official_metric_fields: 1 },
          execution_gap_counts: { official_validation_queue: 1 },
          stop_rule: "scripts/check_live_submit_readiness.py",
          submit_boundary_intact: true,
        },
        summary: {
          candidates: [
            {
              alpha_id: "ALPHA_REPLAY_SAFE",
              submission: {
                anti_overfit_report: { passed: true, score: 0.91, generated_at: "2026-06-12T01:10:00Z" },
                rolling_validation_report: { status: "passed", score: 0.88, sample_size: 30 },
              },
            },
          ],
        },
      },
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
          instrumentType: ["EQUITY"],
          region: ["USA", "CHN", "EUR", "GLB"],
          universe: ["TOP3000", "TOP1000", "TOP500"],
          delay: [0, 1],
          neutralization: ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"],
          dataset: ["pv1", "fundamental6", "analyst4"],
          pasteurization: ["ON", "OFF"],
          unitHandling: ["VERIFY", "RAW", "NONE"],
          nanHandling: ["ON", "OFF"],
          language: ["FASTEXPR"],
          type: ["REGULAR", "POWER_POOL", "ATOM", "PYRAMID"],
        },
        dataset_options: [
          { id: "pv1", name: "Price Volume Data for Equity", field_count: 24 },
          { id: "fundamental6", name: "Company Fundamental Data for Equity", field_count: 886 },
          { id: "analyst4", name: "Analyst Estimate Data for Equity", field_count: 1324 },
        ],
      },
    });
  }
  if (method === "POST" && pathname === "/api/config") {
    return ok({ ok: true, config: configFixture() });
  }
  if (method === "POST" && pathname === "/api/test_connection") {
    return ok({ ok: true, environment: "production", auth: "token" });
  }
  if (method === "GET" && pathname === "/api/snapshot/cloud") {
    return ok({
      ok: true,
      count: 2,
      total: 2,
      submitted_count: 1,
      passed_unsubmitted_count: 1,
      is_stale: false,
      summary: {
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
          expression: "decay_linear(volume, 5)",
          updated_at: "2026-05-30T00:10:00Z",
        },
      ],
    });
  }
  if (method === "GET" && pathname === "/api/snapshot/memory") {
    return ok({
      ok: true,
      total_candidates: 3,
      families: [
        { name: "momentum", count: 2, success_rate: 0.5 },
        { name: "quality", count: 1, success_rate: 0.33 },
      ],
      fields: [
        { name: "close", count: 3, success_rate: 0.5 },
        { name: "volume", count: 2, success_rate: 0.4 },
      ],
      failure_patterns: [
        { reason: "missing_official_metrics", count: 2 },
      ],
    });
  }
  if (method === "GET" && pathname === "/sse") {
    const jobId = url.searchParams.get("job_id") || "";
    if (jobId === "job_validation_interrupted") {
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: [
          "event: progress",
          "data: {\"type\":\"progress\",\"job_id\":\"job_validation_interrupted\",\"status\":\"running\",\"error\":\"raw backend cancellation\",\"user_error\":{\"kind\":\"task_cancelled\",\"message\":\"验证流程已停止，结果未确认完成。\"},\"progress\":{\"phase\":\"session_invalid\",\"status_kind\":\"interrupted\",\"terminal\":true,\"interrupted\":true,\"percent_complete\":100}}",
          "",
          "",
        ].join("\n"),
      };
    }
    if (jobId === "gen_smoke") {
      const event = {
        type: "complete",
        ok: true,
        result: {
          count: 3,
          candidates: [
            candidateFixture("ALPHA_RT_001", "submission_ready", 82),
            candidateFixture("ALPHA_RT_002", "running_backtest", 67),
            candidateFixture("ALPHA_RT_003", "pending_backtest", 48),
          ],
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: `event: complete\ndata: ${JSON.stringify(event)}\n\n`,
      };
    }
    if (jobId === "simulate_queue_zero_smoke") {
      const completeEvent = {
        ok: true,
        type: "complete",
        job_id: "simulate_queue_zero_smoke",
        task_id: "simulate_queue_zero_smoke",
        status: "completed",
        progress: {
          phase: "completed",
          status_message: "BRAIN模拟完成: 0 成功, 0 失败，共 1 个",
          percent_complete: 100,
        },
        result: {
          total: 1,
          completed: 0,
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: `event: complete\ndata: ${JSON.stringify(completeEvent)}\n\n`,
      };
    }
    if (jobId === "simulate_queue_smoke") {
      currentSmokeState.candidateSimulationSucceeded = true;
      const progressEvent = {
        ok: true,
        type: "progress",
        job_id: "simulate_queue_smoke",
        task_id: "simulate_queue_smoke",
        status: "running",
        progress: {
          phase: "simulation_polling",
          status_message: "本地浏览器模拟：官方验证队列运行中，未调用真实 BRAIN API。",
          percent_complete: 50,
          data: {
            total: 1,
            completed: 0,
            failed: 0,
            current_alpha_id: "ALPHA_RT_001",
            simulation_id_present: true,
          },
        },
      };
      const completeEvent = {
        ok: true,
        type: "complete",
        job_id: "simulate_queue_smoke",
        task_id: "simulate_queue_smoke",
        status: "completed",
        progress: {
          phase: "completed",
          status_message: "BRAIN模拟完成: 1 成功, 0 失败，共 1 个",
          percent_complete: 100,
        },
        result: {
          total: 1,
          completed: 1,
          failed: 0,
          results: [
            {
              alpha_id: "ALPHA_RT_001",
              official_alpha_id: "OFFICIAL_RT_001",
              simulation_id: "SIM_ALPHA_RT_001",
              status: "completed",
              official_metrics: {
                pass_fail: "PASS",
                sharpe: 1.6,
                fitness: 1.1,
                turnover: 0.25,
              },
            },
          ],
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: [
          `event: progress\ndata: ${JSON.stringify(progressEvent)}`,
          "",
          `event: complete\ndata: ${JSON.stringify(completeEvent)}`,
          "",
          "",
        ].join("\n"),
      };
    }
    if (jobId === "check_queue_smoke") {
      const progressEvent = {
        ok: true,
        type: "progress",
        job_id: "check_queue_smoke",
        task_id: "check_queue_smoke",
        status: "running",
        progress: {
          operation: "check_batch",
          phase: "checking",
          status_code: "CHECK_RUNNING",
          status_message: "本地浏览器模拟：质量门槛检查运行中，未调用真实 BRAIN API。",
          mode: "quick",
          range: "all",
          total: 1,
          checked: 0,
          submittable: 0,
          blocked: 0,
          failed: 0,
          percent_complete: 0,
          items: [],
        },
      };
      const completeEvent = {
        ok: true,
        type: "complete",
        job_id: "check_queue_smoke",
        task_id: "check_queue_smoke",
        status: "completed",
        progress: {
          operation: "check_batch",
          phase: "completed",
          status_code: "CHECK_COMPLETED",
          status_message: "质量门槛检查完成。",
          percent_complete: 100,
          total: 1,
          checked: 1,
          submittable: 0,
          blocked: 1,
          failed: 0,
          items: [
            {
              ok: true,
              alpha_id: "ALPHA_RT_001",
              official_alpha_id: "OFFICIAL_RT_001",
              mode: "quick",
              passed: false,
              submittable: false,
              status: "BLOCKED",
              is_stale: false,
              failed_reasons: ["mock non-submit browser smoke blocker"],
            },
          ],
        },
        result: {
          ok: true,
          summary: {
            mode: "quick",
            range: "all",
            total: 1,
            checked: 1,
            submittable: 0,
            blocked: 1,
            failed: 0,
            cloud_count: 0,
            cloud_error: "",
            blockers: { mock_non_submit: 1 },
          },
          items: [],
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: [
          `event: progress\ndata: ${JSON.stringify(progressEvent)}`,
          "",
          `event: complete\ndata: ${JSON.stringify(completeEvent)}`,
          "",
          "",
        ].join("\n"),
      };
    }
    if (jobId === "score_smoke") {
      const event = {
        type: "complete",
        ok: true,
        result: {
          total_score: 84.2,
          scoring_schema: "local_browser_smoke",
          decision_band: "official_validation_queue",
          passed_gate: true,
          prior: { score: 30 },
          empirical: { score: 35 },
          checklist: { score: 19.2 },
          attribution_tree: {
            name: "total",
            score: 84.2,
            weight: 1,
            children: [
              { name: "official_metrics", score: 50, weight: 0.6 },
              { name: "local_quality", score: 34.2, weight: 0.4 },
            ],
          },
          hard_gates: [
            { gate_name: "official", passed: true, check_items: [{ name: "sharpe", passed: true, actual: 1.42, target: 1.25, direction: ">=" }] },
          ],
          soft_gates: [],
          top_failures: [],
          improvement_hints: ["keep official metrics current"],
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: `event: complete\ndata: ${JSON.stringify(event)}\n\n`,
      };
    }
    if (jobId === "score_failed_smoke") {
      const event = {
        type: "error",
        ok: false,
        status: "failed",
        status_kind: "failed",
        terminal: true,
        retryable: true,
        error: "raw backend scoring failure password=secret",
        error_code: "RAW_BACKEND_SCORE_STATUS",
        user_error: {
          kind: "score_failed",
          message: "评分失败，请重新评估候选后再继续。",
          retryable: true,
        },
        progress: {
          phase: "scoring",
          status: "failed",
          status_kind: "failed",
          terminal: true,
          percent_complete: 100,
          error: "SESSION_INVALID",
          user_error: {
            kind: "score_failed",
            message: "评分失败，请重新评估候选后再继续。",
            retryable: true,
          },
        },
      };
      return {
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: `event: error\ndata: ${JSON.stringify(event)}\n\n`,
      };
    }
    return {
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      body: "event: complete\ndata: {\"type\":\"complete\",\"ok\":true}\n\n",
    };
  }
  return null;
}

function candidateFixture(alphaId, lifecycleStatus, score) {
  return {
    alpha_id: alphaId,
    official_alpha_id: alphaId === "ALPHA_RT_001" ? "OFFICIAL_RT_001" : "",
    simulation_id: `SIM_${alphaId}`,
    expression: "rank(ts_mean(close, 10)) - group_neutralize(volume, industry)",
    family: alphaId === "ALPHA_RT_002" ? "raw backend family password=secret" : "momentum",
    lifecycle_status: lifecycleStatus,
    scorecard: { total_score: score },
    official_metrics: {
      sharpe: alphaId === "ALPHA_RT_001" ? 1.42 : 0.86,
      fitness: alphaId === "ALPHA_RT_001" ? 1.16 : 0.74,
      turnover: 0.08,
    },
    gate: { passed: alphaId === "ALPHA_RT_001", submission_ready: alphaId === "ALPHA_RT_001" },
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
        dataset: "pv1",
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
    const visibleLabels = ["Alpha Ops", "运行总览", "非提交生产验证", "本轮真实提交（应为 0）", "自动提交", "本地非提交"];
    return {
      title: document.title,
      readyState: document.readyState,
      url: location.href,
      rootExists: Boolean(root),
      rootChildCount: root ? root.childElementCount : 0,
      rootTextLength: root ? root.innerText.length : 0,
      hasHeading: document.title === "BRAIN Alpha Ops" || /BRAIN Alpha Ops|Alpha Ops/.test(text),
      hasLocalSession: /本地非提交页面|本地研究页面/.test(text),
      hasSettingsShortcut: Boolean(document.querySelector('button[aria-label="打开系统配置"]')),
      visibleCardTitles: visibleLabels.filter((title) => text.includes(title)),
      misleadingOnlineLabel: /在线/.test(text),
      roles: {
        alerts: document.querySelectorAll('[role="alert"]').length,
        liveRegions: document.querySelectorAll('[aria-live]').length,
      },
      meta: {
        csrfPresent: Boolean(document.querySelector('meta[name="brain-alpha-csrf"]')?.content),
        streamPresent: Boolean(document.querySelector('meta[name="brain-alpha-stream"]')?.content),
      },
      resources,
      bodyWidth: document.body ? document.body.scrollWidth : 0,
      viewportWidth: window.innerWidth,
      pageOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      forbiddenLifecycleSecretsVisible: ${SECRET_TEXT_PATTERN}.test(text),
      textSample: "<omitted>",
    };
  })()`;
}

function replayAuditInteractionExpression() {
  return `(async () => {
    const waitFrames = async (count = 2) => {
      for (let index = 0; index < count; index += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
    };
    const waitUntil = async (predicate, attempts = 120) => {
      for (let index = 0; index < attempts; index += 1) {
        if (predicate()) return true;
        await waitFrames(1);
      }
      return false;
    };
    const text = () => document.body?.innerText || "";
    const isVisible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
    const enabledButtonsByText = (needle) => Array.from(document.querySelectorAll("button"))
      .filter((button) => isVisible(button) && !button.disabled && (button.textContent || "").includes(needle));
    const openRobustness = async () => {
      if (/稳健性/.test(text()) && /防过拟合与滚动验证/.test(text())) return true;
      const direct = enabledButtonsByText("稳健性证据")[0] || enabledButtonsByText("稳健性")[0];
      if (direct) {
        direct.click();
        await waitFrames(6);
      }
      if (/稳健性/.test(text()) && /防过拟合与滚动验证/.test(text())) return true;
      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(4);
      }
      const menuItem = enabledButtonsByText("稳健性证据")[0] || enabledButtonsByText("稳健性")[0];
      if (menuItem) {
        menuItem.click();
        await waitFrames(6);
      }
      if (/稳健性/.test(text()) && /防过拟合与滚动验证/.test(text())) return true;
      const tools = enabledButtonsByText("工具")[0];
      if (tools) {
        tools.click();
        await waitFrames(6);
      }
      const afterTools = enabledButtonsByText("稳健性证据")[0] || enabledButtonsByText("稳健性")[0];
      if (afterTools) {
        afterTools.click();
        await waitFrames(6);
      }
      return /稳健性/.test(text()) && /防过拟合与滚动验证/.test(text());
    };

    await waitUntil(() => /Alpha Ops/.test(text()) && /非提交生产验证/.test(text()), 120);
    const navigated = await openRobustness();
    await waitUntil(() => /稳健性/.test(text()) && /本地回放审计/.test(text()), 180);
    const robustnessHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /稳健性/.test(heading.textContent || ""));
    const robustnessPanel = robustnessHeading?.closest(".animate-fade-in");
    const robustnessText = robustnessPanel?.innerText || "";
    return {
      robustnessReplay: {
        navigated,
        reached: /稳健性/.test(robustnessText) && /本地回放审计/.test(robustnessText),
        hasReplayMetrics: /回放候选/.test(robustnessText) &&
          /3\\/5/.test(robustnessText) &&
          /生命周期命中/.test(robustnessText) &&
          /2\\/4/.test(robustnessText),
        hasStopRule: /停机规则:check_live_submit_readiness\\.py/.test(robustnessText),
        hasNonSubmitBoundary: /非提交边界/.test(robustnessText) &&
          /已锁定/.test(robustnessText) &&
          /未调用官方接口/.test(robustnessText) &&
          /不允许提交/.test(robustnessText),
        hasScientificAudit: /科学审计/.test(robustnessText) &&
          /2\\/3/.test(robustnessText) &&
          /缺口:1/.test(robustnessText),
        rawBackendHidden: !/\\/Volumes\\/|\\/Users\\/|\\/tmp\\/|raw backend|password=secret|api_key=secret|csrf_token=secret|run_history\\.json/i.test(robustnessText),
        finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
        sample: "<omitted>",
      },
    };
  })()`;
}

function scoringFailureRetryInteractionExpression() {
  return `(async () => {
    const waitFrames = async (count = 2) => {
      for (let index = 0; index < count; index += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
    };
    const waitUntil = async (step, predicate, attempts = 120) => {
      for (let index = 0; index < attempts; index += 1) {
        if (predicate()) return true;
        await waitFrames(1);
      }
      throw new Error(\`step failed: \${step}\`);
    };
    const text = () => document.body?.innerText || "";
    const isVisible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
    const buttonsByText = (needle, { enabledOnly = false } = {}) => Array.from(document.querySelectorAll("button"))
      .filter((button) => isVisible(button) && (!enabledOnly || !button.disabled) && (button.textContent || "").includes(needle));
    const enabledButtonByText = (needle) => buttonsByText(needle, { enabledOnly: true })[0];
    const visibleButtonIn = (selector, needle) => Array.from(document.querySelectorAll(selector))
      .find((button) => isVisible(button) && !button.disabled && (button.textContent || "").includes(needle));
    const clickCandidateNavigation = async () => {
      const onCandidatePage = () => /候选管理/.test(text()) && /目标池容量/.test(text()) && /ALPHA_RT_001/.test(text());
      if (onCandidatePage()) return true;

      const discoverGroup = document.querySelector('button[aria-controls="phase-discover-items"]');
      if (discoverGroup && isVisible(discoverGroup) && discoverGroup.getAttribute("aria-expanded") === "false") {
        discoverGroup.click();
        await waitFrames(4);
      }
      const sidebarCandidate = visibleButtonIn("#phase-discover-items button", "候选管理");
      if (sidebarCandidate) {
        sidebarCandidate.click();
        await waitFrames(6);
      }
      if (onCandidatePage()) return true;

      const discover = enabledButtonByText("候选发现");
      if (discover) {
        discover.click();
        await waitFrames(4);
      }
      const candidateItem = visibleButtonIn("#phase-discover-items button", "候选管理") || enabledButtonByText("候选管理");
      if (candidateItem) {
        candidateItem.click();
        await waitFrames(6);
      }
      if (onCandidatePage()) return true;

      const mobileCandidateTab = buttonsByText("候选")
        .find((button) => (button.textContent || "").trim() === "候选") || enabledButtonByText("候选");
      if (mobileCandidateTab) {
        mobileCandidateTab.click();
        await waitFrames(6);
      }
      return onCandidatePage();
    };
    const scoringPanelText = () => {
      const heading = Array.from(document.querySelectorAll("h1,h2"))
        .find((node) => /^科学评分$/.test((node.textContent || "").trim()));
      return heading?.closest(".animate-fade-in")?.innerText || "";
    };

    await waitUntil("home shell", () => /Alpha Ops/.test(text()) && /非提交生产验证/.test(text()), 160);
    const candidateNavigated = await clickCandidateNavigation();
    await waitUntil("candidate row visible", () => /候选管理/.test(text()) && /ALPHA_RT_001/.test(text()), 180);
    const scoreCandidateButton = Array.from(document.querySelectorAll('button[aria-label^="评分 "]'))
      .find((button) => isVisible(button) && !button.disabled);
    const scoreCandidateClicked = Boolean(scoreCandidateButton);
    const clickedScoreAlphaId = (scoreCandidateButton?.getAttribute("aria-label") || "").match(/ALPHA_[A-Z0-9_]+/)?.[0] || "";
    if (scoreCandidateButton) {
      scoreCandidateButton.click();
      await waitFrames(4);
    }

    await waitUntil("scoring panel selected candidate", () => /科学评分/.test(scoringPanelText()) && /ALPHA_RT_/.test(scoringPanelText()), 180);
    await waitUntil("initial scoring success", () => /归因分析/.test(scoringPanelText()) && /评分卡/.test(scoringPanelText()), 180);
    const scoringText = scoringPanelText();
    const refreshScoreButton = enabledButtonByText("刷新评分");
    const failureRefreshClicked = Boolean(refreshScoreButton && !refreshScoreButton.disabled);
    if (failureRefreshClicked) {
      refreshScoreButton.click();
      await waitUntil("scoring refresh failure", () => /评分失败，请重新评估候选后再继续。/.test(scoringPanelText()), 180);
    }
    const scoringFailureText = scoringPanelText();
    const scoringRetryButton = enabledButtonByText("重试");
    const scoringRetryClicked = Boolean(scoringRetryButton && !scoringRetryButton.disabled);
    if (scoringRetryClicked) {
      scoringRetryButton.click();
      await waitUntil("scoring retry success", () => /归因分析/.test(scoringPanelText()) && /评分卡/.test(scoringPanelText()) && !/评分失败，请重新评估候选后再继续。/.test(scoringPanelText()), 180);
    }
    const scoringRetryText = scoringPanelText();
    return {
      scoringPanel: {
        candidateNavigated,
        clickedAlphaId: clickedScoreAlphaId,
        scoreCandidateClicked,
        reached: /科学评分/.test(scoringText) && Boolean(clickedScoreAlphaId) && scoringText.includes(clickedScoreAlphaId),
        initialSuccess: /归因分析/.test(scoringText) && /评分卡/.test(scoringText),
        attributionVisible: /归因分析/.test(scoringText) && /official_metrics|local_quality|total/.test(scoringText),
        hardGateVisible: /官方门禁检查|门禁/.test(scoringText),
        failureRefreshClicked,
        failureUserCopy: /评分失败，请重新评估候选后再继续。/.test(scoringFailureText),
        failureRetryVisible: /重试/.test(scoringFailureText),
        failureNotComplete: !/(^|\\D)100%/.test(scoringFailureText) && !/评分已刷新/.test(scoringFailureText),
        failureRawBackendHidden: !/raw backend|RAW_BACKEND_SCORE_STATUS|SESSION_INVALID|invalid local session|password=secret/i.test(scoringFailureText),
        retryClicked: scoringRetryClicked,
        recoveredAfterRetry: /归因分析/.test(scoringRetryText) && /评分卡/.test(scoringRetryText) && !/评分失败，请重新评估候选后再继续。/.test(scoringRetryText),
        rawBackendHidden: !/raw backend|RAW_BACKEND_SCORE_STATUS|SESSION_INVALID|invalid local session|password=secret/i.test(scoringText + scoringFailureText + scoringRetryText),
        finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
        sample: "<omitted>",
      },
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
    const waitUntil = async (predicate, attempts = 100) => {
      for (let index = 0; index < attempts; index += 1) {
        if (predicate()) return true;
        await waitFrames(1);
      }
      return false;
    };
    const text = () => document.body?.innerText || "";
    const isVisible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
    const buttonsByText = (needle, { enabledOnly = false } = {}) => Array.from(document.querySelectorAll("button"))
      .filter((button) => isVisible(button) && (!enabledOnly || !button.disabled) && (button.textContent || "").includes(needle));
    const buttonByText = (needle) => buttonsByText(needle)[0];
    const enabledButtonByText = (needle) => buttonsByText(needle, { enabledOnly: true })[0];
    const visibleButtonIn = (selector, needle) => Array.from(document.querySelectorAll(selector))
      .find((button) => isVisible(button) && !button.disabled && (button.textContent || "").includes(needle));
    const clickOfficialOperations = async () => {
      if (/官方同步与阻断复核/.test(text())) return true;
      const manualSync = enabledButtonByText("手动同步");
      if (manualSync) {
        manualSync.click();
        await waitFrames(4);
      }
      if (/官方同步与阻断复核/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const connectGroup = enabledButtonByText("准备与就绪");
      if (connectGroup && connectGroup.getAttribute("aria-expanded") === "false") {
        connectGroup.click();
        await waitFrames(3);
      }
      const syncItem = enabledButtonByText("云端同步") || enabledButtonByText("官方操作");
      if (syncItem) {
        syncItem.click();
        await waitFrames(4);
      }
      return /官方同步与阻断复核/.test(text());
    };
    const clickCandidateNavigation = async () => {
      const onCandidatePage = () => /候选管理/.test(text()) && /目标池容量/.test(text()) && /ALPHA_RT_001/.test(text());
      if (onCandidatePage()) return true;

      const discoverGroup = document.querySelector('button[aria-controls="phase-discover-items"]');
      if (discoverGroup && isVisible(discoverGroup) && discoverGroup.getAttribute("aria-expanded") === "false") {
        discoverGroup.click();
        await waitFrames(4);
      }
      const sidebarCandidate = visibleButtonIn("#phase-discover-items button", "候选管理");
      if (sidebarCandidate) {
        sidebarCandidate.click();
        await waitFrames(6);
      }
      if (onCandidatePage()) return true;

      const discover = enabledButtonByText("候选发现");
      if (discover) {
        discover.click();
        await waitFrames(4);
      }
      const candidateItem = visibleButtonIn("#phase-discover-items button", "候选管理") || enabledButtonByText("候选管理");
      if (candidateItem) {
        candidateItem.click();
        await waitFrames(6);
      }
      if (onCandidatePage()) return true;

      const mobileCandidateTab = buttonsByText("候选")
        .find((button) => (button.textContent || "").trim() === "候选") || buttonByText("候选");
      if (mobileCandidateTab) {
        mobileCandidateTab.click();
        await waitFrames(6);
      }
      return onCandidatePage();
    };
    const clickSubmissionConfirmNavigation = async () => {
      if (/提交前阻断复核/.test(text())) return true;
      const direct = enabledButtonByText("阻断复核") || enabledButtonByText("查看阻断");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/提交前阻断复核/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const readyGroup = enabledButtonByText("提交就绪");
      if (readyGroup && readyGroup.getAttribute("aria-expanded") === "false") {
        readyGroup.click();
        await waitFrames(3);
      }
      const reviewItem = enabledButtonByText("阻断复核") || enabledButtonByText("查看阻断");
      if (reviewItem) {
        reviewItem.click();
        await waitFrames(4);
      }
      return /提交前阻断复核/.test(text());
    };
    const clickBacktestNavigation = async () => {
      if (/官方回测槽位/.test(text())) return true;
      const direct = enabledButtonByText("回测监控") || enabledButtonByText("官方回测");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/官方回测槽位/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const evaluateGroup = enabledButtonByText("评估与验证");
      if (evaluateGroup && evaluateGroup.getAttribute("aria-expanded") === "false") {
        evaluateGroup.click();
        await waitFrames(3);
      }
      const backtestItem = enabledButtonByText("回测监控") || enabledButtonByText("官方回测");
      if (backtestItem) {
        backtestItem.click();
        await waitFrames(4);
      }
      return /官方回测槽位/.test(text());
    };
    const clickQualityNavigation = async () => {
      if (/达标检查/.test(text()) && /提交证据缺口/.test(text())) return true;
      const direct = enabledButtonByText("质量门禁") || enabledButtonByText("检查质量");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/达标检查/.test(text()) && /提交证据缺口/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const evaluateGroup = enabledButtonByText("评估与验证");
      if (evaluateGroup && evaluateGroup.getAttribute("aria-expanded") === "false") {
        evaluateGroup.click();
        await waitFrames(3);
      }
      const qualityItem = enabledButtonByText("质量门禁") || enabledButtonByText("检查质量");
      if (qualityItem) {
        qualityItem.click();
        await waitFrames(4);
      }
      return /达标检查/.test(text()) && /提交证据缺口/.test(text());
    };
    const clickConfigNavigation = async () => {
      if (/连接与生产参数/.test(text())) return true;
      const direct = enabledButtonByText("系统配置");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/连接与生产参数/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const connectGroup = enabledButtonByText("准备与就绪");
      if (connectGroup && connectGroup.getAttribute("aria-expanded") === "false") {
        connectGroup.click();
        await waitFrames(3);
      }
      const configItem = enabledButtonByText("系统配置");
      if (configItem) {
        configItem.click();
        await waitFrames(4);
      }
      return /连接与生产参数/.test(text());
    };
    const clickCheckpointNavigation = async () => {
      if (/续跑记录/.test(text()) && /上次进度、运行历史/.test(text())) return true;
      const direct = enabledButtonByText("续跑记录") || enabledButtonByText("查看历史");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/续跑记录/.test(text()) && /上次进度、运行历史/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const checkpointItem = enabledButtonByText("续跑记录") || enabledButtonByText("查看历史");
      if (checkpointItem) {
        checkpointItem.click();
        await waitFrames(4);
      }
      return /续跑记录/.test(text()) && /上次进度、运行历史/.test(text());
    };
    const clickRobustnessNavigation = async () => {
      if (/稳健性/.test(text()) && /防过拟合与滚动验证/.test(text())) return true;
      const direct = enabledButtonByText("稳健性证据") || enabledButtonByText("稳健性");
      if (direct) {
        direct.click();
        await waitFrames(4);
      }
      if (/稳健性/.test(text()) && /防过拟合与滚动验证/.test(text())) return true;

      const menuButton = document.querySelector('button[aria-label="切换导航菜单"]');
      if (menuButton && isVisible(menuButton)) {
        menuButton.click();
        await waitFrames(3);
      }
      const robustnessItem = enabledButtonByText("稳健性证据") || enabledButtonByText("稳健性");
      if (robustnessItem) {
        robustnessItem.click();
        await waitFrames(4);
      }
      return /稳健性/.test(text()) && /防过拟合与滚动验证/.test(text());
    };
    await waitUntil(() => /Alpha Ops/.test(text()) && /非提交生产验证/.test(text()), 160);
    const visibleLabels = ["Alpha Ops", "运行总览", "非提交生产验证", "本轮真实提交（应为 0）", "自动提交", "本地非提交"];
    const report = {
      home: {
        hasLocalSession: /本地非提交页面|本地研究页面/.test(text()),
        hasTopSettings: Boolean(document.querySelector('button[aria-label="打开系统配置"]')),
        cardTitlesVisible: visibleLabels.filter((title) => text().includes(title)),
        hasProductionValidation: /非提交生产验证/.test(text()),
        hasNoManualSubmitCard: !/手动提交/.test(text()),
        hasProofMetrics: /本轮真实提交（应为 0）/.test(text()) && /自动提交/.test(text()),
        noMisleadingOnline: !/在线/.test(text()),
        sample: "<omitted>",
      },
    };

    const runButton = enabledButtonByText("运行非提交验证");
    const stopButtonBefore = buttonByText("停止");
    const runEnabledBefore = Boolean(runButton && !runButton.disabled);
    if (runEnabledBefore) runButton.click();
    await waitUntil(() => /验证流程已停止，结果未确认完成。/.test(text()), 180);
    const runButtonAfter = buttonByText("运行非提交验证");
    const stopButtonAfter = buttonByText("停止");
    report.productionValidation = {
      reached: /非提交生产验证/.test(text()),
      hasNonSubmitBadge: /非提交/.test(text()),
      hasProofMetrics: /本轮真实提交（应为 0）/.test(text()) && /自动提交/.test(text()),
      runClicked: runEnabledBefore,
      stopAvailableWhileRunning: Boolean(stopButtonBefore),
      interruptedCopy: /验证流程已停止，结果未确认完成。/.test(text()),
      rawBackendHidden: !/raw backend cancellation|SESSION_INVALID|session_invalid|invalid local session/i.test(text()),
      runEnabledAfter: Boolean(runButtonAfter && !runButtonAfter.disabled),
      stopDisabledAfter: Boolean(stopButtonAfter && stopButtonAfter.disabled),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
    };

    await clickOfficialOperations();
    await waitUntil(() => /官方同步与阻断复核/.test(text()), 180);
    await waitUntil(() => /本地会话需要重新连接|监控受阻/.test(text()), 180);
    const sessionInvalidText = text();
    const sessionInvalidOverflowX = document.body ? document.body.scrollWidth > window.innerWidth + 1 : false;
    const reconnectButton = enabledButtonByText("前往运行总览重新连接");
    const reconnectClicked = Boolean(reconnectButton && !reconnectButton.disabled);
    if (reconnectClicked) reconnectButton.click();
    await waitUntil(() => /运行总览/.test(text()) && /非提交生产验证/.test(text()), 180);
    const reconnectNavigated = /运行总览/.test(text()) && /非提交生产验证/.test(text());
    await clickOfficialOperations();
    await waitUntil(() => /官方同步与阻断复核/.test(text()), 180);
    const officialOverviewBefore = document.querySelector('section[aria-label="官方同步数据总览"]');
    const startRefreshButton = enabledButtonByText("开始刷新") || enabledButtonByText("重新刷新");
    const startRefreshEnabled = Boolean(startRefreshButton && !startRefreshButton.disabled);
    if (startRefreshEnabled) startRefreshButton.click();
    await waitUntil(() => /接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界/.test(text()), 240);
    const scanProgressbar = document.querySelector('[role="progressbar"][aria-label*="扫描云端"]');
    const scanProgressPanel = scanProgressbar?.closest(".panel") || scanProgressbar?.parentElement;
    const scanProgressFillStyle = scanProgressPanel?.querySelector(".progress-bar-fill")?.getAttribute("style") || "";
    const openEndedText = text();
    const openEndedOverflowX = document.body ? document.body.scrollWidth > window.innerWidth + 1 : false;
    const stopSyncButton = enabledButtonByText("停止");
    const stopSyncClicked = Boolean(stopSyncButton && !stopSyncButton.disabled);
    if (stopSyncClicked) stopSyncButton.click();
    await waitUntil(() => /官方上下文刷新已停止，结果未确认完成。/.test(text()) && /重新刷新/.test(text()), 300);
    const stoppedText = text();
    const stoppedOverflowX = document.body ? document.body.scrollWidth > window.innerWidth + 1 : false;
    const restartAfterStopped = enabledButtonByText("重新刷新");
    const restartAfterStoppedClicked = Boolean(restartAfterStopped && !restartAfterStopped.disabled);
    if (restartAfterStoppedClicked) restartAfterStopped.click();
    await waitUntil(() => /官方上下文刷新已停止，结果未确认完成。/.test(text()) && /已拉取 8,900/.test(text()) && /重新刷新/.test(text()), 300);
    const cancelledText = text();
    const cancelledOverflowX = document.body ? document.body.scrollWidth > window.innerWidth + 1 : false;
    const restartAfterCancel = enabledButtonByText("重新刷新");
    const restartAfterCancelClicked = Boolean(restartAfterCancel && !restartAfterCancel.disabled);
    if (restartAfterCancelClicked) restartAfterCancel.click();
    await waitUntil(() => /带警告|带警告完成/.test(text()) && /仅重试上下文/.test(text()), 240);
    const readinessButton = enabledButtonByText("读取复核");
    const readinessClicked = Boolean(readinessButton && !readinessButton.disabled);
    if (readinessClicked) readinessButton.click();
    await waitUntil(() => /仍阻断/.test(text()) && /复核通过\\s*否/.test(text()), 180);
    const checksButton = enabledButtonByText("查看结果");
    const checksClicked = Boolean(checksButton && !checksButton.disabled);
    if (checksClicked) checksButton.click();
    await waitUntil(() => /2 条记录|已加载 2 条检查结果|质量检查结果已加载/.test(text()), 180);
    const officialHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /官方同步与阻断复核/.test(heading.textContent || ""));
    const officialPanel = officialHeading?.closest(".animate-fade-in");
    const officialText = officialPanel?.innerText || "";
    const officialOverview = officialPanel?.querySelector('section[aria-label="官方同步数据总览"]');
    const officialTimeline = officialPanel?.querySelector('[aria-label="官方操作时间线"]');
    const officialHistory = officialPanel?.querySelector('section[aria-label="最近官方同步"]');
    report.officialOperations = {
      reached: /官方同步与阻断复核/.test(officialText),
      hasEntryBadges: /官方操作入口/.test(officialText) && /按钮驱动/.test(officialText) && /非提交/.test(officialText),
      hasOverview: Boolean(officialOverview || officialOverviewBefore) && /同步状态/.test(officialOverview?.innerText || "") && /更新时间/.test(officialOverview?.innerText || "") && /分页拉取/.test(officialOverview?.innerText || ""),
      startClicked: startRefreshEnabled,
      sessionInvalidRecovery: reconnectClicked && reconnectNavigated && /本地会话需要重新连接/.test(sessionInvalidText) && /监控受阻/.test(sessionInvalidText) && /重新连接/.test(sessionInvalidText),
      sessionInvalidRawHidden: !/SESSION_INVALID|session_invalid|invalid local session/i.test(sessionInvalidText),
      openEndedScan: Boolean(scanProgressbar) &&
        scanProgressbar.classList.contains("indeterminate") &&
        !scanProgressbar.hasAttribute("aria-valuenow") &&
        !/width:\s*100%/i.test(scanProgressFillStyle) &&
        /接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界/.test(openEndedText) &&
        /已拉取 10,800/.test(openEndedText) &&
        !/(^|\D)(?:99|100)%/.test(openEndedText) &&
        !/预计剩余|实际完成/.test(openEndedText),
      stoppedScan: stopSyncClicked &&
        /已停止|官方上下文刷新已停止/.test(stoppedText) &&
        /官方上下文刷新已停止，结果未确认完成。/.test(stoppedText) &&
        /重新刷新|重试/.test(stoppedText) &&
        !/后台确认状态|用户已停止本次官方上下文刷新/.test(stoppedText) &&
        !/实际完成|预计剩余|接口分页参考数 10,000/.test(stoppedText) &&
        !stoppedText.includes("10,800 / 10,000"),
      cancelledScan: restartAfterStoppedClicked &&
        /已停止|官方上下文刷新已停止/.test(cancelledText) &&
        /官方上下文刷新已停止，结果未确认完成。/.test(cancelledText) &&
        /已拉取 8,900/.test(cancelledText) &&
        /重新刷新|重试/.test(cancelledText) &&
        !/后台确认状态|用户已停止本次官方上下文刷新/.test(cancelledText) &&
        !/实际完成|预计剩余|接口分页参考数 10,000/.test(cancelledText) &&
        !cancelledText.includes("8,900 / 10,000"),
      warningRestartClicked: restartAfterStoppedClicked && restartAfterCancelClicked,
      warningComplete: /带警告|带警告完成/.test(officialText) && /官方上下文已刷新/.test(officialText),
      hasPartialCountCopy: /本次同步实际保存 8 条；接口分页参考数 12 条仅用于分页边界判断/.test(officialText),
      hasContextRetry: /仅重试上下文/.test(officialText) && /上下文刷新未完成，可仅重试上下文/.test(officialText),
      hasHistoryWarning: /最近官方同步/.test(officialText) && /带警告/.test(officialHistory?.innerText || officialText),
      readinessClicked,
      readinessBlocked: /仍阻断/.test(officialText) && /复核通过\\s*否/.test(officialText) && /缺少官方仿真指标/.test(officialText) && /补齐官方证据/.test(officialText),
      scientificAuditBlocked: /缺少科学审计证据/.test(officialText) &&
        /科学审计提交边界异常/.test(officialText) &&
        /最新候选科学审计含测试反馈/.test(officialText) &&
        /科学审计证据不完整/.test(officialText),
      checksClicked,
      checksLoaded: /2 条记录|已加载 2 条检查结果|质量检查结果已加载/.test(officialText),
      rawBackendHidden: !/SESSION_INVALID|session_invalid|invalid local session|raw backend|unknown sync job|mocked unclear sync status|Official context refreshed|candidate family lacks official simulation metrics|fields failed|后台确认状态|用户已停止本次官方上下文刷新/i.test(officialText),
      timelineHidesSecrets: !${SECRET_TEXT_PATTERN}.test(officialTimeline?.innerText || ""),
      forbiddenSecretsHidden: !${SECRET_TEXT_PATTERN}.test(officialText),
      stateOverflowFree: !sessionInvalidOverflowX && !openEndedOverflowX && !stoppedOverflowX && !cancelledOverflowX,
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickCandidateNavigation();
    await waitUntil(() => /生命周期回放/.test(text()), 180);
    await waitUntil(() => /候选管理/.test(text()) && /ALPHA_RT_001/.test(text()), 180);
    const candidatePanelText = () => {
      const heading = Array.from(document.querySelectorAll("h1,h2"))
        .find((node) => /候选管理/.test((node.textContent || "").trim()));
      return heading?.closest("#main-content")?.innerText || document.querySelector("#main-content")?.innerText || text();
    };
    const candidateTextBefore = candidatePanelText();
    const scoreCandidateButton = Array.from(document.querySelectorAll('button[aria-label^="评分 "]'))
      .find((button) => isVisible(button) && !button.disabled);
    const scoreCandidateClicked = Boolean(scoreCandidateButton);
    const clickedScoreAlphaId = (scoreCandidateButton?.getAttribute("aria-label") || "").match(/ALPHA_[A-Z0-9_]+/)?.[0] || "";
    if (scoreCandidateButton) {
      scoreCandidateButton.click();
      await waitFrames(4);
    }
    const scoringPanelText = () => {
      const heading = Array.from(document.querySelectorAll("h1,h2"))
        .find((node) => /^科学评分$/.test((node.textContent || "").trim()));
      return heading?.closest(".animate-fade-in")?.innerText || "";
    };
    await waitUntil(() => /科学评分/.test(scoringPanelText()) && /ALPHA_RT_/.test(scoringPanelText()), 180);
    await waitUntil(() => /归因分析/.test(scoringPanelText()) && /评分卡/.test(scoringPanelText()), 180);
    const scoringText = scoringPanelText();
    const refreshScoreButton = enabledButtonByText("刷新评分");
    const failureRefreshClicked = Boolean(refreshScoreButton && !refreshScoreButton.disabled);
    if (failureRefreshClicked) {
      refreshScoreButton.click();
      await waitUntil(() => /评分失败，请重新评估候选后再继续。/.test(scoringPanelText()), 180);
    }
    const scoringFailureText = scoringPanelText();
    const scoringRetryButton = enabledButtonByText("重试");
    const scoringRetryClicked = Boolean(scoringRetryButton && !scoringRetryButton.disabled);
    if (scoringRetryClicked) {
      scoringRetryButton.click();
      await waitUntil(() => /归因分析/.test(scoringPanelText()) && /评分卡/.test(scoringPanelText()) && !/评分失败，请重新评估候选后再继续。/.test(scoringPanelText()), 180);
    }
    const scoringRetryText = scoringPanelText();
    report.scoringPanel = {
      clickedAlphaId: clickedScoreAlphaId,
      reached: /科学评分/.test(scoringText) && Boolean(clickedScoreAlphaId) && scoringText.includes(clickedScoreAlphaId),
      attributionVisible: /归因分析/.test(scoringText) && /official_metrics|local_quality|total/.test(scoringText),
      hardGateVisible: /官方门禁检查|门禁/.test(scoringText),
      failureRefreshClicked,
      failureUserCopy: /评分失败，请重新评估候选后再继续。/.test(scoringFailureText),
      failureRetryVisible: /重试/.test(scoringFailureText),
      failureNotComplete: !/(^|\D)100%/.test(scoringFailureText) && !/评分已刷新/.test(scoringFailureText),
      failureRawBackendHidden: !/raw backend|RAW_BACKEND_SCORE_STATUS|SESSION_INVALID|invalid local session|password=secret/i.test(scoringFailureText),
      retryClicked: scoringRetryClicked,
      recoveredAfterRetry: /归因分析/.test(scoringRetryText) && /评分卡/.test(scoringRetryText) && !/评分失败，请重新评估候选后再继续。/.test(scoringRetryText),
      rawBackendHidden: !/raw backend|RAW_BACKEND_SCORE_STATUS|SESSION_INVALID|invalid local session|password=secret/i.test(scoringText + scoringFailureText + scoringRetryText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickCandidateNavigation();
    await waitUntil(() => /生命周期回放/.test(text()), 180);
    await waitUntil(() => /候选管理/.test(text()) && /ALPHA_RT_001/.test(text()), 180);
    const autoAdvanceButton = enabledButtonByText("自动推进候选池");
    const autoAdvanceClicked = Boolean(autoAdvanceButton && !autoAdvanceButton.disabled);
    if (autoAdvanceClicked) autoAdvanceButton.click();
    await waitUntil(() => /候选池自动推进完成/.test(candidatePanelText()) || !/推进中/.test(candidatePanelText()), 240);
    const candidateTextAfterAuto = candidatePanelText();
    await waitUntil(() => Boolean(enabledButtonByText("运行官方验证队列")), 240);
    const zeroSuccessQueueButton = enabledButtonByText("运行官方验证队列");
    const negativeOfficialValidationClicked = Boolean(zeroSuccessQueueButton && !zeroSuccessQueueButton.disabled);
    if (negativeOfficialValidationClicked) zeroSuccessQueueButton.click();
    await waitUntil(() => /BRAIN模拟完成/.test(candidatePanelText()) && /0 成功/.test(candidatePanelText()), 240);
    const candidateTextAfterZeroSimulation = candidatePanelText();
    const activeBatchCheckPattern = /正在批量检查|本地浏览器模拟：质量门槛检查运行中/;
    const negativeSimulationFailedVisible =
      /BRAIN模拟完成/.test(candidateTextAfterZeroSimulation) &&
      /0 成功/.test(candidateTextAfterZeroSimulation) &&
      /失败|操作失败|重试/.test(candidateTextAfterZeroSimulation);
    await waitUntil(() => Boolean(enabledButtonByText("运行官方验证队列")), 240);
    const officialQueueButton = enabledButtonByText("运行官方验证队列");
    const officialValidationClicked = Boolean(officialQueueButton && !officialQueueButton.disabled);
    if (officialValidationClicked) officialQueueButton.click();
    await waitUntil(() => /BRAIN模拟完成:\\s*1 成功/.test(candidatePanelText()), 240);
    const candidateTextAfterOfficialSimulation = candidatePanelText();
    await waitUntil(() => /正在批量检查|候选池质量门槛检查已启动|本地浏览器模拟：质量门槛检查运行中/.test(candidatePanelText()), 240);
    await waitUntil(() => /正在批量检查|本地浏览器模拟：质量门槛检查运行中|质量门槛检查完成/.test(candidatePanelText()), 240);
    const candidateTextAfterBatchCheck = candidatePanelText();
    report.candidateOperations = {
      reached: scoreCandidateClicked,
      hasTargetPoolControl: /目标池容量/.test(candidateTextBefore),
      autoAdvanceClicked,
      negativeOfficialValidationClicked,
      negativeTextHasBrainSimulation: /BRAIN模拟完成/.test(candidateTextAfterZeroSimulation),
      negativeTextHasZeroSuccess: /0 成功/.test(candidateTextAfterZeroSimulation),
      negativeTextHasFailureState: /失败|操作失败|重试/.test(candidateTextAfterZeroSimulation),
      negativeTextHasBatchCheck: activeBatchCheckPattern.test(candidateTextAfterZeroSimulation),
      negativeOfficialSimulationFailed: negativeSimulationFailedVisible,
      negativeNoBatchCheckVisible: !activeBatchCheckPattern.test(candidateTextAfterZeroSimulation),
      officialValidationClicked,
      officialSimulationVisible: /BRAIN官方模拟|BRAIN模拟完成|模拟完成/.test(candidateTextAfterOfficialSimulation),
      batchCheckVisible: /质量门槛检查/.test(candidateTextAfterBatchCheck),
      batchCheckCompleted: /正在批量检查|候选池质量门槛检查已启动|质量门槛检查完成/.test(candidateTextAfterBatchCheck),
      scoreCandidateClicked,
      rawBackendHidden: !/raw backend|SESSION_INVALID|invalid local session/i.test(candidateTextBefore + candidateTextAfterAuto + candidateTextAfterZeroSimulation + candidateTextAfterOfficialSimulation + candidateTextAfterBatchCheck),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };
    const lifecycleRegion = document.querySelector('section[aria-label="生命周期回放"]');
    const lifecycleText = lifecycleRegion?.innerText || "";
    const traceRowById = (id) => Array.from(lifecycleRegion?.querySelectorAll(".rounded-md") || [])
      .find((row) => (row.textContent || "").includes(id));
    const recoveredTrace = traceRowById("ALPHA_RT_002");
    const blockedTrace = traceRowById("ALPHA_RT_003");
    report.lifecycleReplay = {
      reached: Boolean(lifecycleRegion),
      hasLocalReadOnlyBadge: /本地只读/.test(lifecycleText),
      hasNonSubmitBadge: /非提交/.test(lifecycleText),
      hasSummaryMetrics: /记录/.test(lifecycleText) && /Alpha|ALPHA/.test(lifecycleText) && /阻断\\/失败/.test(lifecycleText),
      hasErrorAlert: Boolean(lifecycleRegion?.querySelector('[role="alert"]')),
      hasFailureCopy: /生命周期历史加载失败，请稍后重试。/.test(lifecycleText),
      emptyTextHiddenOnFailure: !/暂无匹配的生命周期记录。/.test(lifecycleText),
      rawFailureHidden: !/raw lifecycle backend failure/i.test(lifecycleText),
      hasRecoveredTrace: Boolean(recoveredTrace),
      recoveredTracePassed: /通过/.test(recoveredTrace?.textContent || ""),
      recoveredTraceNotBlocked: !/阻断/.test(recoveredTrace?.textContent || ""),
      hasBlockedTrace: Boolean(blockedTrace) && /复核阻断/.test(blockedTrace?.textContent || ""),
      forbiddenSecretsHidden: !${SECRET_TEXT_PATTERN}.test(lifecycleText),
      sample: "<omitted>",
    };

    await clickBacktestNavigation();
    await waitUntil(() => /官方回测槽位/.test(text()), 180);
    const backtestText = text();
    report.backtestSlots = {
      reached: /官方回测槽位/.test(backtestText),
      showsSlotLimit: /活跃\\s*1\\/3/.test(backtestText) || /活跃 1\\/3/.test(backtestText),
      showsRunningSlot: /运行中|官方回测进行中/.test(backtestText) && /ALPHA_RT_002/.test(backtestText),
      showsEmptySlot: /EMPTY|空闲/.test(backtestText),
      showsCompletedSlot: /已完成|官方回测完成/.test(backtestText) && /ALPHA_RT_001/.test(backtestText),
      rawBackendHidden: !/raw backend|SESSION_INVALID|invalid local session/i.test(backtestText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickQualityNavigation();
    await waitUntil(() => /达标检查/.test(text()) && /本地通过/.test(text()), 220);
    const qualityHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /达标检查/.test(heading.textContent || ""));
    const qualityPanel = qualityHeading?.closest(".animate-fade-in");
    const qualityText = qualityPanel?.innerText || "";
    report.qualityCheck = {
      reached: /达标检查/.test(qualityText),
      hasQualitySummary: /本地通过/.test(qualityText) &&
        /官方仿真/.test(qualityText) &&
        /复核候选/.test(qualityText) &&
        /提交证据缺口/.test(qualityText),
      hasNonSubmitEvidence: /官方接口\\s*未调用/.test(qualityText) &&
        /缺少官方仿真指标/.test(qualityText) &&
        /科学审计含测试反馈|科学审计/.test(qualityText),
      hasNextAction: /下一步/.test(qualityText) && /等待候选和门禁数据/.test(qualityText),
      rawBackendHidden: !/raw backend|RAW_BACKEND_CHECK_STATUS|SESSION_INVALID|invalid local session|raw backend-only|password=secret/i.test(qualityText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickConfigNavigation();
    await waitUntil(() => /连接与生产参数/.test(text()), 180);
    const configText = text();
    report.configPanel = {
      reached: /连接与生产参数/.test(configText),
      safeCredentialCopy: /保存配置不会保存账号、密码或 token/.test(configText) || /这些字段只保留在当前页面/.test(configText),
      autoSubmitClosed: /真实提交|auto_submit|自动提交/.test(configText) ? !/auto_submit\\s*[:=]\\s*true/i.test(configText) : true,
      noConnectionTestClicked: !/连接正常|连接失败/.test(configText),
      rawBackendHidden: !/raw backend|SESSION_INVALID|invalid local session/i.test(configText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickCheckpointNavigation();
    await waitUntil(() => /续跑记录/.test(text()) && /run_raw_snapshot/.test(text()), 220);
    const checkpointHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /续跑记录/.test(heading.textContent || ""));
    const checkpointPanel = checkpointHeading?.closest(".animate-fade-in");
    const checkpointText = checkpointPanel?.innerText || "";
    report.snapshotPanel = {
      reached: /续跑记录/.test(checkpointText) && /run_raw_snapshot/.test(checkpointText),
      hasCheckpointRows: /run_resume/.test(checkpointText) && /run_history_raw/.test(checkpointText),
      statusFailClosed: /状态待确认/.test(checkpointText) && !/RAW_BACKEND_CHECK_STATUS/.test(checkpointText),
      detailFailClosed: /详情待确认/.test(checkpointText) && /本地会话已失效，请重新连接后继续。/.test(checkpointText),
      visibleFieldFailClosed: /记录待确认/.test(checkpointText) &&
        /指标待确认/.test(checkpointText) &&
        /时间待确认/.test(checkpointText) &&
        /趋势待确认/.test(checkpointText) &&
        /对比项待确认/.test(checkpointText),
      rawBackendHidden: !/raw backend|raw backend-only checkpoint failure|RAW_BACKEND_CHECK_STATUS|invalid local session|SESSION_INVALID|password=secret|api_key=secret|csrf_token=secret|RAW_BACKEND_RISK/i.test(checkpointText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickRobustnessNavigation();
    await waitUntil(() => /稳健性/.test(text()) && /本地回放审计/.test(text()), 220);
    const robustnessHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /稳健性/.test(heading.textContent || ""));
    const robustnessPanel = robustnessHeading?.closest(".animate-fade-in");
    const robustnessText = robustnessPanel?.innerText || "";
    report.robustnessReplay = {
      reached: /稳健性/.test(robustnessText) && /本地回放审计/.test(robustnessText),
      hasReplayMetrics: /回放候选/.test(robustnessText) &&
        /3\\/5/.test(robustnessText) &&
        /生命周期命中/.test(robustnessText) &&
        /2\\/4/.test(robustnessText),
      hasStopRule: /停机规则:check_live_submit_readiness\.py/.test(robustnessText),
      hasNonSubmitBoundary: /非提交边界/.test(robustnessText) &&
        /已锁定/.test(robustnessText) &&
        /未调用官方接口/.test(robustnessText) &&
        /不允许提交/.test(robustnessText),
      hasScientificAudit: /科学审计/.test(robustnessText) &&
        /2\\/3/.test(robustnessText) &&
        /缺口:1/.test(robustnessText),
      rawBackendHidden: !/\\/Volumes\\/|\\/Users\\/|\\/tmp\\/|raw backend|password=secret|api_key=secret|csrf_token=secret|run_history\\.json/i.test(robustnessText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
    };

    await clickSubmissionConfirmNavigation();
    await waitUntil(() => /提交前阻断复核/.test(text()) && /状态待确认/.test(text()), 220);
    const submissionHeading = Array.from(document.querySelectorAll("h2"))
      .find((heading) => /提交前阻断复核/.test(heading.textContent || ""));
    const submissionPanel = submissionHeading?.closest(".animate-fade-in");
    const submissionText = submissionPanel?.innerText || "";
    report.submissionConfirm = {
      reached: /提交前阻断复核/.test(submissionText),
      finalReviewBlocked: /复核候选/.test(submissionText) &&
        /阻断/.test(submissionText) &&
        /阻断复核/.test(submissionText) &&
        /未通过/.test(submissionText) &&
        /可提交/.test(submissionText) &&
        /本页面不执行真实提交/.test(submissionText),
      scientificAuditBlocked: /缺少科学审计证据/.test(submissionText) &&
        /科学审计提交边界异常/.test(submissionText) &&
        /最新候选科学审计含测试反馈/.test(submissionText),
      unknownCheckStatusFailClosed: /状态待确认/.test(submissionText) && !/RAW_BACKEND_CHECK_STATUS/.test(submissionText),
      rawBackendHidden: !/SESSION_INVALID|session_invalid|invalid local session|raw backend|candidate family lacks official simulation metrics|raw backend-only submission gap|raw backend-only submit action|raw backend-only check reason|RAW_BACKEND_CHECK_STATUS/i.test(submissionText),
      hasBlockedTable: /阻断与待处理/.test(submissionText) && /ALPHA_RT_002/.test(submissionText),
      hasReadyEmptyState: /暂无通过预提交检查的 Alpha/.test(submissionText) || /ALPHA_RT_001/.test(submissionText),
      forbiddenSecretsHidden: !${SECRET_TEXT_PATTERN}.test(submissionText),
      finalOverflowX: document.body ? document.body.scrollWidth > window.innerWidth + 1 : false,
      sample: "<omitted>",
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
  if (!metrics.hasLocalSession) failures.push("local session badge is not visible");
  if (!metrics.visibleCardTitles.includes("非提交生产验证")) failures.push("production validation surface is missing");
  if (metrics.misleadingOnlineLabel) failures.push("page still shows the misleading online label");
  if (!metrics.meta.csrfPresent || !metrics.meta.streamPresent) failures.push("missing CSRF or stream meta token placeholder");
  if (metrics.resources.length < 2) failures.push("expected JS and CSS assets to load");
  if (metrics.pageOverflowX) failures.push("page overflows horizontally");
  if (metrics.forbiddenLifecycleSecretsVisible) failures.push("page exposed lifecycle replay secret-like text");
  const severeConsole = session.consoleMessages.filter((message) => ["error", "assert"].includes(message.type));
  const failedNonApiResponses = session.responses.filter((response) => response.status >= 400 && !response.isApi);
  const nonLocalRequests = session.networkRequests.filter((request) => !request.isLocal);
  const nonLocalResponses = session.responses.filter((response) => !response.isLocal);
  if (severeConsole.length) failures.push("browser console reported errors");
  if (failedNonApiResponses.length) failures.push("document or asset responses returned HTTP errors");
  if (session.networkFailures.length) failures.push("browser reported network loading failures");
  if (nonLocalRequests.length || nonLocalResponses.length || session.blockedNonLocalRequests.length) {
    failures.push("browser attempted to load a non-local resource");
  }
  return failures;
}

function validateInteractions(interactions, session) {
  const failures = [];
  const requested = (method, pathname) => session.mockRequests.some((request) => request.method === method && request.path === pathname);
  const requestCount = (method, pathname) => session.mockRequests.filter((request) => request.method === method && request.path === pathname).length;
  const home = interactions.home || {};
  if (!home.hasLocalSession || !home.hasProductionValidation) failures.push("home shell does not expose local non-submit validation state");
  if (!home.hasProofMetrics) failures.push("home shell does not expose non-submit proof metrics");
  if (!home.hasNoManualSubmitCard) failures.push("home shell still exposes a manual submit card");
  if (!home.noMisleadingOnline) failures.push("home still implies a remote online login state");

  const lifecycleReplay = interactions.lifecycleReplay || {};
  if (!lifecycleReplay.reached || !lifecycleReplay.hasLocalReadOnlyBadge || !lifecycleReplay.hasNonSubmitBadge) {
    failures.push("lifecycle replay panel did not render local read-only non-submit state");
  }
  if (lifecycleReplay.hasErrorAlert) {
    if (!lifecycleReplay.hasFailureCopy || !lifecycleReplay.emptyTextHiddenOnFailure || !lifecycleReplay.rawFailureHidden) {
      failures.push("lifecycle replay failure state did not show safe distinct user-facing copy");
    }
  } else {
    if (!lifecycleReplay.hasSummaryMetrics) failures.push("lifecycle replay panel did not expose replay summary metrics");
    if (!lifecycleReplay.hasRecoveredTrace || !lifecycleReplay.recoveredTracePassed || !lifecycleReplay.recoveredTraceNotBlocked) {
      failures.push("lifecycle replay recovered trace did not prioritize latest passed state");
    }
    if (!lifecycleReplay.hasBlockedTrace) failures.push("lifecycle replay blocked trace did not show review next action");
  }
  if (!lifecycleReplay.forbiddenSecretsHidden) failures.push("lifecycle replay panel exposed secret-like labels or values");

  const officialOperations = interactions.officialOperations || {};
  if (!officialOperations.reached || !officialOperations.hasEntryBadges || !officialOperations.hasOverview) {
    failures.push("official operations panel did not render the non-submit sync entry and overview");
  }
  if (!officialOperations.startClicked) failures.push("official operations sync refresh button was not clickable");
  if (!officialOperations.sessionInvalidRecovery || !officialOperations.sessionInvalidRawHidden) {
    failures.push("official operations session-invalid recovery state did not show safe reconnect guidance");
  }
  if (!officialOperations.openEndedScan) {
    failures.push("official operations open-ended sync scan did not stay indeterminate and non-complete");
  }
  if (!officialOperations.stoppedScan || !officialOperations.cancelledScan || !officialOperations.warningRestartClicked) {
    failures.push("official operations stopped/cancelled sync state did not stay retry-safe and non-complete");
  }
  if (!officialOperations.warningComplete || !officialOperations.hasPartialCountCopy || !officialOperations.hasContextRetry || !officialOperations.hasHistoryWarning) {
    failures.push("official operations sync warning state did not expose safe partial-success guidance");
  }
  if (!officialOperations.readinessClicked || !officialOperations.readinessBlocked) {
    failures.push("official operations readiness review did not stay visibly blocked and non-submit");
  }
  if (!officialOperations.scientificAuditBlocked) {
    failures.push("official operations readiness review did not show scientific-audit blockers");
  }
  if (!officialOperations.checksClicked || !officialOperations.checksLoaded) {
    failures.push("official operations check-results review did not load visible quality evidence");
  }
  if (!officialOperations.rawBackendHidden || !officialOperations.timelineHidesSecrets || !officialOperations.forbiddenSecretsHidden) {
    failures.push("official operations panel exposed raw backend/session or secret-like text");
  }
  if (!officialOperations.stateOverflowFree) failures.push("official operations intermediate state-error snapshots overflow horizontally");
  if (officialOperations.finalOverflowX) failures.push("official operations warning/readiness/check state overflows horizontally");

  const candidateOperations = interactions.candidateOperations || {};
  if (!candidateOperations.reached || !candidateOperations.hasTargetPoolControl) {
    failures.push("candidate operations panel did not render target-pool recovery controls");
  }
  if (!candidateOperations.autoAdvanceClicked) {
    failures.push("candidate operations auto-advance control was not clickable");
  }
  if (!candidateOperations.negativeOfficialValidationClicked || !candidateOperations.negativeOfficialSimulationFailed || !candidateOperations.negativeNoBatchCheckVisible) {
    failures.push("candidate operations zero-success official validation queue did not fail closed before quality gate check");
  }
  if (!candidateOperations.officialValidationClicked || !candidateOperations.officialSimulationVisible) {
    failures.push("candidate operations official validation queue did not run visible mocked simulation");
  }
  if (!candidateOperations.batchCheckVisible || !candidateOperations.batchCheckCompleted) {
    failures.push("candidate operations official validation queue did not continue into quality gate check");
  }
  if (!candidateOperations.scoreCandidateClicked) {
    failures.push("candidate operations did not navigate from a candidate row into scoring");
  }
  if (!candidateOperations.rawBackendHidden) failures.push("candidate operations panel exposed raw backend/session text");
  if (candidateOperations.finalOverflowX) failures.push("candidate operations panel overflows horizontally");

  const scoringPanel = interactions.scoringPanel || {};
  if (!scoringPanel.reached || !scoringPanel.attributionVisible || !scoringPanel.hardGateVisible) {
    failures.push("scoring panel did not render clicked-candidate scoring attribution and gate evidence");
  }
  if (!scoringPanel.failureRefreshClicked || !scoringPanel.failureUserCopy || !scoringPanel.failureRetryVisible || !scoringPanel.failureNotComplete) {
    failures.push("scoring panel failure state did not stay retry-safe and non-complete");
  }
  if (!scoringPanel.retryClicked || !scoringPanel.recoveredAfterRetry) {
    failures.push("scoring panel retry did not recover after a failed scoring event");
  }
  if (!scoringPanel.failureRawBackendHidden) failures.push("scoring panel failure state exposed raw backend/session text");
  if (!scoringPanel.rawBackendHidden) failures.push("scoring panel exposed raw backend/session text");
  if (scoringPanel.finalOverflowX) failures.push("scoring panel overflows horizontally");

  const backtestSlots = interactions.backtestSlots || {};
  if (!backtestSlots.reached || !backtestSlots.showsSlotLimit) {
    failures.push("official backtest slots panel did not render slot capacity summary");
  }
  if (!backtestSlots.showsRunningSlot || !backtestSlots.showsEmptySlot || !backtestSlots.showsCompletedSlot) {
    failures.push("official backtest slots panel did not render running, empty, and completed slot states");
  }
  if (!backtestSlots.rawBackendHidden) failures.push("official backtest slots panel exposed raw backend/session text");
  if (backtestSlots.finalOverflowX) failures.push("official backtest slots panel overflows horizontally");

  const qualityCheck = interactions.qualityCheck || {};
  if (!qualityCheck.reached || !qualityCheck.hasQualitySummary) {
    failures.push("quality check panel did not render local and official evidence summary");
  }
  if (!qualityCheck.hasNonSubmitEvidence || !qualityCheck.hasNextAction) {
    failures.push("quality check panel did not show non-submit blocker evidence and next action");
  }
  if (!qualityCheck.rawBackendHidden) failures.push("quality check panel exposed raw backend/session text");
  if (qualityCheck.finalOverflowX) failures.push("quality check panel overflows horizontally");

  const configPanel = interactions.configPanel || {};
  if (!configPanel.reached || !configPanel.safeCredentialCopy || !configPanel.autoSubmitClosed) {
    failures.push("config panel did not render safe cache/session configuration copy");
  }
  if (!configPanel.noConnectionTestClicked) failures.push("config panel connection test ran during browser smoke");
  if (!configPanel.rawBackendHidden) failures.push("config panel exposed raw backend/session text");
  if (configPanel.finalOverflowX) failures.push("config panel overflows horizontally");

  const snapshotPanel = interactions.snapshotPanel || {};
  if (!snapshotPanel.reached || !snapshotPanel.hasCheckpointRows) {
    failures.push("snapshot panel did not render checkpoint evidence rows");
  }
  if (!snapshotPanel.statusFailClosed || !snapshotPanel.detailFailClosed || !snapshotPanel.visibleFieldFailClosed || !snapshotPanel.rawBackendHidden) {
    failures.push("snapshot panel exposed raw checkpoint status, visible fields, or backend detail text");
  }
  if (snapshotPanel.finalOverflowX) failures.push("snapshot panel overflows horizontally");

  const robustnessReplay = interactions.robustnessReplay || {};
  if (!robustnessReplay.reached || !robustnessReplay.hasReplayMetrics) {
    failures.push("robustness replay audit panel did not render local latest_result replay metrics");
  }
  if (!robustnessReplay.hasStopRule || !robustnessReplay.hasNonSubmitBoundary || !robustnessReplay.hasScientificAudit) {
    failures.push("robustness replay audit panel did not expose stop-rule, non-submit, and scientific-audit evidence");
  }
  if (!robustnessReplay.rawBackendHidden) failures.push("robustness replay audit panel exposed local path or raw backend text");
  if (robustnessReplay.finalOverflowX) failures.push("robustness replay audit panel overflows horizontally");

  const productionValidation = interactions.productionValidation || {};
  if (!productionValidation.reached || !productionValidation.hasNonSubmitBadge || !productionValidation.hasProofMetrics) {
    failures.push("production validation monitor did not render non-submit proof surface");
  }
  if (!productionValidation.runClicked) failures.push("production validation run button was not clickable");
  if (!productionValidation.stopAvailableWhileRunning) failures.push("production validation stop control was not discoverable");
  if (!productionValidation.interruptedCopy || !productionValidation.rawBackendHidden) {
    failures.push("production validation interrupted state did not show safe user-facing copy");
  }
  if (!productionValidation.runEnabledAfter || !productionValidation.stopDisabledAfter) {
    failures.push("production validation interrupted state did not return controls to retry-safe state");
  }
  if (productionValidation.finalOverflowX) failures.push("production validation interrupted state overflows horizontally");

  const submissionConfirm = interactions.submissionConfirm || {};
  if (!submissionConfirm.reached || !submissionConfirm.finalReviewBlocked || !submissionConfirm.hasBlockedTable) {
    failures.push("submission confirm panel did not render final non-submit blocker review");
  }
  if (!submissionConfirm.scientificAuditBlocked) {
    failures.push("submission confirm panel did not show scientific-audit blockers");
  }
  if (!submissionConfirm.unknownCheckStatusFailClosed || !submissionConfirm.rawBackendHidden || !submissionConfirm.forbiddenSecretsHidden) {
    failures.push("submission confirm panel exposed raw readiness/check/status text");
  }
  if (submissionConfirm.finalOverflowX) failures.push("submission confirm panel overflows horizontally");

  for (const endpoint of ["/api/phase_state", "/api/production-validation/status", "/api/candidates", "/api/alpha_lifecycle", "/api/backtest_slots", "/api/config", "/api/checkpoint_status", "/api/latest_result", "/api/snapshot/cloud", "/api/snapshot/memory", "/api/sync_status", "/api/submit_readiness", "/api/check_results"]) {
    if (!requested("GET", endpoint)) failures.push(`expected mocked GET ${endpoint}`);
  }
  const lifecycleRequests = session.mockRequests.filter((request) => request.method === "GET" && request.path === "/api/alpha_lifecycle");
  if (!lifecycleRequests.some((request) => /(?:\?|&)limit=250(?:&|$)/.test(request.search))) {
    failures.push("lifecycle replay did not request the bounded local history endpoint");
  }
  for (const endpoint of ["/api/run", "/api/sync_alphas", "/api/sync_cancel", "/api/generate_candidates", "/api/candidates/simulate", "/api/check_batch", "/api/scoring/evaluate", "/api/scoring/attribution"]) {
    if (!requested("POST", endpoint)) failures.push(`expected mocked POST ${endpoint}`);
  }
  const runRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/run");
  const unsafeRunRequest = runRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      return body.autoSubmit !== false || body.auto_submit !== false ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeRunRequest) failures.push("production validation run request did not preserve non-submit/no-credential payload");
  const syncStartRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/sync_alphas");
  const unsafeSyncStartRequest = syncStartRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      return body.refreshOfficialContext !== true ||
        body.userFacingOperation !== "official_operations_context_refresh" ||
        !["all", "3d", "7d", "recent", "6months"].includes(String(body.syncRange || "")) ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeSyncStartRequest) failures.push("official operations sync request did not preserve safe local visual-smoke payload");
  const syncCancelRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/sync_cancel");
  const unsafeSyncCancelRequest = syncCancelRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      return body.job_id !== "sync_open_ended_scan" ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeSyncCancelRequest) failures.push("official operations sync cancel request did not preserve safe local visual-smoke payload");
  const generateRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/generate_candidates");
  const unsafeGenerateRequest = generateRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      return body.automation_mode !== "maintain_candidate_pool" ||
        body.auto_simulate_after_generation !== false ||
        body.auto_check_after_simulation !== false ||
        !Number.isFinite(Number(body.target_pool_size)) ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeGenerateRequest) failures.push("candidate operations auto-advance request did not preserve local non-submit/no-credential payload");
  const simulateRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/candidates/simulate");
  if (!simulateRequests.length) failures.push("candidate operations official validation queue did not start mocked candidate simulation");
  if (simulateRequests.length < 2) failures.push("candidate operations official validation queue did not exercise zero-success and successful simulation attempts");
  const simulatedCandidateIds = new Set();
  const unsafeSimulateRequest = simulateRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      const candidateIds = Array.isArray(body.candidate_ids) ? body.candidate_ids.map(String) : [];
      candidateIds.forEach((id) => simulatedCandidateIds.add(id));
      return candidateIds.length < 1 ||
        candidateIds.length > 3 ||
        Number(body.max_simulations || 0) < 1 ||
        Number(body.max_simulations || 0) > 3 ||
        !candidateIds.every((id) => /^ALPHA_RT_[A-Z0-9_]+$/.test(id)) ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeSimulateRequest) failures.push("candidate operations official validation simulation request did not preserve safe Top3 no-credential payload");
  const batchCheckRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === "/api/check_batch");
  if (!batchCheckRequests.length) failures.push("candidate operations official validation queue did not start mocked batch quality check");
  const secondSimulationRequestIndex = session.mockRequests.findIndex((request, index) => (
    request.method === "POST" &&
    request.path === "/api/candidates/simulate" &&
    session.mockRequests.slice(0, index).filter((prior) => prior.method === "POST" && prior.path === "/api/candidates/simulate").length === 1
  ));
  const batchBeforeSuccessfulSimulation = secondSimulationRequestIndex >= 0 && session.mockRequests.some((request, index) => (
    index < secondSimulationRequestIndex && request.method === "POST" && request.path === "/api/check_batch"
  ));
  if (batchBeforeSuccessfulSimulation) failures.push("candidate operations zero-success official validation queue called check_batch before a successful simulation");
  if (currentSmokeState.checkBatchBeforeSimulationSuccessCount > 0) failures.push("candidate operations mock server observed check_batch before official simulation success");
  const unsafeBatchCheckRequest = batchCheckRequests.some((request) => {
    try {
      const body = JSON.parse(request.body || "{}");
      const checkCandidates = Array.isArray(body.check_candidates) ? body.check_candidates : [];
      const checkCandidateIds = checkCandidates.map((candidate) => String(candidate?.alpha_id || candidate?.id || ""));
      return body.mode !== "quick" ||
        body.syncRange !== "all" ||
        checkCandidates.length < 1 ||
        checkCandidates.length > 3 ||
        !checkCandidateIds.every((id) => /^ALPHA_RT_[A-Z0-9_]+$/.test(id)) ||
        !checkCandidateIds.every((id) => simulatedCandidateIds.has(id)) ||
        Boolean(request.hasCredentialFields) ||
        Boolean(request.hasCredentialSearch);
    } catch {
      return true;
    }
  });
  if (unsafeBatchCheckRequest) failures.push("candidate operations batch quality check request did not preserve safe simulated-candidate no-credential payload");
  for (const endpoint of ["/api/scoring/evaluate", "/api/scoring/attribution"]) {
    const scoringRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === endpoint);
    const unsafeScoringRequest = scoringRequests.some((request) => {
      try {
        const body = JSON.parse(request.body || "{}");
        return !body.candidate ||
          !scoringPanel.clickedAlphaId ||
          body.alpha_id !== scoringPanel.clickedAlphaId ||
          body.candidate.alpha_id !== scoringPanel.clickedAlphaId ||
          Boolean(request.hasCredentialFields) ||
          Boolean(request.hasCredentialSearch);
      } catch {
        return true;
      }
    });
    if (unsafeScoringRequest) failures.push(`scoring request ${endpoint} did not preserve no-credential candidate payload`);
  }
  if (requestCount("POST", "/api/submit") !== 0 || requestCount("POST", "/api/submit_batch") !== 0) {
    failures.push("submission confirm panel attempted a submit endpoint");
  }
  for (const request of session.mockRequests) {
    if (MUTATING_METHODS.has(request.method) && !isAllowedMutatingRequest(request.method, request.path)) {
      failures.push(`unexpected browser-smoke mutating request ${request.method} ${request.path}`);
    }
  }
  for (const endpoint of [
	    "/api/submit",
	    "/api/submit_batch",
	    "/api/candidate/submit",
	    "/api/check",
	    "/api/sync-cloud-alphas",
    "/api/sync_context_only",
    "/api/generate",
    "/api/candidates/optimize",
    "/api/test_connection",
    "/api/connection_test",
    "/api/config",
  ]) {
    if (requestCount("POST", endpoint) !== 0) failures.push(`unexpected browser-smoke API request ${endpoint}`);
  }
  for (const request of session.mockRequests) {
    if (request.status === 501) {
      failures.push(`unmocked browser-smoke API request ${request.method} ${request.path}`);
    }
  }
  return failures;
}

function validateReplayAuditInteractions(interactions, session) {
  const failures = [];
  const requested = (method, pathname) => session.mockRequests.some((request) => request.method === method && request.path === pathname);
  const robustnessReplay = interactions.robustnessReplay || {};
  if (!robustnessReplay.navigated) failures.push("robustness replay audit slice did not navigate to the robustness evidence panel");
  if (!robustnessReplay.reached || !robustnessReplay.hasReplayMetrics) {
    failures.push("robustness replay audit panel did not render local latest_result replay metrics");
  }
  if (!robustnessReplay.hasStopRule || !robustnessReplay.hasNonSubmitBoundary || !robustnessReplay.hasScientificAudit) {
    failures.push("robustness replay audit panel did not expose stop-rule, non-submit, and scientific-audit evidence");
  }
  if (!robustnessReplay.rawBackendHidden) failures.push("robustness replay audit panel exposed local path or raw backend text");
  if (robustnessReplay.finalOverflowX) failures.push("robustness replay audit panel overflows horizontally");
  if (!requested("GET", "/api/latest_result")) failures.push("expected mocked GET /api/latest_result");
  if (!requested("GET", "/api/phase_state")) failures.push("expected mocked GET /api/phase_state");
  for (const request of session.mockRequests) {
    if (MUTATING_METHODS.has(request.method)) failures.push(`unexpected browser-smoke mutating request ${request.method} ${request.path}`);
    if (request.status === 501) failures.push(`unmocked browser-smoke API request ${request.method} ${request.path}`);
    if (request.hasCredentialFields || request.hasCredentialSearch) {
      failures.push(`browser-smoke request carried credential-like fields ${request.method} ${request.path}`);
    }
  }
  return failures;
}

function validateScoringFailureRetryInteractions(interactions, session) {
  const failures = [];
  const requested = (method, pathname) => session.mockRequests.some((request) => request.method === method && request.path === pathname);
  const requestCount = (method, pathname) => session.mockRequests.filter((request) => request.method === method && request.path === pathname).length;
  const scoringPanel = interactions.scoringPanel || {};
  if (!scoringPanel.candidateNavigated || !scoringPanel.scoreCandidateClicked || !scoringPanel.reached) {
    failures.push("scoring failure retry slice did not navigate from candidate row into scoring");
  }
  if (!scoringPanel.initialSuccess || !scoringPanel.attributionVisible || !scoringPanel.hardGateVisible) {
    failures.push("scoring failure retry slice did not render initial clicked-candidate scoring success");
  }
  if (!scoringPanel.failureRefreshClicked || !scoringPanel.failureUserCopy || !scoringPanel.failureRetryVisible || !scoringPanel.failureNotComplete) {
    failures.push("scoring failure retry slice did not stay retry-safe and non-complete after refresh failure");
  }
  if (!scoringPanel.retryClicked || !scoringPanel.recoveredAfterRetry) {
    failures.push("scoring failure retry slice did not recover after retry success");
  }
  if (!scoringPanel.failureRawBackendHidden || !scoringPanel.rawBackendHidden) {
    failures.push("scoring failure retry slice exposed raw backend/session text");
  }
  if (scoringPanel.finalOverflowX) failures.push("scoring failure retry slice overflows horizontally");
  for (const endpoint of ["/api/phase_state", "/api/candidates"]) {
    if (!requested("GET", endpoint)) failures.push(`expected mocked GET ${endpoint}`);
  }
  for (const endpoint of ["/api/scoring/evaluate", "/api/scoring/attribution"]) {
    const scoringRequests = session.mockRequests.filter((request) => request.method === "POST" && request.path === endpoint);
    if (!scoringRequests.length) failures.push(`expected mocked POST ${endpoint}`);
    const unsafeScoringRequest = scoringRequests.some((request) => {
      try {
        const body = JSON.parse(request.body || "{}");
        return !body.candidate ||
          !scoringPanel.clickedAlphaId ||
          body.alpha_id !== scoringPanel.clickedAlphaId ||
          body.candidate.alpha_id !== scoringPanel.clickedAlphaId ||
          Boolean(request.hasCredentialFields) ||
          Boolean(request.hasCredentialSearch);
      } catch {
        return true;
      }
    });
    if (unsafeScoringRequest) failures.push(`scoring failure retry request ${endpoint} did not preserve no-credential candidate payload`);
  }
  if (requestCount("POST", "/api/scoring/evaluate") < 3) {
    failures.push("scoring failure retry slice did not exercise initial success, refresh failure, and retry success");
  }
  if (requestCount("POST", "/api/scoring/attribution") < 3) {
    failures.push("scoring failure retry slice did not refresh attribution across success/failure/retry attempts");
  }
  if (requestCount("POST", "/api/submit") !== 0 || requestCount("POST", "/api/submit_batch") !== 0) {
    failures.push("scoring failure retry slice attempted a submit endpoint");
  }
  for (const request of session.mockRequests) {
    if (MUTATING_METHODS.has(request.method) && !isAllowedMutatingRequest(request.method, request.path)) {
      failures.push(`unexpected browser-smoke mutating request ${request.method} ${request.path}`);
    }
    if (request.hasCredentialFields || request.hasCredentialSearch) {
      failures.push(`scoring failure retry slice request carried credential-like fields ${request.method} ${request.path}`);
    }
    if (request.status === 501) failures.push(`unmocked browser-smoke API request ${request.method} ${request.path}`);
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
      { urlPattern: "*", requestStage: "Request" },
    ],
  });
}

async function runSmokeStep(session, viewportName, step, action) {
  const startedAt = Date.now();
  session.setStepContext(viewportName, step, startedAt);
  try {
    return await action();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/last_mock_endpoint=/.test(message)) throw error;
    throw new Error(session.diagnosticMessage(message, step));
  } finally {
    session.clearStepContext();
  }
}

function interactionConfigForSlice(slice) {
  if (slice === "replay_audit") {
    return {
      expression: replayAuditInteractionExpression(),
      timeoutMs: 30000,
      validate: validateReplayAuditInteractions,
    };
  }
  if (slice === "scoring_failure_retry") {
    return {
      expression: scoringFailureRetryInteractionExpression(),
      timeoutMs: 45000,
      validate: validateScoringFailureRetryInteractions,
    };
  }
  return {
    expression: interactionExpression(),
    timeoutMs: 150000,
    validate: validateInteractions,
  };
}

async function runViewport(session, url, viewport, outputDir, slice = "full") {
  session.resetObservations();
  currentSmokeViewport = viewport.name;
  resetSmokeState();
  const step = (name, action) => runSmokeStep(session, viewport.name, name, action);
  await step("configure viewport", () => session.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: Boolean(viewport.mobile),
  }));

  const navigationUrl = new URL(url);
  navigationUrl.searchParams.set("__react_artifact_smoke", `${viewport.name}-${Date.now()}`);
  navigationUrl.searchParams.set("__smoke_viewport", viewport.name);
  await step("navigate and load React shell", async () => {
    const loaded = session.waitForEvent("Page.loadEventFired", 30000);
    await session.send("Page.navigate", { url: navigationUrl.toString() });
    await loaded;
  });
  await step("wait for React paint", () => session.evaluate("new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"));

  const metrics = await step("collect shell metrics", () => session.evaluate(metricsExpression()));
  const homeScreenshotPath = path.join(outputDir, `react-artifact-smoke-${viewport.name}-home.png`);
  await step("capture home screenshot", () => session.captureScreenshot(homeScreenshotPath));
  const interactionConfig = interactionConfigForSlice(slice);
  const interactions = await step(`run ${slice} interactions`, () => session.evaluate(
    interactionConfig.expression,
    interactionConfig.timeoutMs,
  ));
  const finalScreenshotPath = path.join(outputDir, `react-artifact-smoke-${viewport.name}-final.png`);
  await step("capture final screenshot", () => session.captureScreenshot(finalScreenshotPath));

  const interactionFailures = interactionConfig.validate(interactions, session);
  const failures = [...validateMetrics(metrics, session), ...interactionFailures];
  return {
    name: viewport.name,
    ok: failures.length === 0,
    failures,
    screenshots: { home: homeScreenshotPath, final: finalScreenshotPath },
    metrics,
    interactions,
    consoleMessages: [...session.consoleMessages],
    networkFailures: [...session.networkFailures],
    networkRequests: [...session.networkRequests],
    blockedNonLocalRequests: [...session.blockedNonLocalRequests],
    failedNonApiResponses: session.responses.filter((response) => response.status >= 400 && !response.isApi),
    apiResponses: session.responses.filter((response) => response.isApi),
    mockRequests: [...session.mockRequests],
  };
}

async function main() {
  if (hasFlag("--help") || hasFlag("-h")) {
    console.log(usage());
    return 0;
  }
  const rawUrl = argValue("--url");
  if (!rawUrl) {
    console.error(usage());
    return 2;
  }
  const slice = argValue("--slice", "full");
  if (!VALID_SLICES.includes(slice)) {
    throw new Error(`--slice must be one of: ${VALID_SLICES.join(", ")}`);
  }
  const url = requireLoopbackHttpUrl(rawUrl, "--url");
  const devtoolsUrl = requireLoopbackHttpUrl(argValue("--devtools-url", "http://127.0.0.1:9224"), "--devtools-url").replace(/\/$/, "");
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
      runs.push(await runViewport(session, url, viewport, outputDir, slice));
    }
    const result = {
      ok: runs.every((run) => run.ok),
      schema_version: "browser_react_artifact_smoke.v2",
      slice,
      url: redactUrl(url),
      devtoolsUrl: redactUrl(devtoolsUrl),
      generated_at: new Date().toISOString(),
      runs,
    };
    const safeResult = redactReportValue(result);
    const serializedResult = JSON.stringify(safeResult, null, 2);
    assertReportRedacted(serializedResult);
    const resultPath = path.join(outputDir, "browser-react-artifact-smoke.json");
    fs.writeFileSync(resultPath, serializedResult, "utf-8");
    if (hasFlag("--json")) {
      console.log(serializedResult);
    } else {
      console.log(`${safeResult.ok ? "PASS" : "FAIL"} React artifact browser smoke`);
      console.log(`Report: ${resultPath}`);
      for (const run of safeResult.runs) {
        console.log(`- ${run.name}: ${run.ok ? "PASS" : `FAIL ${run.failures.join("; ")}`}`);
      }
    }
    return safeResult.ok ? 0 : 1;
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
