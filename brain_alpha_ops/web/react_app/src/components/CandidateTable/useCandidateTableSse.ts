import { useEffect } from 'react';
import type { SseManagerState, SseManagerActions } from '@/hooks/useSseManager';
import type { CandidatePipeline } from '@/hooks/useCandidatePipeline';
import type { CandidateActions } from '@/hooks/useCandidateActions';

interface Params {
  pipeline: CandidatePipeline;
  sseManager: SseManagerState & SseManagerActions;
  actions: CandidateActions;
}

/**
 * Wires the four pipeline job streams (task, check, optimization, simulation)
 * to the unified SSE manager. Reconnects whenever any jobId or handler changes.
 */
export function useCandidateTableSse({ pipeline, sseManager, actions }: Params) {
  useEffect(() => {
    if (pipeline.task.jobId) {
      sseManager.connect('task', `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`, {
        onEvent: actions.handleTaskEvent,
        onExhausted: actions.handleTaskStreamExhausted,
      });
    } else {
      sseManager.disconnect('task');
    }

    if (pipeline.check.jobId) {
      sseManager.connect('check', `/sse?job_id=${encodeURIComponent(pipeline.check.jobId)}`, {
        onEvent: actions.handleCheckEvent,
        onExhausted: actions.handleCheckStreamExhausted,
      });
    } else {
      sseManager.disconnect('check');
    }

    if (pipeline.optimization.jobId) {
      sseManager.connect(
        'optimization',
        `/sse?job_id=${encodeURIComponent(pipeline.optimization.jobId)}`,
        {
          onEvent: actions.handleOptimizationEvent,
          onExhausted: actions.handleOptimizationStreamExhausted,
        }
      );
    } else {
      sseManager.disconnect('optimization');
    }

    if (pipeline.simulation.jobId) {
      sseManager.connect(
        'simulation',
        `/sse?job_id=${encodeURIComponent(pipeline.simulation.jobId)}`,
        {
          onEvent: actions.handleSimEvent,
          onExhausted: actions.handleSimStreamExhausted,
        }
      );
    } else {
      sseManager.disconnect('simulation');
    }
  }, [
    pipeline.task.jobId,
    pipeline.check.jobId,
    pipeline.optimization.jobId,
    pipeline.simulation.jobId,
    actions.handleTaskEvent,
    actions.handleTaskStreamExhausted,
    actions.handleCheckEvent,
    actions.handleCheckStreamExhausted,
    actions.handleOptimizationEvent,
    actions.handleOptimizationStreamExhausted,
    actions.handleSimEvent,
    actions.handleSimStreamExhausted,
    sseManager,
  ]);
}
