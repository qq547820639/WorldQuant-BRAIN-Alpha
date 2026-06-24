import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ScoringPanel from "@/components/ScoringPanel";
import type { Candidate } from "@/types";

vi.mock("@/components/ProgressFeedback", () => ({
  default: ({ state, title, error, onRetry, compact }: any) => (
    <div data-testid="progress-feedback" data-state={state} data-compact={compact ? "true" : "false"}>
      <span>{title}</span>
      {error && <span data-testid="progress-error">{error}</span>}
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  ),
}));

vi.mock("@/components/Skeleton", () => ({
  default: ({ variant }: any) => <div data-testid={`skeleton-${variant || "default"}`} />,
}));

vi.mock("@/components/ErrorCard", () => ({
  default: ({ title, details, onRetry }: any) => (
    <div data-testid="error-card" role="alert">
      <p>{title}</p>
      {details && <p>{details}</p>}
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  ),
}));

vi.mock("@/components/EmptyState", () => ({
  default: ({ title, description }: any) => (
    <div data-testid="empty-state" role="status">
      <h3>{title}</h3>
      {description && <p>{description}</p>}
    </div>
  ),
}));

vi.mock("@/components/ScoringPanel/Header", () => ({
  default: ({ candidate, scoring, onRetry }: any) => (
    <div data-testid="scoring-header">
      <span>Scoring Header</span>
      {onRetry && <button type="button" onClick={onRetry}>重新评分</button>}
    </div>
  ),
}));

vi.mock("@/components/ScoringPanel/GateResults", () => ({
  default: ({ hardGates, softGates }: any) => (
    <div data-testid="gate-results">
      <span>Hard Gates: {hardGates?.length || 0}</span>
      <span>Soft Gates: {softGates?.length || 0}</span>
    </div>
  ),
}));

vi.mock("@/components/ScoringPanel/ImprovementHints", () => ({
  default: ({ failures, hints }: any) => (
    <div data-testid="improvement-hints">
      <span>Failures: {failures?.length || 0}</span>
      <span>Hints: {hints?.length || 0}</span>
    </div>
  ),
}));

vi.mock("@/hooks/useSSE", () => ({
  useSSE: vi.fn(),
}));

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    alpha_id: "alpha_test_001",
    expression: "rank(close)",
    family: "momentum",
    status: "passed",
    scorecard: {
      total_score: 75.5,
      sharpe: 1.5,
      fitness: 0.8,
      turnover: 0.3,
      decision_band: "A",
      attribution_tree: null,
    },
    ...overrides,
  } as unknown as Candidate;
}

describe("ScoringPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no candidate provided", () => {
    render(<ScoringPanel notify={vi.fn()} candidate={null} />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("选择候选")).toBeInTheDocument();
  });

  it("renders candidate info when candidate provided", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/scoring/evaluate") {
        return jsonResponse({ ok: true, job_id: "job_1", task_id: "task_1" });
      }
      if (path === "/api/scoring/attribution") {
        return jsonResponse({ ok: true, attribution: null, hard_gates: [], soft_gates: [] });
      }
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({ ok: true, records: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ScoringPanel notify={vi.fn()} candidate={mockCandidate()} />);

    await waitFor(() => {
      expect(screen.getByText("科学评分")).toBeInTheDocument();
    });
    expect(screen.getByText(/alpha_test_001/)).toBeInTheDocument();
  });

  it("renders scoring header with cached scorecard", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({ ok: true, records: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const candidate = mockCandidate({
      scorecard: {
        total_score: 85.0,
        sharpe: 2.0,
        fitness: 0.9,
        turnover: 0.25,
        decision_band: "A",
        attribution_tree: { layers: [] },
        prior_score: 30,
        empirical_score: 40,
        checklist_score: 15,
        hard_gates: [],
        top_failures: [],
        improvement_hints: [],
      } as any,
    });

    render(<ScoringPanel notify={vi.fn()} candidate={candidate} />);

    await waitFor(() => {
      expect(screen.getByTestId("scoring-header")).toBeInTheDocument();
    });
    expect(screen.getByTestId("gate-results")).toBeInTheDocument();
    expect(screen.getByTestId("improvement-hints")).toBeInTheDocument();
  });

  it("shows error state when scoring API fails", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/scoring/evaluate") {
        return jsonResponse({ ok: false, error: "评分服务不可用" }, 500);
      }
      if (path === "/api/scoring/attribution") {
        return jsonResponse({ ok: false, error: "归因服务不可用" }, 500);
      }
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({ ok: true, records: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const notify = vi.fn();
    const candidate = mockCandidate({ scorecard: undefined } as any);
    render(<ScoringPanel notify={notify} candidate={candidate} />);

    await waitFor(() => {
      expect(screen.getByTestId("error-card")).toBeInTheDocument();
    });
    expect(notify).toHaveBeenCalled();
  });

  it("renders score history when available", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({
          ok: true,
          records: [
            { timestamp: "2024-01-01T00:00:00Z", total_score: 70 },
            { timestamp: "2024-01-02T00:00:00Z", total_score: 75 },
            { timestamp: "2024-01-03T00:00:00Z", total_score: 80 },
          ],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const candidate = mockCandidate({
      scorecard: {
        total_score: 80,
        sharpe: 1.8,
        fitness: 0.85,
        turnover: 0.3,
        decision_band: "A",
        attribution_tree: null,
      } as any,
    });

    render(<ScoringPanel notify={vi.fn()} candidate={candidate} />);

    await waitFor(() => {
      expect(screen.getByText(/评分历史/)).toBeInTheDocument();
    });
  });

  it("toggles score history expansion", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({
          ok: true,
          records: [
            { timestamp: "2024-01-01T00:00:00Z", total_score: 70 },
            { timestamp: "2024-01-02T00:00:00Z", total_score: 75 },
            { timestamp: "2024-01-03T00:00:00Z", total_score: 80 },
          ],
        });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const candidate = mockCandidate({
      scorecard: {
        total_score: 80,
        sharpe: 1.8,
        fitness: 0.85,
        turnover: 0.3,
        decision_band: "A",
        attribution_tree: null,
      } as any,
    });

    render(<ScoringPanel notify={vi.fn()} candidate={candidate} />);

    await waitFor(() => {
      expect(screen.getByText(/评分历史/)).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole("button", { name: /评分历史/ });
    expect(toggleButton).toHaveAttribute("aria-expanded", "false");

    await user.click(toggleButton);
    expect(toggleButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "评分历史详情" })).toBeInTheDocument();
  });

  it("matches snapshot with candidate", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/alpha_lifecycle")) {
        return jsonResponse({ ok: true, records: [] });
      }
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const candidate = mockCandidate({
      scorecard: {
        total_score: 85.0,
        sharpe: 2.0,
        fitness: 0.9,
        turnover: 0.25,
        decision_band: "A",
        attribution_tree: { layers: [] },
        prior_score: 30,
        empirical_score: 40,
        checklist_score: 15,
        hard_gates: [],
        top_failures: [],
        improvement_hints: [],
      } as any,
    });

    const { container } = render(<ScoringPanel notify={vi.fn()} candidate={candidate} />);

    await waitFor(() => {
      expect(screen.getByTestId("scoring-header")).toBeInTheDocument();
    });

    expect(container).toMatchSnapshot();
  });
});
