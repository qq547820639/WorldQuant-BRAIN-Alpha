/**
 * Candidate management table for the state-card UI.
 *
 * The table keeps the compact card-first workflow, but preserves the production
 * semantics users need before official validation or pre-submit blocker review checks.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { AlphaLifecycleHistoryResponse, AlphaLifecycleTrace, BrainCredentials, Candidate, SSEEvent, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

const DEFAULT_TARGET_POOL_SIZE = 10;
const MIN_TARGET_POOL_SIZE = 1;
const MAX_TARGET_POOL_SIZE = 100;
const AUTO_SIMULATION_BATCH_SIZE = 3;
const MAX_AUTO_OPTIMIZATION_CYCLES = 1;
const MAX_FILTER_LENGTH = 200;
const PAGE_SIZE = 20;
const SUBMIT_ONLY_BLOCKER_CODES = new Set([
  "decision_band_not_submit_candidate",
  "gate_not_submission_ready",
  "human_confirmation_required",
  "manual_confirmation_required",
  "missing_official_alpha_id",
  "missing_official_metrics",
  "missing_official_metric_fields",
  "needs_human_confirmation",
  "official_pass_fail_not_pass",
  "expression_too_nested",
]);
const RAW_CANDIDATE_DISPLAY_TEXT_PATTERN = /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|traceback|exception|stack trace|csrf[_-]?token|session[_-]?id|access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|pwd|token=|password=|api_key=|csrf_token=)/i;

type SortKey = "score" | "status" | "created";
export type CandidateQueueView =
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed";

type CandidateCheckResult = {
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  status?: string;
  passed?: boolean;
  submittable?: boolean;
  is_stale?: boolean;
  score?: number;
  failed_reasons?: string[];
  checked_at?: string;
};

type CandidateListMeta = {
  returned: number;
  total: number;
};

type SimulationResultSummary = {
  completed: number;
  failed: number;
  total: number;
};
type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };
type AutoPipelineStage = "idle" | "await_generation" | "await_quality_check" | "await_optimization";
type CandidateOptimizationResult = {
  candidates?: Candidate[];
  returned_count?: number;
  optimized_count?: number;
  summary?: { automation?: Record<string, unknown> };
};
type CandidatePoolSnapshot = {
  eligibleCount: number;
  retainedCount: number;
  deficit: number;
  retainedCandidates: Candidate[];
  workflowPlan?: CandidateWorkflowPlan | null;
};
type LoadedCandidateState = {
  rows: Candidate[];
  mainPoolCandidates: Candidate[] | null;
  snapshot: CandidatePoolSnapshot;
  workflowPlan?: CandidateWorkflowPlan | null;
};
type CandidateWorkflowQueue = {
  candidate_count?: number;
  candidate_ids?: string[];
  next_candidate_ids?: string[];
  deficit?: number;
  active_pool_count?: number;
  active_candidate_ids?: string[];
  replenish_needed?: boolean;
};
type CandidateWorkflowPlan = {
  schema_version?: string;
  next_action?: string;
  producer?: CandidateWorkflowQueue;
  validator?: CandidateWorkflowQueue & { next_batch_size?: number; batch_limit?: number };
  rework?: CandidateWorkflowQueue;
  archive?: CandidateWorkflowQueue;
  review?: CandidateWorkflowQueue;
  official_api_called?: boolean;
  submit_allowed?: boolean;
};

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  showProductionControls?: boolean;
  showRowActions?: boolean;
  credentials?: BrainCredentials;
  viewMode?: CandidateQueueView;
  onCandidatePoolUpdated?: () => void;
}

export default function CandidateTable({
  credentials,
  notify,
  onCandidatePoolUpdated,
  onScore,
  showProductionControls = true,
  showRowActions = false,
  viewMode = "candidates",
}: Props) {
  const api = useApi<{ candidates?: Candidate[]; items?: Candidate[]; main_pool_candidates?: Candidate[]; workflow_plan?: CandidateWorkflowPlan; candidate_workflow?: CandidateWorkflowPlan; returned_count?: number; total?: number; total_count?: number; partial?: boolean; warning?: string }>();
  const checkResultsApi = useApi<{ items?: CandidateCheckResult[] }>();
  const lifecycleApi = useApi<AlphaLifecycleHistoryResponse>();
  const singleCheckApi = useApi<CandidateCheckResult>();
  const batchCheckApi = useApi<AsyncJobStart>();
  const callApi = api.call;
  const callCheckResultsApi = checkResultsApi.call;
  const callLifecycleApi = lifecycleApi.call;
  const callSingleCheckApi = singleCheckApi.call;
  const callBatchCheckApi = batchCheckApi.call;
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [serverMainPoolCandidates, setServerMainPoolCandidates] = useState<Candidate[] | null>(null);
  const [serverWorkflowPlan, setServerWorkflowPlan] = useState<CandidateWorkflowPlan | null>(null);
  const [candidateMeta, setCandidateMeta] = useState<CandidateListMeta>({ returned: 0, total: 0 });
  const [checkResults, setCheckResults] = useState<Map<string, CandidateCheckResult>>(new Map());
  const [lifecycleHistory, setLifecycleHistory] = useState<AlphaLifecycleHistoryResponse | null>(null);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);

  const [filter, setFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);

  const [targetPoolSize, setTargetPoolSize] = useState(DEFAULT_TARGET_POOL_SIZE);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskState, setTaskState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [, setAutoPipelineStage] = useState<AutoPipelineStage>("idle");
  const autoPipelineStageRef = useRef<AutoPipelineStage>("idle");
  const updateAutoPipelineStage = useCallback((stage: AutoPipelineStage) => {
    autoPipelineStageRef.current = stage;
    setAutoPipelineStage(stage);
  }, []);
  const resetAutoPipelineStageIfCurrent = useCallback((stage: AutoPipelineStage) => {
    if (autoPipelineStageRef.current === stage) {
      updateAutoPipelineStage("idle");
    }
  }, [updateAutoPipelineStage]);
  const [autoOptimizationCycles, setAutoOptimizationCycles] = useState(0);

  // BRAIN simulation state
  const [simJobId, setSimJobId] = useState<string | null>(null);
  const [simState, setSimState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [simProgress, setSimProgress] = useState<UnifiedProgress | null>(null);
  const [simError, setSimError] = useState<string | null>(null);

  const [optimizationJobId, setOptimizationJobId] = useState<string | null>(null);
  const [optimizationState, setOptimizationState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [optimizationProgress, setOptimizationProgress] = useState<UnifiedProgress | null>(null);
  const [optimizationError, setOptimizationError] = useState<string | null>(null);

  const [checkingAlphaId, setCheckingAlphaId] = useState<string | null>(null);
  const [checkJobId, setCheckJobId] = useState<string | null>(null);
  const [checkState, setCheckState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [checkProgress, setCheckProgress] = useState<UnifiedProgress | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const nextBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);
  const lastBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);

  const loadCandidates = useCallback(async (): Promise<LoadedCandidateState | null> => {
    const [result, checkResultsResult, lifecycleResult] = await Promise.all([
      callApi("/api/candidates"),
      callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results"),
      callLifecycleApi<AlphaLifecycleHistoryResponse>("/api/alpha_lifecycle?limit=250"),
    ]);
    let loaded: LoadedCandidateState | null = null;
    if (result?.ok) {
      const nextRows = result.candidates || result.items || [];
      const nextMainPool = Array.isArray(result.main_pool_candidates) ? result.main_pool_candidates : null;
      const nextWorkflowPlan = result.workflow_plan || result.candidate_workflow || null;
      setCandidates((current) => (
        result.partial && nextRows.length === 0 && current.length > 0 ? current : nextRows
      ));
      setServerMainPoolCandidates(nextMainPool);
      setServerWorkflowPlan(nextWorkflowPlan);
      setCandidateMeta({
        returned: Number(result.returned_count ?? nextRows.length),
        total: Number(result.total ?? result.total_count ?? nextRows.length),
      });
      loaded = {
        rows: nextRows,
        mainPoolCandidates: nextMainPool,
        workflowPlan: nextWorkflowPlan,
        snapshot: candidatePoolSnapshot(nextRows, nextMainPool, targetPoolSize, nextWorkflowPlan),
      };
      if (result.partial) {
        notify("warning", result.warning || "候选账本暂不可用，当前仅为预览数据。");
      }
    } else if (result?.error) {
      notify("error", apiErrorMessage(result, "候选数据加载失败"));
    }
    if (checkResultsResult?.ok) {
      setCheckResults(indexCheckResults(checkResultsResult.items || []));
    } else if (checkResultsResult?.error) {
      notify("error", apiErrorMessage(checkResultsResult, "检查结果加载失败"));
    }
    if (lifecycleResult?.ok) {
      setLifecycleHistory(lifecycleResult);
      setLifecycleError(null);
    } else if (lifecycleResult) {
      setLifecycleError(apiErrorMessage(lifecycleResult, "生命周期历史加载失败"));
    } else {
      setLifecycleError("生命周期历史加载失败");
    }
    return loaded;
  }, [callApi, callCheckResultsApi, callLifecycleApi, notify, targetPoolSize]);

  const refreshCheckResults = useCallback(async () => {
    if (viewMode !== "submittable") return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results");
    if (result?.ok) {
      setCheckResults(indexCheckResults(result.items || []));
    } else if (result?.error) {
      notify("error", apiErrorMessage(result, "检查结果加载失败"));
    }
  }, [callCheckResultsApi, notify, viewMode]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  useEffect(() => {
    void refreshCheckResults();
  }, [refreshCheckResults]);

  const handleTaskEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setTaskProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "候选池自动推进失败",
      interrupted: "候选池自动推进已停止，结果未确认完成。",
    });

    if (outcome.kind === "failed") {
      const message = outcome.message;
      setTaskState("error");
      setTaskError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      return;
    }

    if (outcome.kind === "interrupted") {
      const message = outcome.message;
      setTaskState("error");
      setTaskError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      setTaskId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }

    if (outcome.kind === "success") {
      setTaskState("success");
      const result = event.result as {
        candidates?: Candidate[];
        candidates_preview?: Candidate[];
        count?: number;
      } | undefined;
      const rows = result?.candidates || [];
      if (rows.length) setCandidates(rows);
      const message = `候选池自动推进完成${result?.count ? `: ${result.count}` : ""}`;
      notify(outcome.notifyType, message);
      void loadCandidates().then(() => {
        onCandidatePoolUpdated?.();
        resetAutoPipelineStageIfCurrent("await_generation");
      });
      setTaskId(null);
      return;
    }

    setTaskState("progress");
  }, [loadCandidates, notify, onCandidatePoolUpdated, resetAutoPipelineStageIfCurrent, updateAutoPipelineStage]);

  const handleTaskStreamExhausted = useCallback(() => {
    if (!taskId) return;
    const cancelledTaskId = taskId;
    const message = "候选池自动推进进度暂时不可确认，正在请求后台自动中断；取消确认前请刷新状态后再重试。";
    setTaskState("error");
    setTaskError(message);
    updateAutoPipelineStage("idle");
    setTaskId(null);
    setTaskProgress((current) => ({
      ...(current || {}),
      phase: current?.phase || "candidate_generation",
      status_message: message,
      percent_complete: 100,
    }));
    void requestJobCancel({ jobId: cancelledTaskId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选池自动推进进度暂时不可确认，已确认后台停止本次推进。请刷新候选列表后再重试。",
        missing: "候选池自动推进监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选池自动推进进度暂时不可确认，已请求后台自动中断，但取消未确认。请刷新状态或稍后重试。",
      });
      const finalMessage = cancelExperience.message;
      setTaskError(finalMessage);
      setTaskProgress((current) => ({
        ...(current || {}),
        ...cancelExperience.progressPatch,
        phase: current?.phase || "candidate_generation",
        status_message: finalMessage,
        percent_complete: 100,
      }));
      notify(cancelExperience.notifyType, finalMessage);
    });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, taskId, updateAutoPipelineStage]);

  const taskStream = useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}` : null, {
    onEvent: handleTaskEvent,
    onExhausted: handleTaskStreamExhausted,
  });

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

  const poolEligibleCandidates = useMemo(
    () => (
      serverMainPoolCandidates
        ? rankPoolCandidates(serverMainPoolCandidates)
        : rankPoolCandidates(candidates.filter(candidateRetainedPoolEligible))
    ),
    [candidates, serverMainPoolCandidates],
  );
  const retainedPoolCandidates = useMemo(
    () => poolEligibleCandidates.slice(0, targetPoolSize),
    [poolEligibleCandidates, targetPoolSize],
  );

  const generateCandidates = useCallback(async (poolSnapshot?: CandidatePoolSnapshot) => {
    const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
    const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
    const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
    setAutoOptimizationCycles((cycles) => (autoPipelineStageRef.current === "idle" ? 0 : cycles));
    setTaskState("loading");
    setTaskError(null);
    updateAutoPipelineStage("await_generation");
    setTaskProgress({ phase: "candidate_generation", status_message: "正在启动候选池自动推进。" });

    const result = await callApi<AsyncJobStart>("/api/generate_candidates", {
      method: "POST",
      body: JSON.stringify({
        automation_mode: "maintain_candidate_pool",
        auto_simulate_after_generation: false,
        auto_check_after_simulation: false,
        target_pool_size: targetPoolSize,
        existing_pool_size: existingPoolSize,
        retained_pool_size: retainedPoolSize,
        pool_deficit: nextDeficit,
      }),
    });

    const nextTaskId = String(result?.task_id || result?.job_id || "");

    if (result?.ok && nextTaskId) {
      setTaskId(nextTaskId);
      setTaskState("progress");
      notify("info", "候选池自动推进已启动，会按目标池容量补充、预筛并继续非提交验证。");
    } else {
      const message = apiErrorMessage(result, "启动候选池自动推进失败");
      setTaskState("error");
      updateAutoPipelineStage("idle");
      setTaskError(message);
      notify("error", message);
    }
  }, [callApi, notify, poolEligibleCandidates.length, retainedPoolCandidates.length, targetPoolSize, updateAutoPipelineStage]);

  // BRAIN simulation handler
  const startSimulation = useCallback(async (candidate?: Candidate, candidateOverride?: Candidate[]) => {
    setSimState("loading");
    setSimError(null);
    const alphaId = candidate ? candidateIdentity(candidate) : "";
    setSimProgress({
      phase: "simulation_start",
      status_message: alphaId ? `正在启动单个候选 ${alphaId} 的官方模拟请求。` : "正在启动官方模拟请求。",
    });
    const payload: Record<string, unknown> = { ...buildCredentialOverrides() };
    if (alphaId) {
      payload.candidate_ids = [alphaId];
      payload.max_simulations = 1;
      nextBatchCheckCandidatesRef.current = null;
    } else {
      const hasExplicitOverride = Boolean(candidateOverride && candidateOverride.length);
      const candidatesForSimulation = hasExplicitOverride
        ? candidateOverride || []
        : workflowCandidatesForQueue(candidates, retainedPoolCandidates, serverWorkflowPlan?.validator?.next_candidate_ids);
      const candidateIds = simulationCandidateIds(candidatesForSimulation, AUTO_SIMULATION_BATCH_SIZE);
      if (candidateIds.length) {
        payload.candidate_ids = candidateIds;
        payload.max_simulations = Math.min(AUTO_SIMULATION_BATCH_SIZE, candidateIds.length);
        nextBatchCheckCandidatesRef.current = candidateIds
          .map((id) => candidatesForSimulation.find((row) => candidateIdentity(row) === id))
          .filter((row): row is Candidate => Boolean(row));
      } else {
        const message = "候选池暂无可进入官方验证队列的候选，请先自动推进候选池或优化返工队列。";
        nextBatchCheckCandidatesRef.current = null;
        updateAutoPipelineStage("idle");
        setSimState("error");
        setSimError(message);
        setSimProgress({
          phase: "simulation_start",
          status_message: message,
          percent_complete: 100,
        });
        notify("warning", message);
        return;
      }
    }

    const result = await callApi<{ job_id: string; task_id?: string }>("/api/candidates/simulate", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    const nextJobId = String(result?.task_id || result?.job_id || "");

    if (result?.ok && nextJobId) {
      setSimJobId(nextJobId);
      setSimState("progress");
      notify("info", alphaId ? `单个候选 ${alphaId} 的官方模拟已启动。` : "官方模拟已启动，可在本页查看进度。");
    } else {
      const message = apiErrorMessage(result, "启动官方模拟失败");
      setSimState("error");
      updateAutoPipelineStage("idle");
      setSimError(message);
      nextBatchCheckCandidatesRef.current = null;
      notify("error", message);
    }
  }, [callApi, buildCredentialOverrides, candidates, notify, retainedPoolCandidates, serverWorkflowPlan, updateAutoPipelineStage]);

  const startOfficialValidationQueue = useCallback(() => {
    updateAutoPipelineStage("await_quality_check");
    void startSimulation();
  }, [startSimulation, updateAutoPipelineStage]);

  const startOptimization = useCallback(async (
    poolSnapshot?: CandidatePoolSnapshot,
    candidateOverride?: Candidate[],
  ): Promise<boolean> => {
    const candidatesForOptimization = (candidateOverride && candidateOverride.length
      ? candidateOverride
      : optimizationCandidatesForPool(candidates, retainedPoolCandidates, serverWorkflowPlan?.rework?.candidate_ids)
    ).slice(0, AUTO_SIMULATION_BATCH_SIZE);
    if (!candidatesForOptimization.length) {
      return false;
    }
    const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
    const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
    const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
    setOptimizationState("loading");
    setOptimizationError(null);
    updateAutoPipelineStage("await_optimization");
    setAutoOptimizationCycles((cycles) => cycles + 1);
    setOptimizationProgress({
      phase: "candidate_optimization",
      status_message: `正在本地优化 ${candidatesForOptimization.length} 个需优化候选。`,
    });

    const result = await callApi<AsyncJobStart>("/api/candidates/optimize", {
      method: "POST",
      body: JSON.stringify({
        automation_mode: "maintain_candidate_pool",
        auto_simulate_after_optimization: false,
        auto_check_after_simulation: false,
        target_pool_size: targetPoolSize,
        existing_pool_size: existingPoolSize,
        retained_pool_size: retainedPoolSize,
        pool_deficit: nextDeficit,
        max_candidates: candidatesForOptimization.length,
        max_mutations: 3,
        keep_top: 2,
        candidates: candidatesForOptimization,
      }),
    });

    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      setOptimizationJobId(nextJobId);
      setOptimizationState("progress");
      notify("info", "候选池本地优化已启动；产物会重新进入主池排序，不会触发提交。");
      return true;
    }
    const message = apiErrorMessage(result, "启动候选优化失败");
    setOptimizationState("error");
    updateAutoPipelineStage("idle");
    setOptimizationError(message);
    notify("error", message);
    return false;
  }, [callApi, candidates, notify, poolEligibleCandidates.length, retainedPoolCandidates, serverWorkflowPlan, targetPoolSize, updateAutoPipelineStage]);

  const startSingleCheck = useCallback(async (candidate: Candidate) => {
    const alphaId = candidateIdentity(candidate);
    if (!alphaId) {
      notify("warning", "候选缺少 Alpha ID，无法执行单行补查。");
      return;
    }
    setCheckingAlphaId(alphaId);
    setCheckState("loading");
    setCheckError(null);
    setCheckProgress({
      phase: "single_candidate_check",
      status_message: `正在检查候选 ${alphaId} 的提交前阻断证据。`,
    });

    const result = await callSingleCheckApi<CandidateCheckResult>("/api/check", {
      method: "POST",
      body: JSON.stringify({
        ...buildCredentialOverrides(),
        mode: "quick",
        syncRange: "all",
        candidate,
      }),
    });

    if (result?.ok) {
      setCheckState("success");
      setCheckProgress({
        phase: "single_candidate_check",
        status_message: result.submittable ? `候选 ${alphaId} 已通过检查。` : `候选 ${alphaId} 检查完成，仍需处理阻断。`,
        percent_complete: 100,
      });
      setCheckResults((current) => indexCheckResults([...(current.values()), result]));
      notify(result.submittable ? "success" : "warning", result.submittable ? `候选 ${alphaId} 检查通过。` : `候选 ${alphaId} 检查完成，仍未提交就绪。`);
      await loadCandidates();
      onCandidatePoolUpdated?.();
    } else {
      const message = apiErrorMessage(result, "单行补查失败");
      setCheckState("error");
      setCheckError(message);
      setCheckProgress({
        phase: "single_candidate_check",
        status_message: message,
        percent_complete: 100,
      });
      notify("error", message);
    }
    setCheckingAlphaId(null);
  }, [buildCredentialOverrides, callSingleCheckApi, loadCandidates, notify, onCandidatePoolUpdated]);

  const startBatchCheck = useCallback(async (candidateOverride?: Candidate[]) => {
    const candidatesForCheck = candidateOverride && candidateOverride.length
      ? candidateOverride
      : retainedPoolCandidates.length
      ? retainedPoolCandidates
      : poolEligibleCandidates.slice(0, targetPoolSize);
    if (!candidatesForCheck.length) {
      lastBatchCheckCandidatesRef.current = null;
      setCheckState("success");
      setCheckProgress({
        phase: "candidate_quality_check",
        status_message: "候选池暂无可检查候选。",
        percent_complete: 100,
      });
      updateAutoPipelineStage("idle");
      return;
    }

    lastBatchCheckCandidatesRef.current = candidatesForCheck;
    setCheckState("loading");
    setCheckError(null);
    setCheckProgress({
      phase: "candidate_quality_check",
      status_message: `正在批量检查 ${candidatesForCheck.length} 个主池候选的质量门槛。`,
    });

    const result = await callBatchCheckApi<AsyncJobStart>("/api/check_batch", {
      method: "POST",
      body: JSON.stringify({
        ...buildCredentialOverrides(),
        mode: "quick",
        syncRange: "all",
        check_candidates: candidatesForCheck,
      }),
    });

    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      setCheckJobId(nextJobId);
      setCheckState("progress");
      notify("info", "候选池质量门槛检查已启动。");
    } else {
      const message = apiErrorMessage(result, "启动质量门槛检查失败");
      setCheckState("error");
      updateAutoPipelineStage("idle");
      setCheckError(message);
      notify("error", message);
    }
  }, [buildCredentialOverrides, callBatchCheckApi, notify, poolEligibleCandidates, retainedPoolCandidates, targetPoolSize, updateAutoPipelineStage]);

  const handleCheckEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setCheckProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "质量门槛检查失败",
      interrupted: "质量门槛检查已停止，结果未确认完成。",
      success: "质量门槛检查完成。",
    });

    if (outcome.kind === "failed") {
      const message = outcome.message;
      setCheckState("error");
      setCheckError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      setCheckJobId(null);
      return;
    }

    if (outcome.kind === "interrupted") {
      const message = outcome.message;
      setCheckState("error");
      setCheckError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      setCheckJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }

    if (outcome.kind === "success") {
      setCheckState("success");
      setCheckJobId(null);
      const shouldContinueMaintenance = autoPipelineStageRef.current === "await_quality_check";
      void loadCandidates().then((loaded) => {
        onCandidatePoolUpdated?.();
        if (shouldContinueMaintenance && loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
          const reworkCandidates = optimizationCandidatesForPool(
            loaded.rows,
            loaded.snapshot.retainedCandidates,
            loaded.workflowPlan?.rework?.candidate_ids,
          );
          if (autoOptimizationCycles < MAX_AUTO_OPTIMIZATION_CYCLES && reworkCandidates.length) {
            notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，先优化 ${Math.min(reworkCandidates.length, AUTO_SIMULATION_BATCH_SIZE)} 个需优化候选。`);
            void startOptimization(loaded.snapshot, reworkCandidates);
            return;
          }
          notify("info", `主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`);
          void generateCandidates(loaded.snapshot);
        } else {
          resetAutoPipelineStageIfCurrent("await_quality_check");
        }
      });
      void refreshCheckResults();
      notify(outcome.notifyType, outcome.message);
      return;
    }

    setCheckState("progress");
  }, [autoOptimizationCycles, generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, refreshCheckResults, resetAutoPipelineStageIfCurrent, startOptimization, updateAutoPipelineStage]);

  const handleCheckStreamExhausted = useCallback(() => {
    if (!checkJobId) return;
    const cancelledJobId = checkJobId;
    const message = "质量门槛检查进度暂时不可确认，正在请求后台自动中断；请刷新状态后再重试。";
    setCheckState("error");
    setCheckError(message);
    updateAutoPipelineStage("idle");
    setCheckJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "质量门槛检查进度暂时不可确认，已确认后台停止本次检查。",
        missing: "质量门槛检查监控对象已找不到，请刷新状态后再重试。",
        unconfirmed: "质量门槛检查进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      const finalMessage = cancelExperience.message;
      setCheckError(finalMessage);
      setCheckProgress((current) => ({
        ...(current || {}),
        ...cancelExperience.progressPatch,
        phase: current?.phase || "checking",
        status_message: finalMessage,
        percent_complete: 100,
      }));
      notify(cancelExperience.notifyType, finalMessage);
    });
    notify("warning", message);
    void loadCandidates();
  }, [checkJobId, loadCandidates, notify, updateAutoPipelineStage]);

  useSSE(checkJobId ? `/sse?job_id=${encodeURIComponent(checkJobId)}` : null, {
    onEvent: handleCheckEvent,
    onExhausted: handleCheckStreamExhausted,
  });

  const handleOptimizationEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setOptimizationProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "候选本地优化失败",
      interrupted: "候选本地优化已停止，结果未确认完成。",
    });

    if (outcome.kind === "failed") {
      const message = outcome.message;
      setOptimizationState("error");
      setOptimizationError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      setOptimizationJobId(null);
      return;
    }

    if (outcome.kind === "interrupted") {
      const message = outcome.message;
      setOptimizationState("error");
      setOptimizationError(message);
      updateAutoPipelineStage("idle");
      notify(outcome.notifyType, message);
      setOptimizationJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }

    if (outcome.kind === "success") {
      setOptimizationState("success");
      setOptimizationJobId(null);
      const result = event.result as CandidateOptimizationResult | undefined;
      const optimizedRows = Array.isArray(result?.candidates) ? result.candidates : [];
      notify(
        outcome.notifyType,
        `候选本地优化完成: ${Number(result?.returned_count ?? optimizedRows.length)} 个子候选回池。`,
      );
      void loadCandidates().then((loaded) => {
        onCandidatePoolUpdated?.();
        if (loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
          notify("info", `本地优化已回池；主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`);
          void generateCandidates(loaded.snapshot);
          return;
        }
        resetAutoPipelineStageIfCurrent("await_optimization");
      });
      return;
    }

    setOptimizationState("progress");
  }, [generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, resetAutoPipelineStageIfCurrent, updateAutoPipelineStage]);

  const handleOptimizationStreamExhausted = useCallback(() => {
    if (!optimizationJobId) return;
    const cancelledJobId = optimizationJobId;
    const message = "候选本地优化进度暂时不可确认，正在请求后台自动中断；请刷新状态后再重试。";
    setOptimizationState("error");
    setOptimizationError(message);
    updateAutoPipelineStage("idle");
    setOptimizationJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选本地优化进度暂时不可确认，已确认后台停止本次优化。",
        missing: "候选本地优化监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选本地优化进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      const finalMessage = cancelExperience.message;
      setOptimizationError(finalMessage);
      setOptimizationProgress((current) => ({
        ...(current || {}),
        ...cancelExperience.progressPatch,
        phase: current?.phase || "candidate_optimization",
        status_message: finalMessage,
        percent_complete: 100,
      }));
      notify(cancelExperience.notifyType, finalMessage);
    });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, optimizationJobId, updateAutoPipelineStage]);

  useSSE(optimizationJobId ? `/sse?job_id=${encodeURIComponent(optimizationJobId)}` : null, {
    onEvent: handleOptimizationEvent,
    onExhausted: handleOptimizationStreamExhausted,
  });

  // SSE stream for simulation progress
  const handleSimEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setSimProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "BRAIN模拟失败",
      interrupted: "BRAIN模拟已停止，结果未确认完成。",
    });

    if (outcome.kind === "failed") {
      const message = outcome.message;
      setSimState("error");
      setSimError(message);
      updateAutoPipelineStage("idle");
      nextBatchCheckCandidatesRef.current = null;
      notify(outcome.notifyType, message);
      setSimJobId(null);
      return;
    }

    if (outcome.kind === "interrupted") {
      const message = outcome.message;
      setSimState("error");
      setSimError(message);
      updateAutoPipelineStage("idle");
      nextBatchCheckCandidatesRef.current = null;
      notify(outcome.notifyType, message);
      setSimJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }

    if (outcome.kind === "success") {
      const result = simulationResultSummary(event);
      const message = simulationCompletionMessage(result);
      const simulationSucceeded = result.completed > 0;
      if (!simulationSucceeded) {
        setSimState("error");
        setSimError(message);
        notify("error", message);
      } else {
        setSimState("success");
        notify(result.failed > 0 ? "warning" : outcome.notifyType, message);
      }
      setSimJobId(null);
      if (autoPipelineStageRef.current === "await_quality_check" && simulationSucceeded) {
        const candidatesForCheck = nextBatchCheckCandidatesRef.current || undefined;
        nextBatchCheckCandidatesRef.current = null;
        void startBatchCheck(candidatesForCheck);
      } else {
        nextBatchCheckCandidatesRef.current = null;
        resetAutoPipelineStageIfCurrent("await_quality_check");
      }
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }

    setSimState("progress");
  }, [loadCandidates, notify, onCandidatePoolUpdated, resetAutoPipelineStageIfCurrent, startBatchCheck, updateAutoPipelineStage]);


  const handleSimStreamExhausted = useCallback(() => {
    if (!simJobId) return;
    const message = "BRAIN模拟进度通道已耗尽，正在请求后台自动中断；若官方请求已发出，将等待当前请求返回后更新状态。";
    void requestJobCancel({ jobId: simJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "BRAIN模拟进度通道已耗尽，已确认后台停止该模拟任务。",
        missing: "BRAIN模拟监控对象已找不到，请刷新候选列表；若官方请求已发出，请等待当前请求返回。",
        unconfirmed: "BRAIN模拟进度通道已耗尽，已请求后台自动中断，但取消未确认；若官方请求已发出，请等待当前请求返回。",
      });
      const finalMessage = cancelExperience.message;
      setSimError(finalMessage);
      setSimProgress((current) => ({
        ...(current || {}),
        ...cancelExperience.progressPatch,
        phase: current?.phase || "official_simulation",
        status_message: finalMessage,
        percent_complete: 100,
      }));
      notify(cancelExperience.notifyType, finalMessage);
    });
    setSimState("error");
    setSimError(message);
    updateAutoPipelineStage("idle");
    nextBatchCheckCandidatesRef.current = null;
    setSimJobId(null);
    void loadCandidates();
  }, [loadCandidates, simJobId, updateAutoPipelineStage]);

  useSSE(simJobId ? `/sse?job_id=${encodeURIComponent(simJobId)}` : null, {
    onEvent: handleSimEvent,
    onExhausted: handleSimStreamExhausted,
  });

  const rawQueueCandidates = useMemo(
    () => candidates.filter((candidate) => candidateMatchesQueueView(candidate, viewMode, checkResults)),
    [candidates, checkResults, viewMode],
  );
  const displayQueueCandidates = useMemo(
    () => (
      viewMode === "candidates"
        ? candidateManagementDisplayCandidates(candidates, retainedPoolCandidates, serverWorkflowPlan)
        : rawQueueCandidates
    ),
    [candidates, rawQueueCandidates, retainedPoolCandidates, serverWorkflowPlan, viewMode],
  );
  const visibleLifecycleTraces = useMemo(
    () => lifecycleTracesForCandidates(lifecycleHistory?.alpha_traces || [], displayQueueCandidates, filter),
    [displayQueueCandidates, filter, lifecycleHistory],
  );

  const sortedCandidates = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const filtered = normalizedFilter
      ? displayQueueCandidates.filter((c) =>
          candidateText(c.expression).toLowerCase().includes(normalizedFilter) ||
          candidateText(c.family).toLowerCase().includes(normalizedFilter) ||
          candidateIdentity(c).toLowerCase().includes(normalizedFilter) ||
          candidateQualitySearchText(c).toLowerCase().includes(normalizedFilter)
        )
      : displayQueueCandidates;

    return [...filtered].sort((a, b) => {
      let va: number;
      let vb: number;
      switch (sortKey) {
        case "score":
          va = a.scorecard?.total_score ?? 0;
          vb = b.scorecard?.total_score ?? 0;
          break;
        case "status":
          return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        case "created":
          va = candidateCreatedAt(a);
          vb = candidateCreatedAt(b);
          break;
        default:
          return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [displayQueueCandidates, filter, sortAsc, sortKey]);

  const summaryCandidates = displayQueueCandidates;
  const qualitySummary = useMemo(
    () => summarizeCandidateQuality(summaryCandidates, retainedPoolCandidates.length, targetPoolSize),
    [summaryCandidates, retainedPoolCandidates.length, targetPoolSize],
  );
  const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));
  const paginatedCandidates = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return sortedCandidates.slice(startIndex, startIndex + PAGE_SIZE);
  }, [currentPage, sortedCandidates]);
  const canShowRowActions = showRowActions && Boolean(onScore);

  useEffect(() => {
    setCurrentPage(1);
  }, [filter, sortKey, sortAsc, viewMode]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const handleTargetPoolSizeChange = (value: string) => {
    setTargetPoolSize(clampTargetPoolSize(value));
  };

  const handleFilterChange = (value: string) => {
    setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH));
  };

  const loading = api.loading && candidates.length === 0;
  const loadError = api.error;
  const visibleStart = sortedCandidates.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const visibleEnd = Math.min(currentPage * PAGE_SIZE, sortedCandidates.length);
  const title = viewMode === "candidates" ? "候选管理" : `${queueViewLabel(viewMode)}候选`;
  const remoteTruncated = candidateMeta.total > candidateMeta.returned;
  const hasActions = canShowRowActions || showProductionControls;
  const checkBusy = checkState === "loading" || checkState === "progress";
  const taskBusy = taskState === "loading" || taskState === "progress";
  const simulationBusy = simState === "loading" || simState === "progress";
  const optimizationBusy = optimizationState === "loading" || optimizationState === "progress";
  const candidateWorkflowBusy = taskBusy || simulationBusy || optimizationBusy || checkBusy;

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="候选管理"
        progress={{ phase: "candidate_load", status_message: "正在加载候选数据。" }}
      />
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-xl font-medium text-text-primary mb-1">{title}</h1>
      <p className="text-sm text-text-tertiary mb-4" role="status" aria-live="polite">
        {viewMode === "candidates"
          ? `主池 ${retainedPoolCandidates.length}/${targetPoolSize} · 可推进 ${poolEligibleCandidates.length} · 历史 ${rawQueueCandidates.length}`
          : `显示 ${sortedCandidates.length} / ${rawQueueCandidates.length} 个候选`}
        {candidateMeta.total > 0 && ` · 已返回 ${candidateMeta.returned}/${candidateMeta.total}`}
        {viewMode !== "candidates" && ` · ${queueViewLabel(viewMode)}`}
        {filter && " · 已过滤"}
      </p>

      {showProductionControls && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <label className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            目标池容量
            <input
              type="number"
              min={MIN_TARGET_POOL_SIZE}
              max={MAX_TARGET_POOL_SIZE}
              value={targetPoolSize}
              disabled={candidateWorkflowBusy}
              onChange={(event) => handleTargetPoolSizeChange(event.target.value)}
              className="form-input w-20"
            />
          </label>
          <button
            type="button"
            onClick={() => void generateCandidates()}
            disabled={candidateWorkflowBusy}
            className="btn btn-primary btn-sm"
            title="自动维护目标池容量，并在非提交边界内继续官方模拟与质量检查"
          >
            {taskState === "loading" || taskState === "progress" ? "推进中..." : "自动推进候选池"}
          </button>
          <button
            type="button"
            onClick={startOfficialValidationQueue}
            disabled={candidateWorkflowBusy}
            className="btn btn-secondary btn-sm"
            title="自动推进中断或单批证据缺失时使用；按 Top3 进入官方模拟后自动接质量门槛检查，不执行真实 Alpha submit"
          >
            {simState === "loading" || simState === "progress" ? "模拟中..." : "运行官方验证队列"}
          </button>
          <button
            type="button"
            onClick={() => void startOptimization()}
            disabled={candidateWorkflowBusy}
            className="btn btn-secondary btn-sm"
            title="根据服务端返工队列进行本地优化；不会携带凭据，也不会提交 Alpha"
          >
            {optimizationState === "loading" || optimizationState === "progress" ? "优化中..." : "优化返工队列"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
        <QualitySummaryItem label="主池保留" value={String(qualitySummary.retained)} />
        <QualitySummaryItem label="可推进" value={String(qualitySummary.promotable)} />
        <QualitySummaryItem label="需优化" value={String(qualitySummary.rework)} />
        <QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />
        <QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />
      </div>

      <LifecycleReplayPanel
        history={lifecycleHistory}
        error={lifecycleError}
        loading={lifecycleApi.loading}
        filterActive={Boolean(filter.trim())}
        visibleTraces={visibleLifecycleTraces}
      />

      {showProductionControls && taskState !== "idle" && (
        <ProgressFeedback
          state={taskStream.exhausted && taskState === "progress" ? "error" : taskState}
          title="候选池自动推进"
          progress={taskProgress}
          error={taskError || (taskStream.exhausted && taskState === "progress" ? "候选池自动推进状态不明确，取消未确认。" : null)}
          onRetry={() => void generateCandidates()}
          compact={taskState === "success"}
        />
      )}

      {showProductionControls && simState !== "idle" && (
        <ProgressFeedback
          state={simState}
          title="BRAIN官方模拟"
          progress={simProgress}
          error={simError}
          onRetry={() => startSimulation()}
          compact={simState === "success"}
        />
      )}

      {showProductionControls && optimizationState !== "idle" && (
        <ProgressFeedback
          state={optimizationState}
          title="候选本地优化"
          progress={optimizationProgress}
          error={optimizationError}
          onRetry={() => void startOptimization()}
          compact={optimizationState === "success"}
        />
      )}

      {showProductionControls && checkState !== "idle" && (
        <ProgressFeedback
          state={checkState}
          title="质量门槛检查"
          progress={checkProgress}
          error={checkError}
          onRetry={() => void startBatchCheck(lastBatchCheckCandidatesRef.current || undefined)}
          compact={checkState === "success"}
        />
      )}

      {remoteTruncated && (
        <div className="mb-4 px-3 py-2 text-xs rounded-md bg-warning-subtle text-warning" role="status" aria-live="polite">
          当前接口返回 {candidateMeta.returned} 条候选，服务端报告总量为 {candidateMeta.total} 条；请刷新或切换到完整候选源，避免把当前列表误认为全集。
        </div>
      )}

      {loadError && (
        <div className="panel mb-4" style={{ borderColor: "oklch(0.48 0.08 22 / 0.30)", background: "oklch(0.48 0.06 22 / 0.08)" }} role="alert" aria-live="assertive">
          <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="text-sm text-negative">加载候选失败: {loadError}</p>
            <button type="button" onClick={loadCandidates} className="btn btn-secondary btn-sm">重试</button>
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          type="text"
          aria-label="过滤候选"
          placeholder="按表达式、家族、ID、质量原因搜索..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) => handleFilterChange(event.target.value)}
          className="form-input flex-1"
        />
        <button type="button" onClick={loadCandidates} disabled={api.loading} className="btn btn-secondary btn-sm">
          {api.loading ? "刷新中..." : "刷新"}
        </button>
      </div>

      <div className="panel">
        {/* Mobile card list */}
        <div className="panel-body md:hidden">
          {paginatedCandidates.length === 0 ? (
            <EmptyState filter={!!filter} showProductionControls={showProductionControls} />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {paginatedCandidates.map((candidate, index) => (
                <CandidateMobileCard
                  key={`${candidateIdentity(candidate)}_mobile_${index}`}
                  candidate={candidate}
                  checkResults={checkResults}
                  canShowRowActions={canShowRowActions}
                  canSimulate={showProductionControls}
                  canCheck={showProductionControls}
                  workflowBusy={candidateWorkflowBusy}
                  simulationBusy={candidateWorkflowBusy}
                  checkingAlphaId={checkingAlphaId}
                  checkBusy={candidateWorkflowBusy}
                  onScore={onScore}
                  onSimulate={startSimulation}
                  onCheck={startSingleCheck}
                />
              ))}
            </div>
          )}
        </div>

        {/* Desktop table */}
        <div className="hidden md:block" style={{ maxWidth: "100%", overflow: "auto" }}>
          <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
            <thead>
              <tr>
                <th style={{ width: "8rem" }}>ID</th>
                <th style={{ width: "20rem" }}>表达式</th>
                <SortHeader column="score" label="评分" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader column="status" label="状态" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <th style={{ width: "7rem" }}>质量</th>
                <th style={{ width: "14rem" }}>阻断原因</th>
                <th style={{ width: "18rem" }}>输出</th>
                <th style={{ width: "16rem" }}>官方证据</th>
                {hasActions && <th style={{ width: "10rem" }}>操作</th>}
              </tr>
            </thead>
            <tbody>
              {paginatedCandidates.length === 0 ? (
                <tr>
                  <td colSpan={hasActions ? 9 : 8} style={{ padding: "1.5rem", textAlign: "center" }}>
                    <EmptyState filter={!!filter} showProductionControls={showProductionControls} />
                  </td>
                </tr>
              ) : (
                paginatedCandidates.map((candidate, index) => {
                  const quality = candidateQualityBadge(candidate);
                  const evidence = officialEvidenceText(candidate, checkResults);
                  return (
                    <tr key={`${candidateIdentity(candidate)}_${index}`}>
                      <td className="id">{candidateIdentity(candidate).slice(0, 16) || "--"}</td>
                      <td>
                        <div className="font-mono text-xs text-text-secondary break-words" title={candidateText(candidate.expression)}>
                          {candidateText(candidate.expression) || "--"}
                        </div>
                        <div className="text-2xs text-text-tertiary mt-1">{safeCandidateDisplayText(candidate.family, "家族待确认")}</div>
                      </td>
                      <td className="num" style={{ fontWeight: 500, color: "oklch(0.92 0.003 45)" }}>
                        {candidate.scorecard?.total_score?.toFixed(1) ?? "--"}
                      </td>
                      <td>
                        <span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>
                          {candidateStatus(candidate) || "--"}
                        </span>
                      </td>
                      <td><span className={`badge ${quality.tone}`} title={quality.title}>{quality.label}</span></td>
                      <td className="text-xs text-text-secondary">{candidateBlockerText(candidate)}</td>
                      <td className="text-xs">
                        <div className="font-medium text-text-primary">{candidateOutputSummary(candidate)}</div>
                        <div className="text-text-tertiary mt-1">{candidateOutputDetail(candidate)}</div>
                      </td>
                      <td className="text-xs">
                        <div className="text-text-secondary">{evidence}</div>
                        <div className="text-text-tertiary mt-1">{candidateText(candidate.simulation_id) || "simulation:--"}</div>
                      </td>
                      {hasActions && (
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {canShowRowActions && (
                              <button type="button" className="btn btn-ghost btn-sm"
                                aria-label={`评分 ${candidateIdentity(candidate)}`}
                                disabled={candidateWorkflowBusy}
                                onClick={() => onScore?.(candidate)}>
                                评分
                              </button>
                            )}
                            {showProductionControls && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                aria-label={`单行补查 ${candidateIdentity(candidate)}`}
                                disabled={candidateWorkflowBusy}
                                onClick={() => startSingleCheck(candidate)}
                              >
                                {checkingAlphaId === candidateIdentity(candidate) ? "检查中..." : "单行补查"}
                              </button>
                            )}
                            {showProductionControls && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                aria-label={`单行补模拟 ${candidateIdentity(candidate)}`}
                                disabled={candidateWorkflowBusy}
                                onClick={() => startSimulation(candidate)}
                              >
                                单行补模拟
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border-subtle px-3.5 py-3">
          <div className="text-sm text-text-tertiary" role="status" aria-live="polite">
            显示 {visibleStart}-{visibleEnd}，共 {sortedCandidates.length} 条
          </div>
          {sortedCandidates.length > PAGE_SIZE && (
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1} className="btn btn-ghost btn-sm">上一页</button>
              <span className="text-sm text-text-secondary">{currentPage} / {totalPages}</span>
              <button type="button" onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="btn btn-ghost btn-sm">下一页</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SortHeader({ column, label, sortKey, sortAsc, onSort }: {
  column: SortKey; label: string; sortKey: SortKey; sortAsc: boolean; onSort: (column: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th scope="col" className={active ? "is-sorted" : "is-sortable"} style={{ width: "7rem" }}
      aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}>
      <button type="button" className="flex items-center gap-1" onClick={() => onSort(column)}>
        {label}
        <span className="text-accent" aria-hidden="true">{active ? (sortAsc ? "\u2191" : "\u2193") : ""}</span>
      </button>
    </th>
  );
}

function QualitySummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className="font-mono-value text-base font-medium text-text-primary">{value}</p>
    </div>
  );
}

function LifecycleReplayPanel({
  error,
  filterActive,
  history,
  loading,
  visibleTraces,
}: {
  error: string | null;
  filterActive: boolean;
  history: AlphaLifecycleHistoryResponse | null;
  loading: boolean;
  visibleTraces: AlphaLifecycleTrace[];
}) {
  const summary: NonNullable<AlphaLifecycleHistoryResponse["summary"]> = history?.summary || {};
  const recordCount = numericResultField(summary.record_count ?? history?.count);
  const alphaCount = numericResultField(summary.alpha_count);
  const traceRows = visibleTraces.slice(0, 4);
  return (
    <section className="panel mb-4" aria-label="生命周期回放">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span>生命周期回放</span>
          <span className="badge badge-neutral">本地只读</span>
          <span className="badge badge-neutral">非提交</span>
          {filterActive && <span className="badge badge-info">已过滤</span>}
        </div>
      </div>
      <div className="panel-body-padded">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}
        >
          <LifecycleMetric label="记录" value={loading && !history ? "..." : String(recordCount)} />
          <LifecycleMetric label="Alpha" value={String(alphaCount)} />
          <LifecycleMetric label="通过" value={String(numericResultField(summary.passed_count))} tone="text-positive" />
          <LifecycleMetric label="阻断/失败" value={`${numericResultField(summary.blocked_count)}/${numericResultField(summary.failed_count)}`} tone="text-negative" />
          <LifecycleMetric label="已提交" value={String(numericResultField(summary.submitted_count))} />
        </div>

        {error ? (
          <p className="mt-4 rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative" role="alert">
            {error}
          </p>
        ) : traceRows.length > 0 ? (
          <div className="mt-4 grid gap-2">
            {traceRows.map((trace) => (
              <div
                key={trace.trace_key || trace.expression_digest || trace.latest_event_at}
                className="rounded-md border border-border-subtle bg-surface-2 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-mono-value text-xs text-accent" title={lifecycleTraceTitle(trace)}>
                      {shortLifecycleTraceId(trace)}
                    </p>
                    <p className="mt-1 text-xs text-text-tertiary">
                      {candidateText(trace.latest_stage) || "--"} · {candidateText(trace.latest_status) || "--"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`badge ${lifecycleStatusBadgeClass(trace)}`}>{lifecycleStatusLabel(trace)}</span>
                    <span className="badge badge-neutral">{lifecycleNextActionLabel(trace.next_action)}</span>
                    <span className="font-mono-value text-xs text-text-tertiary">{numericResultField(trace.event_count)} events</span>
                  </div>
                </div>
                {safeLifecycleNote(trace.last_note) && (
                  <p className="mt-2 truncate text-xs text-text-secondary" title={safeLifecycleNote(trace.last_note)}>
                    {safeLifecycleNote(trace.last_note)}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-xs text-text-tertiary">
            {loading ? "正在读取生命周期历史。" : "暂无匹配的生命周期记录。"}
          </p>
        )}
      </div>
    </section>
  );
}

function LifecycleMetric({ label, tone = "text-text-primary", value }: { label: string; tone?: string; value: string }) {
  return (
    <div className="min-w-0 border-l border-border-subtle pl-3">
      <p className="text-2xs font-semibold uppercase tracking-wider text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-base font-medium ${tone}`}>{value}</p>
    </div>
  );
}

function CandidateMobileCard({
  candidate,
  checkResults,
  canShowRowActions,
  canSimulate,
  canCheck,
  workflowBusy,
  simulationBusy,
  checkingAlphaId,
  checkBusy,
  onScore,
  onSimulate,
  onCheck,
}: {
  candidate: Candidate;
  checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean;
  canSimulate: boolean;
  canCheck: boolean;
  workflowBusy: boolean;
  simulationBusy: boolean;
  checkingAlphaId: string | null;
  checkBusy: boolean;
  onScore?: (candidate: Candidate) => void;
  onSimulate?: (candidate: Candidate) => void;
  onCheck?: (candidate: Candidate) => void;
}) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  const identity = candidateIdentity(candidate);
  const hasActions = canShowRowActions || canSimulate || canCheck;
  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="text-xs font-mono text-info">{candidateIdentity(candidate).slice(0, 24) || "--"}</p>
          <p className="text-xs font-mono text-text-secondary mt-2 break-words">{candidateText(candidate.expression) || "--"}</p>
        </div>
        <span className={`badge shrink-0 ${quality.tone}`}>{quality.label}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12, fontSize: "0.75rem" }}>
        <div><span className="text-text-tertiary">评分</span><p className="font-mono-value text-text-primary">{candidate.scorecard?.total_score?.toFixed(1) ?? "--"}</p></div>
        <div><span className="text-text-tertiary">状态</span><p className="mt-1"><span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>{candidateStatus(candidate) || "--"}</span></p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">阻断原因</span><p className="text-text-secondary break-words">{candidateBlockerText(candidate)}</p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">官方证据</span><p className="text-text-secondary break-words">{evidence}</p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">输出</span><p className="text-text-primary">{candidateOutputSummary(candidate)}</p><p className="text-text-tertiary">{candidateOutputDetail(candidate)}</p></div>
      </div>
      {hasActions && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
          {canShowRowActions && (
            <button type="button" className="btn btn-ghost btn-sm" style={{ width: "100%" }}
              aria-label={`评分 ${candidateIdentity(candidate)}`} disabled={workflowBusy} onClick={() => onScore?.(candidate)}>
              评分
            </button>
          )}
          {canCheck && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: "100%" }}
              aria-label={`单行补查 ${identity}`}
              disabled={checkBusy}
              onClick={() => onCheck?.(candidate)}
            >
              {checkingAlphaId === identity ? "检查中..." : "单行补查"}
            </button>
          )}
          {canSimulate && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: "100%" }}
              aria-label={`单行补模拟 ${identity}`}
              disabled={simulationBusy}
              onClick={() => onSimulate?.(candidate)}
            >
              单行补模拟
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function rankPoolCandidates(candidates: Candidate[]) {
  return [...candidates].sort((a, b) => candidatePoolRankScore(b) - candidatePoolRankScore(a));
}

function candidatePoolSnapshot(
  rows: Candidate[],
  mainPoolCandidates: Candidate[] | null,
  targetPoolSize: number,
  workflowPlan?: CandidateWorkflowPlan | null,
): CandidatePoolSnapshot {
  const eligible = mainPoolCandidates
    ? rankPoolCandidates(mainPoolCandidates)
    : rankPoolCandidates(rows.filter(candidateRetainedPoolEligible));
  const retained = eligible.slice(0, targetPoolSize);
  const producerDeficit = Number(workflowPlan?.producer?.deficit);
  return {
    eligibleCount: eligible.length,
    retainedCount: retained.length,
    deficit: Number.isFinite(producerDeficit) ? Math.max(0, Math.trunc(producerDeficit)) : Math.max(0, targetPoolSize - eligible.length),
    retainedCandidates: retained,
    workflowPlan,
  };
}

function simulationCandidateIds(candidates: Candidate[], limit: number) {
  const ids: string[] = [];
  for (const candidate of candidates) {
    const id = candidateIdentity(candidate);
    if (id && !ids.includes(id)) ids.push(id);
    if (ids.length >= limit) break;
  }
  return ids;
}

function workflowCandidatesForQueue(
  rows: Candidate[],
  fallbackCandidates: Candidate[],
  queueIds?: string[],
) {
  const ids = (queueIds || []).map((id) => candidateText(id).trim()).filter(Boolean);
  if (!ids.length) return fallbackCandidates;
  const byId = new Map<string, Candidate>();
  for (const candidate of [...rows, ...fallbackCandidates]) {
    for (const id of candidateIds(candidate)) {
      if (!byId.has(id)) byId.set(id, candidate);
    }
  }
  const queued = ids
    .map((id) => byId.get(id))
    .filter((candidate): candidate is Candidate => Boolean(candidate));
  return queued.length ? queued : fallbackCandidates;
}

function candidateManagementDisplayCandidates(
  rows: Candidate[],
  retainedCandidates: Candidate[],
  workflowPlan?: CandidateWorkflowPlan | null,
) {
  const queued = [
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.validator?.next_candidate_ids || workflowPlan?.validator?.candidate_ids),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.rework?.candidate_ids),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.review?.candidate_ids),
    ...rows.filter(candidateNeedsOptimization),
  ];
  return rankPoolCandidates(uniqueCandidatesByIdentity([...retainedCandidates, ...queued]));
}

function optimizationCandidatesForPool(rows: Candidate[], retainedCandidates: Candidate[], queueIds?: string[]) {
  const serverQueued = workflowCandidatesForQueue(rows, [], queueIds).filter(candidateNeedsOptimization);
  if (serverQueued.length) return rankPoolCandidates(serverQueued);
  const seen = new Set<string>();
  const prioritized = [...retainedCandidates, ...rows];
  const selected: Candidate[] = [];
  for (const candidate of prioritized) {
    const id = candidateIdentity(candidate) || candidateText(candidate.expression);
    if (!id || seen.has(id) || !candidateNeedsOptimization(candidate)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return rankPoolCandidates(selected);
}

function uniqueCandidatesByIdentity(candidates: Candidate[]) {
  const seen = new Set<string>();
  const selected: Candidate[] = [];
  for (const candidate of candidates) {
    const id = candidateIdentity(candidate) || candidateText(candidate.expression);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return selected;
}

function candidatePoolRankScore(candidate: Candidate) {
  const fallbackScore = (candidate as { score?: unknown }).score;
  const score = Number(candidate.scorecard?.total_score ?? fallbackScore ?? 0);
  return Number.isFinite(score) ? score : 0;
}

function candidateRetainedPoolEligible(candidate: Candidate) {
  const status = candidateStatus(candidate);
  if (candidate.production_decision?.action === "archive" || candidate.decision_action === "archive") return false;
  if (
    status === "submitted" ||
    status === "submission_ready" ||
    status.includes("simulation_failed") ||
    status.includes("official_standard_rejected") ||
    status.includes("local_prefilter_rejected") ||
    status.includes("local_standard_rejected") ||
    status.includes("candidate_pool_pruned") ||
    status.includes("high_cloud_similarity") ||
    status.includes("rejected") ||
    status.includes("failed")
  ) {
    return false;
  }
  if (status.includes("blocked") && !candidateHasSubmitOnlyBlockers(candidate)) {
    return false;
  }
  return !candidateHasLocalBlockingQuality(candidate);
}

function clampTargetPoolSize(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return MIN_TARGET_POOL_SIZE;
  return Math.min(Math.max(Math.trunc(parsed), MIN_TARGET_POOL_SIZE), MAX_TARGET_POOL_SIZE);
}

function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

function simulationResultSummary(event: SSEEvent): SimulationResultSummary {
  const result = record(event.result);
  const progress = record(event.progress);
  const data = record(progress.data);
  return {
    completed: numericResultField(result.completed ?? data.completed),
    failed: numericResultField(result.failed ?? data.failed),
    total: numericResultField(result.total ?? data.total),
  };
}

function numericResultField(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.trunc(number)) : 0;
}

function simulationCompletionMessage(result: SimulationResultSummary) {
  const total = result.total > 0 ? `，共 ${result.total} 个` : "";
  return `BRAIN模拟完成: ${result.completed} 成功, ${result.failed} 失败${total}`;
}

function indexCheckResults(rows: CandidateCheckResult[]) {
  const index = new Map<string, CandidateCheckResult>();
  for (const row of rows) {
    for (const id of candidateIds(row)) index.set(id, row);
  }
  return index;
}

function lifecycleTracesForCandidates(
  traces: AlphaLifecycleTrace[],
  candidates: Candidate[],
  filter: string,
) {
  const candidateIdSet = new Set<string>();
  for (const candidate of candidates) {
    candidateIds(candidate).forEach((id) => candidateIdSet.add(id));
  }
  const normalizedFilter = filter.trim().toLowerCase();
  return traces.filter((trace) => {
    const identities = lifecycleTraceIds(trace);
    const matchesCandidate = candidateIdSet.size === 0 || identities.some((id) => candidateIdSet.has(id));
    if (!matchesCandidate) return false;
    if (!normalizedFilter) return true;
    return lifecycleTraceSearchText(trace).includes(normalizedFilter);
  });
}

function lifecycleTraceIds(trace: AlphaLifecycleTrace) {
  return [trace.alpha_id, trace.official_alpha_id, trace.simulation_id, trace.trace_key]
    .map((value) => candidateText(value).trim())
    .filter(Boolean);
}

function lifecycleTraceSearchText(trace: AlphaLifecycleTrace) {
  return [
    ...lifecycleTraceIds(trace),
    trace.latest_stage,
    trace.latest_status,
    trace.status_category,
    trace.last_note,
    trace.next_action,
    trace.expression_digest,
    ...(trace.stages || []),
  ].map((value) => candidateText(value).toLowerCase()).join(" ");
}

function lifecycleStatusBadgeClass(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === "blocked") return "badge-negative";
  if (category === "failed") return "badge-negative";
  if (category === "submitted") return "badge-positive";
  if (category === "passed") return "badge-positive";
  if (trace.submitted) return "badge-positive";
  if (trace.passed) return "badge-positive";
  if (trace.blocked || trace.failed) return "badge-negative";
  return "badge-neutral";
}

function lifecycleStatusLabel(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === "blocked") return "阻断";
  if (category === "failed") return "失败";
  if (category === "submitted") return "已提交";
  if (category === "passed") return "通过";
  if (trace.submitted) return "已提交";
  if (trace.passed) return "通过";
  if (trace.blocked) return "阻断";
  if (trace.failed) return "失败";
  return category || "记录";
}

function lifecycleNextActionLabel(action: unknown) {
  const normalized = candidateText(action);
  const labels: Record<string, string> = {
    collect_official_identity: "补官方ID",
    continue_validation: "继续验证",
    monitor_official_result: "监控结果",
    optimize_or_archive: "优化/归档",
    review_blockers: "复核阻断",
  };
  return labels[normalized] || normalized || "继续审查";
}

function safeLifecycleNote(value: unknown) {
  const text = candidateText(value).trim();
  if (!text) return "";
  return text
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted]")
    .replace(/\b(username|account|email|password|passwd|pwd|token|auth_token|access_token|csrf_token|stream_token|session_id|cookie)\b\s*[:=]\s*[^,\s;]+/gi, "[redacted]")
    .replace(/\b(csrf-secret|session-secret|auth-secret|access-secret)\b/gi, "[redacted]")
    .replace(/\b(password|passwd|pwd|auth[_ -]?token|access[_ -]?token|csrf[_ -]?token|stream[_ -]?token|session[_ -]?id|cookie|secret)\b/gi, "[redacted]")
    .slice(0, 180);
}

function lifecycleTraceTitle(trace: AlphaLifecycleTrace) {
  return lifecycleTraceIds(trace).join(" / ") || trace.expression_digest || "";
}

function shortLifecycleTraceId(trace: AlphaLifecycleTrace) {
  const raw = lifecycleTraceIds(trace)[0] || trace.expression_digest || "unknown";
  return raw.length > 24 ? `${raw.slice(0, 24)}...` : raw;
}

function checkResultForCandidate(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  for (const id of candidateIds(candidate)) {
    const result = checkResults.get(id);
    if (result) return result;
  }
  return undefined;
}

function candidateMatchesQueueView(
  candidate: Candidate,
  viewMode: CandidateQueueView,
  checkResults: Map<string, CandidateCheckResult>,
) {
  if (viewMode === "candidates") return true;
  const status = candidateStatus(candidate);
  const stage = candidateStage(candidate);
  const result = checkResultForCandidate(candidate, checkResults);
  if (viewMode === "pending_backtest") return status === "pending_backtest";
  if (viewMode === "running_backtest") return status === "running_backtest" || status === "running";
  if (viewMode === "backtest_rework") return status === "backtest_rework" || status === "failed_backtest" || status === "rejected";
  if (viewMode === "passed") return candidateSubmissionReady(candidate);
  if (viewMode === "submittable") return status !== "submitted" && result?.is_stale !== true && Boolean(result?.submittable ?? result?.passed ?? candidate.quality_diagnosis?.submission_ready);
  if (viewMode === "submitted") return status === "submitted" || stage === "submitted";
  return (
    status === "failed" ||
    status === "rejected" ||
    status.includes("high_cloud_similarity") ||
    (status.includes("blocked") && !candidateHasSubmitOnlyBlockers(candidate)) ||
    candidateHasLocalBlockingQuality(candidate)
  );
}

function queueViewLabel(viewMode: CandidateQueueView) {
  const labels: Record<CandidateQueueView, string> = {
    candidates: "全部候选",
    pending_backtest: "等待回测",
    running_backtest: "回测中",
    backtest_rework: "需返工",
    passed: "已达标",
    submittable: "复核预检",
    submitted: "已提交",
    failed: "失败/阻断",
  };
  return labels[viewMode];
}

function candidateIdentity(candidate: Candidate) {
  return candidateIds(candidate)[0] || "";
}

function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CandidateCheckResult) {
  return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function candidateStatus(candidate: Candidate) {
  const normalized = candidateText(candidate.lifecycle_status || candidate.quality_diagnosis?.status || candidate.gate?.status);
  return normalized.toLowerCase();
}

function candidateStage(candidate: Candidate) {
  const submission = record(candidate.submission);
  return candidateText(submission.stage || submission.status || candidate.lifecycle_status).toLowerCase();
}

function candidateText(value: unknown) {
  return String(value || "");
}

function safeCandidateDisplayText(value: unknown, fallback: string) {
  const text = candidateText(value).trim();
  if (!text) return fallback;
  return RAW_CANDIDATE_DISPLAY_TEXT_PATTERN.test(text) ? fallback : text;
}

function candidateCreatedAt(candidate: Candidate) {
  return new Date(candidate.created_at || candidate.updated_at || 0).getTime();
}

function candidateQualitySearchText(candidate: Candidate) {
  return [
    candidateBlockerText(candidate),
    candidateOutputSummary(candidate),
    candidateOutputDetail(candidate),
    candidate.official_alpha_id,
    candidate.simulation_id,
    candidate.dataset_id,
  ].filter(Boolean).join(" ");
}

function candidateQualityBadge(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (candidateSubmissionReady(candidate)) {
    return { label: "达标", tone: "badge-positive", title: "符合提交前质量复核条件" };
  }
  if (candidateHasLocalBlockingQuality(candidate)) {
    return { label: "阻断", tone: "badge-negative", title: candidateBlockerText(candidate) };
  }
  if (diagnosis.qualified) {
    return { label: "待确认", tone: "badge-warning", title: "质量达标，但仍有提交前阻断需要处理" };
  }
  if (candidateNeedsOptimization(candidate)) {
    return { label: "需优化", tone: "badge-warning", title: candidateBlockerText(candidate) };
  }
  if (candidateLocalValid(candidate) || candidateRetainedPoolEligible(candidate)) {
    return { label: "可推进", tone: "badge-warning", title: "本地候选可继续补证据或挑战主池排序" };
  }
  return { label: "未验证", tone: "badge-neutral", title: "缺少质量诊断" };
}

function candidateBlockerText(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const primary = record(diagnosis.primary_reason);
  const primaryText = candidateText(primary.message || primary.code || primary.category);
  if (primaryText) return primaryText;
  const decisionEvidence = candidateDecisionEvidenceText(candidate);
  if (decisionEvidence) return decisionEvidence;
  if ((diagnosis.blocking_reasons || []).length) return (diagnosis.blocking_reasons || []).join("; ");
  if ((candidate.local_quality?.reasons || []).length) return candidate.local_quality?.reasons?.join("; ") || "";
  if ((candidate.gate?.failed_reasons || []).length) return candidate.gate?.failed_reasons?.join("; ") || "";
  if (candidate.local_quality?.passed === false) return "local_quality_failed";
  if (!candidate.quality_diagnosis) return "missing_quality_diagnosis";
  return "-";
}

function candidateDecisionEvidenceText(candidate: Candidate) {
  const evidence = candidate.production_decision?.decision_evidence;
  const lifecycleRisk = evidence?.lifecycle_risk;
  if (lifecycleRisk?.reason_code) {
    const status = candidateText(lifecycleRisk.latest_status || lifecycleRisk.latest_status_category).trim();
    const action = candidateText(lifecycleRisk.action_hint) === "archive" ? "归档" : "返工优化";
    return `历史证据: ${status || lifecycleRisk.reason_code}，需先${action}`;
  }
  const auditReasons = evidence?.scientific_audit_policy_reasons || evidence?.hard_blocking_reasons || [];
  if (auditReasons.length) {
    return `科学审计阻断: ${auditReasons.join("; ")}`;
  }
  if (candidate.production_decision?.reason && candidate.production_decision.action === "archive") {
    return candidate.production_decision.reason;
  }
  return "";
}

function candidateLocalValid(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (typeof diagnosis.local_candidate_valid === "boolean") {
    return diagnosis.local_candidate_valid;
  }
  return candidate.local_quality?.passed === true;
}

function candidateHasBlockingQuality(candidate: Candidate) {
  return candidateHasLocalBlockingQuality(candidate) || candidateNeedsOptimization(candidate);
}

function candidateHasLocalBlockingQuality(candidate: Candidate) {
  const localCodes = candidateBlockingCodes(candidate).filter((code) => !isSubmitOnlyBlockerText(code));
  const gateHardCodes = (candidate.gate?.failed_reasons || [])
    .map((reason) => candidateText(reason).trim())
    .filter((code) => code && !isSubmitOnlyBlockerText(code));
  return Boolean(
    localCodes.length ||
    candidate.local_quality?.passed === false ||
    candidate.local_quality?.local_backtest?.pass_local === false ||
    gateHardCodes.length
  );
}

function candidateHasSubmitOnlyBlockers(candidate: Candidate) {
  return candidateBlockingCodes(candidate).some(isSubmitOnlyBlockerText) ||
    (candidate.gate?.failed_reasons || []).some((reason) => isSubmitOnlyBlockerText(candidateText(reason).trim()));
}

function candidateNeedsOptimization(candidate: Candidate) {
  if (candidateSubmissionReady(candidate) || candidateHasLocalBlockingQuality(candidate)) return false;
  if (candidate.production_decision?.action === "optimize" || candidate.decision_action === "optimize") return true;
  const band = candidateText(candidate.scorecard?.decision_band || candidate.decision_band);
  return Boolean(
    (band && band !== "submit_candidate") ||
    candidateBlockingCodes(candidate).some(isSubmitOnlyBlockerText)
  );
}

function candidateBlockingCodes(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const codes = new Set<string>();
  const primary = record(diagnosis.primary_reason);
  const primaryCode = candidateText(primary.code);
  if (primaryCode) codes.add(primaryCode);
  for (const reason of diagnosis.blocking_reasons || []) {
    const code = candidateText(reason).trim();
    if (code) codes.add(code);
  }
  for (const row of diagnosis.reasons || []) {
    if (row?.severity && row.severity !== "blocking") continue;
    const code = candidateText(row?.code).trim();
    if (code) codes.add(code);
  }
  for (const reason of candidate.local_quality?.reasons || []) {
    const code = candidateText(reason).split(":", 1)[0].trim();
    if (code) codes.add(code);
  }
  return [...codes];
}

function isSubmitOnlyBlockerText(value: string) {
  const normalized = value.trim().toLowerCase().replace(/\s+/g, "_");
  if (SUBMIT_ONLY_BLOCKER_CODES.has(normalized)) return true;
  return (
    normalized.includes("decision_band") && normalized.includes("not_submit_candidate")
  ) || (
    normalized.includes("gate") && normalized.includes("not_submission_ready")
  ) || (
    normalized.includes("human") && normalized.includes("confirmation")
  ) || (
    normalized.includes("official_alpha_id") && normalized.includes("missing")
  ) || (
    normalized.includes("official") && normalized.includes("metric") && normalized.includes("missing")
  );
}

function candidateOutputSummary(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  if (config.local_only === true) return "本地输出";
  if (config.official_api_called === true) return "官方证据";
  if (config.allow_submit === false) return "禁止提交";
  return config.alpha_type || candidate.decision_band || "-";
}

function candidateOutputDetail(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  const settings = record(config.settings);
  const dataset = config.dataset_id || candidate.dataset_id || settings.dataset;
  const alphaType = config.alpha_type || settings.type;
  const official = config.official_api_called === true ? "official_called" : "official_not_called";
  return [dataset ? `dataset:${dataset}` : "", alphaType ? `type:${alphaType}` : "", official].filter(Boolean).join(" · ");
}

function officialEvidenceText(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  const result = checkResultForCandidate(candidate, checkResults);
  if (result) {
    const status = result.status || (result.submittable ? "submittable" : result.passed ? "passed" : "blocked");
    const stale = result.is_stale ? " · stale" : "";
    return `${candidateText(result.official_alpha_id || candidate.official_alpha_id || "official:-")} · ${status}${stale}`;
  }
  return candidateText(candidate.official_alpha_id || "official:-");
}

function summarizeCandidateQuality(candidates: Candidate[], retained: number, targetPoolSize: number) {
  const ready = candidates.filter(candidateSubmissionReady).length;
  const promotable = candidates.filter(candidateRetainedPoolEligible).length;
  const rework = candidates.filter(candidateNeedsOptimization).length;
  const blocked = candidates.filter(candidateHasLocalBlockingQuality).length;
  const outputModes = candidates.map(candidateOutputSummary).filter((value) => value && value !== "-");
  return {
    ready,
    retained: `${retained}/${targetPoolSize}`,
    promotable,
    rework,
    blocked,
    outputMode: mostCommon(outputModes) || "-",
  };
}

function candidateSubmissionReady(candidate: Candidate) {
  const status = candidateStatus(candidate);
  return Boolean(
    status === "submission_ready" ||
    candidate.quality_diagnosis?.submission_ready === true ||
    candidate.gate?.submission_ready === true
  );
}

function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("submitted") || normalized.includes("completed") || normalized.includes("candidate_pool_retained")) return "badge-positive";
  if (normalized.includes("failed") || normalized.includes("blocked") || normalized.includes("rejected")) return "badge-negative";
  if (normalized.includes("validat") || normalized.includes("simulat") || normalized.includes("running")) return "badge-warning";
  return "badge-neutral";
}

function mostCommon(values: unknown[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    const text = candidateText(value);
    if (!text) continue;
    counts.set(text, (counts.get(text) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

// ── Empty state with guidance ──────────────────────────────────────────────

function EmptyState({ filter, showProductionControls }: { filter: boolean; showProductionControls: boolean }) {
  if (filter) {
    return (
      <div style={{ padding: "2rem 0", color: "oklch(0.52 0.006 45)", fontSize: 13 }}>
        <p>没有匹配的候选</p>
        <p style={{ marginTop: 4, fontSize: 12 }}>
          尝试调整筛选条件，或清除筛选查看全部候选。
        </p>
      </div>
    );
  }

  if (showProductionControls) {
    return (
      <div style={{ padding: "1.5rem 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 48, height: 48, borderRadius: "50%",
          background: "oklch(0.65 0.08 80 / 0.12)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="oklch(0.68 0.10 82)" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
        </div>
        <div>
          <p style={{ color: "oklch(0.65 0.003 45)", fontSize: 14, fontWeight: 500 }}>暂无候选记录</p>
          <p style={{ color: "oklch(0.52 0.006 45)", fontSize: 12, marginTop: 4, lineHeight: 1.5, maxWidth: 320 }}>
            候选 Alpha 通过顶部「自动推进候选池」启动生产搜索、预筛与本地排序；官方验证队列和质量检查单独推进。
            全流程保持非提交边界，提交仍需人工确认。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "1.5rem 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <p style={{ color: "oklch(0.52 0.006 45)", fontSize: 13 }}>暂无候选记录</p>
      <p style={{ color: "oklch(0.44 0.006 45)", fontSize: 12, lineHeight: 1.5, maxWidth: 280 }}>
        请先运行非提交验证产生候选，或从候选管理页面选择一个候选进入评分。
      </p>
    </div>
  );
}
