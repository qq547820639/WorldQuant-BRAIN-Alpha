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
    "Usage: node scripts/browser_populated_layout_smoke.mjs --url <local-url> [options]",
    "",
    "Options:",
    "  --devtools-url <url>   Chrome DevTools HTTP URL, default http://127.0.0.1:9223",
    "  --output-dir <dir>     Artifact directory, default output/browser-populated-layout",
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

  handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.id && this.pending.has(message.id)) {
      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(`${message.error.message || "CDP error"} (${message.error.code})`));
      else resolve(message.result || {});
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

  close() {
    if (this.ws) this.ws.close();
  }
}

function seedExpression() {
  return `(() => {
    const now = Date.now();
    const families = ["momentum", "quality", "sentiment", "volatility", "reversal"];
    const statuses = ["pending_backtest", "running_backtest", "submission_ready", "submitted", "failed"];
    const candidates = Array.from({ length: 120 }, (_, i) => {
      const index = i + 1;
      const alphaId = "ALPHA_" + String(index).padStart(4, "0");
      const status = statuses[i % statuses.length];
      return {
        alpha_id: alphaId,
        official_alpha_id: index % 6 === 0 ? "OS_" + alphaId : "",
        simulation_id: "SIM_" + alphaId,
        expression: "rank(ts_mean(close, " + (5 + (i % 30)) + ")) - group_neutralize(volume, industry)",
        family: families[i % families.length],
        hypothesis: "Populated browser layout smoke candidate " + index,
        lifecycle_status: status,
        status,
        submission_risk: index % 7 === 0 ? "self-correlation review required" : "",
        scorecard: { total_score: 62 + (i % 35), local_rank_score: 55 + (i % 40), decision_band: index % 3 === 0 ? "promote" : "review" },
        official_metrics: { sharpe: 1.1 + (i % 20) / 20, fitness: 0.8 + (i % 25) / 25, turnover: 0.02 + (i % 18) / 100 },
        gate: { submission_ready: status === "submission_ready" },
      };
    });
    const checkResults = {};
    candidates.filter((candidate) => candidate.lifecycle_status === "submission_ready").forEach((candidate) => {
      checkResults[candidate.alpha_id] = {
        passed: true,
        checked_at: new Date(now - 60000).toISOString(),
        checks: [{ name: "official_pre_submit_check", passed: true }],
      };
    });
    const cloud = candidates.slice(0, 36).map((candidate, i) => ({
      alpha_id: candidate.official_alpha_id || candidate.alpha_id,
      status: i % 4 === 0 ? "PRODUCTION" : i % 5 === 0 ? "REJECTED" : "APPROVED",
      sharpe: candidate.official_metrics.sharpe,
      fitness: candidate.official_metrics.fitness,
      turnover: candidate.official_metrics.turnover,
      self_correlation: 0.12 + (i % 12) / 100,
      expression: candidate.expression,
    }));
    const lifecycle = candidates.slice(0, 45).map((candidate, i) => ({
      alpha_id: candidate.alpha_id,
      stage: i % 3 === 0 ? "submitted" : "backtest",
      status: i % 8 === 0 ? "failed" : "completed",
      timestamp: new Date(now - i * 300000).toISOString(),
      message: "Lifecycle event " + (i + 1),
    }));
    const robustness = {
      candidates: candidates.slice(0, 24).map((candidate, i) => ({
        alpha_id: candidate.alpha_id,
        family: candidate.family,
        scorecard: candidate.scorecard,
        gate: candidate.gate,
        risk: i % 4 === 0 ? "turnover sensitivity" : "ok",
      })),
    };
    window.AppState.setBatch({
      "activeView": "candidates",
      "currentResult.summary": {
        generated_at: new Date(now).toISOString(),
        candidates,
        cloud_alphas: cloud,
        lifecycle_records: lifecycle,
        robustness_snapshot: robustness,
        cloud_sync: { status: "completed", loaded: cloud.length, scanned: cloud.length },
      },
      "currentResult.candidates": candidates,
      "currentResult.cloud_alphas": cloud,
      "currentResult.lifecycle_records": lifecycle,
      "currentResult.robustness_snapshot": robustness,
      "checkResults": checkResults,
      "selectedSubmitIds": [],
      "isRunning": false,
      "syncInFlight": false,
      "batchCheckInFlight": false,
      "submitInFlight": false,
      "lastSubmitResults": [],
    });
    window.renderAll();
    return {
      candidates: candidates.length,
      cloud: cloud.length,
      lifecycle: lifecycle.length,
      submittable: Object.keys(checkResults).length,
    };
  })()`;
}

function metricsExpression() {
  return `(() => {
    const isVisible = (el) => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const rectFor = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        selector,
        visible: isVisible(el),
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        className: String(el.className || ""),
      };
    };
    const leaking = Array.from(document.body.querySelectorAll("*"))
      .filter(isVisible)
      .map((el) => ({ tag: el.tagName.toLowerCase(), id: el.id || "", className: String(el.className || ""), rect: el.getBoundingClientRect() }))
      .filter((item) => item.rect.right > window.innerWidth + 1 || item.rect.left < -1)
      .slice(0, 20)
      .map((item) => ({
        tag: item.tag,
        id: item.id,
        className: item.className,
        left: Math.round(item.rect.left),
        right: Math.round(item.rect.right),
        width: Math.round(item.rect.width),
      }));
    const smallActionControls = Array.from(document.querySelectorAll("button, .btn, [role='button']"))
      .filter(isVisible)
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return { label: (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 80), id: el.id || "", width: Math.round(rect.width), height: Math.round(rect.height) };
      })
      .filter((item) => item.height < 38 || item.width < 32);
    return {
      title: document.title,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      scroll: {
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        pageOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1 || document.body.scrollWidth > window.innerWidth + 1,
      },
      roles: {
        tablist: document.querySelectorAll('[role="tablist"]').length,
        tab: document.querySelectorAll('[role="tab"]').length,
        selectedTabs: document.querySelectorAll('[role="tab"][aria-selected="true"]').length,
        tabpanel: document.querySelectorAll('[role="tabpanel"]').length,
        progressbar: document.querySelectorAll('[role="progressbar"]').length,
        liveRegions: document.querySelectorAll('[aria-live]').length,
      },
      table: rectFor("#candidateTable"),
      mobileCards: rectFor("#mobileCardList"),
      runtimeStatus: rectFor("#runtimeStatusPanel"),
      workflowRail: rectFor("#workflowRail"),
      visibleRows: document.querySelectorAll("#candidateRows tr").length,
      visibleCards: document.querySelectorAll("#mobileCardList .mobile-card").length,
      countPill: (document.querySelector("#countPill")?.textContent || "").trim(),
      activeView: window.AppState.get("activeView"),
      leaking,
      smallActionControls: smallActionControls.slice(0, 20),
    };
  })()`;
}

async function runViewport(session, url, viewport, outputDir) {
  await session.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: viewport.width <= 640,
  });
  const loaded = session.waitForEvent("Page.loadEventFired", 30000);
  const navigationUrl = new URL(url);
  navigationUrl.searchParams.set("__layout_smoke", `${viewport.name}-${Date.now()}`);
  await session.send("Page.navigate", { url: navigationUrl.toString() });
  await loaded;
  await session.evaluate("document.readyState");
  const seed = await session.evaluate(seedExpression());
  const views = {};
  for (const view of ["candidates", "passed", "submittable", "cloud", "lifecycle", "robustness"]) {
    await session.evaluate(`window.switchView(${JSON.stringify(view)}); window.renderCurrentView(); true`);
    views[view] = await session.evaluate(metricsExpression());
  }
  await session.evaluate('window.switchView("candidates"); window.renderCurrentView(); true');
  const screenshot = await session.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const screenshotPath = path.join(outputDir, `${viewport.name}.png`);
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));
  const candidatesMetrics = views.candidates;
  const failures = [];
  if (candidatesMetrics.title !== "BRAIN Alpha Ops") failures.push("page title mismatch");
  if (candidatesMetrics.roles.tablist < 1) failures.push("missing tablist");
  if (candidatesMetrics.roles.selectedTabs !== 1) failures.push("expected exactly one selected tab");
  if (candidatesMetrics.roles.tabpanel < 1) failures.push("missing tabpanel");
  if (candidatesMetrics.roles.progressbar < 2) failures.push("missing progress bars");
  if (candidatesMetrics.roles.liveRegions < 4) failures.push("missing live regions");
  if (candidatesMetrics.scroll.pageOverflowX) failures.push("page overflows horizontally");
  if (candidatesMetrics.leaking.length) failures.push("visible elements leak outside viewport");
  if (viewport.width <= 640) {
    if (candidatesMetrics.table && candidatesMetrics.table.visible) failures.push("desktop table visible on mobile");
    if (!candidatesMetrics.mobileCards || !candidatesMetrics.mobileCards.visible) failures.push("mobile cards hidden on mobile");
    if (candidatesMetrics.smallActionControls.length) failures.push("small visible action controls on mobile");
  } else {
    if (!candidatesMetrics.table || !candidatesMetrics.table.visible) failures.push("desktop table hidden on desktop");
  }
  for (const [view, viewMetrics] of Object.entries(views)) {
    if (viewMetrics.roles.selectedTabs !== 1) failures.push(`${view} selected tab count mismatch`);
    if (viewMetrics.scroll.pageOverflowX) failures.push(`${view} overflows horizontally`);
  }
  return {
    name: viewport.name,
    ok: failures.length === 0,
    failures,
    seed,
    screenshot: screenshotPath,
    views,
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
  const devtoolsUrl = argValue("--devtools-url", "http://127.0.0.1:9223").replace(/\/$/, "");
  const outputDir = argValue("--output-dir", "output/browser-populated-layout");
  fs.mkdirSync(outputDir, { recursive: true });

  let target = null;
  let session = null;
  try {
    target = await fetchJson(`${devtoolsUrl}/json/new?about:blank`, { method: "PUT" });
    session = new CdpSession(target.webSocketDebuggerUrl);
    await session.connect();
    await session.send("Page.enable");
    await session.send("Runtime.enable");
    await session.send("Network.enable");
    await session.send("Network.setCacheDisabled", { cacheDisabled: true });

    const viewports = [
      { name: "desktop-1366x900", width: 1366, height: 900 },
      { name: "mobile-390x844", width: 390, height: 844 },
    ];
    const runs = [];
    for (const viewport of viewports) {
      runs.push(await runViewport(session, url, viewport, outputDir));
    }
    const result = {
      ok: runs.every((run) => run.ok),
      schema_version: "browser_populated_layout_smoke.v1",
      url,
      devtoolsUrl,
      generated_at: new Date().toISOString(),
      runs,
    };
    const resultPath = path.join(outputDir, "browser-populated-layout.json");
    fs.writeFileSync(resultPath, JSON.stringify(result, null, 2), "utf-8");
    if (hasFlag("--json")) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      console.log(`${result.ok ? "PASS" : "FAIL"} browser populated layout smoke`);
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
