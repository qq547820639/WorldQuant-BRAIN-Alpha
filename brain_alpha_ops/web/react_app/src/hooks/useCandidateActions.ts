import { useCallback, useRef } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import type { SSEEvent, Candidate } from "@/types";
import {
  candidateIdentity,
  candidateNeedsOptimization,
  simulationResultSummary,
  simulationCompletionMessage,
  simulationCandidateIds,
  workflowCandidatesForQueue,
  rankPoolCandidates,
  type CandidatePoolSnapshot,
  type CandidateWorkflowPlan,
  type CandidateCheckResult,
} from "@/components/CandidateTableUtils";
import type { CandidatePipeline, AutoPipelineStage } from "./useCandidatePipeline";

const AUTO_SIMULATION_BATCH_SIZE = 3;
const MAX_AUTO_OPTIMIZATION_CYCLES = 1;

type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };
type CandidateOptimizationResult = {
  candidates?: Candidate[];
  returned_count?: number;
  optimized_count?: number;
  summary?: { automation?: Record<string, unknown> };
};

export interface CandidateActionsDeps {
  pipeline: CandidatePipeline;
  callApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
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
  credentials?: { username: string; password: string; token: string };
  candidates: Candidate[];
  retainedPoolCandidates: Candidate[];
  poolEligibleCandidates: Candidate[];
  serverWorkflowPlan: CandidateWorkflowPlan | null;
  targetPoolSize: number;
}

export interface CandidateActions {
  generateCandidates: (poolSnapshot?: CandidatePoolSnapshot) => Promise<void>;
  startSimulation: (candidate?: Candidate, candidateOverride?: Candidate[]) => Promise<void>;
  startOfficialValidationQueue: () => void;
  startOptimization: (poolSnapshot?: CandidatePoolSnapshot, candidateOverride?: Candidate[]) => Promise<boolean>;
  startSingleCheck: (candidate: Candidate) => Promise<void>;
  startBatchCheck: (candidateOverride?: Candidate[]) => Promise<void>;
  handleTaskEvent: (event: SSEEvent) => void;
  handleTaskStreamExhausted: () => void;
  handleSimEvent: (event: SSEEvent) => void;
  handleSimStreamExhausted: () => void;
  handleOptimizationEvent: (event: SSEEvent) => void;
  handleOptimizationStreamExhausted: () => void;
  handleCheckEvent: (event: SSEEvent) => void;
  handleCheckStreamExhausted: () => void;
  buildCredentialOverrides: () => Record<string, string>;
  nextBatchCheckCandidatesRef: React.MutableRefObject<Candidate[] | null>;
  lastBatchCheckCandidatesRef: React.MutableRefObject<Candidate[] | null>;
}

function optimizationCandidatesForPool(rows: Candidate[], retainedCandidates: Candidate[], queueIds?: string[]) {
  const serverQueued = workflowCandidatesForQueue(rows, [], queueIds).filter(candidateNeedsOptimization);
  if (serverQueued.length) return rankPoolCandidates(serverQueued);
  const seen = new Set<string>();
  const prioritized = [...retainedCandidates, ...rows];
  const selected: Candidate[] = [];
  for (const candidate of prioritized) {
    const id = candidateIdentity(candidate) || (candidate.expression || "");
    if (!id || seen.has(id) || !candidateNeedsOptimization(candidate)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return rankPoolCandidates(selected);
}

export function useCandidateActions(deps: CandidateActionsDeps): CandidateActions {
  const {
    pipeline,
    callApi,
    callSingleCheckApi,
    callBatchCheckApi,
    loadCandidates,
    refreshCheckResults,
    onCandidatePoolUpdated,
    notify,
    credentials,
    candidates,
    retainedPoolCandidates,
    poolEligibleCandidates,
    serverWorkflowPlan,
    targetPoolSize,
  } = deps;

  const nextBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);
  const lastBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);

  const buildCredentialOverrides = useCallback((): Record<string, string> => {
    const overrides: Record<string, string> = {};
    const username = credentials?.username.trim() || "";
    const password = credentials?.password || "";
    const token = credentials?.token.trim() || "";
    if (username) overrides.username = username;
    if (password) overrides.password = password;
    if (token) overrides.token = token;
    return overrides;
  }, [credentials]);

  const generateCandidates = useCallback(async (poolSnapshot?: CandidatePoolSnapshot) => {
    const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
    const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
    const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
    pipeline.setAutoOptimizationCycles((cycles) => (pipeline.autoPipelineStageRef.current === "idle" ? 0 : cycles));
    pipeline.task.setState("loading"); pipeline.task.setError(null);
    pipeline.setTaskSuccessBanner(null);
    pipeline.updateAutoPipelineStage("await_generation");
    pipeline.task.setProgress({ phase: "candidate_generation", status_message: "正在启动候选池自动推进。" });

    const result = await callApi<AsyncJobStart>("/api/generate_candidates", {
      method: "POST",
      body: JSON.stringify({ automation_mode: "maintain_candidate_pool", auto_simulate_after_generation: false, auto_check_after_simulation: false, target_pool_size: targetPoolSize, existing_pool_size: existingPoolSize, retained_pool_size: retainedPoolSize, pool_deficit: nextDeficit }),
    });
    const nextTaskId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextTaskId) {
      pipeline.task.setJobId(nextTaskId); pipeline.task.setState("progress");
      notify("info", "候选池自动推进已启动，会按目标池容量补充、预筛并继续非提交验证。");
    } else {
      pipeline.task.setState("error"); pipeline.updateAutoPipelineStage("idle");
      pipeline.task.setError(apiErrorMessage(result, "启动候选池自动推进失败"));
      notify("error", apiErrorMessage(result, "启动候选池自动推进失败"));
    }
  }, [callApi, notify, poolEligibleCandidates.length, retainedPoolCandidates.length, targetPoolSize, pipeline]);

  const handleTaskEvent = useCallback((event: SSEEvent) => {
    try {
      const progress = event.progress || event.data || {};
      pipeline.task.setProgress(progress as import("@/types").UnifiedProgress);
      const outcome = resolveJobEventState(event, progress, {
        failed: "候选池自动推进失败",
        interrupted: "候选池自动推进已停止，结果未确认完成。",
      });
      if (outcome.kind === "failed") {
        pipeline.task.setState("error"); pipeline.task.setError(outcome.message);
        pipeline.setTaskSuccessBanner(null);
        pipeline.updateAutoPipelineStage("idle"); notify(outcome.notifyType, outcome.message);
        return;
      }
      if (outcome.kind === "interrupted") {
        pipeline.task.setState("error"); pipeline.task.setError(outcome.message);
        pipeline.updateAutoPipelineStage("idle"); notify(outcome.notifyType, outcome.message);
        pipeline.task.setJobId(null);
        void loadCandidates().then(() => onCandidatePoolUpdated?.());
        return;
      }
      if (outcome.kind === "success") {
        pipeline.task.setState("success");
        const result = event.result as { candidates?: Candidate[]; candidates_preview?: Candidate[]; count?: number; new_candidates?: Candidate[]; optimized_candidates?: Candidate[] } | undefined;
        const rows = result?.candidates || [];
        if (rows.length) {
          // setCandidates is not available here; we rely on loadCandidates below
        }
        const newCount = Array.isArray(result?.new_candidates) ? result.new_candidates.length : (rows.length > 0 ? rows.length : 0);
        const optimizedCount = Array.isArray(result?.optimized_candidates) ? result.optimized_candidates.length : 0;
        pipeline.setTaskSuccessBanner({
          newCount,
          optimizedCount,
          message: outcome.message,
        });
        notify(outcome.notifyType, `候选池自动推进完成${result?.count ? `: ${result.count}` : ""}`);
        void loadCandidates().then(() => {
          onCandidatePoolUpdated?.();
          pipeline.resetAutoPipelineStageIfCurrent("await_generation");
        });
        pipeline.task.setJobId(null);
        return;
      }
      pipeline.task.setState("progress");
    } catch (err) {
      console.error("SSE event handler error:", err);
      pipeline.task.setError("事件处理异常");
    }
  }, [loadCandidates, notify, onCandidatePoolUpdated, pipeline]);

  const handleTaskStreamExhausted = useCallback(() => {
    if (!pipeline.task.jobId) return;
    const cancelledTaskId = pipeline.task.jobId;
    const message = "候选池自动推进进度暂时不可确认，正在请求后台自动中断；取消确认前请刷新状态后再重试。";
    pipeline.task.setState("error"); pipeline.task.setError(message);
    pipeline.updateAutoPipelineStage("idle"); pipeline.task.setJobId(null);
    pipeline.task.setProgress((current) => ({ ...(current || {}), phase: current?.phase || "candidate_generation", status_message: message, percent_complete: 100 }));
    void requestJobCancel({ jobId: cancelledTaskId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选池自动推进进度暂时不可确认，已确认后台停止本次推进。请刷新候选列表后再重试。",
        missing: "候选池自动推进监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选池自动推进进度暂时不可确认，已请求后台自动中断，但取消未确认。请刷新状态或稍后重试。",
      });
      pipeline.task.setError(cancelExperience.message);
      pipeline.task.setProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "candidate_generation", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, pipeline]);

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

  const startOptimization = useCallback(async (poolSnapshot?: CandidatePoolSnapshot, candidateOverride?: Candidate[]): Promise<boolean> => {
    const candidatesForOptimization = (candidateOverride && candidateOverride.length
      ? candidateOverride
      : optimizationCandidatesForPool(candidates, retainedPoolCandidates, serverWorkflowPlan?.rework?.candidate_ids)
    ).slice(0, AUTO_SIMULATION_BATCH_SIZE);
    if (!candidatesForOptimization.length) return false;
    const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
    const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
    const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
    pipeline.optimization.setState("loading"); pipeline.optimization.setError(null);
    pipeline.updateAutoPipelineStage("await_optimization");
    pipeline.setAutoOptimizationCycles((cycles) => cycles + 1);
    pipeline.optimization.setProgress({ phase: "candidate_optimization", status_message: `正在本地优化 ${candidatesForOptimization.length} 个需优化候选。` });
    const result = await callApi<AsyncJobStart>("/api/candidates/optimize", {
      method: "POST",
      body: JSON.stringify({ automation_mode: "maintain_candidate_pool", auto_simulate_after_optimization: false, auto_check_after_simulation: false, target_pool_size: targetPoolSize, existing_pool_size: existingPoolSize, retained_pool_size: retainedPoolSize, pool_deficit: nextDeficit, max_candidates: candidatesForOptimization.length, max_mutations: 3, keep_top: 2, candidates: candidatesForOptimization }),
    });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      pipeline.optimization.setJobId(nextJobId); pipeline.optimization.setState("progress");
      notify("info", "候选池本地优化已启动；产物会重新进入主池排序，不会触发提交。");
      return true;
    }
    const message = apiErrorMessage(result, "启动候选优化失败");
    pipeline.optimization.setState("error"); pipeline.updateAutoPipelineStage("idle"); pipeline.optimization.setError(message);
    notify("error", message);
    return false;
  }, [callApi, candidates, notify, poolEligibleCandidates.length, retainedPoolCandidates, serverWorkflowPlan, targetPoolSize, pipeline]);

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
            const reworkCandidates = optimizationCandidatesForPool(loaded.rows, loaded.snapshot.retainedCandidates, loaded.workflowPlan?.rework?.candidate_ids);
            if (pipeline.autoOptimizationCycles < MAX_AUTO_OPTIMIZATION_CYCLES && reworkCandidates.length) {
              notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，先优化 ${Math.min(reworkCandidates.length, AUTO_SIMULATION_BATCH_SIZE)} 个需优化候选。`);
              void startOptimization(loaded.snapshot, reworkCandidates);
              return;
            }
            notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`);
            void generateCandidates(loaded.snapshot);
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
  }, [generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, refreshCheckResults, pipeline, startOptimization]);

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

  const handleOptimizationEvent = useCallback((event: SSEEvent) => {
    try {
      const progress = event.progress || event.data || {};
      pipeline.optimization.setProgress(progress as import("@/types").UnifiedProgress);
      const outcome = resolveJobEventState(event, progress, { failed: "候选本地优化失败", interrupted: "候选本地优化已停止，结果未确认完成。" });
      if (outcome.kind === "failed") {
        pipeline.optimization.setState("error"); pipeline.optimization.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        notify(outcome.notifyType, outcome.message); pipeline.optimization.setJobId(null);
        return;
      }
      if (outcome.kind === "interrupted") {
        pipeline.optimization.setState("error"); pipeline.optimization.setError(outcome.message); pipeline.updateAutoPipelineStage("idle");
        notify(outcome.notifyType, outcome.message); pipeline.optimization.setJobId(null);
        void loadCandidates().then(() => onCandidatePoolUpdated?.());
        return;
      }
      if (outcome.kind === "success") {
        pipeline.optimization.setState("success"); pipeline.optimization.setJobId(null);
        const result = event.result as CandidateOptimizationResult | undefined;
        const optimizedRows = Array.isArray(result?.candidates) ? result.candidates : [];
        notify(outcome.notifyType, `候选本地优化完成: ${Number(result?.returned_count ?? optimizedRows.length)} 个子候选回池。`);
        void loadCandidates().then((loaded) => {
          onCandidatePoolUpdated?.();
          if (loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
            notify("info", `本地优化已回池；主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`);
            void generateCandidates(loaded.snapshot);
            return;
          }
          pipeline.resetAutoPipelineStageIfCurrent("await_optimization");
        });
        return;
      }
      pipeline.optimization.setState("progress");
    } catch (err) {
      console.error("SSE event handler error:", err);
      pipeline.optimization.setError("事件处理异常");
    }
  }, [generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, pipeline]);

  const handleOptimizationStreamExhausted = useCallback(() => {
    if (!pipeline.optimization.jobId) return;
    const cancelledJobId = pipeline.optimization.jobId;
    const message = "候选本地优化进度暂时不可确认，正在请求后台自动中断；请刷新状态后再重试。";
    pipeline.optimization.setState("error"); pipeline.optimization.setError(message); pipeline.updateAutoPipelineStage("idle"); pipeline.optimization.setJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选本地优化进度暂时不可确认，已确认后台停止本次优化。",
        missing: "候选本地优化监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选本地优化进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      pipeline.optimization.setError(cancelExperience.message);
      pipeline.optimization.setProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "candidate_optimization", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, pipeline]);

  const handleSimEvent = useCallback((event: SSEEvent) => {
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
          void startBatchCheck(cForCheck);
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
  }, [loadCandidates, notify, onCandidatePoolUpdated, pipeline, startBatchCheck]);

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
    generateCandidates,
    startSimulation,
    startOfficialValidationQueue,
    startOptimization,
    startSingleCheck,
    startBatchCheck,
    handleTaskEvent,
    handleTaskStreamExhausted,
    handleSimEvent,
    handleSimStreamExhausted,
    handleOptimizationEvent,
    handleOptimizationStreamExhausted,
    handleCheckEvent,
    handleCheckStreamExhausted,
    buildCredentialOverrides,
    nextBatchCheckCandidatesRef,
    lastBatchCheckCandidatesRef,
  };
}
