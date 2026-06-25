import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import React from "react";
import Dashboard from "@/components/Dashboard";
import { GlobalDataProvider } from "@/hooks/useGlobalData";

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

function renderWithProvider(ui: React.ReactElement) {
  return render(<GlobalDataProvider>{ui}</GlobalDataProvider>);
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
        summary: { count: 100, total: 100, submitted_count: 10, passed_unsubmitted_count: 20, is_stale: false },
        sample_alphas: [],
      });
    }
    if (path.startsWith("/api/snapshot/memory")) {
      return jsonResponse(overrides.memory ?? {
        ok: true,
        total_candidates: 50,
        families: [{ name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 }],
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
      return jsonResponse(overrides.trends ?? { ok: true, data: [] });
    }
    console.warn("Unmocked fetch:", path);
    return jsonResponse({ ok: false, error: "Not mocked" }, 404);
  });
}

describe("Dashboard", () => {
  it("shows loading state on initial render", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    expect(screen.getByText("运行总览")).toBeInTheDocument();
    expect(screen.getByText(/当前阶段：/)).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("shows KPI cards after data loads", async () => {
    const fetchMock = defaultFetchMock({
      status: { ok: true, job_id: "job_1", status: "running", progress: { candidates_generated: 50, backtests_completed: 3, backtests_pending: 2 } },
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
      memory: { ok: true, total_candidates: 1247, families: [{ name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 }], fields: [], failure_patterns: [] },
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    expect(await screen.findByText(/1247/)).toBeInTheDocument();
    expect(screen.getAllByText("25549").length).toBeGreaterThan(0);
  });

  it("shows retry button on error", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: false, error: "Service unavailable" }, 503);
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
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const notify = vi.fn();
    renderWithProvider(<Dashboard notify={notify} connected contextFresh onNavigateToSync={vi.fn()} />);

    const retryBtn = await screen.findByText("重试");
    expect(retryBtn).toBeInTheDocument();
    fireEvent.click(retryBtn);
  });

  it("does not surface raw backend text in dashboard error banners", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") {
        return jsonResponse({ ok: false, error: "raw backend status password=secret" }, 500);
      }
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({ ok: false, error_code: "RAW_BACKEND_CLOUD_ERROR", error: "Traceback csrf_token=secret" }, 500);
      }
      if (path.startsWith("/api/snapshot/memory")) {
        return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    await screen.findByText("仪表盘数据需要关注");
    expect(screen.getAllByText(/请求失败|状态读取失败|BRAIN 官方接口暂时不可用/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/raw backend|Traceback|password=secret|csrf_token=secret|RAW_BACKEND/i)).not.toBeInTheDocument();
  });

  it("describes cloud sync as elapsed progress rather than a countdown", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, summary: { count: 0, total: 0 }, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh={false} onNavigateToSync={vi.fn()} />);

    expect(screen.getByText(/未检测到本地缓存/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /开始首次同步/ })).toBeInTheDocument();
    expect(screen.getByText(/后续刷新改为手动触发/)).toBeInTheDocument();
    expect(screen.queryByText(/倒计时/)).not.toBeInTheDocument();
  });

  it("shows a manual sync entry when local cache is available", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: {
            count: 40852,
            total: 40852,
            submitted_count: 1,
            passed_unsubmitted_count: 2,
            is_stale: true,
          },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const autoStartSync = vi.fn();
    const openManualSync = vi.fn();

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={autoStartSync} onOpenSync={openManualSync} />);

    const manualButton = await screen.findByText("手动同步");
    fireEvent.click(manualButton);

    expect(openManualSync).toHaveBeenCalledTimes(1);
    expect(autoStartSync).not.toHaveBeenCalled();
    expect((await screen.findAllByText("40852")).length).toBeGreaterThan(0);
  });

  it("shows cached dashboard data in cache mode before account connection", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: {
            count: 40852,
            total: 40852,
            submitted_count: 33,
            passed_unsubmitted_count: 532,
            is_stale: false,
          },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 7, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected={false} contextFresh onNavigateToSync={vi.fn()} />);

    expect(await screen.findByText("本地缓存可用，当前为缓存模式")).toBeInTheDocument();
    expect(screen.getAllByText("账户/缓存").length).toBeGreaterThan(0);
    expect(screen.getByText("检测到本地缓存，可先以缓存模式继续")).toBeInTheDocument();
    expect(screen.getByText(/手动同步、官方回测和提交前复核需要先测试 BRAIN 连接/)).toBeInTheDocument();
    expect((await screen.findAllByText("40852")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "手动同步" })).not.toBeInTheDocument();
  });

  it("dismisses the getting started guide when close button clicked", async () => {
    const user = userEvent.setup();
    localStorage.removeItem("brain_alpha_guide_dismissed");
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, summary: { count: 0, total: 0 }, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    const closeButton = await screen.findByLabelText("关闭引导");
    expect(closeButton).toBeInTheDocument();

    await user.click(closeButton);
    expect(localStorage.getItem("brain_alpha_guide_dismissed")).toBe("1");
  });

  it("shows guide again after re-show button clicked", async () => {
    const user = userEvent.setup();
    localStorage.setItem("brain_alpha_guide_dismissed", "1");
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, summary: { count: 0, total: 0 }, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    const reshowButton = await screen.findByLabelText("重新显示首次使用引导");
    expect(reshowButton).toBeInTheDocument();

    await user.click(reshowButton);
    expect(localStorage.getItem("brain_alpha_guide_dismissed")).toBeNull();
    expect(screen.getByText(/首次使用？按顺序完成以下步骤/)).toBeInTheDocument();
  });

  it("expands and collapses snapshot panel", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: { count: 100, total: 100, submitted_count: 10, passed_unsubmitted_count: 20, is_stale: false },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 50, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    await screen.findByText("运行总览");

    const expandButton = screen.getByRole("button", { name: /数据快照/ });
    expect(expandButton).toHaveAttribute("aria-expanded", "false");

    await user.click(expandButton);
    expect(expandButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("热门家族")).toBeInTheDocument();
    expect(screen.getByText("热门字段")).toBeInTheDocument();
    expect(screen.getByText("失败模式")).toBeInTheDocument();

    await user.click(expandButton);
    expect(expandButton).toHaveAttribute("aria-expanded", "false");
  });

  it("opens report modal when generate report button clicked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle", progress: { candidates_generated: 50, backtests_completed: 10 } });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: { count: 100, total: 100, submitted_count: 10, passed_unsubmitted_count: 20, is_stale: false },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 50, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    const reportButton = await screen.findByText("📋 生成报告");
    expect(reportButton).toBeInTheDocument();

    await user.click(reportButton);
    expect(screen.getByRole("dialog", { name: /工作日报/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制为 Markdown" })).toBeInTheDocument();
  });

  it("shows step progress bar with correct step", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, summary: { count: 0, total: 0 }, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    await screen.findByText("运行总览");
    expect(screen.getByText(/当前阶段：/)).toBeInTheDocument();
  });

  it("shows phase loading state correctly", async () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh phaseStatus="loading" onNavigateToSync={vi.fn()} />);

    expect(screen.getByText("正在读取本地状态")).toBeInTheDocument();
    expect(screen.getByText(/正在确认本地 session/)).toBeInTheDocument();
  });

  it("shows phase error state correctly", async () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh phaseStatus="error" onNavigateToSync={vi.fn()} />);

    expect(screen.getAllByText("状态读取失败").length).toBeGreaterThan(0);
    expect(screen.getByText(/暂时无法确认账户连接/)).toBeInTheDocument();
  });

  it("matches snapshot with data loaded", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, status: "idle" });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          summary: { count: 100, total: 100, submitted_count: 10, passed_unsubmitted_count: 20, is_stale: false },
          sample_alphas: [],
        });
      }
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 50, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("brain_alpha_guide_dismissed", "1");

    const { container } = renderWithProvider(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    await screen.findByText("运行总览");
    expect(container).toMatchSnapshot();
  });
});
