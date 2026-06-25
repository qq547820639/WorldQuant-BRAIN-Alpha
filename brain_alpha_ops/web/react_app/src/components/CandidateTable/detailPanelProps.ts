import type { UnifiedProgress } from '@/types';
import type { SseManagerState, SseManagerActions } from '@/hooks/useSseManager';
import type { CandidatePipeline } from '@/hooks/useCandidatePipeline';
import type { CandidateActions } from '@/hooks/useCandidateActions';

export type PipelineStageName = 'idle' | 'loading' | 'progress' | 'success' | 'error';

export interface DetailPanelProps {
  showProductionControls: boolean;
  taskState: PipelineStageName;
  taskProgress: UnifiedProgress | null;
  taskError: string | null;
  taskStreamExhausted: boolean;
  onRetryTask: () => void;
  simState: PipelineStageName;
  simProgress: UnifiedProgress | null;
  simError: string | null;
  onRetrySim: () => void;
  optimizationState: PipelineStageName;
  optimizationProgress: UnifiedProgress | null;
  optimizationError: string | null;
  onRetryOptimization: () => void;
  checkState: PipelineStageName;
  checkProgress: UnifiedProgress | null;
  checkError: string | null;
  onRetryCheck: () => void;
}

interface BuildParams {
  showProductionControls: boolean;
  pipeline: CandidatePipeline;
  sseManager: SseManagerState & SseManagerActions;
  actions: CandidateActions;
}

/**
 * Build the detail panel props object consumed by CandidateTableToolbar.
 * Caller is expected to wrap this in useMemo with the appropriate deps.
 */
export function buildDetailPanelProps({
  showProductionControls,
  pipeline,
  sseManager,
  actions,
}: BuildParams): DetailPanelProps {
  return {
    showProductionControls,
    taskState: pipeline.task.state,
    taskProgress: pipeline.task.progress,
    taskError: pipeline.task.error,
    taskStreamExhausted: sseManager.task.exhausted,
    onRetryTask: () => {
      void actions.generateCandidates();
    },
    simState: pipeline.simulation.state,
    simProgress: pipeline.simulation.progress,
    simError: pipeline.simulation.error,
    onRetrySim: () => {
      actions.startSimulation();
    },
    optimizationState: pipeline.optimization.state,
    optimizationProgress: pipeline.optimization.progress,
    optimizationError: pipeline.optimization.error,
    onRetryOptimization: () => {
      void actions.startOptimization();
    },
    checkState: pipeline.check.state,
    checkProgress: pipeline.check.progress,
    checkError: pipeline.check.error,
    onRetryCheck: () => {
      void actions.startBatchCheck(actions.lastBatchCheckCandidatesRef.current || undefined);
    },
  };
}
