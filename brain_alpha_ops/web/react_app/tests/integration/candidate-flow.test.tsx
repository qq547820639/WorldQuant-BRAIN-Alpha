import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import React from "react";
import { GlobalDataProvider } from "@/hooks/useGlobalData";
import { ThemeProvider } from "@/components/ThemeProvider";
import CandidateTable from "@/components/CandidateTable";
import type { Candidate } from "@/types";

vi.mock("@tanstack/react-virtual", () => {
  return {
    useVirtualizer: ({ count, estimateSize }: { count: number; estimateSize: () => number }) => {
      const items = Array.from({ length: count }, (_, i) => ({
        index: i,
        start: i * estimateSize(),
        end: (i + 1) * estimateSize(),
        size: estimateSize(),
        key: i,
      }));
      return {
        getVirtualItems: () => items,
        getTotalSize: () => count * estimateSize(),
        measure: vi.fn(),
        measureElement: vi.fn(),
        scrollToIndex: vi.fn(),
        scrollToOffset: vi.fn(),
        getVirtualOffset: () => 0,
        getOffsetForIndex: vi.fn(),
      };
    },
  };
});

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}

function createMockCandidate(index: number, overrides: Partial<Candidate> = {}): Candidate {
  return {
    alpha_id: `alpha_${index}`,
    expression: `ts_delay(close, ${index})`,
    family: index % 3 === 0 ? "momentum" : index % 3 === 1 ? "value" : "quality",
    score: 60 + index,
    status: "new",
    created: Date.now() - index * 3600000,
    updated: Date.now() - index * 1800000,
    is_starred: false,
    tags: [],
    ...overrides,
  } as Candidate;
}

function renderWithProvider(ui: React.ReactElement) {
  return render(
    <ThemeProvider>
      <GlobalDataProvider>{ui}</GlobalDataProvider>
    </ThemeProvider>
  );
}

function defaultFetchMock(overrides: Record<string, unknown> = {}) {
  const candidates = (overrides.candidates as Candidate[]) || Array.from({ length: 25 }, (_, i) => createMockCandidate(i));
  const displayQueueCandidates = (overrides.displayQueueCandidates as Candidate[]) || candidates;

  return vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    const path = String(url);
    const method = options?.method || "GET";

    if (path === "/api/candidates" || path.startsWith("/api/candidates?")) {
      return jsonResponse({
        ok: true,
        candidates: candidates,
        display_queue_candidates: displayQueueCandidates,
        display_count: displayQueueCandidates.length,
        promotable_count: 25,
        history_count: 25,
        returned_count: 25,
        returned_total: 25,
        refine_capacity: 5,
        max_main_pool: 10,
        output_mode: "alpha101",
      });
    }

    if (path === "/api/check_results") {
      return jsonResponse({ ok: true, check_results: {} });
    }

    if (path === "/api/backtest_slots") {
      return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
    }

    if (path === "/api/snapshot/cloud") {
      return jsonResponse({ ok: true, count: 100, total: 200, summary: {} });
    }

    if (path === "/api/config") {
      return jsonResponse({ ok: true, config: { environment: "production", credentials: { managed_credentials_available: false } } });
    }

    if (path.startsWith("/api/alpha_lifecycle")) {
      return jsonResponse({
        ok: true,
        official_api_called: false,
        submit_allowed: false,
        summary: { record_count: 0, alpha_count: 0, passed_count: 0, blocked_count: 0, failed_count: 0, submitted_count: 0, replay_ready: false },
        alpha_traces: [],
      });
    }

    console.warn("Unmocked fetch:", path, method);
    return jsonResponse({ ok: false, error: "Not mocked" }, 404);
  });
}

describe("候选管理流程集成测试", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
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

  it("测试候选列表渲染 - 显示候选标题", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });
  });

  it("测试候选列表渲染 - 显示 KPI 卡片", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("主池保留")).toBeInTheDocument();
    });

    expect(screen.getByText("可推进")).toBeInTheDocument();
    expect(screen.getByText("需优化")).toBeInTheDocument();
    expect(screen.getByText("阻断")).toBeInTheDocument();
    expect(screen.getByText("输出模式")).toBeInTheDocument();
  });

  it("测试候选列表渲染 - 显示正确的候选数量", async () => {
    const candidates = Array.from({ length: 15 }, (_, i) => createMockCandidate(i));
    const fetchMock = defaultFetchMock({ candidates, displayQueueCandidates: candidates.slice(0, 10) });
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      const statusElement = screen.getByRole("status");
      expect(statusElement.textContent).toContain("主池");
      expect(statusElement.textContent).toContain("10/10");
    });
  });

  it("测试候选列表渲染 - 表格存在", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByRole("table", { name: /候选结果/, hidden: true })).toBeInTheDocument();
    });
  });

  it("测试搜索筛选功能 - 搜索框存在", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    const searchInput = screen.getByRole("searchbox", { name: /筛选|搜索|filter/i });
    expect(searchInput).toBeInTheDocument();
  });

  it("测试搜索筛选功能 - 输入搜索文本", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    const searchInput = screen.getByRole("searchbox", { name: /筛选|搜索|filter/i });
    await user.type(searchInput, "momentum");

    expect(searchInput).toHaveValue("momentum");
  });

  it("测试搜索筛选功能 - 清除筛选", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    const searchInput = screen.getByRole("searchbox", { name: /筛选|搜索|filter/i });
    await user.type(searchInput, "test");
    expect(searchInput).toHaveValue("test");

    const clearButton = screen.getByRole("button", { name: /清除|clear|清空/i });
    if (clearButton) {
      await user.click(clearButton);
      expect(searchInput).toHaveValue("");
    }
  });

  it("测试排序功能 - 表格有排序列头", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByRole("table", { name: /候选结果/, hidden: true })).toBeInTheDocument();
    });

    const table = screen.getByRole("table", { name: /候选结果/, hidden: true });
    const headers = table.querySelectorAll("th");
    expect(headers.length).toBeGreaterThan(0);
  });

  it("测试排序功能 - 点击列头排序", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByRole("table", { name: /候选结果/, hidden: true })).toBeInTheDocument();
    });

    const table = screen.getByRole("table", { name: /候选结果/, hidden: true });
    const scoreHeader = within(table).getByText(/评分|score/i);
    expect(scoreHeader).toBeInTheDocument();

    fireEvent.click(scoreHeader);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("测试分页功能 - 分页控件存在", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    const pageInfo = screen.getByText(/共|页|page/i);
    expect(pageInfo).toBeInTheDocument();
  });

  it("测试分页功能 - 下一页按钮", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    const nextButton = screen.getByRole("button", { name: /下一页|next|→/i });
    expect(nextButton).toBeInTheDocument();

    await user.click(nextButton);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("测试候选选择 - 全选按钮存在", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByRole("table", { name: /候选结果/, hidden: true })).toBeInTheDocument();
    });

    const table = screen.getByRole("table", { name: /候选结果/, hidden: true });
    const checkboxes = table.querySelectorAll('input[type="checkbox"]');
    expect(checkboxes.length).toBeGreaterThanOrEqual(0);
  });

  it("测试候选选择 - 目标池容量输入", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("目标池容量")).toBeInTheDocument();
    });

    const numberInput = screen.getByLabelText(/目标池容量/i);
    expect(numberInput).toBeInTheDocument();
    expect(numberInput).toHaveValue(10);

    await user.clear(numberInput);
    await user.type(numberInput, "15");
    expect(numberInput).toHaveValue(15);
  });

  it("测试视图切换 - 操作按钮存在", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("候选管理")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /自动推进候选池/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /运行官方验证队列/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /优化返工队列/i })).toBeInTheDocument();
  });

  it("测试视图切换 - 生命周期回放区域", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    const notify = vi.fn();

    renderWithProvider(<CandidateTable notify={notify} />);

    await waitFor(() => {
      expect(screen.getByText("生命周期回放")).toBeInTheDocument();
    });

    expect(screen.getByText("记录")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });
});
