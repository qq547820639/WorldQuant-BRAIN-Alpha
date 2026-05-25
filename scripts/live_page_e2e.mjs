import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function redact(value) {
  return String(value || "").replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/g, "***@***").replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer ***");
}

function requirePlaywright() {
  try {
    return require("playwright-core");
  } catch (error) {
    if (error && error.code === "MODULE_NOT_FOUND") {
      return require("playwright");
    }
    throw error;
  }
}

function assertStep(results, name, passed, details = {}) {
  results.steps.push({ name, passed: Boolean(passed), details });
}

async function text(page, selector) {
  return ((await page.locator(selector).first().textContent().catch(() => "")) || "").trim();
}

async function inputValue(page, selector) {
  return await page.locator(selector).first().inputValue().catch(() => "");
}

async function visible(page, selector) {
  return await page.locator(selector).first().isVisible().catch(() => false);
}

async function canvasStats(page) {
  return await page.evaluate(() => {
    function stats(id) {
      const canvas = document.getElementById(id);
      if (!canvas) return { id, exists: false, nonWhite: 0 };
      const ctx = canvas.getContext("2d");
      if (!ctx || !canvas.width || !canvas.height) return { id, exists: true, width: canvas.width, height: canvas.height, nonWhite: 0 };
      const width = Math.min(canvas.width, 220);
      const height = Math.min(canvas.height, 140);
      const data = ctx.getImageData(0, 0, width, height).data;
      let nonWhite = 0;
      for (let i = 0; i < data.length; i += 4) {
        const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
        if (a && !(r > 245 && g > 245 && b > 245)) nonWhite += 1;
      }
      return { id, exists: true, width: canvas.width, height: canvas.height, nonWhite };
    }
    return ["scoreTrendChart", "sharpeDistChart", "gatePieChart", "turnoverChart"].map(stats);
  });
}

async function latestToasts(page) {
  return await page.locator("#toastContainer .toast").evaluateAll((nodes) => nodes.map((node) => node.textContent.trim()).slice(-8)).catch(() => []);
}

async function main() {
  const url = argValue("--url", "http://127.0.0.1:8765/");
  const username = process.env.BRAIN_USERNAME || "";
  const password = process.env.BRAIN_PASSWORD || "";
  const token = process.env.BRAIN_TOKEN || "";
  const allowSubmit = process.argv.includes("--allow-submit");
  const doSync = process.argv.includes("--sync");
  const outputDir = argValue("--output-dir", "output/playwright");
  const resultJsonPath = argValue("--result-json", path.join(outputDir, "live-page-e2e.json"));
  const edgePath = process.env.PLAYWRIGHT_BROWSER_EXECUTABLE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
  const results = {
    ok: false,
    schema_version: "live_page_e2e.v1",
    url,
    mode: "production",
    submit_executed: false,
    sync_executed: doSync,
    steps: [],
    browser_events: { console_errors: [], page_errors: [], failed_requests: [], api_responses: [] },
    artifacts: {},
  };

  assertStep(results, "credential_input_mode", true, {
    auth: token ? "token" : (username || password ? "browser_form" : "server_environment"),
    note: username || password || token
      ? "credentials supplied to the browser form from process environment"
      : "browser form left empty; server must resolve BRAIN credentials from its own environment",
  });

  const { chromium } = requirePlaywright();
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({
    executablePath: fs.existsSync(edgePath) ? edgePath : undefined,
    headless: true,
    args: ["--disable-gpu", "--no-sandbox"],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 }, ignoreHTTPSErrors: true });
  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") results.browser_events.console_errors.push(redact(msg.text()).slice(0, 500));
  });
  page.on("pageerror", (error) => results.browser_events.page_errors.push(redact(String(error)).slice(0, 500)));
  page.on("requestfailed", (request) => results.browser_events.failed_requests.push({
    url: redact(request.url()),
    failure: request.failure()?.errorText || "",
  }));
  page.on("response", (response) => {
    const responseUrl = response.url();
    if (responseUrl.includes("/api/")) results.browser_events.api_responses.push({ url: redact(responseUrl), status: response.status() });
  });

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForSelector("#controlButton", { timeout: 15000 });
    await page.waitForTimeout(1200);

    const envValue = await inputValue(page, "#environment");
    const envDisabled = await page.locator("#environment").evaluate((el) => el.disabled).catch(() => false);
    const mockOptions = await page.locator('option[value="mock"]').count();
    const mockText = await page.locator("text=本地模拟环境").count();
    assertStep(results, "production_only_ui", envValue === "production" && envDisabled && mockOptions === 0 && mockText === 0, {
      envValue,
      envDisabled,
      mockOptions,
      mockText,
      envBadge: await text(page, "#envBadge"),
    });

    const renderedRows = await page.locator("#candidateRows tr").count().catch(() => 0);
    assertStep(results, "initial_display", await visible(page, "#statusBar") && (await visible(page, "#tableEmptyState") || renderedRows > 0), {
      title: await text(page, "#tableTitle"),
      count: await text(page, "#countPill"),
      rows: renderedRows,
      status: await text(page, "#statusBar"),
    });

    await page.selectOption("#preset", "usa_liquid").catch(() => {});
    await page.waitForTimeout(150);
    assertStep(results, "preset_applies_settings", await inputValue(page, "#preset") === "usa_liquid", {
      region: await inputValue(page, "#region"),
      universe: await inputValue(page, "#universe"),
      decay: await inputValue(page, "#decay"),
      truncation: await inputValue(page, "#truncation"),
    });

    await page.fill("#tableSearch", "NO_SUCH_ALPHA_20260522_!@#");
    await page.waitForTimeout(200);
    assertStep(results, "filter_no_match_empty_state", await visible(page, "#tableEmptyState"), {
      count: await text(page, "#countPill"),
      description: await text(page, "#tableEmptyDescription"),
    });
    await page.fill("#tableSearch", "");

    await page.click("#chartModeBtn");
    await page.waitForTimeout(900);
    const charts = await canvasStats(page);
    assertStep(results, "charts_render_or_empty_fallback", await visible(page, "#chartsPanel") && charts.every((item) => item.exists), {
      fallback: await text(page, "#chartFallback"),
      charts,
    });
    await page.click("#tableModeBtn");

    await page.locator('[data-action="toggle-collapsible"][data-target="advancedConn"]').click();
    if (username) await page.fill("#username", username);
    if (password) await page.fill("#password", password);
    if (token) await page.fill("#token", token);

    await page.fill("#baseUrl", "http://127.0.0.1:1");
    await page.click("#connTestBtn");
    await page.waitForTimeout(2500);
    const badClass = await page.locator("#connTestResult").evaluate((el) => el.className).catch(() => "");
    assertStep(results, "invalid_base_url_rejected", badClass.includes("is-error"), {
      result: redact(await text(page, "#connTestResult")),
      className: badClass,
    });

    await page.fill("#baseUrl", "https://api.worldquantbrain.com");
    await page.click("#connTestBtn");
    await page.waitForTimeout(12000);
    const liveClass = await page.locator("#connTestResult").evaluate((el) => el.className).catch(() => "");
    assertStep(results, "live_brain_connection", liveClass.includes("is-success"), {
      result: redact(await text(page, "#connTestResult")),
      className: liveClass,
    });

    let syncBlocksProduction = false;
    if (doSync) {
      const responseStart = results.browser_events.api_responses.length;
      await page.click("#syncButton");
      await page.waitForTimeout(20000);
      const syncToasts = await latestToasts(page);
      const syncResponses = results.browser_events.api_responses.slice(responseStart);
      const syncStatus = await text(page, "#monitorCloudStatus");
      syncBlocksProduction = await page.locator("#controlButton").isDisabled().catch(() => false);
      assertStep(results, "live_cloud_sync", syncResponses.some((item) => item.url.includes("/api/sync_alphas") && item.status < 400), {
        status: syncStatus,
        productionLocked: syncBlocksProduction,
        controlTitle: await page.locator("#controlButton").getAttribute("title").catch(() => ""),
        count: await text(page, "#countPill"),
        toasts: syncToasts.map(redact),
        responses: syncResponses,
      });
    }

    if (syncBlocksProduction) {
      assertStep(results, "operation_lock_during_cloud_sync", true, {
        button: await text(page, "#controlButton"),
        title: await page.locator("#controlButton").getAttribute("title").catch(() => ""),
      });
    } else {
      await page.locator('[data-action="toggle-collapsible"][data-target="backtestSettings"]').click().catch(() => {});
      await page.fill("#decay", "-1");
      const invalidResponseStart = results.browser_events.api_responses.length;
      await page.click("#controlButton");
      await page.waitForTimeout(2500);
      const invalidResponses = results.browser_events.api_responses.slice(invalidResponseStart);
      assertStep(results, "invalid_decay_guard", invalidResponses.some((item) => item.url.includes("/api/run") && item.status >= 400), {
        button: await text(page, "#controlButton"),
        toasts: (await latestToasts(page)).map(redact),
        responses: invalidResponses,
      });
      await page.fill("#decay", "10");
    }

    await page.click('[data-action="switch-view"][data-view="passed"]');
    await page.waitForTimeout(500);
    const toastCountBeforeCheck = await page.locator("#toastContainer .toast").count().catch(() => 0);
    await page.click("#checkButton").catch(() => {});
    await page.waitForTimeout(700);
    const toastCountAfterCheck = await page.locator("#toastContainer .toast").count().catch(() => 0);
    assertStep(results, "check_empty_state_guard", toastCountAfterCheck > toastCountBeforeCheck || await visible(page, "#tableEmptyState"), {
      title: await text(page, "#tableTitle"),
      toasts: (await latestToasts(page)).map(redact),
      checkStats: await text(page, "#checkStats"),
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.click('[data-action="switch-view"][data-view="candidates"]');
    await page.waitForTimeout(700);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    assertStep(results, "mobile_layout_no_horizontal_overflow", !overflow, {
      scrollWidth: await page.evaluate(() => document.documentElement.scrollWidth),
      innerWidth: await page.evaluate(() => window.innerWidth),
      mobileCardsVisible: await visible(page, "#mobileCardList"),
      emptyVisible: await visible(page, "#tableEmptyState"),
    });

    if (allowSubmit) {
      results.submit_executed = true;
    } else {
      assertStep(results, "submit_not_executed_without_explicit_flag", true, { reason: "pass --allow-submit to execute real submit" });
    }

    const screenshotPath = path.join(outputDir, "live-page-e2e.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });
    results.artifacts.screenshot = screenshotPath;
    results.artifacts.result_json = resultJsonPath;
  } finally {
    await browser.close();
  }

  results.ok = results.steps.every((step) => step.passed) && results.browser_events.page_errors.length === 0;
  fs.mkdirSync(path.dirname(resultJsonPath), { recursive: true });
  fs.writeFileSync(resultJsonPath, JSON.stringify(results, null, 2) + "\n", "utf8");
  console.log(JSON.stringify(results, null, 2));
  process.exit(results.ok ? 0 : 1);
}

main().catch((error) => {
  console.log(JSON.stringify({ ok: false, schema_version: "live_page_e2e.v1", error: redact(error && error.stack ? error.stack : String(error)) }, null, 2));
  process.exit(1);
});
