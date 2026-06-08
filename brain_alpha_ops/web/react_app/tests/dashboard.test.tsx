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

    render(<Dashboard notify={vi.fn()} />);

    // Loading: title visible, data shows placeholder "--"
    expect(screen.getByText("运行总览")).toBeInTheDocument();
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);

    vi.useRealTimers();
  });

  it("shows KPI cards after data loads", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: true, job_id: "job_1", status: "running", progress: { candidates_generated: 50, backtests_completed: 3, backtests_pending: 2 } });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 25549, submitted_count: 3847, passed_unsubmitted_count: 2156, is_stale: false, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 1247, families: [{ name: "momentum", count: 320, success_rate: 0.72, avg_score: 75, avg_sharpe: 1.5 }], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard notify={vi.fn()} />);

    expect(await screen.findByText("1247")).toBeInTheDocument();
    // Cloud count appears in both KPI card and panel header
    expect(screen.getAllByText("25549").length).toBeGreaterThan(0);
  });

  it("shows retry button on error", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/production-validation/status") return jsonResponse({ ok: false, error: "Service unavailable" }, 503);
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 0, submitted_count: 0, passed_unsubmitted_count: 0, is_stale: true, sample_alphas: [] });
      if (path.startsWith("/api/snapshot/memory")) return jsonResponse({ ok: true, total_candidates: 0, families: [], fields: [], failure_patterns: [] });
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const notify = vi.fn();
    render(<Dashboard notify={notify} />);

    const retryBtn = await screen.findByText("重试");
    expect(retryBtn).toBeInTheDocument();
    fireEvent.click(retryBtn);
  });
});
