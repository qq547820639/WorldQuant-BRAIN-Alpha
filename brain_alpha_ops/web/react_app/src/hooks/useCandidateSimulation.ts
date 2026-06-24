import { useCallback, useRef } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import type { SSEEvent, Candidate } from "@/types";
import {
  candidateIdentity,
  simulationResultSummary,
  simulationCompletionMessage,
  simulationCandidateIds,
  workflowCandidatesForQueue,
  type CandidateWorkflowPlan,
} from "@/components/CandidateTableUtils";
import type { CandidatePipeline } from "./useCandidatePipeline";

const AUTO_SIMULATION_BATCH_SIZE = 3;

export interface CandidateSimulationDeps {
  pipeline: CandidatePipeline;
  callApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
  loadCandidates: () => Promise<{
    rows: Candidate[];
    mainPoolCandidates: Candidate[] | null;
    snapshot: import("@/components/CandidateTableUtils").CandidatePoolSnapshot;
    workflowPlan?: CandidateWorkflowPlan | null;
  } | null>;
  onCandidatePoolUpdated?: () => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  buildCredentialOverrides: () => Record<string, string>;
  candidates: Candidate[];
  retainedPoolCandidates: Candidate[];
  serverWorkflowPlan: CandidateWorkflowPlan | null;
}

export function useCandidateSimulation(deps: CandidateSimulationDeps) {
  const {
    pipeline,
    callApi,
    loadCandidates,
    onCandidatePoolUpdated,
    notify,
    buildCredentialOverrides,
    candidates,
    retainedPoolCandidates,
    serverWorkflowPlan,
  } = deps;

  const nextBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);

  const startSimulation = useCallback(async (candidate?: Candidate, candidateOverride?: Candidate[]) => {
    pipeline.simulation.setState("loading"); pipeline.simulation.setError(null);
    const alphaId = candidate ? candidateIdentity(candidate) : "";
    pipeline.simulation.setProgress({ phase: "simulation_start", status_message: alphaId ? `正在启动单个候选 ${alphaId} 的官方模拟请求。` : "正在启动官方模拟请求。" });
    const payload: Record<string, unknown> = { ...buildCredentialOverrides() };
    if (alphaId) {
      payload.candidate_ids = [alphaId]; payload.max_simulations = 1;
      nextBatchCheckCandidatesRef.current = null;
    } else {
      const hasExplicitOverride = Boolean(candidateOverride && candidateOverride.length);
      const candidatesForSimulation = hasExplicitOverride
        ? candidateOverride || []
        : workflowCandidatesForQueue(candidates, retainedPoolCandidates, serverWorkflowPlan?.validator?.next_candidate_ids);
      const cIds = simulationCandidateIds(candidatesForSimulation, AUTO_SIMULATION_BATCH_SIZE);
      if (cIds.length) {
        payload.candidate_ids = cIds; payload.max_simulations = Math.min(AUTO_SIMULATION_BATCH_SIZE, cIds.length);
        nextBatchCheckCandidatesRef.current = cIds
          .map((id) => candidatesForSimulation.find((row) => candidateIdentity(row) === id))
          .filter((row): row is Candidate => Boolean(row));
      } else {
        const message = "候选池暂无可进入官方验证队列的候选，请先自动推进候选池或优化返工队列。";
        nextBatchCheckCandidatesRef.current = null; pipeline.updateAutoPipelineStage("idle");
        pipeline.simulation.setState("error"); pipeline.simulation.setError(message);
        pipeline.simulation.setProgress({ phase: "simulation_start", status_message: message, percent_complete: 100 });
        notify("warning", message);
        return;
      }
    }
    const result = await callApi<{ job_id: string; task_id?: string }>("/api/candidates/simulate", { method: "POST", body: JSON.stringify(payload) });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      pipeline.simulation.setJobId(nextJobId); pipeline.simulation.setState("progress");
      notify("info", alphaId ? `单个候选 ${alphaId} 的官方模拟已启动。` : "官方模拟已启动，可在本页查看进度。");
    } else {
      const message = apiErrorMessage(result, "启动官方模拟失败");
      pipeline.simulation.setState("error"); pipeline.updateAutoPipelineStage("idle"); pipeline.simulation.setError(message);
      nextBatchCheckCandidatesRef.current = null;
      notify("error", message);
    }
  }, [callApi, buildCredentialOverrides, candidates, notify, retainedPoolCandidates, serverWorkflowPlan, pipeline]);

  const startOfficialValidationQueue = useCallback(() => {
    pipeline.updateAutoPipelineStage("await_quality_check");
    void startSimulation();
  }, [startSimulation, pipeline]);

  const handleSimEvent = useCallback((event: SSEEvent, startBatchCheck?: (candidateOverride?: Candidate[]) => Promise<void>) => {
    try {
      const progress = event.progress || event.data || {};
      pipeline.simulation.setProgress(progress as import("@/types").UnifiedProgress);
      const outcome = resolveJobEventState(event, progress, { failed: "BRAIN模拟失败", interrupted: "BRAIN模拟已停止，结果未确认完成。" });
      if (outcome.kind === "failed") {
        pipeline.simulation.setState("error"); pipeline.simulation.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        nextBatchCheckCandidatesRef.current = null; notify(outcome.notifyType, outcome.message); pipeline.simulation.setJobId(null);
        return;
      }
      if (outcome.kind === "interrupted") {
        pipeline.simulation.setState("error"); pipeline.simulation.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        nextBatchCheckCandidatesRef.current = null; notify(outcome.notifyType, outcome.message); pipeline.simulation.setJobId(null);
        void loadCandidates().then(() => onCandidatePoolUpdated?.());
        return;
      }
      if (outcome.kind === "success") {
        const result = simulationResultSummary(event);
        const message = simulationCompletionMessage(result);
        const simulationSucceeded = result.completed > 0;
        if (!simulationSucceeded) {
          pipeline.simulation.setState("error"); pipeline.simulation.setError(message); notify("error", message);
        } else {
          pipeline.simulation.setState("success"); notify(result.failed > 0 ? "warning" : outcome.notifyType, message);
        }
        pipeline.simulation.setJobId(null);
        if (pipeline.autoPipelineStageRef.current === "await_quality_check" && simulationSucceeded) {
          const cForCheck = nextBatchCheckCandidatesRef.current || undefined;
          nextBatchCheckCandidatesRef.current = null;
          if (startBatchCheck) {
            void startBatchCheck(cForCheck);
          }
        } else {
          nextBatchCheckCandidatesRef.current = null;
          pipeline.resetAutoPipelineStageIfCurrent("await_quality_check");
        }
        void loadCandidates().then(() => onCandidatePoolUpdated?.());
        return;
      }
      pipeline.simulation.setState("progress");
    } catch (err) {
      console.error("SSE event handler error:", err);
      pipeline.simulation.setError("事件处理异常");
    }
  }, [loadCandidates, notify, onCandidatePoolUpdated, pipeline]);

  const handleSimStreamExhausted = useCallback(() => {
    if (!pipeline.simulation.jobId) return;
    const message = "BRAIN模拟进度通道已耗尽，正在请求后台自动中断；若官方请求已发出，将等待当前请求返回后更新状态。";
    void requestJobCancel({ jobId: pipeline.simulation.jobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "BRAIN模拟进度通道已耗尽，已确认后台停止该模拟任务。",
        missing: "BRAIN模拟监控对象已找不到，请刷新候选列表；若官方请求已发出，请等待当前请求返回。",
        unconfirmed: "BRAIN模拟进度通道已耗尽，已请求后台自动中断，但取消未确认；若官方请求已发出，请等待当前请求返回。",
      });
      pipeline.simulation.setError(cancelExperience.message);
      pipeline.simulation.setProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "official_simulation", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    pipeline.simulation.setState("error"); pipeline.simulation.setError(message); pipeline.updateAutoPipelineStage("idle");
    nextBatchCheckCandidatesRef.current = null; pipeline.simulation.setJobId(null);
    void loadCandidates();
  }, [loadCandidates, pipeline.simulation.jobId, pipeline]);

  return {
    startSimulation,
    startOfficialValidationQueue,
    handleSimEvent,
    handleSimStreamExhausted,
    nextBatchCheckCandidatesRef,
  };
}
