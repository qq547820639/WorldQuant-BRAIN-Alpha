import { useCallback } from "react";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, hasCredentials, jobStatusMessage } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus } from "@/types";
import { saveResumeState } from "@/utils/resumeState";
import { saveJobId as saveSessionJobId, clearSavedJobId } from "@/hooks/useJobRecovery";
import { requestNotificationPermission } from "./useJobNotifications";

export interface JobLifecycleDeps {
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void },
  ) => void;
  credentials?: BrainCredentials;
  jobId: string | null;
  setJobId: React.Dispatch<React.SetStateAction<string | null>>;
  setRunning: React.Dispatch<React.SetStateAction<boolean>>;
  setStatus: React.Dispatch<React.SetStateAction<JobStatus | null>>;
  setProgressError: React.Dispatch<React.SetStateAction<string | null>>;
  setPollFailures: React.Dispatch<React.SetStateAction<number>>;
  clearDisconnectedTimer: () => void;
  setDisconnected: (disconnected: boolean) => void;
  addEventSlice: (msg: string) => void;
  api: ReturnType<typeof useApi>;
}

export function useJobLifecycle(deps: JobLifecycleDeps) {
  const {
    notify,
    credentials,
    jobId,
    setJobId,
    setRunning,
    setStatus,
    setProgressError,
    setPollFailures,
    clearDisconnectedTimer,
    setDisconnected,
    addEventSlice,
    api,
  } = deps;

  const startJob = useCallback(async (resume = false) => {
    requestNotificationPermission();

    if (!hasCredentials(credentials)) {
      const msg = "请先在左侧「连接与生产参数」面板填写 BRAIN 账户邮箱和密码，或粘贴 API Token，然后点击「测试连接」。";
      setProgressError(msg);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: msg, progress: { ...(prev.progress || {}), phase: "failed", status_message: msg, percent_complete: 100 } } : prev);
      setRunning(false);
      notify("warning", msg);
      return;
    }
    setPollFailures(0);
    setProgressError(null);
    clearDisconnectedTimer();
    setDisconnected(false);
    setStatus({
      job_id: "", task_id: "", status: "running", phase: "queued",
      progress: { phase: "queued", status_message: "正在启动非提交流水线验证。", percent_complete: 0 },
    });
    setRunning(true);
    const result = await api.call<{ job_id: string }>("/api/run", {
      method: "POST", body: JSON.stringify(buildRunPayload(resume, credentials)),
    });
    const jid = String(result?.job_id || "");
    if (result?.ok && jid) {
      setJobId(jid); saveSessionJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued",
        progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      saveResumeState({ lastPhase: "evaluate", lastPipelineJob: jid, lastError: null, lastConnectionOk: true });
      notify("info", `${resume ? "非提交续跑" : "非提交验证"}已启动`);
    } else {
      clearSavedJobId();
      setRunning(false); setPollFailures(0);
      const message = result ? jobStatusMessage(result, "启动验证流程失败") : "网络错误，请检查连接后重试";
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
      setJobId(null);
    }
  }, [api, credentials, notify, clearDisconnectedTimer, setDisconnected, setJobId, setRunning, setStatus, setProgressError, setPollFailures]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call<{ ok?: boolean; error?: string; error_code?: string }>("/api/production-validation/stop", { method: "POST", body: JSON.stringify({ job_id: stoppedJobId }) });
    if (!result || result.ok === false) {
      const message = result ? jobStatusMessage(result, "停止请求失败，后台状态仍未确认。") : "停止请求失败，后台状态仍未确认。";
      setProgressError(message);
      setStatus((prev) => ({
        ...(prev || {}), job_id: stoppedJobId,
        status: "running",
        progress: {
          ...(prev?.progress || {}),
          phase: prev?.progress?.phase || prev?.phase || "running",
          status_message: message,
          percent_complete: prev?.progress?.percent_complete,
        },
      }));
      addEventSlice(`停止失败: ${message}`);
      notify("error", message);
      return;
    }
    clearSavedJobId();
    setRunning(false); setJobId(null);
    setStatus((prev) => ({
      ...(prev || {}), job_id: stoppedJobId,
      status: "stopped",
      progress: { ...(prev?.progress || {}), phase: "stopped", status_message: "验证流程已停止", percent_complete: prev?.progress?.percent_complete },
    }));
    setProgressError(null);
    addEventSlice("验证流程已停止");
    notify("info", "验证流程已停止");
  }, [api, jobId, notify, setJobId, setRunning, setStatus, setProgressError, addEventSlice]);

  return {
    startJob,
    stopJob,
  };
}
