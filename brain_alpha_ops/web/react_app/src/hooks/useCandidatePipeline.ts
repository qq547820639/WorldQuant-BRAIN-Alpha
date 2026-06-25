import { useCallback, useMemo, useRef, useState } from 'react';
import type { UnifiedProgress } from '@/types';

export type PipelineStage = 'idle' | 'loading' | 'progress' | 'success' | 'error';

export type AutoPipelineStage =
  | 'idle'
  | 'await_generation'
  | 'await_quality_check'
  | 'await_optimization';

export interface PipelineState {
  state: PipelineStage;
  progress: UnifiedProgress | null;
  error: string | null;
  jobId: string | null;
}

export interface TaskSuccessBanner {
  newCount: number;
  optimizedCount: number;
  message: string;
}

export interface CandidatePipeline {
  task: PipelineState & {
    setState: (s: PipelineStage) => void;
    setProgress: (
      p: UnifiedProgress | null | ((prev: UnifiedProgress | null) => UnifiedProgress | null)
    ) => void;
    setError: (e: string | null) => void;
    setJobId: (id: string | null) => void;
  };
  simulation: PipelineState & {
    setState: (s: PipelineStage) => void;
    setProgress: (
      p: UnifiedProgress | null | ((prev: UnifiedProgress | null) => UnifiedProgress | null)
    ) => void;
    setError: (e: string | null) => void;
    setJobId: (id: string | null) => void;
  };
  optimization: PipelineState & {
    setState: (s: PipelineStage) => void;
    setProgress: (
      p: UnifiedProgress | null | ((prev: UnifiedProgress | null) => UnifiedProgress | null)
    ) => void;
    setError: (e: string | null) => void;
    setJobId: (id: string | null) => void;
  };
  check: PipelineState & {
    setState: (s: PipelineStage) => void;
    setProgress: (
      p: UnifiedProgress | null | ((prev: UnifiedProgress | null) => UnifiedProgress | null)
    ) => void;
    setError: (e: string | null) => void;
    setJobId: (id: string | null) => void;
  };
  checkingAlphaId: string | null;
  setCheckingAlphaId: (id: string | null) => void;
  taskSuccessBanner: TaskSuccessBanner | null;
  setTaskSuccessBanner: (b: TaskSuccessBanner | null) => void;
  autoPipelineStage: AutoPipelineStage;
  autoPipelineStageRef: React.MutableRefObject<AutoPipelineStage>;
  updateAutoPipelineStage: (stage: AutoPipelineStage) => void;
  resetAutoPipelineStageIfCurrent: (stage: AutoPipelineStage) => void;
  autoOptimizationCycles: number;
  setAutoOptimizationCycles: React.Dispatch<React.SetStateAction<number>>;
}

export function useCandidatePipeline(): CandidatePipeline {
  const [taskState, setTaskState] = useState<PipelineStage>('idle');
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskSuccessBanner, setTaskSuccessBanner] = useState<TaskSuccessBanner | null>(null);

  const [simState, setSimState] = useState<PipelineStage>('idle');
  const [simProgress, setSimProgress] = useState<UnifiedProgress | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [simJobId, setSimJobId] = useState<string | null>(null);

  const [optimizationState, setOptimizationState] = useState<PipelineStage>('idle');
  const [optimizationProgress, setOptimizationProgress] = useState<UnifiedProgress | null>(null);
  const [optimizationError, setOptimizationError] = useState<string | null>(null);
  const [optimizationJobId, setOptimizationJobId] = useState<string | null>(null);

  const [checkState, setCheckState] = useState<PipelineStage>('idle');
  const [checkProgress, setCheckProgress] = useState<UnifiedProgress | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [checkJobId, setCheckJobId] = useState<string | null>(null);
  const [checkingAlphaId, setCheckingAlphaId] = useState<string | null>(null);

  const [autoPipelineStage, setAutoPipelineStage] = useState<AutoPipelineStage>('idle');
  const autoPipelineStageRef = useRef<AutoPipelineStage>('idle');
  const updateAutoPipelineStage = useCallback((stage: AutoPipelineStage) => {
    autoPipelineStageRef.current = stage;
    setAutoPipelineStage(stage);
  }, []);
  const resetAutoPipelineStageIfCurrent = useCallback(
    (stage: AutoPipelineStage) => {
      if (autoPipelineStageRef.current === stage) {
        updateAutoPipelineStage('idle');
      }
    },
    [updateAutoPipelineStage]
  );

  const [autoOptimizationCycles, setAutoOptimizationCycles] = useState(0);

  return useMemo(
    () => ({
      task: {
        state: taskState,
        progress: taskProgress,
        error: taskError,
        jobId: taskId,
        setState: setTaskState,
        setProgress: setTaskProgress,
        setError: setTaskError,
        setJobId: setTaskId,
      },
      simulation: {
        state: simState,
        progress: simProgress,
        error: simError,
        jobId: simJobId,
        setState: setSimState,
        setProgress: setSimProgress,
        setError: setSimError,
        setJobId: setSimJobId,
      },
      optimization: {
        state: optimizationState,
        progress: optimizationProgress,
        error: optimizationError,
        jobId: optimizationJobId,
        setState: setOptimizationState,
        setProgress: setOptimizationProgress,
        setError: setOptimizationError,
        setJobId: setOptimizationJobId,
      },
      check: {
        state: checkState,
        progress: checkProgress,
        error: checkError,
        jobId: checkJobId,
        setState: setCheckState,
        setProgress: setCheckProgress,
        setError: setCheckError,
        setJobId: setCheckJobId,
      },
      checkingAlphaId,
      setCheckingAlphaId,
      taskSuccessBanner,
      setTaskSuccessBanner,
      autoPipelineStage,
      autoPipelineStageRef,
      updateAutoPipelineStage,
      resetAutoPipelineStageIfCurrent,
      autoOptimizationCycles,
      setAutoOptimizationCycles,
    }),
    [
      taskState,
      taskProgress,
      taskError,
      taskId,
      simState,
      simProgress,
      simError,
      simJobId,
      optimizationState,
      optimizationProgress,
      optimizationError,
      optimizationJobId,
      checkState,
      checkProgress,
      checkError,
      checkJobId,
      checkingAlphaId,
      taskSuccessBanner,
      autoPipelineStage,
      autoOptimizationCycles,
      setTaskState,
      setTaskProgress,
      setTaskError,
      setTaskId,
      setSimState,
      setSimProgress,
      setSimError,
      setSimJobId,
      setOptimizationState,
      setOptimizationProgress,
      setOptimizationError,
      setOptimizationJobId,
      setCheckState,
      setCheckProgress,
      setCheckError,
      setCheckJobId,
      setCheckingAlphaId,
      setTaskSuccessBanner,
      updateAutoPipelineStage,
      resetAutoPipelineStageIfCurrent,
      setAutoOptimizationCycles,
    ]
  );
}
