import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { CandidateTableToolbarProps } from "@/components/CandidateTableToolbar";
import { CandidateTableToolbar } from "@/components/CandidateTableToolbar";
import type { Candidate, CandidateListMeta, CandidateQueueView } from "@/types";

vi.mock("@/components/CandidateTableSubComponents", () => ({
  QualitySummaryItem: ({ label, value }: { label: string; value: string }) => (
    <div data-testid={`quality-${label}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  ),
  LifecycleReplayPanel: () => <div data-testid="lifecycle-replay-panel" />,
}));

vi.mock("@/components/CandidateDetailPanel", () => ({
  CandidateDetailPanel: () => <div data-testid="candidate-detail-panel" />,
}));

vi.mock("@/components/ErrorCard", () => ({
  default: ({ title, details, onRetry }: { title: string; details?: string; onRetry?: () => void }) => (
    <div data-testid="error-card" role="alert">
      <p>{title}</p>
      {details && <p>{details}</p>}
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  ),
}));

vi.mock("@/components/Tooltip", () => ({
  default: ({ children, content }: { children: React.ReactNode; content: string }) => (
    <div data-testid="tooltip" title={content}>{children}</div>
  ),
}));

function baseProps(overrides: Partial<CandidateTableToolbarProps> = {}): CandidateTableToolbarProps {
  const candidateMeta: CandidateListMeta = { returned: 10, total: 10 };
  return {
    title: "候选管理",
    viewMode: "candidates" as CandidateQueueView,
    retainedCount: 5,
    targetPoolSize: 10,
    poolEligibleCount: 3,
    rawQueueCount: 10,
    sortedCount: 10,
    candidateMeta,
    filter: "",
    remoteTruncated: false,
    showProductionControls: true,
    candidateWorkflowBusy: false,
    taskState: "idle",
    simState: "idle",
    optimizationState: "idle",
    onTargetPoolSizeChange: vi.fn(),
    onGenerateCandidates: vi.fn(),
    onStartValidationQueue: vi.fn(),
    onStartOptimization: vi.fn(),
    qualitySummary: {
      retained: "5",
      promotable: 3,
      rework: 2,
      blocked: 1,
      outputMode: "标准模式",
    },
    lifecycleHistory: null,
    lifecycleError: null,
    lifecycleLoading: false,
    visibleLifecycleTraces: [],
    detailPanel: {
      showProductionControls: true,
      taskState: "idle",
      taskProgress: null,
      taskError: null,
      taskStreamExhausted: false,
      onRetryTask: vi.fn(),
      simState: "idle",
      simProgress: null,
      simError: null,
      onRetrySim: vi.fn(),
      optimizationState: "idle",
      optimizationProgress: null,
      optimizationError: null,
      onRetryOptimization: vi.fn(),
      checkState: "idle",
      checkProgress: null,
      checkError: null,
      onRetryCheck: vi.fn(),
    },
    loadError: null,
    apiLoading: false,
    onRetryLoad: vi.fn(),
    onFilterChange: vi.fn(),
    showStarredOnly: false,
    onToggleStarFilter: vi.fn(),
    selectedIds: new Set(),
    selectedCount: 0,
    onClearSelection: vi.fn(),
    onBatchScore: vi.fn(),
    onBatchCheck: vi.fn(),
    onBatchSimulate: vi.fn(),
    sortedCandidates: [] as Candidate[],
    ...overrides,
  };
}

describe("CandidateTableToolbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders title and statistics", () => {
    render(<CandidateTableToolbar {...baseProps()} />);
    expect(screen.getByRole("heading", { name: "候选管理" })).toBeInTheDocument();
    expect(screen.getByText(/主池 5\/10/)).toBeInTheDocument();
  });

  it("renders production controls when showProductionControls is true", () => {
    render(<CandidateTableToolbar {...baseProps()} />);
    expect(screen.getByLabelText("目标池容量")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自动推进候选池" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行官方验证队列" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "优化返工队列" })).toBeInTheDocument();
  });

  it("does not render production controls when showProductionControls is false", () => {
    render(<CandidateTableToolbar {...baseProps({ showProductionControls: false })} />);
    expect(screen.queryByLabelText("目标池容量")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "自动推进候选池" })).not.toBeInTheDocument();
  });

  it("calls onGenerateCandidates when auto-advance button clicked", async () => {
    const user = userEvent.setup();
    const onGenerateCandidates = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ onGenerateCandidates })} />);

    await user.click(screen.getByRole("button", { name: "自动推进候选池" }));
    expect(onGenerateCandidates).toHaveBeenCalledTimes(1);
  });

  it("calls onTargetPoolSizeChange when pool size input changes", async () => {
    const user = userEvent.setup();
    const onTargetPoolSizeChange = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ onTargetPoolSizeChange })} />);

    const input = screen.getByLabelText("目标池容量");
    await user.clear(input);
    await user.type(input, "20");
    expect(onTargetPoolSizeChange).toHaveBeenCalled();
  });

  it("renders batch selection bar when candidates are selected", () => {
    render(<CandidateTableToolbar {...baseProps({ selectedCount: 3, selectedIds: new Set(["1", "2", "3"]) })} />);
    expect(screen.getByRole("button", { name: "批量评分" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批量补查" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批量补模拟" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消选择" })).toBeInTheDocument();
  });

  it("does not render batch selection bar when no candidates selected", () => {
    render(<CandidateTableToolbar {...baseProps({ selectedCount: 0 })} />);
    expect(screen.queryByRole("button", { name: "批量评分" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批量补查" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批量补模拟" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "取消选择" })).not.toBeInTheDocument();
  });

  it("calls onBatchScore when batch score button clicked", async () => {
    const user = userEvent.setup();
    const onBatchScore = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ selectedCount: 2, selectedIds: new Set(["1", "2"]), onBatchScore })} />);

    await user.click(screen.getByRole("button", { name: "批量评分" }));
    expect(onBatchScore).toHaveBeenCalledTimes(1);
  });

  it("renders filter input and calls onFilterChange", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ onFilterChange })} />);

    const filterInput = screen.getByLabelText("过滤候选");
    expect(filterInput).toBeInTheDocument();

    await user.type(filterInput, "test");
    expect(onFilterChange).toHaveBeenCalled();
  });

  it("renders refresh button and calls onRetryLoad", async () => {
    const user = userEvent.setup();
    const onRetryLoad = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ onRetryLoad })} />);

    const refreshButton = screen.getByRole("button", { name: "刷新" });
    expect(refreshButton).toBeInTheDocument();

    await user.click(refreshButton);
    expect(onRetryLoad).toHaveBeenCalledTimes(1);
  });

  it("renders star filter toggle when onToggleStarFilter provided", () => {
    const onToggleStarFilter = vi.fn();
    render(<CandidateTableToolbar {...baseProps({ onToggleStarFilter })} />);
    expect(screen.getByRole("button", { name: "仅显示收藏的候选" })).toBeInTheDocument();
  });

  it("toggles star filter state", async () => {
    const user = userEvent.setup();
    const onToggleStarFilter = vi.fn();
    const { rerender } = render(<CandidateTableToolbar {...baseProps({ showStarredOnly: false, onToggleStarFilter })} />);

    const starButton = screen.getByRole("button", { name: "仅显示收藏的候选" });
    await user.click(starButton);
    expect(onToggleStarFilter).toHaveBeenCalledTimes(1);

    rerender(<CandidateTableToolbar {...baseProps({ showStarredOnly: true, onToggleStarFilter })} />);
    expect(screen.getByRole("button", { name: "显示全部候选" })).toBeInTheDocument();
  });

  it("renders export dropdown and toggles it", async () => {
    const user = userEvent.setup();
    const candidates = [
      { alpha_id: "alpha_1", expression: "rank(close)", family: "momentum", status: "passed" },
    ] as unknown as Candidate[];
    render(<CandidateTableToolbar {...baseProps({ sortedCandidates: candidates })} />);

    const exportButton = screen.getByRole("button", { name: "导出 ▾" });
    expect(exportButton).toBeInTheDocument();
    expect(exportButton).toHaveAttribute("aria-expanded", "false");

    await user.click(exportButton);
    expect(screen.getByRole("menu", { name: "导出选项" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "导出为 CSV 格式" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "导出为 JSON 格式" })).toBeInTheDocument();
  });

  it("disables export button when no candidates", () => {
    render(<CandidateTableToolbar {...baseProps({ sortedCandidates: [] })} />);
    const exportButton = screen.getByRole("button", { name: "导出 ▾" });
    expect(exportButton).toBeDisabled();
  });

  it("renders error card when loadError is present", () => {
    render(<CandidateTableToolbar {...baseProps({ loadError: "网络错误" })} />);
    expect(screen.getByTestId("error-card")).toBeInTheDocument();
    expect(screen.getByText("加载候选失败")).toBeInTheDocument();
  });

  it("renders remote truncated warning when remoteTruncated is true", () => {
    const candidateMeta = { returned: 100, total: 500 };
    render(<CandidateTableToolbar {...baseProps({ remoteTruncated: true, candidateMeta })} />);
    expect(screen.getByText(/服务端报告总量为 500 条/)).toBeInTheDocument();
  });

  it("renders quality summary items", () => {
    render(<CandidateTableToolbar {...baseProps()} />);
    expect(screen.getByTestId("quality-主池保留")).toBeInTheDocument();
    expect(screen.getByTestId("quality-可推进")).toBeInTheDocument();
    expect(screen.getByTestId("quality-需优化")).toBeInTheDocument();
    expect(screen.getByTestId("quality-阻断")).toBeInTheDocument();
    expect(screen.getByTestId("quality-输出模式")).toBeInTheDocument();
  });

  it("matches snapshot", () => {
    const { container } = render(<CandidateTableToolbar {...baseProps()} />);
    expect(container).toMatchSnapshot();
  });
});
