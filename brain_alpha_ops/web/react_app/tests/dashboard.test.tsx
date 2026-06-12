import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "@/components/Dashboard";

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

describe("Dashboard", () => {
  it("shows loading state on initial render", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    // Loading: title visible, data shows placeholder "--"
    expect(screen.getByText("运行总览")).toBeInTheDocument();
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);

    vi.useRealTimers();
  });

  it("shows KPI cards after data loads", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, job_id: "job_1", status: "running", progress: { candidates_generated: 50, backtests_completed: 3, backtests_pending: 2 } });
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
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
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 1247, families: [{ name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 }], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

    expect(await screen.findByText("1247")).toBeInTheDocument();
    // Cloud count appears in both KPI card and panel header
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
    render(<Dashboard notify={notify} connected contextFresh onNavigateToSync={vi.fn()} />);

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

    render(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={vi.fn()} />);

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

    render(<Dashboard notify={vi.fn()} connected contextFresh={false} onNavigateToSync={vi.fn()} />);

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

    render(<Dashboard notify={vi.fn()} connected contextFresh onNavigateToSync={autoStartSync} onOpenSync={openManualSync} />);

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

    render(<Dashboard notify={vi.fn()} connected={false} contextFresh onNavigateToSync={vi.fn()} />);

    expect(await screen.findByText("本地缓存可用，当前为缓存模式")).toBeInTheDocument();
    expect(screen.getAllByText("账户/缓存").length).toBeGreaterThan(0);
    expect(screen.getByText("检测到本地缓存，可先以缓存模式继续")).toBeInTheDocument();
    expect(screen.getByText(/手动同步、官方回测和提交前复核需要先测试 BRAIN 连接/)).toBeInTheDocument();
    expect((await screen.findAllByText("40852")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "手动同步" })).not.toBeInTheDocument();
  });
});
