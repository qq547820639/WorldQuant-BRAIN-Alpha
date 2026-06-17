import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import ToastContainer from "@/components/ToastContainer";
import ProgressFeedback from "@/components/ProgressFeedback";
import { useToast } from "@/hooks/useToast";
import type { Toast, UnifiedProgress } from "@/types";

// ── Helpers ────────────────────────────────────────────────────────────────

function buildToast(overrides: Partial<Toast> = {}): Toast {
  return {
    id: "t1",
    type: "info",
    message: "Hello",
    ...overrides,
  };
}

function buildProgress(overrides: Partial<UnifiedProgress> = {}): UnifiedProgress {
  return {
    percent_complete: 50,
    phase: "testing",
    phase_label: "测试阶段",
    ...overrides,
  };
}

/** Progress object where percent fields are truly absent → indeterminate */
const NO_PERCENT: UnifiedProgress = {};

// ── ToastContainer ─────────────────────────────────────────────────────────

describe("ToastContainer", () => {
  let onDismiss: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onDismiss = vi.fn();
  });

  afterEach(() => {
    cleanup();
  });

  describe("empty state", () => {
    it("renders nothing when toasts array is empty", () => {
      const { container } = render(
        <ToastContainer toasts={[]} onDismiss={onDismiss} />,
      );
      expect(container.innerHTML).toBe("");
    });
  });

  describe("rendering multiple toasts", () => {
    it("renders all toasts when count is within max limit", () => {
      const toasts: Toast[] = [
        buildToast({ id: "a", message: "Alpha" }),
        buildToast({ id: "b", message: "Beta" }),
      ];
      render(<ToastContainer toasts={toasts} onDismiss={onDismiss} />);
      expect(screen.getByText("Alpha")).toBeInTheDocument();
      expect(screen.getByText("Beta")).toBeInTheDocument();
    });

    it("renders only the last 3 toasts when more than 3 are provided", () => {
      const toasts: Toast[] = [1, 2, 3, 4, 5].map((n) =>
        buildToast({ id: String(n), message: `Toast ${n}` }),
      );
      render(<ToastContainer toasts={toasts} onDismiss={onDismiss} />);
      expect(screen.queryByText("Toast 1")).not.toBeInTheDocument();
      expect(screen.queryByText("Toast 2")).not.toBeInTheDocument();
      expect(screen.getByText("Toast 3")).toBeInTheDocument();
      expect(screen.getByText("Toast 4")).toBeInTheDocument();
      expect(screen.getByText("Toast 5")).toBeInTheDocument();
    });
  });

  describe("dismiss by click", () => {
    it("calls onDismiss with the toast id when close button is clicked", () => {
      const toast = buildToast({ id: "dismiss-me", message: "Close this" });
      render(<ToastContainer toasts={[toast]} onDismiss={onDismiss} />);
      fireEvent.click(screen.getByLabelText("关闭通知"));
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(onDismiss).toHaveBeenCalledWith("dismiss-me");
    });
  });

  describe("auto-dismiss after timeout", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
      cleanup();
    });

    function ToastPage() {
      const { toasts, addToast, dismissToast } = useToast(5);
      return (
        <div>
          <button
            data-testid="add-toast"
            onClick={() => addToast("info", "Auto-dismiss message", 1000)}
          >
            Add
          </button>
          <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </div>
      );
    }

    it("auto-dismisses a toast after its duration expires", () => {
      render(<ToastPage />);
      fireEvent.click(screen.getByTestId("add-toast"));
      expect(screen.getByText("Auto-dismiss message")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1100);
      });

      expect(screen.queryByText("Auto-dismiss message")).not.toBeInTheDocument();
    });
  });

  describe("toast types", () => {
    it("renders success toast with checkmark icon and correct class", () => {
      render(
        <ToastContainer
          toasts={[buildToast({ id: "s", type: "success", message: "OK" })]}
          onDismiss={onDismiss}
        />,
      );
      const toast = screen.getByRole("status");
      expect(toast).toHaveClass("toast-success");
      expect(toast.textContent).toContain("\u2713");
    });

    it("renders error toast with cross icon, alert role, and correct class", () => {
      render(
        <ToastContainer
          toasts={[buildToast({ id: "e", type: "error", message: "Fail" })]}
          onDismiss={onDismiss}
        />,
      );
      const toast = screen.getByRole("alert");
      expect(toast).toHaveClass("toast-error");
      expect(toast.textContent).toContain("\u2715");
      expect(toast).toHaveAttribute("aria-live", "assertive");
    });

    it("renders warning toast with warning icon and correct class", () => {
      render(
        <ToastContainer
          toasts={[buildToast({ id: "w", type: "warning", message: "Caution" })]}
          onDismiss={onDismiss}
        />,
      );
      const toast = screen.getByRole("status");
      expect(toast).toHaveClass("toast-warning");
      expect(toast.textContent).toContain("\u26A0");
      expect(toast).toHaveAttribute("aria-live", "polite");
    });

    it("renders info toast with info icon, status role, and correct class", () => {
      render(
        <ToastContainer
          toasts={[buildToast({ id: "i", type: "info", message: "FYI" })]}
          onDismiss={onDismiss}
        />,
      );
      const toast = screen.getByRole("status");
      expect(toast).toHaveClass("toast-info");
      expect(toast.textContent).toContain("\u2139");
    });
  });

  describe("action button", () => {
    it("renders action button when action_label and on_action are provided", () => {
      const onAction = vi.fn();
      render(
        <ToastContainer
          toasts={[
            buildToast({
              id: "act",
              message: "Action needed",
              action_label: "Undo",
              on_action: onAction,
            }),
          ]}
          onDismiss={onDismiss}
        />,
      );
      const btn = screen.getByText("Undo");
      fireEvent.click(btn);
      expect(onAction).toHaveBeenCalledTimes(1);
      expect(onDismiss).toHaveBeenCalledWith("act");
    });

    it("does not render action button when action_label is missing", () => {
      render(
        <ToastContainer
          toasts={[buildToast({ id: "noact", message: "No action" })]}
          onDismiss={onDismiss}
        />,
      );
      expect(screen.queryByRole("button", { name: /No action/ })).not.toBeInTheDocument();
    });
  });
});

// ── ProgressFeedback ───────────────────────────────────────────────────────

describe("ProgressFeedback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  describe("render in progress state", () => {
    it("shows the progress bar with percentage when progress data is provided", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Uploading"
          progress={buildProgress({ percent_complete: 75 })}
        />,
      );
      expect(screen.getByText("75%")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).not.toHaveClass("indeterminate");
    });

    it("shows indeterminate progress bar when percent is absent", () => {
      render(
        <ProgressFeedback
          state="loading"
          title="Processing"
          progress={NO_PERCENT}
        />,
      );
      expect(screen.getByRole("progressbar")).toHaveClass("indeterminate");
    });
  });

  describe("error state with retry button", () => {
    it("shows error message and retry button", () => {
      const onRetry = vi.fn();
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          error="Connection lost"
          onRetry={onRetry}
        />,
      );
      expect(screen.getByText("Connection lost")).toBeInTheDocument();
      const retryBtn = screen.getByText("重试");
      expect(retryBtn).toBeInTheDocument();
      fireEvent.click(retryBtn);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("prefers structured backend progress error copy over raw error text", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          error="raw caller failure"
          progress={{
            phase: "scoring",
            error: "raw backend failure",
            user_error: { message: "评分任务状态已失效，请重新读取后重试。" },
          }}
        />,
      );
      expect(screen.getByText("评分任务状态已失效，请重新读取后重试。")).toBeInTheDocument();
      expect(screen.queryByText("raw caller failure")).not.toBeInTheDocument();
      expect(screen.queryByText("raw backend failure")).not.toBeInTheDocument();
    });

    it("hides unknown raw progress error text when no structured copy is available", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          progress={{
            phase: "scoring",
            error: "Traceback: private backend stack",
          }}
        />,
      );
      expect(screen.getByText("操作失败。")).toBeInTheDocument();
      expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
    });

    it("hides unknown raw progress errors even when an unmapped error code is present", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          progress={{
            phase: "scoring",
            error_code: "UNMAPPED_BACKEND_ERROR",
            error: "Traceback: private backend stack",
          }}
        />,
      );
      expect(screen.getByText("操作失败。")).toBeInTheDocument();
      expect(screen.queryByText(/UNMAPPED_BACKEND_ERROR/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
    });

    it("hides retry button when onRetry is not provided", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          error="Something went wrong"
        />,
      );
      expect(screen.queryByText("重试")).not.toBeInTheDocument();
    });

    it("uses aria-live assertive for error state", () => {
      render(<ProgressFeedback state="error" title="ErrTitle" error="Fail" />);
      // Both title and label render "ErrTitle" (label falls back to title).
      // Pick the first match — it sits inside the assertive container.
      const [titleEl] = screen.getAllByText("ErrTitle");
      expect(titleEl.closest('[aria-live="assertive"]')).toBeTruthy();
    });

    it("falls back to default error text when error is not provided", () => {
      render(<ProgressFeedback state="error" title="Error" />);
      expect(screen.getByText("操作失败。")).toBeInTheDocument();
    });
  });

  describe("compact mode", () => {
    it("returns null when state is idle and compact is true", () => {
      const { container } = render(
        <ProgressFeedback state="idle" compact />,
      );
      expect(container.innerHTML).toBe("");
    });

    it("renders normally when state is not idle even with compact mode", () => {
      render(
        <ProgressFeedback state="loading" compact title="CompactActive" />,
      );
      // title and label both show "CompactActive" — getAllByText confirms both exist
      expect(screen.getAllByText("CompactActive")).toHaveLength(2);
    });
  });

  describe("indeterminate mode", () => {
    it("renders indeterminate progress bar when percent is absent during busy state", () => {
      render(
        <ProgressFeedback
          state="loading"
          title="Scanning"
          progress={NO_PERCENT}
        />,
      );
      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveClass("indeterminate");
      expect(bar).not.toHaveAttribute("aria-valuenow");
    });

    it("renders determinate progress bar when percent is available", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Uploading"
          progress={buildProgress({ percent_complete: 42 })}
        />,
      );
      const bar = screen.getByRole("progressbar");
      expect(bar).not.toHaveClass("indeterminate");
      expect(bar).toHaveAttribute("aria-valuenow", "42");
    });

    it("shows dynamic scan pagination as open-ended when the window reference is not completion", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Cloud sync"
          progress={buildProgress({
            operation: "sync_alphas",
            phase: "scan",
            phase_label: "扫描云端",
            status_code: "SCAN",
            status_message: "已拉取 10,800 / 10,800 条云端 Alpha；第 108 / 108 页；本页 100 条，分页参数 100 条/页，下一 offset 10,800。",
            percent_complete: 100,
            eta_seconds: 49,
            scanned: 10800,
            total: 10800,
            api_reported_total: 10000,
            pages_fetched: 108,
            expected_pages: 108,
            page_size: 100,
            page_limit: 100,
            next_offset: 10800,
          })}
        />,
      );

      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveClass("indeterminate");
      expect(bar).not.toHaveAttribute("aria-valuenow");
      expect(screen.queryByText("100%")).not.toBeInTheDocument();
      expect(screen.queryByText("99%")).not.toBeInTheDocument();
      expect(screen.getByText("运行中")).toBeInTheDocument();
      expect(screen.queryByText(/预计剩余/)).not.toBeInTheDocument();
      expect(screen.getByText("已拉取 10,800 条云端 Alpha；接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界。")).toBeInTheDocument();
      expect(screen.queryByText(/10,800 \/ 10,800 条云端 Alpha/)).not.toBeInTheDocument();
      expect(screen.getByText("已拉取 10,800 条；当前第 108 页 · 本页 100 条 · 100 条/页 · 下一请求确认分页边界")).toBeInTheDocument();
      expect(screen.queryByText(/第 108\s*\/\s*108 页/)).not.toBeInTheDocument();
    });

    it("treats explicit open-ended scan progress as dynamic even when phase is generic", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Cloud sync"
          progress={buildProgress({
            phase: "running",
            phase_label: "扫描云端",
            status_message: "Scanning cloud alphas: 4000 / 10000",
            percent_complete: 40,
            scanned: 4000,
            total: 4700,
            filter_window_count: 10000,
            pages_fetched: 40,
            expected_pages: 100,
            page_size: 100,
            page_limit: 100,
            next_offset: 4000,
            open_ended: true,
            indeterminate: true,
          })}
        />,
      );

      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveClass("indeterminate");
      expect(bar).not.toHaveAttribute("aria-valuenow");
      expect(screen.queryByText("40%")).not.toBeInTheDocument();
      expect(screen.getByText("运行中")).toBeInTheDocument();
      expect(screen.queryByText(/4,000 \/ 10,000/)).not.toBeInTheDocument();
      expect(screen.queryByText(/第 40\s*\/\s*100 页/)).not.toBeInTheDocument();
      expect(screen.getByText("已拉取 4,000 条云端 Alpha；接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界。")).toBeInTheDocument();
    });

    it("keeps legacy scan counts indeterminate until an explicit window reference arrives", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Cloud sync"
          progress={buildProgress({
            operation: "sync_alphas",
            phase: "scan",
            phase_label: "扫描云端",
            status_code: "SCAN",
            status_message: "Scanning cloud alphas: 8900 / 10000",
            scanned: 8900,
            total: 10000,
            eta_seconds: 49,
          })}
        />,
      );

      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveClass("indeterminate");
      expect(bar).not.toHaveAttribute("aria-valuenow");
      expect(screen.queryByText("89%")).not.toBeInTheDocument();
      expect(screen.queryByText(/预计剩余/)).not.toBeInTheDocument();
      expect(screen.queryByText(/8,900 \/ 10,000/)).not.toBeInTheDocument();
      expect(screen.queryByText("Scanning cloud alphas: 8900 / 10000")).not.toBeInTheDocument();
      expect(screen.getByText("已拉取 8,900 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。")).toBeInTheDocument();
      expect(screen.getByText("已拉取 8,900 条")).toBeInTheDocument();
    });

    it("does not render a failed 100 percent sentinel as completed progress", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Pipeline"
          error="Web flow watchdog stopped this task after no clear progress update."
          progress={buildProgress({
            phase: "watchdog_failed",
            status: "failed",
            percent_complete: 100,
          })}
        />,
      );

      expect(screen.getByText("失败")).toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      expect(screen.queryByText("100%")).not.toBeInTheDocument();
    });

    it("renders interrupted partial progress with a negative track", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Submission"
          error="Rate limited"
          progress={buildProgress({
            phase: "failed",
            status: "failed",
            percent_complete: 45,
            checked: 5,
            total: 11,
          })}
        />,
      );

      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "45");
      expect(screen.getByText("中断")).toBeInTheDocument();
      expect(screen.getByText("45%")).toBeInTheDocument();
      expect(bar.querySelector(".progress-bar-fill")).toHaveClass("negative");
    });

    it("uses shared interrupted classification for stopped backend progress", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Scoring"
          error="评分进度暂时不可确认。"
          progress={buildProgress({
            status: "stopped",
            status_kind: "interrupted",
            interrupted: true,
            terminal: true,
            percent_complete: 100,
          })}
        />,
      );

      expect(screen.getByText("已停止")).toBeInTheDocument();
      expect(screen.queryByText("失败")).not.toBeInTheDocument();
      expect(screen.queryByText("100%")).not.toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });

    it("uses backend ETA deadline when present", async () => {
      vi.setSystemTime(new Date("2026-06-04T00:00:00Z"));
      render(
        <ProgressFeedback
          state="progress"
          title="Deadline"
          progress={buildProgress({
            eta_seconds: 99,
            eta_deadline_at_ms: Date.parse("2026-06-04T00:00:05Z"),
          })}
        />,
      );
      expect(screen.getByText("预计剩余 00:05")).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(screen.getByText("预计剩余 00:03")).toBeInTheDocument();
    });
  });

  describe("title and message display", () => {
    it("displays the title prop", () => {
      render(
        <ProgressFeedback
          state="loading"
          title="Custom Title"
          progress={buildProgress({ phase_label: undefined, phase: undefined })}
        />,
      );
      // With no phase_label/phase, label also falls back to title → both render it
      expect(screen.getAllByText("Custom Title")).toHaveLength(2);
    });

    it("displays progress phase label when available", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ phase_label: "数据验证" })}
        />,
      );
      expect(screen.getByText("数据验证")).toBeInTheDocument();
    });

    it("uses stable copy for unknown phase when phase_label is absent", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ phase_label: undefined, phase: "RAW_BACKEND_PHASE" })}
        />,
      );
      expect(screen.getByText("当前阶段")).toBeInTheDocument();
      expect(screen.queryByText("RAW_BACKEND_PHASE")).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/RAW_BACKEND_PHASE/)).not.toBeInTheDocument();
    });

    it("maps backend-only phase codes to safe progress labels", () => {
      render(
        <ProgressFeedback
          state="error"
          title="Pipeline"
          error="验证流程已停止，结果未确认完成。"
          progress={buildProgress({
            phase_label: undefined,
            phase: "session_invalid",
            percent_complete: 100,
            status_kind: "interrupted",
            interrupted: true,
            terminal: true,
          })}
        />,
      );

      expect(screen.getByText("本地会话需重新确认")).toBeInTheDocument();
      expect(screen.getByText("监控受阻")).toBeInTheDocument();
      expect(screen.queryByText("100%")).not.toBeInTheDocument();
      expect(screen.queryByText("session_invalid")).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/session_invalid/)).not.toBeInTheDocument();
    });

    it("shows idle text in idle state", () => {
      render(<ProgressFeedback state="idle" idleText="等待中..." />);
      expect(screen.getByText("等待中...")).toBeInTheDocument();
    });

    it("shows success text in success state", () => {
      render(
        <ProgressFeedback
          state="success"
          title="Done"
          successText="操作成功"
        />
      );
      expect(screen.getByText("操作成功")).toBeInTheDocument();
    });

    it("shows safe product status messages when available in busy state", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ status_message: "正在处理文件" })}
        />,
      );
      expect(screen.getByText("正在处理文件")).toBeInTheDocument();
    });

    it("hides unknown raw status messages in busy state", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ status_message: "Traceback: private backend worker detail" })}
        />,
      );

      expect(screen.getByText("处理中...")).toBeInTheDocument();
      expect(screen.queryByText(/Traceback: private backend worker detail/)).not.toBeInTheDocument();
    });
  });

  describe("success state", () => {
    it("renders a success checkmark indicator", () => {
      const { container } = render(<ProgressFeedback state="success" title="Done" />);
      expect(screen.getByText("完成")).toBeInTheDocument();
      const checkmark = container.querySelector('[aria-hidden="true"]');
      expect(checkmark?.textContent).toBe("\u2713");
    });
  });

  describe("eta countdown", () => {
    it("displays remaining time when eta_seconds > 0 during progress", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ eta_seconds: 125 })}
        />,
      );
      // 125 seconds -> "02:05"
      expect(screen.getByText("预计剩余 02:05")).toBeInTheDocument();
    });

    it("does not display eta when eta_seconds is 0", () => {
      render(
        <ProgressFeedback
          state="progress"
          title="Processing"
          progress={buildProgress({ eta_seconds: 0 })}
        />,
      );
      expect(screen.queryByText(/预计剩余/)).not.toBeInTheDocument();
    });
  });
});
