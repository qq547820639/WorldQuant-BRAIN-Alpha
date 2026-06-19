/**
 * Candidate management table for the state-card UI.
 *
 * The table keeps the compact card-first workflow, but preserves the production
 * semantics users need before official validation or pre-submit blocker review checks.
 *
 * Refactored: extracted CandidateRow, CandidateTableToolbar, useCandidateColumns,
 * and CandidateDetailPanel into separate files.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { AlphaLifecycleHistoryResponse, Candidate, SSEEvent, UnifiedProgress } from "@/types";
import { getStarred } from "@/utils/starredCandidates";
import ProgressFeedback from "@/components/ProgressFeedback";
import {
  candidateIdentity,
  candidateStatus,
  candidateCreatedAt,
  candidateText,
  candidateQualitySearchText,
  candidateNeedsOptimization,
  candidateRetainedPoolEligible,
  clampTargetPoolSize,
  sanitizeTextInput,
  simulationResultSummary,
  simulationCompletionMessage,
  indexCheckResults,
  lifecycleTracesForCandidates,
  queueViewLabel,
  CandidateCheckResult,
  CandidateQueueView,
  CandidatePoolSnapshot,
  CandidateWorkflowPlan,
  CandidateListMeta,
  summarizeCandidateQuality,
  rankPoolCandidates,
  candidatePoolSnapshot,
  simulationCandidateIds,
  workflowCandidatesForQueue,
  candidateMatchesQueueView,
} from "./CandidateTableUtils";
import {
  CandidateMobileCard,
  EmptyState,
} from "./CandidateTableSubComponents";
import { CandidateRow } from "./CandidateRow";
import { CandidateTableToolbar } from "./CandidateTableToolbar";
import type { QualitySummaryData } from "./CandidateTableToolbar";
import { useCandidateColumns } from "./useCandidateColumns";

const DEFAULT_TARGET_POOL_SIZE = 10;
const AUTO_SIMULATION_BATCH_SIZE = 3;
const MAX_AUTO_OPTIMIZATION_CYCLES = 1;
const MAX_FILTER_LENGTH = 200;
const PAGE_SIZE = 20;

type SortKey = "score" | "status" | "created";

type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };
type AutoPipelineStage = "idle" | "await_generation" | "await_quality_check" | "await_optimization";
type CandidateOptimizationResult = {
  candidates?: Candidate[];
  returned_count?: number;
  optimized_count?: number;
  summary?: { automation?: Record<string, unknown> };
};
type LoadedCandidateState = {
  rows: Candidate[];
  mainPoolCandidates: Candidate[] | null;
  snapshot: CandidatePoolSnapshot;
  workflowPlan?: CandidateWorkflowPlan | null;
};

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  showProductionControls?: boolean;
  showRowActions?: boolean;
  credentials?: import("@/types").BrainCredentials;
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
  const [showStarredOnly, setShowStarredOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);

  const [targetPoolSize, setTargetPoolSize] = useState(DEFAULT_TARGET_POOL_SIZE);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskState, setTaskState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  // P2-3: Success banner data
  const [taskSuccessBanner, setTaskSuccessBanner] = useState<{ newCount: number; optimizedCount: number; message: string } | null>(null);
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

  // P1-4: cooldown ref for candidate pool deficit warnings (max 1 per 30 min)
  const lastPoolDeficitWarningRef = useRef<number>(0);
  const POOL_DEFICIT_WARNING_COOLDOWN_MS = 30 * 60 * 1000;

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
      // P1-4: candidate pool deficit warning with 30-min cooldown
      const eligibleCount = loaded.snapshot.eligibleCount;
      if (eligibleCount < targetPoolSize) {
        const now = Date.now();
        if (now - lastPoolDeficitWarningRef.current >= POOL_DEFICIT_WARNING_COOLDOWN_MS) {
          lastPoolDeficitWarningRef.current = now;
          notify("warning", `候选池不足: 当前合格候选 ${eligibleCount}，目标池容量 ${targetPoolSize}，建议启动候选池自动推进补充候选。`);
        }
      }
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

  useEffect(() => { void loadCandidates(); }, [loadCandidates]);
  useEffect(() => { void refreshCheckResults(); }, [refreshCheckResults]);

  const handleTaskEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setTaskProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "候选池自动推进失败",
      interrupted: "候选池自动推进已停止，结果未确认完成。",
    });
    if (outcome.kind === "failed") {
      setTaskState("error"); setTaskError(outcome.message);
      setTaskSuccessBanner(null);
      updateAutoPipelineStage("idle"); notify(outcome.notifyType, outcome.message);
      return;
    }
    if (outcome.kind === "interrupted") {
      setTaskState("error"); setTaskError(outcome.message);
      updateAutoPipelineStage("idle"); notify(outcome.notifyType, outcome.message);
      setTaskId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }
    if (outcome.kind === "success") {
      setTaskState("success");
      const result = event.result as { candidates?: Candidate[]; candidates_preview?: Candidate[]; count?: number; new_candidates?: Candidate[]; optimized_candidates?: Candidate[] } | undefined;
      const rows = result?.candidates || [];
      if (rows.length) setCandidates(rows);
      // P2-3: Store success banner data
      const newCount = Array.isArray(result?.new_candidates) ? result.new_candidates.length : (rows.length > 0 ? rows.length : 0);
      const optimizedCount = Array.isArray(result?.optimized_candidates) ? result.optimized_candidates.length : 0;
      setTaskSuccessBanner({
        newCount,
        optimizedCount,
        message: outcome.message,
      });
      notify(outcome.notifyType, `候选池自动推进完成${result?.count ? `: ${result.count}` : ""}`);
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
    setTaskState("error"); setTaskError(message);
    updateAutoPipelineStage("idle"); setTaskId(null);
    setTaskProgress((current) => ({ ...(current || {}), phase: current?.phase || "candidate_generation", status_message: message, percent_complete: 100 }));
    void requestJobCancel({ jobId: cancelledTaskId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选池自动推进进度暂时不可确认，已确认后台停止本次推进。请刷新候选列表后再重试。",
        missing: "候选池自动推进监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选池自动推进进度暂时不可确认，已请求后台自动中断，但取消未确认。请刷新状态或稍后重试。",
      });
      setTaskError(cancelExperience.message);
      setTaskProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "candidate_generation", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
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
    () => (serverMainPoolCandidates ? rankPoolCandidates(serverMainPoolCandidates) : rankPoolCandidates(candidates.filter(candidateRetainedPoolEligible))),
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
    setTaskState("loading"); setTaskError(null);
    setTaskSuccessBanner(null); // P2-3: Clear previous success banner
    updateAutoPipelineStage("await_generation");
    setTaskProgress({ phase: "candidate_generation", status_message: "正在启动候选池自动推进。" });

    const result = await callApi<AsyncJobStart>("/api/generate_candidates", {
      method: "POST",
      body: JSON.stringify({ automation_mode: "maintain_candidate_pool", auto_simulate_after_generation: false, auto_check_after_simulation: false, target_pool_size: targetPoolSize, existing_pool_size: existingPoolSize, retained_pool_size: retainedPoolSize, pool_deficit: nextDeficit }),
    });
    const nextTaskId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextTaskId) {
      setTaskId(nextTaskId); setTaskState("progress");
      notify("info", "候选池自动推进已启动，会按目标池容量补充、预筛并继续非提交验证。");
    } else {
      setTaskState("error"); updateAutoPipelineStage("idle");
      setTaskError(apiErrorMessage(result, "启动候选池自动推进失败"));
      notify("error", apiErrorMessage(result, "启动候选池自动推进失败"));
    }
  }, [callApi, notify, poolEligibleCandidates.length, retainedPoolCandidates.length, targetPoolSize, updateAutoPipelineStage]);

  // BRAIN simulation handler
  const startSimulation = useCallback(async (candidate?: Candidate, candidateOverride?: Candidate[]) => {
    setSimState("loading"); setSimError(null);
    const alphaId = candidate ? candidateIdentity(candidate) : "";
    setSimProgress({ phase: "simulation_start", status_message: alphaId ? `正在启动单个候选 ${alphaId} 的官方模拟请求。` : "正在启动官方模拟请求。" });
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
        nextBatchCheckCandidatesRef.current = null; updateAutoPipelineStage("idle");
        setSimState("error"); setSimError(message);
        setSimProgress({ phase: "simulation_start", status_message: message, percent_complete: 100 });
        notify("warning", message);
        return;
      }
    }
    const result = await callApi<{ job_id: string; task_id?: string }>("/api/candidates/simulate", { method: "POST", body: JSON.stringify(payload) });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      setSimJobId(nextJobId); setSimState("progress");
      notify("info", alphaId ? `单个候选 ${alphaId} 的官方模拟已启动。` : "官方模拟已启动，可在本页查看进度。");
    } else {
      const message = apiErrorMessage(result, "启动官方模拟失败");
      setSimState("error"); updateAutoPipelineStage("idle"); setSimError(message);
      nextBatchCheckCandidatesRef.current = null;
      notify("error", message);
    }
  }, [callApi, buildCredentialOverrides, candidates, notify, retainedPoolCandidates, serverWorkflowPlan, updateAutoPipelineStage]);

  const startOfficialValidationQueue = useCallback(() => {
    updateAutoPipelineStage("await_quality_check");
    void startSimulation();
  }, [startSimulation, updateAutoPipelineStage]);

  const startOptimization = useCallback(async (poolSnapshot?: CandidatePoolSnapshot, candidateOverride?: Candidate[]): Promise<boolean> => {
    const candidatesForOptimization = (candidateOverride && candidateOverride.length
      ? candidateOverride
      : optimizationCandidatesForPool(candidates, retainedPoolCandidates, serverWorkflowPlan?.rework?.candidate_ids)
    ).slice(0, AUTO_SIMULATION_BATCH_SIZE);
    if (!candidatesForOptimization.length) return false;
    const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
    const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
    const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
    setOptimizationState("loading"); setOptimizationError(null);
    updateAutoPipelineStage("await_optimization");
    setAutoOptimizationCycles((cycles) => cycles + 1);
    setOptimizationProgress({ phase: "candidate_optimization", status_message: `正在本地优化 ${candidatesForOptimization.length} 个需优化候选。` });
    const result = await callApi<AsyncJobStart>("/api/candidates/optimize", {
      method: "POST",
      body: JSON.stringify({ automation_mode: "maintain_candidate_pool", auto_simulate_after_optimization: false, auto_check_after_simulation: false, target_pool_size: targetPoolSize, existing_pool_size: existingPoolSize, retained_pool_size: retainedPoolSize, pool_deficit: nextDeficit, max_candidates: candidatesForOptimization.length, max_mutations: 3, keep_top: 2, candidates: candidatesForOptimization }),
    });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      setOptimizationJobId(nextJobId); setOptimizationState("progress");
      notify("info", "候选池本地优化已启动；产物会重新进入主池排序，不会触发提交。");
      return true;
    }
    const message = apiErrorMessage(result, "启动候选优化失败");
    setOptimizationState("error"); updateAutoPipelineStage("idle"); setOptimizationError(message);
    notify("error", message);
    return false;
  }, [callApi, candidates, notify, poolEligibleCandidates.length, retainedPoolCandidates, serverWorkflowPlan, targetPoolSize, updateAutoPipelineStage]);

  const startSingleCheck = useCallback(async (candidate: Candidate) => {
    const alphaId = candidateIdentity(candidate);
    if (!alphaId) { notify("warning", "候选缺少 Alpha ID，无法执行单行补查。"); return; }
    setCheckingAlphaId(alphaId); setCheckState("loading"); setCheckError(null);
    setCheckProgress({ phase: "single_candidate_check", status_message: `正在检查候选 ${alphaId} 的提交前阻断证据。` });
    const result = await callSingleCheckApi<CandidateCheckResult>("/api/check", { method: "POST", body: JSON.stringify({ ...buildCredentialOverrides(), mode: "quick", syncRange: "all", candidate }) });
    if (result?.ok) {
      setCheckState("success");
      setCheckProgress({ phase: "single_candidate_check", status_message: result.submittable ? `候选 ${alphaId} 已通过检查。` : `候选 ${alphaId} 检查完成，仍需处理阻断。`, percent_complete: 100 });
      setCheckResults((current) => indexCheckResults([...(current.values()), result]));
      notify(result.submittable ? "success" : "warning", result.submittable ? `候选 ${alphaId} 检查通过。` : `候选 ${alphaId} 检查完成，仍未提交就绪。`);
      await loadCandidates();
      onCandidatePoolUpdated?.();
    } else {
      const message = apiErrorMessage(result, "单行补查失败");
      setCheckState("error"); setCheckError(message);
      setCheckProgress({ phase: "single_candidate_check", status_message: message, percent_complete: 100 });
      notify("error", message);
    }
    setCheckingAlphaId(null);
  }, [buildCredentialOverrides, callSingleCheckApi, loadCandidates, notify, onCandidatePoolUpdated]);

  const startBatchCheck = useCallback(async (candidateOverride?: Candidate[]) => {
    const candidatesForCheck = candidateOverride && candidateOverride.length
      ? candidateOverride
      : retainedPoolCandidates.length ? retainedPoolCandidates : poolEligibleCandidates.slice(0, targetPoolSize);
    if (!candidatesForCheck.length) {
      lastBatchCheckCandidatesRef.current = null; setCheckState("success");
      setCheckProgress({ phase: "candidate_quality_check", status_message: "候选池暂无可检查候选。", percent_complete: 100 });
      updateAutoPipelineStage("idle");
      return;
    }
    lastBatchCheckCandidatesRef.current = candidatesForCheck;
    setCheckState("loading"); setCheckError(null);
    setCheckProgress({ phase: "candidate_quality_check", status_message: `正在批量检查 ${candidatesForCheck.length} 个主池候选的质量门槛。` });
    const result = await callBatchCheckApi<AsyncJobStart>("/api/check_batch", { method: "POST", body: JSON.stringify({ ...buildCredentialOverrides(), mode: "quick", syncRange: "all", check_candidates: candidatesForCheck }) });
    const nextJobId = String(result?.task_id || result?.job_id || "");
    if (result?.ok && nextJobId) {
      setCheckJobId(nextJobId); setCheckState("progress");
      notify("info", "候选池质量门槛检查已启动。");
    } else {
      const message = apiErrorMessage(result, "启动质量门槛检查失败");
      setCheckState("error"); updateAutoPipelineStage("idle"); setCheckError(message);
      notify("error", message);
    }
  }, [buildCredentialOverrides, callBatchCheckApi, notify, poolEligibleCandidates, retainedPoolCandidates, targetPoolSize, updateAutoPipelineStage]);

  const handleCheckEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setCheckProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, { failed: "质量门槛检查失败", interrupted: "质量门槛检查已停止，结果未确认完成。", success: "质量门槛检查完成。" });
    if (outcome.kind === "failed") {
      setCheckState("error"); setCheckError(outcome.message); updateAutoPipelineStage("idle");
      notify(outcome.notifyType, outcome.message); setCheckJobId(null);
      return;
    }
    if (outcome.kind === "interrupted") {
      setCheckState("error"); setCheckError(outcome.message); updateAutoPipelineStage("idle");
      notify(outcome.notifyType, outcome.message); setCheckJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }
    if (outcome.kind === "success") {
      setCheckState("success"); setCheckJobId(null);
      const shouldContinueMaintenance = autoPipelineStageRef.current === "await_quality_check";
      void loadCandidates().then((loaded) => {
        onCandidatePoolUpdated?.();
        if (shouldContinueMaintenance && loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
          const reworkCandidates = optimizationCandidatesForPool(loaded.rows, loaded.snapshot.retainedCandidates, loaded.workflowPlan?.rework?.candidate_ids);
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
    setCheckState("error"); setCheckError(message); updateAutoPipelineStage("idle"); setCheckJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "质量门槛检查进度暂时不可确认，已确认后台停止本次检查。",
        missing: "质量门槛检查监控对象已找不到，请刷新状态后再重试。",
        unconfirmed: "质量门槛检查进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      setCheckError(cancelExperience.message);
      setCheckProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "checking", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    notify("warning", message);
    void loadCandidates();
  }, [checkJobId, loadCandidates, notify, updateAutoPipelineStage]);

  useSSE(checkJobId ? `/sse?job_id=${encodeURIComponent(checkJobId)}` : null, { onEvent: handleCheckEvent, onExhausted: handleCheckStreamExhausted });

  const handleOptimizationEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setOptimizationProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, { failed: "候选本地优化失败", interrupted: "候选本地优化已停止，结果未确认完成。" });
    if (outcome.kind === "failed") {
      setOptimizationState("error"); setOptimizationError(outcome.message); updateAutoPipelineStage("idle");
      notify(outcome.notifyType, outcome.message); setOptimizationJobId(null);
      return;
    }
    if (outcome.kind === "interrupted") {
      setOptimizationState("error"); setOptimizationError(outcome.message); updateAutoPipelineStage("idle");
      notify(outcome.notifyType, outcome.message); setOptimizationJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }
    if (outcome.kind === "success") {
      setOptimizationState("success"); setOptimizationJobId(null);
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
    setOptimizationState("error"); setOptimizationError(message); updateAutoPipelineStage("idle"); setOptimizationJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "候选本地优化进度暂时不可确认，已确认后台停止本次优化。",
        missing: "候选本地优化监控对象已找不到，请刷新候选列表后再重试。",
        unconfirmed: "候选本地优化进度暂时不可确认，已请求后台自动中断，但取消未确认。",
      });
      setOptimizationError(cancelExperience.message);
      setOptimizationProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "candidate_optimization", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, optimizationJobId, updateAutoPipelineStage]);

  useSSE(optimizationJobId ? `/sse?job_id=${encodeURIComponent(optimizationJobId)}` : null, { onEvent: handleOptimizationEvent, onExhausted: handleOptimizationStreamExhausted });

  // SSE stream for simulation progress
  const handleSimEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setSimProgress(progress as UnifiedProgress);
    const outcome = resolveJobEventState(event, progress, { failed: "BRAIN模拟失败", interrupted: "BRAIN模拟已停止，结果未确认完成。" });
    if (outcome.kind === "failed") {
      setSimState("error"); setSimError(outcome.message); updateAutoPipelineStage("idle");
      nextBatchCheckCandidatesRef.current = null; notify(outcome.notifyType, outcome.message); setSimJobId(null);
      return;
    }
    if (outcome.kind === "interrupted") {
      setSimState("error"); setSimError(outcome.message); updateAutoPipelineStage("idle");
      nextBatchCheckCandidatesRef.current = null; notify(outcome.notifyType, outcome.message); setSimJobId(null);
      void loadCandidates().then(() => onCandidatePoolUpdated?.());
      return;
    }
    if (outcome.kind === "success") {
      const result = simulationResultSummary(event);
      const message = simulationCompletionMessage(result);
      const simulationSucceeded = result.completed > 0;
      if (!simulationSucceeded) {
        setSimState("error"); setSimError(message); notify("error", message);
      } else {
        setSimState("success"); notify(result.failed > 0 ? "warning" : outcome.notifyType, message);
      }
      setSimJobId(null);
      if (autoPipelineStageRef.current === "await_quality_check" && simulationSucceeded) {
        const cForCheck = nextBatchCheckCandidatesRef.current || undefined;
        nextBatchCheckCandidatesRef.current = null;
        void startBatchCheck(cForCheck);
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
      setSimError(cancelExperience.message);
      setSimProgress((current) => ({ ...(current || {}), ...cancelExperience.progressPatch, phase: current?.phase || "official_simulation", status_message: cancelExperience.message, percent_complete: 100 }));
      notify(cancelExperience.notifyType, cancelExperience.message);
    });
    setSimState("error"); setSimError(message); updateAutoPipelineStage("idle");
    nextBatchCheckCandidatesRef.current = null; setSimJobId(null);
    void loadCandidates();
  }, [loadCandidates, simJobId, updateAutoPipelineStage]);

  useSSE(simJobId ? `/sse?job_id=${encodeURIComponent(simJobId)}` : null, { onEvent: handleSimEvent, onExhausted: handleSimStreamExhausted });

  const rawQueueCandidates = useMemo(
    () => candidates.filter((c) => candidateMatchesQueueView(c, viewMode, checkResults)),
    [candidates, checkResults, viewMode],
  );
  const displayQueueCandidates = useMemo(
    () => (viewMode === "candidates" ? candidateManagementDisplayCandidates(candidates, retainedPoolCandidates, serverWorkflowPlan) : rawQueueCandidates),
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
    // P2-2: Star filter
    const starFiltered = showStarredOnly
      ? filtered.filter((c) => getStarred().has(candidateIdentity(c)))
      : filtered;
    return [...starFiltered].sort((a, b) => {
      let va: number; let vb: number;
      switch (sortKey) {
        case "score": va = a.scorecard?.total_score ?? 0; vb = b.scorecard?.total_score ?? 0; break;
        case "status": return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        case "created": va = candidateCreatedAt(a); vb = candidateCreatedAt(b); break;
        default: return 0;
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

  const currentPageIds = useMemo(
    () => paginatedCandidates.map((c) => candidateIdentity(c)),
    [paginatedCandidates],
  );

  const selectedCount = selectedIds.size;
  const canShowRowActions = showRowActions && Boolean(onScore);

  // Batch operation handlers
  const handleBatchScore = useCallback(() => {
    if (!onScore) return;
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    selected.forEach((c) => onScore(c));
  }, [onScore, selectedIds, sortedCandidates]);

  const handleBatchCheck = useCallback(() => {
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    if (selected.length > 0) {
      void startBatchCheck(selected);
    }
  }, [selectedIds, sortedCandidates, startBatchCheck]);

  const handleBatchSimulate = useCallback(() => {
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    if (selected.length > 0) {
      startSimulation(undefined, selected);
    }
  }, [selectedIds, sortedCandidates, startSimulation]);

  useEffect(() => { setCurrentPage(1); }, [filter, sortKey, sortAsc, viewMode]);
  useEffect(() => { setCurrentPage((page) => Math.min(page, totalPages)); }, [totalPages]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortAsc(!sortAsc); } else { setSortKey(key); setSortAsc(false); }
  };
  const handleTargetPoolSizeChange = (value: string) => { setTargetPoolSize(clampTargetPoolSize(value)); };
  const handleFilterChange = (value: string) => { setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH)); };

  // Batch selection handlers
  const handleToggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleToggleSelectAll = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const loading = api.loading;
  const loadError = api.error;
  const visibleStart = sortedCandidates.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const visibleEnd = Math.min(currentPage * PAGE_SIZE, sortedCandidates.length);
  const title = viewMode === "candidates" ? "候选管理" : `${queueViewLabel(viewMode)}候选`;
  const remoteTruncated = candidateMeta.total > candidateMeta.returned;
  const hasActions = canShowRowActions || showProductionControls;
  const candidateWorkflowBusy = (taskState === "loading" || taskState === "progress")
    || (simState === "loading" || simState === "progress")
    || (optimizationState === "loading" || optimizationState === "progress")
    || (checkState === "loading" || checkState === "progress");

  if (loading) {
    return (
      <ProgressFeedback state="loading" title="候选管理" progress={{ phase: "candidate_load", status_message: "正在加载候选数据。" }} />
    );
  }

  // Build detail panel props — extracted here to avoid inline object recreation in JSX
  const detailPanelProps = useMemo(() => ({
    showProductionControls,
    taskState, taskProgress, taskError,
    taskStreamExhausted: taskStream.exhausted,
    onRetryTask: () => { void generateCandidates(); },
    simState, simProgress, simError,
    onRetrySim: () => { startSimulation(); },
    optimizationState, optimizationProgress, optimizationError,
    onRetryOptimization: () => { void startOptimization(); },
    checkState, checkProgress, checkError,
    onRetryCheck: () => { void startBatchCheck(lastBatchCheckCandidatesRef.current || undefined); },
  }), [showProductionControls, taskState, taskProgress, taskError, taskStream.exhausted, generateCandidates,
    simState, simProgress, simError, startSimulation,
    optimizationState, optimizationProgress, optimizationError, startOptimization,
    checkState, checkProgress, checkError, startBatchCheck]);

  // Column definitions for desktop table
  const { columnCount, renderHeader } = useCandidateColumns({
    sortKey,
    sortAsc,
    hasActions,
    checkResults,
    canShowRowActions,
    showProductionControls,
    candidateWorkflowBusy,
    checkingAlphaId,
    onSort: handleSort,
    onScore,
    onSimulate: (c: Candidate) => { startSimulation(c); },
    onCheck: startSingleCheck,
    allCurrentPageIds: currentPageIds,
    selectedIds,
    onToggleSelectAll: handleToggleSelectAll,
    onToggleSelect: handleToggleSelect,
  });

  // Fix 4: Virtual scroll for desktop table
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const ESTIMATED_ROW_HEIGHT = 48;
  const rowVirtualizer = useVirtualizer({
    count: paginatedCandidates.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5,
  });

  return (
    <div className="animate-fade-in">
      <CandidateTableToolbar
        title={title}
        viewMode={viewMode}
        retainedCount={retainedPoolCandidates.length}
        targetPoolSize={targetPoolSize}
        poolEligibleCount={poolEligibleCandidates.length}
        rawQueueCount={rawQueueCandidates.length}
        sortedCount={sortedCandidates.length}
        candidateMeta={candidateMeta}
        filter={filter}
        remoteTruncated={remoteTruncated}
        showProductionControls={showProductionControls}
        candidateWorkflowBusy={candidateWorkflowBusy}
        taskState={taskState}
        simState={simState}
        optimizationState={optimizationState}
        onTargetPoolSizeChange={handleTargetPoolSizeChange}
        onGenerateCandidates={() => { void generateCandidates(); }}
        onStartValidationQueue={startOfficialValidationQueue}
        onStartOptimization={() => { void startOptimization(); }}
        qualitySummary={qualitySummary as QualitySummaryData}
        lifecycleHistory={lifecycleHistory}
        lifecycleError={lifecycleError}
        lifecycleLoading={lifecycleApi.loading}
        visibleLifecycleTraces={visibleLifecycleTraces}
        detailPanel={detailPanelProps}
        loadError={loadError}
        apiLoading={api.loading}
        onRetryLoad={loadCandidates}
        onFilterChange={handleFilterChange}
        showStarredOnly={showStarredOnly}
        onToggleStarFilter={() => setShowStarredOnly((v) => !v)}
        selectedIds={selectedIds}
        selectedCount={selectedCount}
        onClearSelection={handleClearSelection}
        onBatchScore={handleBatchScore}
        onBatchCheck={handleBatchCheck}
        onBatchSimulate={handleBatchSimulate}
        sortedCandidates={sortedCandidates}
      />

      <div className="panel">
        {/* P2-3: Success banner */}
        {taskState === "success" && taskSuccessBanner && (
          <div
            className="panel-body-padded"
            style={{
              borderBottom: "0.5px solid oklch(0.22 0.007 45)",
              background: "oklch(0.55 0.08 85 / 0.06)",
              borderLeft: "3px solid oklch(0.55 0.14 85 / 0.6)",
              margin: 0,
            }}
            role="status"
            aria-live="polite"
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 16px" }}>
              <span style={{ fontSize: 14, marginRight: 4 }}>✅</span>
              <span className="text-sm font-medium text-text-primary">
                候选池自动推进完成
              </span>
              <span className="text-xs text-text-secondary">
                新增 <span className="font-mono-value text-positive">{taskSuccessBanner.newCount}</span> 个候选
              </span>
              {taskSuccessBanner.optimizedCount > 0 && (
                <span className="text-xs text-text-secondary">
                  优化 <span className="font-mono-value text-accent">{taskSuccessBanner.optimizedCount}</span> 个
                </span>
              )}
              <span className="text-xs text-text-tertiary">
                当前池状态：
                <span className="font-mono-value text-text-primary">{retainedPoolCandidates.length}/{targetPoolSize}</span>
              </span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 6 }}
              onClick={() => setTaskSuccessBanner(null)}
              aria-label="关闭成功提示"
            >
              关闭提示
            </button>
          </div>
        )}

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

        {/* Desktop table with virtual scrolling (Fix 4) */}
        <div ref={tableContainerRef} className="hidden md:block overflow-auto" style={{ maxWidth: "100%", height: "min(640px, 70vh)" }}>
          <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
            <thead>
              {renderHeader()}
            </thead>
            <tbody style={{ position: "relative", height: rowVirtualizer.getTotalSize() }}>
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const candidate = paginatedCandidates[virtualRow.index];
                return (
                  <CandidateRow
                    key={`${candidateIdentity(candidate)}_v_${virtualRow.index}`}
                    candidate={candidate}
                    checkResults={checkResults}
                    hasActions={hasActions}
                    canShowRowActions={canShowRowActions}
                    showProductionControls={showProductionControls}
                    candidateWorkflowBusy={candidateWorkflowBusy}
                    checkingAlphaId={checkingAlphaId}
                    onScore={onScore}
                    onSimulate={(c) => { startSimulation(c); }}
                    onCheck={startSingleCheck}
                    isSelected={selectedIds.has(candidateIdentity(candidate))}
                    onToggleSelect={handleToggleSelect}
                    style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                  />
                );
              })}
              {paginatedCandidates.length === 0 && (
                <tr>
                  <td colSpan={columnCount} style={{ padding: "1.5rem", textAlign: "center" }}>
                    <EmptyState filter={!!filter} showProductionControls={showProductionControls} />
                  </td>
                </tr>
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

// ── Internal helpers (used by this module only) ──

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
