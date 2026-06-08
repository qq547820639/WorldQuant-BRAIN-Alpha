import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

/** Safely parse request body from a fetch mock call. Throws clear error if call is missing. */
function safeJson(call: [unknown, RequestInit?] | undefined): Record<string, unknown> {
  if (!call) throw new Error("Expected fetch call was never made");
  const body = call[1]?.body;
  if (body == null) throw new Error("Expected request body is missing");
  return JSON.parse(String(body));
}
import App from "@/App";
import { requestJobCancel } from "@/api/jobCancel";
import CandidateTable from "@/components/CandidateTable";
import ConfigPanel from "@/components/ConfigPanel";
import JobMonitor from "@/components/JobMonitor";
import QualityCheckPanel from "@/components/QualityCheckPanel";
import ScoringPanel from "@/components/ScoringPanel";
import SnapshotPanel from "@/components/SnapshotPanel";
import SubmissionPanel from "@/components/SubmissionPanel";
import OfficialOperationsPanel from "@/components/OfficialOperationsPanel";
import type { Candidate } from "@/types";

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
      if (path.startsWith("/api/production-validation/status")) return jsonResponse({ ok: true, job_id: "job_homepage_proof", status: "running" });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByText("凭证与连接");
    fireEvent.change(screen.getByLabelText("账户邮箱"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "session-secret" } });
    fireEvent.change(screen.getByLabelText("Token（可选）"), { target: { value: "session-token" } });

    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await screen.findByText("连接正常: production");

    const connectionCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/test_connection" && options?.method === "POST"
    ));
    expect(safeJson(connectionCall)).toEqual({
      username: "reader@example.com",
      password: "session-secret",
      token: "session-token",
    });

    fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));
    await screen.findByText("job_ho...roof");

    const runCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/run" && options?.method === "POST"
    ));
    expect(safeJson(runCall)).toEqual({
      autoSubmit: false,
      auto_submit: false,
      username: "reader@example.com",
      password: "session-secret",
      token: "session-token",
    });
  });

  it("keeps manual submit out of the default state-card workflow", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [], total: 0 });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/checkpoint_status") return jsonResponse({ ok: true, history_count: 0, checkpoint_count: 0, resume_available: false });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, total: 0, summary: { returned_count: 0 } });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByText("凭证与连接");
    expect(screen.getByText("阻断复核")).toBeInTheDocument();
    expect(screen.queryByText("手动提交")).not.toBeInTheDocument();
  });
});

describe("requestJobCancel", () => {
  it("keeps ordinary Web cancellation on the production-validation stop endpoint", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: false, error_code: "JOB_NOT_FOUND", error: "unknown job" }, 404);
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestJobCancel({
      jobId: "task_9",
      reason: "sse_exhausted",
      message: "SSE exhausted during async scoring.",
    });

    expect(result?.ok).toBe(false);
    expect(result?.error_code).toBe("JOB_NOT_FOUND");
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/production-validation/stop",
    ]);
    for (const [, options] of fetchMock.mock.calls) {
      expect(JSON.parse(String(options?.body))).toMatchObject({
        job_id: "task_9",
        task_id: "task_9",
        reason: "sse_exhausted",
        source: "web",
      });
    }
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
    const savedPayload = safeJson(saveCall);
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
    expect(safeJson(connectionCall)).toMatchObject({
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
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_7", status: "stopping" });
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
    expect(safeJson(generateCall)).toEqual({ count: 7 });
    expect(notify).toHaveBeenCalledWith("info", "候选生成已启动，可在本页查看进度。");

    const table = screen.getByRole("table", { name: "候选结果" });
    fireEvent.click(within(table).getByRole("button", { name: "评分 alpha_decay" }));
    expect(onScore).toHaveBeenCalledWith(expect.objectContaining({ alpha_id: "alpha_decay" }));
  });

  it("requests backend cancellation when candidate generation progress becomes ambiguous", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [] });
      if (path === "/api/check_results") return jsonResponse({ ok: true, items: [] });
      if (path === "/api/generate_candidates" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_candidate_lost" });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_candidate_lost", status: "stopping" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CandidateTable notify={notify} />);
    await screen.findByRole("heading", { name: "候选管理" });
    fireEvent.click(screen.getByRole("button", { name: "生成候选" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/generate_candidates",
      expect.objectContaining({ method: "POST" }),
    ));

    await emitSseErrors(31);

    expect(screen.getByText("候选生成进度暂时不可确认，系统已安全停止本次生成。请刷新候选列表后再重试。")).toBeInTheDocument();
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/production-validation/stop",
      expect.objectContaining({ method: "POST" }),
    );
    const stopCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/production-validation/stop" && options?.method === "POST"
    ));
    expect(safeJson(stopCall)).toMatchObject({
      job_id: "job_candidate_lost",
      reason: "sse_exhausted",
      source: "web",
    });
    expect(screen.getByRole("button", { name: "生成候选" })).not.toBeDisabled();
  });

  it("does not reconnect SSE after candidate generation reaches a terminal event", async () => {
    const notify = vi.fn();
    const generated = candidate({ alpha_id: "alpha_terminal", expression: "rank(close)", score: 91 });
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [] });
      if (path === "/api/check_results") return jsonResponse({ ok: true, items: [] });
      if (path === "/api/generate_candidates" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_terminal" });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_terminal", status: "stopping" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CandidateTable notify={notify} />);
    await screen.findByRole("heading", { name: "候选管理" });
    fireEvent.click(screen.getByRole("button", { name: "生成候选" }));
    await waitFor(() => {
      const eventSourceClass = EventSource as unknown as {
        instances?: Array<{ emit: (type: string, data: unknown) => void; emitError: () => void }>;
      };
      expect(eventSourceClass.instances?.length).toBe(1);
    });
    const eventSourceClass = EventSource as unknown as {
      instances?: Array<{ emit: (type: string, data: unknown) => void; emitError: () => void }>;
    };
    const first = eventSourceClass.instances?.[0];
    expect(first).toBeTruthy();

    await act(async () => {
      first?.emit("complete", { type: "complete", result: { candidates: [generated], count: 1 } });
      await Promise.resolve();
    });
    expect(notify).toHaveBeenCalledWith("success", "候选生成完成: 1");

    vi.useFakeTimers();
    await act(async () => {
      first?.emitError();
      await vi.advanceTimersByTimeAsync(3500);
    });

    expect(eventSourceClass.instances?.length).toBe(1);
    expect(fetchMock).not.toHaveBeenCalledWith("/api/production-validation/stop", expect.any(Object));
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
  it("is a read-only compatibility wrapper around submit readiness", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/candidates?limit=1000") {
        return jsonResponse({ ok: true, candidates: [] });
      }
      if (path === "/api/check_results") {
        return jsonResponse({ ok: true, items: [] });
      }
      if (path === "/api/submit_readiness") {
        return jsonResponse({
          ok: true,
          ready_to_submit: false,
          eligible_count: 0,
          top_blocking_reasons: [{ reason: "缺少官方 Alpha ID", count: 1 }],
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SubmissionPanel notify={notify} />);

    expect(screen.getByText(/旧提交面板已退役/)).toBeInTheDocument();
    expect(await screen.findByText(/缺少官方 Alpha ID/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交Alpha" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/submit", expect.any(Object));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/submit_batch", expect.any(Object));
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
    expect(screen.getByText("Alpha 表达式")).toBeInTheDocument();
  });

  it("requests backend cancellation when scoring progress stream is exhausted", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/scoring/evaluate" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_score_lost" });
      }
      if (path === "/api/scoring/attribution" && options?.method === "POST") {
        return jsonResponse({ ok: true, attribution: { name: "root", score: 1, weight: 1, children: [] } });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_score_lost", status: "stopping" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ScoringPanel notify={notify} candidate={candidate({
      alpha_id: "alpha_score_lost",
      expression: "rank(close)",
      score: 80,
    })} />);

    await screen.findByText("root");
    await emitSseErrors(31);

    expect(screen.getByText("评分进度暂时不可确认，系统已安全停止。请稍后重试评分。")).toBeInTheDocument();
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/production-validation/stop",
      expect.objectContaining({ method: "POST" }),
    );
    const stopCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/production-validation/stop" && options?.method === "POST"
    ));
    expect(safeJson(stopCall)).toMatchObject({
      job_id: "job_score_lost",
      reason: "sse_exhausted",
      source: "web",
    });
    expect(screen.getAllByRole("button", { name: "重试" }).length).toBeGreaterThan(0);
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
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_proof", status: "stopping" });
      }
      if (path.startsWith("/api/production-validation/status")) {
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
    expect(screen.getByText("本轮真实提交（应为 0）")).toBeInTheDocument();
    expect(screen.getByText("自动提交")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));

    await waitFor(() => expect(notify).toHaveBeenCalledWith("info", "验证流程已停止"));
    // The stopped message may show either the full text or the fallback short text
    const hasStopMsg = screen.queryByText((c) => c.includes("非提交证据")) !== null
      || screen.queryByText("停止请求已发送") !== null;
    expect(hasStopMsg).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/production-validation/stop",
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
      if (path.startsWith("/api/production-validation/status")) {
        return jsonResponse({ ok: true, job_id: "job_resume", status: "running" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "继续上次验证" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/run",
      expect.objectContaining({ method: "POST" }),
    ));
    const runCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/run" && options?.method === "POST"
    ));
    expect(safeJson(runCall)).toEqual({
      resume: true,
      autoSubmit: false,
      auto_submit: false,
      username: "runner@example.com",
      password: "run-secret",
    });
  });

  it("auto-stops the browser monitor when the backend watchdog fails a stalled job", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_watchdog" });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_watchdog", status: "stopping" });
      }
      if (path.startsWith("/api/production-validation/status")) {
        return jsonResponse({
          ok: true,
          job_id: "job_watchdog",
          status: "failed",
          error: "Web flow watchdog stopped this task after no clear progress update.",
          progress: {
            phase: "watchdog_failed",
            status_message: "Web flow watchdog stopped this task after no clear progress update.",
            percent_complete: 100,
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));

    await screen.findByText("job_watchdog");
    await waitFor(() => expect(notify).toHaveBeenCalledWith("error", "Web flow watchdog stopped this task after no clear progress update."), { timeout: 3500 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/production-validation/stop",
      expect.objectContaining({ method: "POST" }),
    ), { timeout: 3500 });
    expect(screen.getAllByText("Web flow watchdog stopped this task after no clear progress update.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "运行非提交验证" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "停止" })).toBeDisabled();
  });

  it("auto-interrupts monitoring after repeated ambiguous status refresh failures", async () => {
    vi.useFakeTimers();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_status_lost" });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_status_lost", status: "stopping" });
      }
      if (path.startsWith("/api/production-validation/status")) {
        return jsonResponse({ ok: false, error_code: "JOB_NOT_FOUND", error: "unknown job" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));
    await flushPromises();
    expect(screen.getByText("job_st...lost")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6500);
    });
    await flushPromises();

    expect(notify).toHaveBeenCalledWith("error", "状态连续刷新失败，系统已安全停止本次验证: unknown job");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/production-validation/stop",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.getAllByText("状态连续刷新失败，系统已安全停止本次验证: unknown job").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "运行非提交验证" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "停止" })).toBeDisabled();
  });

  it("auto-interrupts monitoring when status refresh hits network errors", async () => {
    vi.useFakeTimers();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/run" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_network_lost" });
      }
      if (path === "/api/production-validation/stop" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "job_network_lost", status: "stopping" });
      }
      if (path.startsWith("/api/production-validation/status")) {
        throw new Error("network down");
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(<JobMonitor notify={notify} credentials={{ username: "runner@example.com", password: "run-secret", token: "" }} />);
      fireEvent.click(screen.getByRole("button", { name: "运行非提交验证" }));
      await flushPromises();
      expect(screen.getByText("job_ne...lost")).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(6500);
      });
      await flushPromises();

      expect(notify).toHaveBeenCalledWith("error", "状态连续刷新失败，系统已安全停止本次验证: 状态刷新失败或网络中断");
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/production-validation/stop",
        expect.objectContaining({ method: "POST" }),
      );
      expect(screen.getAllByText("状态连续刷新失败，系统已安全停止本次验证: 状态刷新失败或网络中断").length).toBeGreaterThan(0);
      expect(screen.getByRole("button", { name: "运行非提交验证" })).not.toBeDisabled();
      expect(screen.getByRole("button", { name: "停止" })).toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("OfficialOperationsPanel", () => {
  it("shows data overview cards for sync status, update time, and data total", () => {
    render(<OfficialOperationsPanel notify={vi.fn()} />);

    const overview = screen.getByLabelText("官方同步数据总览");
    expect(within(overview).getByText("同步状态")).toBeInTheDocument();
    expect(within(overview).getByText("更新时间")).toBeInTheDocument();
    expect(within(overview).getByText("官方报告总量")).toBeInTheDocument();
    expect(within(overview).getByText("待启动")).toBeInTheDocument();
    expect(within(overview).getByText("暂无同步更新时间。")).toBeInTheDocument();
    expect(within(overview).getByText("等待云端 Alpha 同步；不会使用固定同步上限。")).toBeInTheDocument();
  });

  it("sends page-only BRAIN credentials when the operator starts official context refresh", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_with_session_credentials" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({
          ok: true,
          job_id: "sync_with_session_credentials",
          status: "completed",
          progress: {
            phase: "completed",
            status_code: "COMPLETED",
            status_message: "Official context refreshed.",
            percent_complete: 100,
            fields_count: 12,
            operators_count: 7,
            datasets_count: 3,
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel
      notify={notify}
      credentials={{ username: "panel@example.com", password: "panel-secret", token: "panel-token" }}
    />);
    fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/sync_alphas",
      expect.objectContaining({ method: "POST" }),
    ));
    const syncCall = fetchMock.mock.calls.find(([url, options]) => (
      String(url) === "/api/sync_alphas" && options?.method === "POST"
    ));
    expect(safeJson(syncCall)).toEqual({
      syncRange: "3d",
      refreshOfficialContext: true,
      userFacingOperation: "official_operations_context_refresh",
      username: "panel@example.com",
      password: "panel-secret",
      token: "panel-token",
    });
    expect((await screen.findAllByText("官方上下文已刷新。")).length).toBeGreaterThan(0);
    expect(screen.queryByText("panel-secret")).not.toBeInTheDocument();
    expect(screen.queryByText("panel-token")).not.toBeInTheDocument();
  });

  it("shows completed sync data total from the actual final count", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_completed_count" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({
          ok: true,
          job_id: "sync_completed_count",
          status: "completed",
          result: {
            count: 21000,
            scanned: 21000,
            total: 21000,
            updated_at_ms: Date.UTC(2026, 5, 7, 5, 10, 30),
          },
          progress: {
            phase: "completed",
            status_code: "COMPLETED",
            status_message: "Official context refreshed.",
            percent_complete: 100,
            scanned: 21000,
            total: 21000,
            updated_at_ms: Date.UTC(2026, 5, 7, 5, 10, 30),
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));

    const overview = await screen.findByLabelText("官方同步数据总览");
    await within(overview).findByText("21,000");
    expect(within(overview).getByText("已刷新")).toBeInTheDocument();
    expect(within(overview).getByText("实际完成数量；不是同步上限。")).toBeInTheDocument();
  });

  it("polls official context refresh once immediately and then on the interval", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_visual_1" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({
          ok: true,
          job_id: "sync_visual_1",
          status: "running",
          progress: {
            phase: "context",
            status_code: "CONTEXT_FIELDS",
            status_message: "Updating official fields cache: 10 / 100",
            percent_complete: 10,
            fields_count: 10,
            total: 100,
            scanned: 10,
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/sync_alphas",
      expect.objectContaining({ method: "POST" }),
    ));
    await waitFor(() => expect(syncStatusCallCount(fetchMock)).toBe(1));

    await delay(300);
    expect(syncStatusCallCount(fetchMock)).toBe(1);
    await delay(2200);
    await waitFor(() => expect(syncStatusCallCount(fetchMock)).toBe(2));

    expect(screen.getByText("刷新中...")).toBeDisabled();
    expect(screen.getAllByText("正在刷新官方字段缓存: 10 / 100").length).toBeGreaterThan(0);
  }, 8000);

  it("does not show 100 percent before official context refresh reaches a terminal state", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_not_terminal_100" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({
          ok: true,
          job_id: "sync_not_terminal_100",
          status: "running",
          progress: {
            phase: "scan",
            status_code: "SCAN",
            status_message: "Scanning cloud alphas: 10800 / 10800",
            percent_complete: 100,
            scanned: 10800,
            total: 10800,
          },
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));

    await screen.findByText("已扫描 10,800 条云端 Alpha；官方当前报告总量 10,800，这不是同步上限，仍会继续读取后续页面。");
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
    expect(screen.queryByText("99%")).not.toBeInTheDocument();
    expect(screen.getByText("刷新中...")).toBeDisabled();
    expect(screen.getAllByText("已扫描 10,800 条云端 Alpha；官方当前报告总量 10,800，这不是同步上限，仍会继续读取后续页面。").length).toBeGreaterThan(0);
    expect(screen.getByText("已扫描 10,800")).toBeInTheDocument();
    expect(screen.getByText("官方当前报告总量 10,800；这不是同步上限，仍会继续读取后续页面。")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "操作进度: 扫描云端" })).not.toHaveAttribute("aria-valuenow");
  });

  it("auto-stops official context refresh after repeated status failures", async () => {
    vi.useFakeTimers();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_status_lost" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({ ok: false, error_code: "JOB_NOT_FOUND", error: "unknown sync job" });
      }
      if (path === "/api/sync_cancel" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_status_lost", status: "stopping" });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(<OfficialOperationsPanel notify={notify} />);
      fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));
      await flushPromises();
      expect(screen.getByText("刷新中...")).toBeDisabled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4500);
      });
      await flushPromises();

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sync_cancel",
        expect.objectContaining({ method: "POST" }),
      );
      expect(notify).toHaveBeenCalledWith("warning", "连续读取刷新状态失败，已自动停止本次刷新。请检查网络或稍后重试。");
      expect(screen.getAllByText("连续读取刷新状态失败，已自动停止本次刷新。请检查网络或稍后重试。").length).toBeGreaterThan(0);
      expect(screen.getByRole("button", { name: "开始刷新" })).not.toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps failed refresh errors out of later readiness and check-result views", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/sync_alphas" && options?.method === "POST") {
        return jsonResponse({ ok: true, job_id: "sync_failed_1" });
      }
      if (path.startsWith("/api/sync_status")) {
        return jsonResponse({
          ok: true,
          job_id: "sync_failed_1",
          status: "failed",
          error: "official context timeout",
          progress: { phase: "failed", status_message: "official context timeout", percent_complete: 100 },
        });
      }
      if (path === "/api/submit_readiness") {
        return jsonResponse({ ok: true, ready_to_submit: false, eligible_count: 0, candidate_count: 2 });
      }
      if (path === "/api/check_results") {
        return jsonResponse({ ok: true, items: [{ alpha_id: "alpha_checked" }, { alpha_id: "alpha_blocked" }] });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "开始刷新" }));
    await screen.findByText("官方上下文刷新超时，请稍后重试。");

    fireEvent.click(screen.getByRole("button", { name: "读取复核" }));
    await screen.findByText("阻断复核 0 / 候选 2");
    expect(screen.queryByText("操作失败。")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    await screen.findByText("已加载 2 条检查结果。");
    expect(screen.getByText("质量检查结果已加载: 2 条。")).toBeInTheDocument();
  });

  it("explains pre-submit blockers and convergence gaps in the browser", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/submit_readiness") {
        return jsonResponse({
          ok: true,
          ready_to_submit: false,
          eligible_count: 0,
          candidate_count: 0,
          job_family_candidate_count: 2,
          latest_job_id: "job_0011",
          summary_counts: {
            official_validation_passed: 2,
            officially_simulated: 0,
            submission_ready: 0,
          },
          top_blocking_reasons: [
            { reason: "missing_official_alpha_id", count: 2 },
            { reason: "missing_official_metrics", count: 2 },
          ],
          top_family_blocking_reasons: [
            { reason: "decision_band_not_submit_candidate", count: 2 },
            { reason: "high_cloud_similarity", count: 2 },
          ],
          production_gaps: [
            {
              code: "candidate_family_missing_official_metrics",
              message: "candidate family lacks official simulation metrics",
            },
          ],
          best_candidate: {
            alpha_id: "alpha_15da920d34",
            score: 66.9,
            decision_band: "research_only",
            local_backtest_passed: false,
            max_similarity: 1,
            risk_level: "high",
            blocking_reasons: [
              "local_backtest_failed",
              "high_turnover_generation_risk",
            ],
          },
          required_next_steps: [
            "run official simulation/check in a trusted environment",
            "resolve local blockers before submit review",
          ],
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "读取复核" }));

    await screen.findByText("阻断复核 0 / 候选 0");
    expect(screen.getByText("缺少官方 Alpha ID (2)")).toBeInTheDocument();
    expect(screen.getByText("缺少官方仿真指标 (2)")).toBeInTheDocument();
    expect(screen.getByText("评分决策仍非提交候选 (2)")).toBeInTheDocument();
    expect(screen.getByText("候选族缺少官方仿真指标")).toBeInTheDocument();
    expect(screen.getByText("在可信环境运行官方仿真/检查")).toBeInTheDocument();
    expect(screen.getByText("先修复本地阻断，再进入提交复核")).toBeInTheDocument();
    expect(screen.getByText("本地回测未通过")).toBeInTheDocument();
    expect(screen.getByText("生成表达式存在高换手风险")).toBeInTheDocument();
    expect(screen.getByText("alpha_15da920d34")).toBeInTheDocument();
    expect(screen.getByText("66.900")).toBeInTheDocument();
    expect(screen.getAllByText("仅限研究").length).toBeGreaterThan(0);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getAllByText("高").length).toBeGreaterThan(0);
  });

  it("does not invent best-candidate metrics when readiness has no candidate evidence", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/submit_readiness") {
        return jsonResponse({
          ok: true,
          ready_to_submit: false,
          eligible_count: 0,
          candidate_count: 0,
          latest_job_id: "job_empty",
          summary_counts: {
            official_validation_passed: 0,
            officially_simulated: 0,
            submission_ready: 0,
          },
          best_candidate: {
            alpha_id: "",
            score: undefined,
            decision_band: "",
            local_backtest_passed: false,
            max_similarity: undefined,
            risk_level: "",
            blocking_reasons: [],
          },
          required_next_steps: ["resolve local blockers before submit review"],
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OfficialOperationsPanel notify={notify} />);
    fireEvent.click(screen.getByRole("button", { name: "读取复核" }));

    await screen.findByText("阻断复核 0 / 候选 0");
    expect(screen.getByText("先修复本地阻断，再进入提交复核")).toBeInTheDocument();
    const evidenceRegion = screen.getByText("最佳候选证据").closest("div");
    expect(evidenceRegion).toBeTruthy();
    expect(within(evidenceRegion as HTMLElement).getAllByText("-").length).toBeGreaterThanOrEqual(6);
    expect(within(evidenceRegion as HTMLElement).queryByText("fail")).not.toBeInTheDocument();
    expect(within(evidenceRegion as HTMLElement).queryByText("0")).not.toBeInTheDocument();
  });

  it("times out unclear readiness reads and returns the browser flow to an actionable state", async () => {
    vi.useFakeTimers();
    const notify = vi.fn();
    const fetchMock = vi.fn((url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/submit_readiness") {
        return new Promise((_, reject) => {
          options?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(<OfficialOperationsPanel notify={notify} />);
      fireEvent.click(screen.getByRole("button", { name: "读取复核" }));
      expect(screen.getByRole("button", { name: "检查中..." })).toBeDisabled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      await flushPromises();

      expect(screen.getByRole("button", { name: "读取复核" })).not.toBeDisabled();
      expect(screen.getAllByText("提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。").length).toBeGreaterThan(0);
      expect(notify).toHaveBeenCalledWith("error", "提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("QualityCheckPanel", () => {
  it("shows pre-official-work blockers and next action in browser-readable language", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) {
        return jsonResponse({
          ok: true,
          candidates: [
            candidate({
              alpha_id: "alpha_local_ok",
              expression: "rank(close)",
              local_quality: { passed: true },
              quality_diagnosis: { local_candidate_valid: true, submission_ready: false },
            }),
            candidate({
              alpha_id: "alpha_local_blocked",
              expression: "rank(ts_delta(returns, 10))",
              local_quality: { passed: false },
              quality_diagnosis: { local_candidate_valid: false, blocking_reasons: ["local_quality_failed"] },
            }),
          ],
        });
      }
      if (path === "/api/backtest_slots") {
        return jsonResponse({
          ok: true,
          slot_limit: 3,
          active_count: 1,
          slots: [{ slot: 1, status: "RUNNING", alpha_id: "alpha_running" }],
          queue_summary: {
            slot_limit: 3,
            open_slot_count: 2,
            local_valid_count: 1,
            above_simulation_score_count: 1,
            review_candidate_count: 0,
            submit_evidence_blocking_count: 2,
            official_api_called: false,
            top_blocking_reasons: [
              { reason: "local_backtest_failed", count: 1 },
              { reason: "score_below_official_simulation_threshold", count: 1 },
            ],
            top_submit_blocking_reasons: [
              { reason: "missing_official_metrics", count: 2 },
            ],
            next_action: "improve_or_regenerate_candidates",
          },
        });
      }
      if (path === "/api/submit_readiness") {
        return jsonResponse({
          ok: true,
          ready_to_submit: false,
          eligible_count: 0,
          summary_counts: { officially_simulated: 0, submission_ready: 0 },
          threshold_summary: {
            min_sharpe: 1.25,
            min_fitness: 1,
            platform_max_turnover: 0.7,
            max_self_correlation: 0.7,
          },
          top_family_blocking_reasons: [
            { reason: "high_cloud_similarity", count: 1 },
          ],
        });
      }
      if (path === "/api/check_results") return jsonResponse({ ok: true, items: [] });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<QualityCheckPanel notify={notify} />);

    await screen.findByRole("heading", { name: "达标检查" });
    await screen.findByText("本地通过 1 · 官方仿真 0 · 复核候选 0");
    expect(screen.getByText("本地阻断")).toBeInTheDocument();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getByText("官方工作阻断: 本地回测未通过 1 · 未达到官方仿真分数门槛 1")).toBeInTheDocument();
    expect(screen.getByText("提交证据阻断: 缺少官方仿真指标 2")).toBeInTheDocument();
    expect(screen.getByText("候选族阻断: 云端相似度过高 1")).toBeInTheDocument();
    expect(screen.getByText("下一步: 优化或重新生成候选")).toBeInTheDocument();
    expect(screen.getByText("官方门槛: 夏普 1.25 · 适应度 1 · 换手率 <= 0.70 · 自相关 <= 0.70")).toBeInTheDocument();
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
    expect(screen.getByRole("table", { name: "续跑记录表格" })).toBeInTheDocument();
    expect(screen.getByText("可续跑")).toBeInTheDocument();
    expect(screen.getByText("对比 2 项: best_score, submission_ready")).toBeInTheDocument();
    expect(screen.getAllByText("对比").length).toBeGreaterThan(0);
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
  local_quality,
  quality_diagnosis,
}: {
  alpha_id: string;
  expression: string;
  score?: number;
  lifecycle_status?: string;
  gate?: Record<string, unknown>;
  local_quality?: Candidate["local_quality"];
  quality_diagnosis?: Candidate["quality_diagnosis"];
}): Candidate {
  const totalScore = score ?? 80;
  return {
    alpha_id,
    expression,
    family: "momentum",
    hypothesis: "Test candidate",
    lifecycle_status,
    scorecard: {
      total_score: totalScore,
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
    local_quality,
    quality_diagnosis,
  };
}

function syncStatusCallCount(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/sync_status")).length;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function emitSseErrors(count: number) {
  const eventSourceClass = EventSource as unknown as { instances?: Array<{ emitError: () => void }> };
  await act(async () => {
    for (let index = 0; index < count; index += 1) {
      eventSourceClass.instances?.at(-1)?.emitError();
    }
    await Promise.resolve();
  });
}

async function flushPromises() {
  await act(async () => {
    await new Promise((resolve) => queueMicrotask(resolve));
    await new Promise((resolve) => queueMicrotask(resolve));
  });
}
