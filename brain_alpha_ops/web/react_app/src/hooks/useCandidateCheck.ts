import { useCallback, useRef } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import type { SSEEvent, Candidate } from "@/types";
import {
  candidateIdentity,
  type CandidatePoolSnapshot,
  type CandidateWorkflowPlan,
  type CandidateCheckResult,
} from "@/components/CandidateTableUtils";
import type { CandidatePipeline } from "./useCandidatePipeline";

type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };

export interface CandidateCheckDeps {
  pipeline: CandidatePipeline;
  callSingleCheckApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
  callBatchCheckApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
  loadCandidates: () => Promise<{
    rows: Candidate[];
    mainPoolCandidates: Candidate[] | null;
    snapshot: CandidatePoolSnapshot;
    workflowPlan?: CandidateWorkflowPlan | null;
  } | null>;
  refreshCheckResults: () => Promise<void>;
  onCandidatePoolUpdated?: () => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  buildCredentialOverrides: () => Record<string, string>;
  poolEligibleCandidates: Candidate[];
  retainedPoolCandidates: Candidate[];
  targetPoolSize: number;
  generateCandidates?: (poolSnapshot?: CandidatePoolSnapshot) => Promise<void>;
  startOptimization?: (poolSnapshot?: CandidatePoolSnapshot, candidateOverride?: Candidate[]) => Promise<boolean>;
  optimizationCandidatesForPool?: (rows: Candidate[], retainedCandidates: Candidate[], queueIds?: string[]) => Candidate[];
  autoOptimizationCycles: number;
  maxAutoOptimizationCycles: number;
  autoSimulationBatchSize: number;
}

export function useCandidateCheck(deps: CandidateCheckDeps) {
  const {
    pipeline,
    callSingleCheckApi,
    callBatchCheckApi,
    loadCandidates,
    refreshCheckResults,
    onCandidatePoolUpdated,
    notify,
    buildCredentialOverrides,
    poolEligibleCandidates,
    retainedPoolCandidates,
    targetPoolSize,
    generateCandidates,
    startOptimization,
    optimizationCandidatesForPool,
    autoOptimizationCycles,
    maxAutoOptimizationCycles,
    autoSimulationBatchSize,
  } = deps;

  const lastBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);

  const startSingleCheck = useCallback(async (candidate: Candidate) => {
    const alphaId = candidateIdentity(candidate);
    if (!alphaId) { notify("warning", "候选缺少 Alpha ID，无法执行单行补查。"); return; }
    pipeline.setCheckingAlphaId(alphaId); pipeline.check.setState("loading"); pipeline.check.setError(null);
    pipeline.check.setProgress({ phase: "single_candidate_check", status_message: `正在检查候选 ${alphaId} 的提交前阻断证据。` });
    const result = await callSingleCheckApi<CandidateCheckResult>("/api/check", { method: "POST", body: JSON.stringify({ ...buildCredentialOverrides(), mode: "quick", syncRange: "all", candidate }) });
    if (result?.ok) {
      pipeline.check.setState("success");
      pipeline.check.setProgress({ phase: "single_candidate_check", status_message: result.submittable ? `候选 ${alphaId} 已通过检查。` : `候选 ${alphaId} 检查完成，仍需处理阻断。`, percent_complete: 100 });
      notify(result.submittable ? "success" : "warning", result.submittable ? `候选 ${alphaId} 检查通过。` : `候选 ${alphaId} 检查完成，仍未提交就绪。`);
      await loadCandidates();
      onCandidatePoolUpdated?.();
    } else {
      const message = apiErrorMessage(result, "单行补查失败");
      pipeline.check.setState("error"); pipeline.check.setError(message);
      pipeline.check.setProgress({ phase: "single_candidate_check", status_message: message, percent_complete: 100 });
      notify("error", message);
    }
    pipeline.setCheckingAlphaId(null);
  }, [buildCredentialOverrides, callSingleCheckApi, loadCandidates, notify, onCandidatePoolUpdated, pipeline]);

  const startBatchCheck = useCallback(async (candidateOverride?: Candidate[]) => {
    const candidatesForCheck = candidateOverride && candidateOverride.length
      ? candidateOverride
      : retainedPoolCandidates.length ? retainedPoolCandidates : poolEligibleCandidates.slice(0, targetPoolSize);
    if (!candidatesForCheck.length) {
      lastBatchCheckCandidatesRef.current = null; pipeline.check.setState("success");
      pipeline.check.setProgress({ phase: "candidate_quality_check", status_message: "候选池暂无可检查候选。", percent_complete: 100 });
      pipeline.updateAutoPipelineStage("idle");
      return;
    }
    lastBatchCheckCandidatesRef.current = candidatesForCheck;
    pipeline.check.setState("loading"); pipeline.check.setError(null);
    pipeline.check.setProgress({ phase: "candidate_quality_check", status_message: `正在批量检查 ${candidatesForCheck.length} 个主池候选的质量门槛。` });
    const result = await callBatchCheckApi<AsyncJobStart>("/api/check_batch", { method: "POST", body: JSON.stringify({ ...buildCredentialOverrides(), mode: "quick", syncRange: "all", check_candidates: candidatesForCheck }) });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      pipeline.check.setJobId(nextJobId); pipeline.check.setState("progress");
      notify("info", "候选池质量门槛检查已启动。");
    } else {
      const message = apiErrorMessage(result, "启动质量门槛检查失败");
      pipeline.check.setState("error"); pipeline.updateAutoPipelineStage("idle"); pipeline.check.setError(message);
      notify("error", message);
    }
  }, [buildCredentialOverrides, callBatchCheckApi, notify, poolEligibleCandidates, retainedPoolCandidates, targetPoolSize, pipeline]);

  const handleCheckEvent = useCallback((event: SSEEvent) => {
    try {
      const progress = event.progress || event.data || {};
      pipeline.check.setProgress(progress as import("@/types").UnifiedProgress);
      const outcome = resolveJobEventState(event, progress, { failed: "质量门槛检查失败", interrupted: "质量门槛检查已停止，结果未确认完成。", success: "质量门槛检查完成。" });
      if (outcome.kind === "failed") {
        pipeline.check.setState("error"); pipeline.check.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        notify(outcome.notifyType, outcome.message); pipeline.check.setJobId(null);
        return;
      }
      if (outcome.kind === "interrupted") {
        pipeline.check.setState("error"); pipeline.check.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        notify(outcome.notifyType, outcome.message); pipeline.check.setJobId(null);
        void loadCandidates().then(() => onCandidatePoolUpdated?.());
        return;
      }
      if (outcome.kind === "success") {
        pipeline.check.setState("success"); pipeline.check.setJobId(null);
        const shouldContinueMaintenance = pipeline.autoPipelineStageRef.current === "await_quality_check";
        void loadCandidates().then((loaded) => {
          onCandidatePoolUpdated?.();
          if (shouldContinueMaintenance && loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
            if (optimizationCandidatesForPool && startOptimization && generateCandidates) {
              const reworkCandidates = optimizationCandidatesForPool(loaded.rows, loaded.snapshot.retainedCandidates, loaded.workflowPlan?.rework?.candidate_ids);
              if (autoOptimizationCycles < maxAutoOptimizationCycles && reworkCandidates.length) {
                notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，先优化 ${Math.min(reworkCandidates.length, autoSimulationBatchSize)} 个需优化候选。`);
                void startOptimization(loaded.snapshot, reworkCandidates);
                return;
              }
              notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`);
              void generateCandidates(loaded.snapshot);
            }
          } else {
            pipeline.resetAutoPipelineStageIfCurrent("await_quality_check");
          }
        });
        void refreshCheckResults();
        notify(outcome.notifyType, outcome.message);
        return;
      }
      pipeline.check.setState("progress");
    } catch (err) {
      console.error("SSE event handler error:", err);
      pipeline.check.setError("事件处理异常");
    }
  }, [generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, refreshCheckResults, pipeline, startOptimization, optimizationCandidatesForPool, autoOptimizationCycles, maxAutoOptimizationCycles, autoSimulationBatchSize]);

  const handleCheckStreamExhausted = useCallback(() => {
    if (!pipeline.check.jobId) return;
    const cancelledJobId = pipeline.check.jobId;
    const message = "质量门槛检查进度暂时不可确认，正在请求后台自动中断；请刷新状态后再重试。";
    pipeline.check.setState("error"); pipeline.check.setError(message); pipeline.updateAutoPipelineStage("idle"); pipeline.check.setJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "质量门槛检查进度暂时不可确认，已确认后台停止本次检查。",
        missing: "质量门槛检查监控对象已找不到，请刷新状态后再重试。",
        unconfirmed: "质量门槛检查进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      pipeline.check.setError(cancelExperience.message);
      pipeline.check.setProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "checking", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    notify("warning", message);
    void loadCandidates();
  }, [pipeline.check.jobId, loadCandidates, notify, pipeline]);

  return {
    startSingleCheck,
    startBatchCheck,
    handleCheckEvent,
    handleCheckStreamExhausted,
    lastBatchCheckCandidatesRef,
  };
}
