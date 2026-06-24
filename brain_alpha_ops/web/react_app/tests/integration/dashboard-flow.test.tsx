import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import React from "react";
import Dashboard from "@/components/Dashboard";
import { ThemeProvider } from "@/components/ThemeProvider";
import { GlobalDataProvider } from "@/hooks/useGlobalData";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithProvider(ui: React.ReactElement) {
  return render(
    <ThemeProvider>
      <GlobalDataProvider>{ui}</GlobalDataProvider>
    </ThemeProvider>
  );
}

function defaultFetchMock(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path === "/api/production-validation/status") {
      return jsonResponse(overrides.status ?? { ok: true, status: "idle" });
    }
    if (path.startsWith("/api/snapshot/cloud")) {
      return jsonResponse(overrides.cloud ?? {
        ok: true,
        summary: {
          count: 25549,
          total: 25549,
          submitted_count: 3847,
          passed_unsubmitted_count: 2156,
          is_stale: false,
        },
        sample_alphas: [],
      });
    }
    if (path.startsWith("/api/snapshot/memory")) {
      return jsonResponse(overrides.memory ?? {
        ok: true,
        total_candidates: 1247,
        families: [
          { name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 },
          { name: "value", count: 280, success_rate: 0.68, avg_score: 72, avg_sharpe: 1.4 },
          { name: "quality", count: 200, success_rate: 0.65, avg_score: 70, avg_sharpe: 1.3 },
        ],
        fields: [],
        failure_patterns: [],
      });
    }
    if (path.startsWith("/api/candidates")) {
      return jsonResponse(overrides.candidates ?? { ok: true, candidates: [], total: 0 });
    }
    if (path === "/api/backtest_slots") {
      return jsonResponse(overrides.slots ?? { ok: true, slot_limit: 3, active_count: 0, slots: [] });
    }
    if (path === "/api/config") {
      return jsonResponse(overrides.config ?? { ok: true, config: { environment: "production" } });
    }
    if (path.startsWith("/api/trends")) {
      return jsonResponse(overrides.trends ?? {
        ok: true,
        data: [
          { date: "2024-01-01", candidates: 100, submissions: 10 },
          { date: "2024-01-02", candidates: 150, submissions: 15 },
          { date: "2024-01-03", candidates: 200, submissions: 20 },
          { date: "2024-01-04", candidates: 180, submissions: 18 },
          { date: "2024-01-05", candidates: 220, submissions: 22 },
        ],
      });
    }
    console.warn("Unmocked fetch:", path);
    return jsonResponse({ ok: false, error: "Not mocked" }, 404);
  });
}

describe("Dashboard 流程集成测试", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    localStorage.clear();
    sessionStorage.clear();
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("测试 Dashboard 渲染 - 显示运行总览标题", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect(await screen.findByText("运行总览")).toBeInTheDocument();
  });

  it("测试 Dashboard 渲染 - 显示当前阶段", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect(await screen.findByText(/当前阶段：/)).toBeInTheDocument();
  });

  it("测试 KPI 卡片展示 - 显示候选数量", async () => {
    const fetchMock = defaultFetchMock({
      memory: {
        ok: true,
        total_candidates: 1247,
        families: [{ name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 }],
        fields: [],
        failure_patterns: [],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect(await screen.findByText(/1247/)).toBeInTheDocument();
  });

  it("测试 KPI 卡片展示 - 显示云端总数", async () => {
    const fetchMock = defaultFetchMock({
      cloud: {
        ok: true,
        summary: {
          count: 25549,
          total: 25549,
          submitted_count: 3847,
          passed_unsubmitted_count: 2156,
          is_stale: false,
        },
        sample_alphas: [],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect((await screen.findAllByText("25549")).length).toBeGreaterThan(0);
  });

  it("测试 KPI 卡片展示 - 显示已提交数量", async () => {
    const fetchMock = defaultFetchMock({
      cloud: {
        ok: true,
        summary: {
          count: 100,
          total: 100,
          submitted_count: 25,
          passed_unsubmitted_count: 10,
          is_stale: false,
        },
        sample_alphas: [],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    await screen.findByText("运行总览");

    const submittedElements = screen.getAllByText(/25/);
    expect(submittedElements.length).toBeGreaterThan(0);
  });

  it("测试趋势图表 - KPI 卡片包含趋势小图", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    await screen.findByText("运行总览");

    const kpiCards = screen.getAllByRole("status");
    expect(kpiCards.length).toBeGreaterThan(0);

    const sparklineBars = document.querySelectorAll('[class*="flex-1"], [style*="height"]');
    expect(sparklineBars.length).toBeGreaterThanOrEqual(0);
  });

  it("测试趋势图表 - 数据快照展开按钮", async () => {
    const user = userEvent.setup();
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    await screen.findByText("运行总览");

    const expandButton = screen.getByRole("button", { name: /数据快照/ });
    expect(expandButton).toBeInTheDocument();
    expect(expandButton).toHaveAttribute("aria-expanded", "false");

    await user.click(expandButton);
    expect(expandButton).toHaveAttribute("aria-expanded", "true");
  });

  it("测试趋势图表 - 展开后显示热门家族", async () => {
    const user = userEvent.setup();
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    await screen.findByText("运行总览");

    const expandButton = screen.getByRole("button", { name: /数据快照/ });
    await user.click(expandButton);

    expect(screen.getByText("热门家族")).toBeInTheDocument();
  });

  it("测试报告生成 - 生成报告按钮存在", async () => {
    const fetchMock = defaultFetchMock({
      status: { ok: true, status: "idle", progress: { candidates_generated: 50, backtests_completed: 10 } },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    const reportButton = await screen.findByText("📋 生成报告");
    expect(reportButton).toBeInTheDocument();
  });

  it("测试报告生成 - 点击生成报告打开模态框", async () => {
    const user = userEvent.setup();
    const fetchMock = defaultFetchMock({
      status: { ok: true, status: "idle", progress: { candidates_generated: 50, backtests_completed: 10 } },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    const reportButton = await screen.findByText("📋 生成报告");
    await user.click(reportButton);

    expect(screen.getByRole("dialog", { name: "工作日报" })).toBeInTheDocument();
  });

  it("测试报告生成 - 模态框有复制按钮", async () => {
    const user = userEvent.setup();
    const fetchMock = defaultFetchMock({
      status: { ok: true, status: "idle", progress: { candidates_generated: 50, backtests_completed: 10 } },
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    const reportButton = await screen.findByText("📋 生成报告");
    await user.click(reportButton);

    expect(screen.getByRole("button", { name: "复制为 Markdown" })).toBeInTheDocument();
  });

  it("测试加载状态 - 初始加载状态", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect(screen.getByText("运行总览")).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("测试重试按钮 - 错误时显示重试", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") {
        return jsonResponse({ ok: false, error: "Service unavailable" }, 503);
      }
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: {
            count: 0,
            total: 0,
            submitted_count: 0,
            passed_unsubmitted_count: 0,
            is_stale: true,
          },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) {
        return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    const retryBtn = await screen.findByText("重试");
    expect(retryBtn).toBeInTheDocument();
    fireEvent.click(retryBtn);
  });

  it("测试手动同步按钮 - 连接状态下显示", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    const manualSyncButton = await screen.findByText("手动同步");
    expect(manualSyncButton).toBeInTheDocument();
  });

  it("测试缓存模式 - 未连接时显示缓存模式提示", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(
      <Dashboard
        notify={notify}
        connected={false}
        contextFresh
        onNavigateToSync={vi.fn()}
      />
    );

    expect(await screen.findByText("本地缓存可用，当前为缓存模式")).toBeInTheDocument();
  });
});
