import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const root = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha";
const outDir = path.join(root, "output/playwright");
await mkdir(outDir, { recursive: true });

const require = createRequire(import.meta.url);
const { chromium } = require("/Users/panhao/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const browser = await chromium.launch({ headless: true });
const results = [];

async function checkViewport(name, viewport) {
  console.error(`[${name}] open`);
  const page = await browser.newPage({ viewport });
  page.setDefaultTimeout(10000);
  page.setDefaultNavigationTimeout(10000);
  await page.route("**/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/config" || pathname === "/api/config_schema") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, candidates: [], count: 0, rows: [] }),
    });
  });
  console.error(`[${name}] goto`);
  await page.goto("http://127.0.0.1:18769/", { waitUntil: "domcontentloaded" });
  console.error(`[${name}] wait settings`);
  await page.getByRole("button", { name: "打开系统配置" }).waitFor({ state: "visible" });
  console.error(`[${name}] click settings`);
  await page.getByRole("button", { name: "打开系统配置" }).click();
  console.error(`[${name}] fill credentials`);
  await page.getByRole("heading", { name: "连接与生产参数" }).waitFor({ state: "visible" });
  await page.getByLabel("账户邮箱").fill("reader@example.com");
  await page.getByLabel("密码").fill("session-secret");
  await page.getByLabel("Token").fill("token-placeholder");

  const visible = {
    heading: await page.getByRole("heading", { name: "连接与生产参数" }).isVisible(),
    username: await page.getByLabel("账户邮箱").isVisible(),
    password: await page.getByLabel("密码").isVisible(),
    token: await page.getByLabel("Token").isVisible(),
    testButton: await page.getByRole("button", { name: "测试 BRAIN 连接" }).isVisible(),
    sessionBadge: await page.getByText("BRAIN 已填写").isVisible().catch(() => false),
  };

  const screenshot = path.join(outDir, `brain-config-${name}.png`);
  console.error(`[${name}] screenshot`);
  await page.screenshot({ path: screenshot, fullPage: true });

  const metrics = await page.evaluate(() => {
    const body = document.body;
    const doc = document.documentElement;
    const overflowX = Math.max(body.scrollWidth, doc.scrollWidth) - Math.max(body.clientWidth, doc.clientWidth);
    const panels = [...document.querySelectorAll(".reader-panel")].length;
    const bodyText = document.body.innerText;
    return {
      overflowX,
      panels,
      hasCredentialCopy: bodyText.includes("保存配置不会保存账号、密码或 token"),
      hasServerFallbackCopy: bodyText.includes("未填写则使用服务端环境变量"),
    };
  });

  await page.close();
  console.error(`[${name}] done`);
  results.push({ name, viewport, screenshot, visible, metrics });
}

await checkViewport("desktop", { width: 1440, height: 1000 });
await checkViewport("mobile", { width: 390, height: 900 });
await browser.close();

console.log(JSON.stringify(results, null, 2));
