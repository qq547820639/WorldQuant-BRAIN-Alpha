import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import App from "@/App";
import CandidateTable from "@/components/CandidateTable";
import ConfigPanel from "@/components/ConfigPanel";
import JobMonitor from "@/components/JobMonitor";
import ScoringPanel from "@/components/ScoringPanel";
import SnapshotPanel from "@/components/SnapshotPanel";
import SubmissionPanel from "@/components/SubmissionPanel";

describe("App credential quick start", () => {
  it("lets operators enter BRAIN credentials and start a non-submit production proof", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [], total: 0 });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path === "/api/submit_readiness") return jsonResponse({ ok: true, eligible_count: 0, ready_to_submit: false });
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/checkpoint_status") return jsonResponse({ ok: true, history_count: 0, checkpoint_count: 0, resume_available: false });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, total: 0, summary: { returned_count: 0 } });
      if (path === "/api/test_connection" && options?.method === "POST") {
        return jsonResponse({ ok: true, environment: "production", auth: "basic" });
      }
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_homepage_proof", auto_submit: false, submitted: false });
      }
      if (path.startsWith("/api/status")) return jsonResponse({ ok: true, job_id: "job_homepage_proof", status: "running" });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByRole("heading", { name: "BRAIN 账户连接" });
    fireEvent.change(screen.getByLabelText("账户邮箱"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "session-secret" } });
    fireEvent.change(screen.getByLabelText("Token（可选）"), { target: { value: "session-token" } });

    fireEvent.click(screen.getByRole("button", { name: "测试 BRAIN 连接" }));
    await screen.findByText("连接正常: production");

    const connectionCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/test_connection" && options?.method === "POST"
    ));
    expect(JSON.parse(String(connectionCall?.[1]?.body))).toEqual({
      username: "reader@example.com",
      password: "session-secret",
      token: "session-token",
    });

    fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));
    await screen.findByText("job_homepage_proof");

    const runCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/run" && options?.method === "POST"
    ));
    expect(JSON.parse(String(runCall?.[1]?.body))).toEqual({
      autoSubmit: false,
      auto_submit: false,
      username: "reader@example.com",
      password: "session-secret",
      token: "session-token",
    });
  });
});

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
              instrumentType: ["EQUITY"],
              region: ["USA"],
              universe: ["TOP3000"],
              delay: [0, 1],
              neutralization: ["SUBINDUSTRY"],
              dataset: ["analyst4", "fundamental6", "pv1"],
              pasteurization: ["ON", "OFF"],
              unitHandling: ["VERIFY", "RAW", "NONE"],
              nanHandling: ["ON", "OFF"],
              language: ["FASTEXPR"],
              type: ["REGULAR", "POWER_POOL"],
            },
            dataset_options: [
              { id: "analyst4", name: "Analyst Estimate Data for Equity", field_count: 1324 },
              { id: "fundamental6", name: "Company Fundamental Data for Equity", field_count: 886 },
              { id: "pv1", name: "Price Volume Data for Equity", field_count: 24 },
            ],
          },
        });
      }
      if (path === "/api/test_connection" && options?.method === "POST") {
        return jsonResponse({ ok: true, environment: "production", auth: "token" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    await screen.findByRole("heading", { name: "连接与生产参数" });
    const dataset = screen.getByRole("combobox", { name: "数据集" });
    const save = screen.getByRole("button", { name: "保存" });
    const username = screen.getByLabelText("账户邮箱");
    const password = screen.getByLabelText("密码");

    expect(within(dataset).getByRole("option", {
      name: "fundamental6 - Company Fundamental Data for Equity, 886 fields",
    })).toBeInTheDocument();

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
    const savedPayload = JSON.parse(String(saveCall?.[1]?.body));
    expect(savedPayload).toMatchObject({
      settings: {
        dataset: "fundamental6",
        region: "USA",
        universe: "TOP3000",
        instrumentType: "EQUITY",
        type: "REGULAR",
      },
      candidates: 20,
      cycles: 10,
    });
    expect(savedPayload.username).toBeUndefined();
    expect(savedPayload.password).toBeUndefined();
    expect(notify).toHaveBeenCalledWith("success", "配置已保存");

    fireEvent.change(username, { target: { value: "reader@example.com" } });
    fireEvent.change(password, { target: { value: "session-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "测试 BRAIN 连接" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/test_connection",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const connectionCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/test_connection" && options?.method === "POST"
    ));
    expect(JSON.parse(String(connectionCall?.[1]?.body))).toMatchObject({
      username: "reader@example.com",
      password: "session-secret",
    });
    expect(await screen.findByText("连接正常: production")).toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith("success", "BRAIN 连接测试通过");
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
      if (path === "/api/check_results") {
        return jsonResponse({ ok: true, items: [] });
      }
      if (path === "/api/generate_candidates" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_7" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CandidateTable notify={notify} onScore={onScore} showRowActions />);

    expect((await screen.findAllByText("rank(close)")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("过滤候选"), { target: { value: "decay" } });

    expect((await screen.findAllByText("decay_linear(volume, 5)")).length).toBeGreaterThan(0);
    expect(screen.queryByText("rank(close)")).not.toBeInTheDocument();

    const count = screen.getByLabelText("数量");
    fireEvent.change(count, { target: { value: "1010" } });
    expect(count).toHaveValue(100);

    fireEvent.change(count, { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "生成候选" }));

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
    expect(notify).toHaveBeenCalledWith("info", "候选生成已启动: job_7");

    const table = screen.getByRole("table", { name: "候选结果" });
    fireEvent.click(within(table).getByRole("button", { name: "评分 alpha_decay" }));
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
    await screen.findByRole("heading", { name: "已达标候选" });
    expect((await screen.findAllByText("passed_expr")).length).toBeGreaterThan(0);
    expect(screen.queryByText("submitted_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="submittable" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/check_results", expect.any(Object)));
    expect((await screen.findAllByText("passed_expr")).length).toBeGreaterThan(0);
    expect(screen.queryByText("stale_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="submitted" />);
    expect((await screen.findAllByText("submitted_expr")).length).toBeGreaterThan(0);
    expect(screen.queryByText("failed_expr")).not.toBeInTheDocument();

    rerender(<CandidateTable notify={notify} viewMode="failed" />);
    expect((await screen.findAllByText("failed_expr")).length).toBeGreaterThan(0);
    expect(screen.queryByText("passed_expr")).not.toBeInTheDocument();
  });
});

describe("SubmissionPanel", () => {
  it("requires a fresh successful check before submitting an alpha", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/check" && options?.method === "POST") {
        return jsonResponse({ ok: true, alpha_id: "alpha_checked", passed: true });
      }
      if (path === "/api/submit" && options?.method === "POST") {
        return jsonResponse({ ok: true, alpha_id: "alpha_checked" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SubmissionPanel notify={notify} />);

    const alphaInput = screen.getByPlaceholderText("例如 alpha_abc123...");
    fireEvent.change(alphaInput, { target: { value: "alpha_checked" } });
    const submit = screen.getByRole("button", { name: "提交Alpha" });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "提交前检查" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/check",
      expect.objectContaining({ method: "POST" }),
    ));
    fireEvent.click(screen.getByLabelText(/我确认此Alpha已通过所有提交前检查/));
    await waitFor(() => expect(submit).toBeEnabled());

    fireEvent.click(submit);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/submit",
      expect.objectContaining({ method: "POST" }),
    ));
    const submitCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/submit" && options?.method === "POST"
    ));
    expect(JSON.parse(String(submitCall?.[1]?.body))).toEqual({
      alpha_id: "alpha_checked",
      confirm_submit: true,
    });
  });
});

describe("ScoringPanel", () => {
  it("does not crash when attribution children are not an array", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/scoring/evaluate" && options?.method === "POST") {
        return jsonResponse({ ok: true });
      }
      if (path === "/api/scoring/attribution" && options?.method === "POST") {
        return jsonResponse({
          ok: true,
          attribution: {
            name: "root",
            score: 1,
            weight: 1,
            children: { invalid: true },
          },
          hard_gates: { invalid: true },
          soft_gates: null,
          top_failures: { invalid: true },
          improvement_hints: "retry with official evidence",
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ScoringPanel notify={notify} candidate={candidate({
      alpha_id: "alpha_scoring",
      expression: "rank(close)",
      score: 80,
    })} />);

    expect(await screen.findByText("root")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alpha表达式" })).toBeInTheDocument();
  });
});

describe("JobMonitor", () => {
  it("keeps non-submit proof visible after a production run is stopped", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_proof" });
      }
      if (path === "/api/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_proof", status: "stopping" });
      }
      if (path.startsWith("/api/status")) {
        return jsonResponse({
          ok: true,
          job_id: "job_proof",
          status: "running",
          result: { summary: { submitted_this_run: 0, auto_submitted: 0, official_validation_attempted: 1, official_validation_passed: 1 } },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));

    await screen.findByText("job_proof");
    expect(screen.getByText("运行证明")).toBeInTheDocument();
    expect(screen.getByText("本轮提交")).toBeInTheDocument();
    expect(screen.getByText("自动提交")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));

    await waitFor(() => expect(notify).toHaveBeenCalledWith("info", "任务已停止"));
    expect(screen.getByText("任务已停止，非提交证据已保留。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/stop",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sends resume=true when starting from the resume control", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_resume" });
      }
      if (path.startsWith("/api/status")) {
        return jsonResponse({ ok: true, job_id: "job_resume", status: "running" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "续跑非提交断点" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/run",
      expect.objectContaining({ method: "POST" }),
    ));
    const runCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/run" && options?.method === "POST"
    ));
    expect(JSON.parse(String(runCall?.[1]?.body))).toEqual({
      resume: true,
      autoSubmit: false,
      auto_submit: false,
      username: "runner@example.com",
      password: "run-secret",
    });
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

    expect((await screen.findAllByText("ALPHA_CLOUD_1")).length).toBeGreaterThan(0);
    expect(screen.getByRole("table", { name: "云端数据表格" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  it("loads checkpoint history rows for resume and history review", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/checkpoint_status") {
        return jsonResponse({
          ok: true,
          checkpoint_count: 1,
          history_count: 2,
          resume_available: true,
          storage_dir: "data",
          latest: {
            run_id: "run_resume",
            phase_completed: "official_validation",
            saved_at: "2026-06-05T00:00:00Z",
          },
          history: [
            {
              run_id: "run_resume",
              status: "completed",
              best_score: 88.5,
              completed_at: "2026-06-05T00:05:00Z",
            },
          ],
          latest_comparison: {
            deltas: { best_score: 4.5, submission_ready: 1 },
          },
          history_analytics: {
            schema_version: "run_history_analytics.v1",
            trend_status: "ready",
            latest_run_id: "run_resume",
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SnapshotPanel notify={notify} viewMode="checkpoint_status" />);

    expect((await screen.findAllByText("run_resume")).length).toBeGreaterThan(0);
    expect(screen.getByRole("table", { name: "断点历史表格" })).toBeInTheDocument();
    expect(screen.getByText("可续跑")).toBeInTheDocument();
    expect(screen.getByText("comparison 对比 2 项: best_score, submission_ready")).toBeInTheDocument();
    expect(screen.getAllByText("comparison").length).toBeGreaterThan(0);
  });
});

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

function ConfigPanelHarness({ notify }: { notify: (type: "success" | "error" | "warning" | "info", msg: string) => void }) {
  const [credentials, setCredentials] = useState({ username: "", password: "", token: "" });
  return <ConfigPanel notify={notify} credentials={credentials} onCredentialsChange={setCredentials} />;
}

function baseConfig(dataset: string) {
  return {
    environment: "production",
    auto_submit: false,
    ops: {
      settings: {
        instrumentType: "EQUITY",
        region: "USA",
        universe: "TOP3000",
        delay: 1,
        decay: 10,
        neutralization: "SUBINDUSTRY",
        dataset,
        pasteurization: "ON",
        unitHandling: "VERIFY",
        nanHandling: "ON",
        language: "FASTEXPR",
        type: "REGULAR",
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
