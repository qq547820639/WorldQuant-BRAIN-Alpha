/**
 * useJobDisconnectedState — Disconnected state machine with auto-cancel timer.
 *
 * When SSE exhausts or the polling watchdog fires, enters a "disconnected"
 * state where the user is shown a toast with [继续等待] / [终止重试] buttons.
 * If the user takes no action within 60s, auto-cancellation takes effect.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import type { CancelReason } from "@/api/jobCancel";

const DISCONNECTED_AUTO_CANCEL_MS = 60000;

interface AutoCancelCallbacks {
  jobId: string | null | undefined;
  callApi: <T>(url: string) => Promise<T | null>;
  failMonitor: (message: string) => void;
  cancelAmbiguousJob: (
    reason: CancelReason,
    message: string,
    targetJobId?: string | null,
  ) => Promise<unknown>;
  reconnectJob: (jobId: string) => void;
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
  ) => void;
}

interface DisconnectedCallbacks extends AutoCancelCallbacks {
  onReconnect: () => void;
}

export function useJobDisconnectedState({
  notify,
  failMonitor,
  cancelAmbiguousJob,
  onReconnect,
}: DisconnectedCallbacks) {
  const [disconnected, setDisconnected] = useState(false);
  const disconnectedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disconnectedNotifyRef = useRef(false);
  const callbacksRef = useRef<AutoCancelCallbacks | null>(null);

  const clearDisconnectedTimer = useCallback(() => {
    if (disconnectedTimerRef.current) {
      clearTimeout(disconnectedTimerRef.current);
      disconnectedTimerRef.current = null;
    }
  }, []);

  const enterDisconnectedState = useCallback(
    (trigger: "sse_exhausted" | "polling_watchdog", extraCallbacks?: AutoCancelCallbacks) => {
      if (disconnected) return;
      setDisconnected(true);
      disconnectedNotifyRef.current = true;
      if (extraCallbacks) callbacksRef.current = extraCallbacks;

      const message =
        trigger === "sse_exhausted"
          ? "检测到 SSE 连接中断（已与服务器失去联系超过 40 秒）。BRAIN 平台上的任务可能仍在运行。要终止并重试，还是继续等待自动重连？"
          : "状态连续刷新失败（已与服务器失去联系超过 24 秒）。BRAIN 平台上的任务可能仍在运行。要终止并重试，还是继续等待自动重连？";

      const cancelFn = () => {
        clearDisconnectedTimer();
        setDisconnected(false);
        disconnectedNotifyRef.current = false;
        const failureMsg =
          trigger === "sse_exhausted"
            ? "页面暂时收不到最新进度，用户确认终止。"
            : "状态连续刷新失败，用户确认终止。";
        failMonitor(failureMsg);
        void cancelAmbiguousJob(
          trigger === "sse_exhausted" ? "sse_exhausted" : "status_failed",
          failureMsg,
        );
        notify("error", "BRAIN 平台任务已被终止。");
      };

      const resumeFn = () => {
        clearDisconnectedTimer();
        setDisconnected(false);
        disconnectedNotifyRef.current = false;
        onReconnect();
        notify("info", "已恢复等待。系统将继续尝试重连…");
      };

      notify("warning", message, { label: "终止重试", onClick: cancelFn });
      notify("info", "点击「继续等待」重置倒计时，系统将继续尝试重连。", {
        label: "继续等待",
        onClick: resumeFn,
      });

      disconnectedTimerRef.current = setTimeout(async () => {
        if (!disconnectedNotifyRef.current) return;
        const cb = callbacksRef.current;
        if (cb?.jobId) {
          try {
            const statusResult = await cb.callApi<{ status?: string; ok?: boolean }>(
              `/api/status?job_id=${encodeURIComponent(cb.jobId)}`,
            );
            if (statusResult?.ok && statusResult?.status === "running") {
              cb.reconnectJob(cb.jobId);
              setDisconnected(false);
              disconnectedNotifyRef.current = false;
              notify("info", "任务仍在运行，已重新连接 SSE 进度流。");
              return;
            }
          } catch {
            console.warn("useJobState: status check failed, falling through");
          }
        }
        const autoMsg =
          trigger === "sse_exhausted"
            ? "连接中断超过 60 秒未响应，自动终止 BRAIN 平台任务。"
            : "状态刷新失败超过 60 秒未响应，自动终止 BRAIN 平台任务。";
        failMonitor(autoMsg);
        void cancelAmbiguousJob(
          trigger === "sse_exhausted" ? "sse_exhausted" : "status_failed",
          autoMsg,
        );
        setDisconnected(false);
        disconnectedNotifyRef.current = false;
        notify("error", autoMsg);
      }, DISCONNECTED_AUTO_CANCEL_MS);
    },
    [cancelAmbiguousJob, disconnected, failMonitor, notify, clearDisconnectedTimer, onReconnect],
  );

  const resumeWatchdog = useCallback(() => {
    if (!disconnected) return;
    clearDisconnectedTimer();
    setDisconnected(false);
    disconnectedNotifyRef.current = false;
    onReconnect();
    notify("info", "已恢复等待。系统将继续尝试重连…");
  }, [disconnected, clearDisconnectedTimer, notify, onReconnect]);

  const forceCancelDisconnected = useCallback(() => {
    if (!disconnected) return;
    clearDisconnectedTimer();
    const failureMsg = "用户确认终止连接中断的任务。";
    failMonitor(failureMsg);
    void cancelAmbiguousJob("sse_exhausted", failureMsg);
    setDisconnected(false);
    disconnectedNotifyRef.current = false;
    notify("error", "BRAIN 平台任务已被终止。");
  }, [disconnected, clearDisconnectedTimer, cancelAmbiguousJob, failMonitor, notify]);

  useEffect(() => {
    return () => {
      if (disconnectedTimerRef.current) {
        clearTimeout(disconnectedTimerRef.current);
      }
    };
  }, []);

  return {
    disconnected,
    enterDisconnectedState,
    resumeWatchdog,
    forceCancelDisconnected,
    clearDisconnectedTimer,
    setDisconnected,
  };
}
