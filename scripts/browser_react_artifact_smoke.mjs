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
    "Usage: node scripts/browser_react_artifact_smoke.mjs --url <local-react-url>",
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
        requestId: message.params?.requestId || "",
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

  async captureScreenshot(filePath) {
    const screenshot = await this.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(filePath, Buffer.from(screenshot.data, "base64"));
    return filePath;
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
      search: url.search,
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
  if (method === "GET" && pathname === "/api/backtest_slots") {
    return ok({
      ok: true,
      slot_limit: 3,
      queue_summary: { slot_limit: 3 },
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
      eligible_count: 0,
      blocked_count: 2,
      summary_counts: { submission_ready: 0, submitted_this_run: 0, auto_submitted: 0 },
      top_blocking_reasons: [{ reason: "missing_official_metrics", count: 2 }],
      required_next_steps: ["complete official simulation metrics before any submit review"],
    });
  }
  if (method === "GET" && pathname === "/api/check_results") {
    return ok({
      ok: true,
      count: 2,
      items: [
        { alpha_id: "ALPHA_RT_001", status: "PASS", passed: true, summary: "official checks passed" },
        { alpha_id: "ALPHA_RT_002", status: "BLOCKED", passed: false, summary: "official metrics missing" },
      ],
    });
  }
  if (method === "POST" && pathname === "/api/sync_alphas") {
    return ok({ ok: true, job_id: "sync_smoke", task_id: "sync_smoke", status_url: "/api/sync_status?job_id=sync_smoke" });
  }
  if (method === "GET" && pathname === "/api/sync_status") {
    return ok({ ok: false, error_code: "STATUS_UNCLEAR", error: "mocked unclear sync status" });
  }
  if (method === "POST" && pathname === "/api/sync_cancel") {
    return ok({ ok: true, job_id: "sync_smoke", status: "stopped" });
  }
  if (method === "POST" && pathname === "/api/generate_candidates") {
    return ok({ ok: true, job_id: "gen_smoke", task_id: "gen_smoke" });
  }
  if (method === "POST" && pathname === "/api/scoring/evaluate") {
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
      history_count: 2,
      resume_available: true,
      storage_dir: "data",
      latest: {
        run_id: "run_resume",
        phase_completed: "official_validation",
        saved_at: "2026-06-05T00:00:00Z",
      },
      history: [
        {
          run_id: "run_resume",
          status: "completed",
          best_score: 88.5,
          completed_at: "2026-06-05T00:05:00Z",
        },
      ],
      latest_comparison: {
        deltas: { best_score: 4.5, submission_ready: 1 },
      },
      history_analytics: {
        schema_version: "run_history_analytics.v1",
        trend_status: "ready",
        latest_run_id: "run_resume",
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
  if (method === "GET" && pathname === "/sse") {
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
    family: "momentum",
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
    const cardTitles = ["官方操作", "运行总览", "候选管理", "回测监控", "科学评分", "质量门禁", "阻断复核", "续跑记录", "系统配置", "云端快照"];
    return {
      title: document.title,
      readyState: document.readyState,
      url: location.href,
      rootExists: Boolean(root),
      rootChildCount: root ? root.childElementCount : 0,
      rootTextLength: root ? root.innerText.length : 0,
      hasHeading: /BRAIN Alpha Ops/.test(text),
      hasLocalSession: /本地非提交页面|本地研究页面/.test(text),
      hasSettingsShortcut: Boolean(document.querySelector('button[aria-label="打开系统配置"]')),
      visibleCardTitles: cardTitles.filter((title) => text.includes(title)),
      misleadingOnlineLabel: /在线/.test(text),
      roles: {
        alerts: document.querySelectorAll('[role="alert"]').length,
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
      textSample: text.slice(0, 500),
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
    const buttonByText = (needle) => Array.from(document.querySelectorAll("button"))
      .find((button) => (button.textContent || "").includes(needle));
    const buttonByAria = (label) => document.querySelector('button[aria-label="' + label + '"]');
    const labelControl = (labelText) => {
      const labels = Array.from(document.querySelectorAll("label"));
      const label = labels.find((node) => (node.innerText || "").includes(labelText));
      return label ? label.querySelector("input, textarea, select") : null;
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

    await waitUntil(() => /本地 Web 页面/.test(text()) && /系统配置/.test(text()) && /云端快照/.test(text()) && /官方操作/.test(text()), 160);
    const cardTitles = ["官方操作", "运行总览", "候选管理", "回测监控", "科学评分", "质量门禁", "阻断复核", "续跑记录", "系统配置", "云端快照"];
    const report = {
      home: {
        hasLocalSession: /本地非提交页面|本地研究页面/.test(text()),
        hasTopSettings: Boolean(buttonByAria("打开系统配置")),
        cardTitlesVisible: cardTitles.filter((title) => text().includes(title)),
        hasOfficialOperations: /官方操作/.test(text()),
        hasNoManualSubmitCard: !/手动提交/.test(text()),
        hasConfigCardAction: Boolean(buttonByText("系统设置")),
        hasCandidateCardAction: Boolean(buttonByText("管理候选")),
        hasCheckpointCardAction: Boolean(buttonByText("查看历史")),
        hasCloudCardAction: Boolean(buttonByText("查看快照")),
        hasOfficialOperationsAction: Boolean(buttonByText("打开操作")),
        noMisleadingOnline: !/在线/.test(text()),
        sample: text().slice(0, 300),
      },
    };

    buttonByAria("打开系统配置")?.click();
    await waitUntil(() => /系统配置/.test(text()) && /BRAIN 设置/.test(text()) && /预算控制/.test(text()), 160);
    const connectionButton = buttonByText("测试 BRAIN 连接");
    const connectionEnabled = Boolean(connectionButton && !connectionButton.disabled);
    if (connectionEnabled) connectionButton.click();
    await waitUntil(() => /连接正常|BRAIN 连接测试通过/.test(text()), 120);
    const datasetInput = labelControl("数据集");
    if (datasetInput) setValue(datasetInput, "fundamental6");
    await waitFrames(8);
    const saveButton = buttonByText("保存");
    const saveEnabledBeforeClick = Boolean(saveButton && !saveButton.disabled);
    if (saveEnabledBeforeClick) saveButton.click();
    await waitUntil(() => /配置已保存/.test(text()) || Boolean(saveButton?.disabled), 80);
    report.configTopShortcut = {
      reached: /系统配置/.test(text()),
      hasBrainSettings: /BRAIN 设置/.test(text()),
      hasBudget: /预算控制/.test(text()),
      hasQualityThresholds: /质量阈值/.test(text()),
      hasEnvironmentSettings: /环境设置/.test(text()),
      hasConnectionSection: /BRAIN 连接/.test(text()),
      connectionClicked: connectionEnabled,
      connectionOk: /连接正常/.test(text()),
      hasLocalSessionBadge: /本页凭证已填写|未连接 BRAIN/.test(text()),
      hasDatasetInput: Boolean(datasetInput),
      saveClicked: saveEnabledBeforeClick,
      saveToastShown: /配置已保存/.test(text()),
    };

    buttonByAria("返回状态卡")?.click();
    await waitUntil(() => /本地 Web 页面/.test(text()) && /查看快照/.test(text()), 120);
    report.returnedAfterConfig = /本地 Web 页面/.test(text());

    buttonByText("查看快照")?.click();
    await waitUntil(() => /云端数据/.test(text()) && /ALPHA_CLOUD_1/.test(text()), 160);
    const cloudFilter = document.querySelector('input[aria-label="筛选 云端数据"]');
    if (cloudFilter) setValue(cloudFilter, "ALPHA_CLOUD_2");
    await waitUntil(() => /1 \\/ 2 行/.test(text()) || /ALPHA_CLOUD_2/.test(text()), 80);
    report.cloud = {
      reached: /云端数据/.test(text()),
      hasRefresh: Boolean(buttonByText("刷新")),
      hasMetrics: /返回数量/.test(text()) && /已提交/.test(text()) && /已通过/.test(text()),
      hasTable: Boolean(document.querySelector('table[aria-label="云端数据表格"]')),
      hasFirstAlpha: /ALPHA_CLOUD_1|ALPHA_CLOUD_2/.test(text()),
      hasFilter: Boolean(cloudFilter),
      filterWorked: /ALPHA_CLOUD_2/.test(text()) && !/ALPHA_CLOUD_1/.test(text()),
    };

	    buttonByAria("返回状态卡")?.click();
	    await waitUntil(() => /本地 Web 页面/.test(text()) && /查看历史/.test(text()), 120);

	    buttonByText("打开操作")?.click();
	    await waitUntil(() => /官方同步与阻断复核/.test(text()) && /开始刷新/.test(text()), 160);
	    buttonByText("读取复核")?.click();
	    await waitUntil(() => /当前仍未达到提交前阻断复核通过标准|阻断复核仍未通过/.test(text()), 120);
	    buttonByText("查看结果")?.click();
	    await waitUntil(() => /质量检查结果已加载|2 条记录/.test(text()), 120);
	    buttonByText("开始刷新")?.click();
	    await waitUntil(() => /连续读取刷新状态失败|已自动停止/.test(text()), 360);
	    report.officialOperations = {
	      reached: /官方同步与阻断复核/.test(text()),
	      hasButtonDrivenCopy: /按钮驱动/.test(text()) && /非提交/.test(text()),
	      readinessBlocked: /当前仍未达到提交前阻断复核通过标准|阻断复核仍未通过/.test(text()),
	      checkResultsLoaded: /质量检查结果已加载|2 条记录/.test(text()),
	      autoInterrupted: /连续读取刷新状态失败|已自动停止/.test(text()),
	      hidesCommands: !/(python |npm |shell|命令行)/i.test(text()),
	    };

	    buttonByAria("返回状态卡")?.click();
	    await waitUntil(() => /本地 Web 页面/.test(text()) && /管理候选/.test(text()), 120);

	    const installFailingEventSource = () => {
	      const NativeEventSource = window.EventSource;
	      const nativeSetTimeout = window.setTimeout.bind(window);
	      const nativeClearTimeout = window.clearTimeout.bind(window);
	      window.setTimeout = (handler, timeout, ...args) => nativeSetTimeout(handler, timeout === 3000 ? 1 : timeout, ...args);
	      class FailingEventSource {
	        static instances = [];
	        constructor(url) {
	          this.url = url;
	          this.readyState = 0;
	          FailingEventSource.instances.push(this);
	          nativeSetTimeout(() => {
	            this.readyState = 2;
	            if (typeof this.onerror === "function") this.onerror(new Event("error"));
	          }, 1);
	        }
	        addEventListener(_name, _handler) {}
	        removeEventListener(_name, _handler) {}
	        close() { this.readyState = 2; }
	      }
	      window.EventSource = FailingEventSource;
	      return () => {
	        window.EventSource = NativeEventSource;
	        window.setTimeout = nativeSetTimeout;
	        window.clearTimeout = nativeClearTimeout;
	      };
	    };
	    const restoreEventSource = installFailingEventSource();
	    buttonByText("管理候选")?.click();
	    await waitUntil(() => /候选管理/.test(text()) && /生成候选/.test(text()) && /ALPHA_RT_001/.test(text()), 160);
	    buttonByText("生成候选")?.click();
	    await waitUntil(() => /候选生成进度暂时不可确认|系统已安全停止本次生成/.test(text()), 260);
	    const scoreButton = buttonByAria("评分 ALPHA_RT_001") || buttonByText("评分");
	    scoreButton?.click();
	    await waitUntil(() => /评分与验证/.test(text()) && /评分进度暂时不可确认|系统已安全停止/.test(text()), 320);
	    restoreEventSource();
	    report.alphaFlow = {
	      candidatesReached: /候选管理/.test(text()) || /评分与验证/.test(text()),
	      candidateRowsVisible: /ALPHA_RT_001/.test(text()),
	      generateClicked: true,
	      generationAutoStopped: /候选生成进度暂时不可确认|系统已安全停止本次生成/.test(text()),
	      scoreReached: /评分与验证/.test(text()),
	      scoreAutoStopped: /评分进度暂时不可确认|系统已安全停止/.test(text()),
	    };

	    buttonByAria("返回状态卡")?.click();
	    await waitUntil(() => /本地 Web 页面/.test(text()) && /查看历史/.test(text()), 120);
	    buttonByText("查看历史")?.click();
    await waitUntil(() => /续跑记录/.test(text()) && /run_resume/.test(text()), 160);
    report.checkpoint = {
      reached: /续跑记录/.test(text()),
      hasMetrics: /续跑记录/.test(text()) && /历史记录/.test(text()) && /可续跑/.test(text()),
      hasTable: Boolean(document.querySelector('table[aria-label="续跑记录表格"]')),
      hasResumeRun: /run_resume/.test(text()),
      hasComparison: /对比/.test(text()),
    };

    buttonByAria("返回状态卡")?.click();
    await waitUntil(() => /本地 Web 页面/.test(text()) && /系统设置/.test(text()), 120);
    buttonByText("系统设置")?.click();
    await waitUntil(() => /系统配置/.test(text()) && /BRAIN 设置/.test(text()), 120);
    report.configCard = {
      reached: /系统配置/.test(text()),
      activeTitle: /系统配置/.test(text()),
      hasBrainSettings: /BRAIN 设置/.test(text()),
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
  if (!metrics.hasSettingsShortcut) failures.push("top-level settings shortcut is missing");
  if ((metrics.visibleCardTitles || []).length !== 10) failures.push("state-card navigation did not render all ten cards");
  if (metrics.misleadingOnlineLabel) failures.push("page still shows the misleading online label");
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
  const requested = (method, pathname) => session.mockRequests.some((request) => request.method === method && request.path === pathname);
  const requestCount = (method, pathname) => session.mockRequests.filter((request) => request.method === method && request.path === pathname).length;
  const home = interactions.home || {};
  if (!home.hasLocalSession || !home.hasTopSettings) failures.push("home shell does not expose local session and settings shortcut");
  if ((home.cardTitlesVisible || []).length !== 10) failures.push("home state-card set is incomplete");
  if (!home.hasConfigCardAction || !home.hasCheckpointCardAction || !home.hasCloudCardAction) {
    failures.push("config/checkpoint/cloud card actions are not discoverable");
  }
  if (!home.noMisleadingOnline) failures.push("home still implies a remote online login state");

  const configTop = interactions.configTopShortcut || {};
  if (!configTop.reached || !configTop.hasBrainSettings || !configTop.hasBudget || !configTop.hasQualityThresholds) {
    failures.push("top settings shortcut did not open the complete config panel");
  }
  if (!configTop.hasConnectionSection || !configTop.connectionClicked || !configTop.connectionOk || !requested("POST", "/api/test_connection")) {
    failures.push("config panel did not expose and complete the BRAIN connection test");
  }
  if (!configTop.hasDatasetInput) failures.push("config panel did not expose dataset settings");
  if (!configTop.saveClicked || !configTop.saveToastShown || !requested("POST", "/api/config")) {
    failures.push("config save flow did not complete through the browser UI");
  }
  if (!interactions.returnedAfterConfig) failures.push("back button did not return from config to state cards");

  const cloud = interactions.cloud || {};
  if (!cloud.reached || !cloud.hasMetrics || !cloud.hasTable || !cloud.hasFirstAlpha) {
    failures.push("cloud snapshot card did not render mocked cloud data");
  }
  if (!cloud.hasFilter || !cloud.filterWorked) failures.push("cloud snapshot filter did not narrow mocked rows");

  const officialOperations = interactions.officialOperations || {};
  if (!officialOperations.reached || !officialOperations.hasButtonDrivenCopy) {
    failures.push("official operations card did not expose the button-driven Web flow");
  }
  if (!officialOperations.readinessBlocked || !officialOperations.checkResultsLoaded) {
    failures.push("official operations did not show readiness blockers and check results");
  }
  if (!officialOperations.autoInterrupted) {
    failures.push("official operations did not auto-interrupt unclear refresh state");
  }
  if (!officialOperations.hidesCommands) {
    failures.push("official operations still exposes command-line wording");
  }

  const alphaFlow = interactions.alphaFlow || {};
  if (!alphaFlow.candidatesReached || !alphaFlow.candidateRowsVisible || !alphaFlow.generateClicked) {
    failures.push("candidate generation flow was not exercised through the Web UI");
  }
  if (!alphaFlow.generationAutoStopped) {
    failures.push("candidate generation did not request backend cancellation after ambiguous SSE state");
  }
  if (!alphaFlow.scoreReached || !alphaFlow.scoreAutoStopped) {
    failures.push("scoring flow did not request backend cancellation after ambiguous SSE state");
  }

  const checkpoint = interactions.checkpoint || {};
  if (!checkpoint.reached || !checkpoint.hasMetrics || !checkpoint.hasTable || !checkpoint.hasResumeRun || !checkpoint.hasComparison) {
    failures.push("checkpoint history card did not render mocked resume and history data");
  }

  const configCard = interactions.configCard || {};
  if (!configCard.reached || !configCard.hasBrainSettings) failures.push("state-card config entry did not open config");

  for (const endpoint of ["/api/candidates", "/api/backtest_slots", "/api/submit_readiness", "/api/checkpoint_status", "/api/config", "/api/config_schema", "/api/snapshot/cloud", "/api/check_results", "/api/sync_status"]) {
    if (!requested("GET", endpoint)) failures.push(`expected mocked GET ${endpoint}`);
  }
  for (const endpoint of ["/api/test_connection", "/api/config", "/api/sync_alphas", "/api/sync_cancel", "/api/generate_candidates", "/api/scoring/evaluate", "/api/scoring/attribution", "/api/cancel"]) {
    if (!requested("POST", endpoint)) failures.push(`expected mocked POST ${endpoint}`);
  }
  for (const endpoint of ["/api/submit", "/api/submit_batch"]) {
    if (requestCount("POST", endpoint) !== 0) failures.push(`unexpected submit endpoint request ${endpoint}`);
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
  const homeScreenshotPath = path.join(outputDir, `react-artifact-smoke-${viewport.name}-home.png`);
  await session.captureScreenshot(homeScreenshotPath);
  const interactions = await session.evaluate(interactionExpression());
  const finalScreenshotPath = path.join(outputDir, `react-artifact-smoke-${viewport.name}-final.png`);
  await session.captureScreenshot(finalScreenshotPath);

  const failures = [...validateMetrics(metrics, session), ...validateInteractions(interactions, session)];
  return {
    name: viewport.name,
    ok: failures.length === 0,
    failures,
    screenshots: { home: homeScreenshotPath, final: finalScreenshotPath },
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
      schema_version: "browser_react_artifact_smoke.v2",
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
