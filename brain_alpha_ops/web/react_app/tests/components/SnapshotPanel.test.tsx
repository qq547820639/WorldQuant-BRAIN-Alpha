import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import SnapshotPanel from "@/components/SnapshotPanel";

vi.mock("@/components/ProgressFeedback", () => ({
  default: ({ state, title, error, onRetry, compact }: any) => (
    <div data-testid="progress-feedback" data-state={state} data-compact={compact ? "true" : "false"}>
      <span>{title}</span>
      {error && <span data-testid="progress-error">{error}</span>}
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  ),
}));

vi.mock("@/hooks/useDebounce", () => ({
  useDebounce: (value: string) => value,
}));

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SnapshotPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders cloud snapshot with data", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          total: 2,
          summary: { count: 2, returned_count: 2, submitted_count: 1, passed_unsubmitted_count: 1 },
          alphas: [
            { id: "alpha_1", expression: "rank(close)", family: "momentum", status: "passed", sharpe: 1.5, fitness: 0.8, timestamp: "2024-01-01" },
            { id: "alpha_2", expression: "rank(volume)", family: "volume", status: "failed", sharpe: 0.5, fitness: 0.3, timestamp: "2024-01-02" },
          ],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="cloud" />);

    await waitFor(() => {
      expect(screen.getByText("云端数据")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(screen.getByLabelText("筛选 云端数据")).toBeInTheDocument();
    expect(screen.getByText("缓存总数")).toBeInTheDocument();
  });

  it("renders loading state initially", () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="cloud" />);
    expect(screen.getByTestId("progress-feedback")).toBeInTheDocument();
  });

  it("renders error state", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({ ok: false, error: "加载失败" }, 500);
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const notify = vi.fn();
    render(<SnapshotPanel notify={notify} viewMode="cloud" />);

    await waitFor(() => {
      expect(screen.getByText(/加载 云端数据 失败/)).toBeInTheDocument();
    });
    expect(notify).toHaveBeenCalled();
  });

  it("calls refresh when refresh button clicked", async () => {
    const user = userEvent.setup();
    let callCount = 0;
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/snapshot/cloud")) {
        callCount++;
        return jsonResponse({
          ok: true,
          total: 0,
          summary: { count: 0, returned_count: 0 },
          sample_alphas: [],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="cloud" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    });

    const initialCount = callCount;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(callCount).toBeGreaterThan(initialCount);
  });

  it("renders checkpoint_status view with resume available", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/checkpoint_status") {
        return jsonResponse({
          ok: true,
          resume_available: true,
          history_count: 5,
          checkpoint_count: 3,
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onNavigate = vi.fn();
    render(<SnapshotPanel notify={vi.fn()} viewMode="checkpoint_status" onNavigate={onNavigate} />);

    await waitFor(() => {
      expect(screen.getByText("续跑记录")).toBeInTheDocument();
    });
    expect(screen.getByText("检测到可继续的上次进度")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进入候选管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看质量门禁" })).toBeInTheDocument();
  });

  it("renders checkpoint_status view without resume", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/checkpoint_status") {
        return jsonResponse({
          ok: true,
          resume_available: false,
          history_count: 0,
          checkpoint_count: 0,
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="checkpoint_status" />);

    await waitFor(() => {
      expect(screen.getByText("续跑记录")).toBeInTheDocument();
    });
    expect(screen.getByText("暂无可继续的上次进度")).toBeInTheDocument();
  });

  it("navigates when navigation buttons clicked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/checkpoint_status") {
        return jsonResponse({
          ok: true,
          resume_available: true,
          history_count: 5,
          checkpoint_count: 3,
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onNavigate = vi.fn();
    render(<SnapshotPanel notify={vi.fn()} viewMode="checkpoint_status" onNavigate={onNavigate} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "进入候选管理" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "进入候选管理" }));
    expect(onNavigate).toHaveBeenCalledWith("candidates");

    await user.click(screen.getByRole("button", { name: "查看质量门禁" }));
    expect(onNavigate).toHaveBeenCalledWith("quality_check");
  });

  it("renders research_memory view", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/research_memory")) {
        return jsonResponse({
          ok: true,
          total_candidates: 100,
          families: [{ name: "momentum", count: 50 }],
          fields: [{ name: "close", count: 30 }],
          failure_patterns: [{ reason: "low sharpe", count: 10 }],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="research_memory" />);

    await waitFor(() => {
      expect(screen.getByText("研究记忆")).toBeInTheDocument();
    });
  });

  it("renders lifecycle view", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/lifecycle") {
        return jsonResponse({
          ok: true,
          records: [
            { id: "1", type: "created", timestamp: "2024-01-01", details: "测试" },
          ],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="lifecycle" />);

    await waitFor(() => {
      expect(screen.getByText("生命周期")).toBeInTheDocument();
    });
  });

  it("renders research_knowledge view", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/research_knowledge")) {
        return jsonResponse({
          ok: true,
          rules: [],
          discoveries: [],
          failures: [],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={vi.fn()} viewMode="research_knowledge" />);

    await waitFor(() => {
      expect(screen.getByText("知识库")).toBeInTheDocument();
    });
  });

  it("matches snapshot with cloud view", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          total: 1,
          summary: { count: 1, returned_count: 1 },
          sample_alphas: [
            { id: "alpha_1", expression: "rank(close)", family: "momentum", status: "passed", sharpe: 1.5, fitness: 0.8, timestamp: "2024-01-01" },
          ],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<SnapshotPanel notify={vi.fn()} viewMode="cloud" />);

    await waitFor(() => {
      expect(screen.getByText("云端数据")).toBeInTheDocument();
    });

    expect(container).toMatchSnapshot();
  });
});
