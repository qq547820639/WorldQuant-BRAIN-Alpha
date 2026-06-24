import { useCallback, useRef, useMemo } from "react";
import type { SSEEvent, Candidate } from "@/types";
import {
  type CandidatePoolSnapshot,
  type CandidateWorkflowPlan,
  type CandidateCheckResult,
} from "@/components/CandidateTableUtils";
import type { CandidatePipeline, AutoPipelineStage } from "./useCandidatePipeline";
import { useCandidateGeneration } from "./useCandidateGeneration";
import { useCandidateSimulation } from "./useCandidateSimulation";
import { useCandidateOptimization, optimizationCandidatesForPool } from "./useCandidateOptimization";
import { useCandidateCheck } from "./useCandidateCheck";
import { useCandidateSSEHandlers } from "./useCandidateSSEHandlers";

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

  const generation = useCandidateGeneration({
    pipeline,
    callApi,
    loadCandidates,
    onCandidatePoolUpdated,
    notify,
    poolEligibleCandidates,
    retainedPoolCandidates,
    targetPoolSize,
  });

  const optimization = useCandidateOptimization({
    pipeline,
    callApi,
    loadCandidates,
    onCandidatePoolUpdated,
    notify,
    candidates,
    retainedPoolCandidates,
    poolEligibleCandidates,
    serverWorkflowPlan,
    targetPoolSize,
    generateCandidates: generation.generateCandidates,
  });

  const check = useCandidateCheck({
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
    generateCandidates: generation.generateCandidates,
    startOptimization: optimization.startOptimization,
    optimizationCandidatesForPool,
    autoOptimizationCycles: pipeline.autoOptimizationCycles,
    maxAutoOptimizationCycles: optimization.MAX_AUTO_OPTIMIZATION_CYCLES,
    autoSimulationBatchSize: optimization.AUTO_SIMULATION_BATCH_SIZE,
  });

  const simulation = useCandidateSimulation({
    pipeline,
    callApi,
    loadCandidates,
    onCandidatePoolUpdated,
    notify,
    buildCredentialOverrides,
    candidates,
    retainedPoolCandidates,
    serverWorkflowPlan,
  });

  const handleSimEvent = useCallback((event: SSEEvent) => {
    simulation.handleSimEvent(event, check.startBatchCheck);
  }, [simulation, check.startBatchCheck]);

  const sseHandlers = useCandidateSSEHandlers({
    generationHandlers: {
      handleTaskEvent: generation.handleTaskEvent,
      handleTaskStreamExhausted: generation.handleTaskStreamExhausted,
    },
    simulationHandlers: {
      handleSimEvent,
      handleSimStreamExhausted: simulation.handleSimStreamExhausted,
    },
    optimizationHandlers: {
      handleOptimizationEvent: optimization.handleOptimizationEvent,
      handleOptimizationStreamExhausted: optimization.handleOptimizationStreamExhausted,
    },
    checkHandlers: {
      handleCheckEvent: check.handleCheckEvent,
      handleCheckStreamExhausted: check.handleCheckStreamExhausted,
    },
  });

  return {
    generateCandidates: generation.generateCandidates,
    startSimulation: simulation.startSimulation,
    startOfficialValidationQueue: simulation.startOfficialValidationQueue,
    startOptimization: optimization.startOptimization,
    startSingleCheck: check.startSingleCheck,
    startBatchCheck: check.startBatchCheck,
    handleTaskEvent: sseHandlers.handleTaskEvent,
    handleTaskStreamExhausted: sseHandlers.handleTaskStreamExhausted,
    handleSimEvent: sseHandlers.handleSimEvent,
    handleSimStreamExhausted: sseHandlers.handleSimStreamExhausted,
    handleOptimizationEvent: sseHandlers.handleOptimizationEvent,
    handleOptimizationStreamExhausted: sseHandlers.handleOptimizationStreamExhausted,
    handleCheckEvent: sseHandlers.handleCheckEvent,
    handleCheckStreamExhausted: sseHandlers.handleCheckStreamExhausted,
    buildCredentialOverrides,
    nextBatchCheckCandidatesRef: simulation.nextBatchCheckCandidatesRef,
    lastBatchCheckCandidatesRef: check.lastBatchCheckCandidatesRef,
  };
}
