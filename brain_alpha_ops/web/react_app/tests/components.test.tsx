import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CandidateTable from "@/components/CandidateTable";
import ConfigPanel from "@/components/ConfigPanel";
import SnapshotPanel from "@/components/SnapshotPanel";

describe("ConfigPanel", () => {
  it("validates editable fields and posts the saved config payload", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/config" && options?.method === "POST") {
        return jsonResponse({ ok: true, config: baseConfig("fundamental6") });
      }
      if (path === "/api/config") {
        return jsonResponse({ ok: true, config: baseConfig("analyst4") });
      }
      if (path === "/api/config_schema") {
        return jsonResponse({
          ok: true,
          schema: {
            settings_options: {
              region: ["USA"],
              universe: ["TOP3000"],
              delay: [0, 1],
              neutralization: ["SUBINDUSTRY"],
            },
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanel notify={notify} />);

    await screen.findByRole("heading", { name: "Configuration" });
    const dataset = screen.getByLabelText("Dataset");
    const save = screen.getByRole("button", { name: "Save" });

    fireEvent.change(dataset, { target: { value: "bad value!" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dataset may only contain letters, numbers, underscore, dash, dot, or colon.",
    );
    expect(save).toBeDisabled();

    fireEvent.change(dataset, { target: { value: "fundamental6" } });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/config",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const saveCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/config" && options?.method === "POST"
    ));
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
      settings: { dataset: "fundamental6", region: "USA", universe: "TOP3000" },
      candidates: 20,
      cycles: 10,
    });
    expect(notify).toHaveBeenCalledWith("success", "Configuration saved");
  });
});

describe("CandidateTable", () => {
  it("filters candidates, clamps generate count, and posts the requested count", async () => {
    const notify = vi.fn();
    const onScore = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) {
        return jsonResponse({
          ok: true,
          candidates: [
            candidate({ alpha_id: "alpha_rank", expression: "rank(close)", score: 88 }),
            candidate({ alpha_id: "alpha_decay", expression: "decay_linear(volume, 5)", score: 72 }),
          ],
        });
      }
      if (path === "/api/generate_candidates" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_7" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CandidateTable notify={notify} onScore={onScore} />);

    await screen.findByText("rank(close)");
    fireEvent.change(screen.getByLabelText("Filter candidates"), { target: { value: "decay" } });

    expect(await screen.findByText("decay_linear(volume, 5)")).toBeInTheDocument();
    expect(screen.queryByText("rank(close)")).not.toBeInTheDocument();

    const count = screen.getByLabelText("Count");
    fireEvent.change(count, { target: { value: "1010" } });
    expect(count).toHaveValue(100);

    fireEvent.change(count, { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/generate_candidates",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const generateCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/generate_candidates" && options?.method === "POST"
    ));
    expect(JSON.parse(String(generateCall?.[1]?.body))).toEqual({ count: 7 });
    expect(notify).toHaveBeenCalledWith("info", "Candidate generation started: job_7");

    const table = screen.getByRole("table", { name: "Candidate results" });
    fireEvent.click(within(table).getByRole("button", { name: "Score alpha_decay" }));
    expect(onScore).toHaveBeenCalledWith(expect.objectContaining({ alpha_id: "alpha_decay" }));
  });

  it("renders submission queue filters from candidates and check results", async () => {
    const notify = vi.fn();
    const rows = [
      candidate({ alpha_id: "alpha_passed", expression: "passed_expr", score: 88, lifecycle_status: "submission_ready", gate: { passed: true, submission_ready: true } }),
      candidate({ alpha_id: "alpha_stale", expression: "stale_expr", score: 80, lifecycle_status: "submission_ready", gate: { passed: true, submission_ready: true } }),
      candidate({ alpha_id: "alpha_submitted", expression: "submitted_expr", score: 76, lifecycle_status: "submitted" }),
      candidate({ alpha_id: "alpha_failed", expression: "failed_expr", score: 12, lifecycle_status: "blocked" }),
    ];
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) {
        return jsonResponse({ ok: true, candidates: rows });
      }
      if (path === "/api/check_results") {
        return jsonResponse({
          ok: true,
          items: [
            { alpha_id: "alpha_passed", passed: true, submittable: true, is_stale: false },
            { alpha_id: "alpha_stale", passed: true, submittable: true, is_stale: true },
          ],
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<CandidateTable notify={notify} viewMode="passed" />);
    await screen.findByRole("heading", { name: "Passed candidates" });
    expect(await screen.findByText("passed_expr")).toBeInTheDocument();
    expect(screen.queryByText("submitted_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="submittable" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/check_results", expect.any(Object)));
    expect(await screen.findByText("passed_expr")).toBeInTheDocument();
    expect(screen.queryByText("stale_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="submitted" />);
    expect(await screen.findByText("submitted_expr")).toBeInTheDocument();
    expect(screen.queryByText("failed_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="failed" />);
    expect(await screen.findByText("failed_expr")).toBeInTheDocument();
    expect(screen.queryByText("passed_expr")).not.toBeInTheDocument();
  });
});

describe("SnapshotPanel", () => {
  it("loads cloud snapshot rows and refreshes the data view", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/snapshot/cloud")) {
        return jsonResponse({
          ok: true,
          alphas: [
            {
              alpha_id: "ALPHA_CLOUD_1",
              status: "ACTIVE",
              pass_fail: "PASS",
              sharpe: 1.25,
              fitness: 1.08,
              turnover: 0.19,
              expression: "rank(close)",
            },
          ],
          summary: {
            returned_count: 1,
            submitted_count: 1,
            passed_unsubmitted_count: 0,
            is_stale: false,
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={notify} viewMode="cloud" />);

    expect(await screen.findByText("ALPHA_CLOUD_1")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Cloud data rows" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });
});

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

function baseConfig(dataset: string) {
  return {
    environment: "production",
    auto_submit: false,
    ops: {
      settings: {
        region: "USA",
        universe: "TOP3000",
        delay: 1,
        decay: 10,
        neutralization: "SUBINDUSTRY",
        dataset,
      },
      budget: {
        max_candidates_per_cycle: 20,
        max_cycles: 10,
        retained_alpha_pool_size: 30,
        official_backtest_batch_size: 3,
        require_cloud_sync: true,
      },
      thresholds: {
        min_sharpe: 1.25,
        min_fitness: 1,
        min_turnover: 0.01,
        platform_max_turnover: 0.7,
        max_self_correlation: 0.7,
        max_weight_concentration: 0.1,
      },
      scoring: {
        prior_layer_weight: 0.3,
        empirical_layer_weight: 0.45,
        checklist_layer_weight: 0.25,
        market_regime: "production",
      },
    },
  };
}

function candidate({
  alpha_id,
  expression,
  score,
  lifecycle_status = "completed",
  gate = { passed: false },
}: {
  alpha_id: string;
  expression: string;
  score: number;
  lifecycle_status?: string;
  gate?: Record<string, unknown>;
}) {
  return {
    alpha_id,
    expression,
    family: "momentum",
    hypothesis: "Test candidate",
    lifecycle_status,
    scorecard: {
      total_score: score,
      prior_score: 20,
      empirical_score: 40,
      checklist_score: 20,
      decision_band: "promote",
    },
    official_metrics: {
      sharpe: 1.4,
      fitness: 1.1,
      turnover: 0.2,
      returns: 0.08,
      drawdown: 0.03,
      correlation: 0.2,
      weight_concentration: 0.05,
    },
    gate,
  };
}
