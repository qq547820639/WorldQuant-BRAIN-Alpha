import { useCallback } from 'react';
import { cancelResultExperience, requestJobCancel } from '@/api/jobCancel';
import { apiErrorMessage } from '@/helpers/errorExperience';
import { resolveJobEventState } from '@/helpers/runPayload';
import type { SSEEvent, Candidate } from '@/types';
import {
  candidateIdentity,
  candidateNeedsOptimization,
  workflowCandidatesForQueue,
  rankPoolCandidates,
  type CandidatePoolSnapshot,
  type CandidateWorkflowPlan,
} from '@/components/CandidateTableUtils';
import type { CandidatePipeline } from './useCandidatePipeline';

const AUTO_SIMULATION_BATCH_SIZE = 3;
const MAX_AUTO_OPTIMIZATION_CYCLES = 1;

type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };
type CandidateOptimizationResult = {
  candidates?: Candidate[];
  returned_count?: number;
  optimized_count?: number;
  summary?: { automation?: Record<string, unknown> };
};

export function optimizationCandidatesForPool(
  rows: Candidate[],
  retainedCandidates: Candidate[],
  queueIds?: string[]
) {
  const serverQueued = workflowCandidatesForQueue(rows, [], queueIds).filter(
    candidateNeedsOptimization
  );
  if (serverQueued.length) return rankPoolCandidates(serverQueued);
  const seen = new Set<string>();
  const prioritized = [...retainedCandidates, ...rows];
  const selected: Candidate[] = [];
  for (const candidate of prioritized) {
    const id = candidateIdentity(candidate) || candidate.expression || '';
    if (!id || seen.has(id) || !candidateNeedsOptimization(candidate)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return rankPoolCandidates(selected);
}

export interface CandidateOptimizationDeps {
  pipeline: CandidatePipeline;
  callApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
  loadCandidates: () => Promise<{
    rows: Candidate[];
    mainPoolCandidates: Candidate[] | null;
    snapshot: CandidatePoolSnapshot;
    workflowPlan?: CandidateWorkflowPlan | null;
  } | null>;
  onCandidatePoolUpdated?: () => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  candidates: Candidate[];
  retainedPoolCandidates: Candidate[];
  poolEligibleCandidates: Candidate[];
  serverWorkflowPlan: CandidateWorkflowPlan | null;
  targetPoolSize: number;
  generateCandidates?: (poolSnapshot?: CandidatePoolSnapshot) => Promise<void>;
}

export function useCandidateOptimization(deps: CandidateOptimizationDeps) {
  const {
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
    generateCandidates,
  } = deps;

  const startOptimization = useCallback(
    async (
      poolSnapshot?: CandidatePoolSnapshot,
      candidateOverride?: Candidate[]
    ): Promise<boolean> => {
      const candidatesForOptimization = (
        candidateOverride && candidateOverride.length
          ? candidateOverride
          : optimizationCandidatesForPool(
              candidates,
              retainedPoolCandidates,
              serverWorkflowPlan?.rework?.candidate_ids
            )
      ).slice(0, AUTO_SIMULATION_BATCH_SIZE);
      if (!candidatesForOptimization.length) return false;
      const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
      const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
      const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
      pipeline.optimization.setState('loading');
      pipeline.optimization.setError(null);
      pipeline.updateAutoPipelineStage('await_optimization');
      pipeline.setAutoOptimizationCycles((cycles) => cycles + 1);
      pipeline.optimization.setProgress({
        phase: 'candidate_optimization',
        status_message: `正在本地优化 ${candidatesForOptimization.length} 个需优化候选。`,
      });
      const result = await callApi<AsyncJobStart>('/api/candidates/optimize', {
        method: 'POST',
        body: JSON.stringify({
          automation_mode: 'maintain_candidate_pool',
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
      const nextJobId = String(result?.task_id || result?.job_id || '');
      if (result?.ok && nextJobId) {
        pipeline.optimization.setJobId(nextJobId);
        pipeline.optimization.setState('progress');
        notify('info', '候选池本地优化已启动；产物会重新进入主池排序，不会触发提交。');
        return true;
      }
      const message = apiErrorMessage(result, '启动候选优化失败');
      pipeline.optimization.setState('error');
      pipeline.updateAutoPipelineStage('idle');
      pipeline.optimization.setError(message);
      notify('error', message);
      return false;
    },
    [
      callApi,
      candidates,
      notify,
      poolEligibleCandidates.length,
      retainedPoolCandidates,
      serverWorkflowPlan,
      targetPoolSize,
      pipeline,
    ]
  );

  const handleOptimizationEvent = useCallback(
    (event: SSEEvent) => {
      try {
        const progress = event.progress || event.data || {};
        pipeline.optimization.setProgress(progress);
        const outcome = resolveJobEventState(event, progress, {
          failed: '候选本地优化失败',
          interrupted: '候选本地优化已停止，结果未确认完成。',
        });
        if (outcome.kind === 'failed') {
          pipeline.optimization.setState('error');
          pipeline.optimization.setError(outcome.message);
          pipeline.updateAutoPipelineStage('idle');
          notify(outcome.notifyType, outcome.message);
          pipeline.optimization.setJobId(null);
          return;
        }
        if (outcome.kind === 'interrupted') {
          pipeline.optimization.setState('error');
          pipeline.optimization.setError(outcome.message);
          pipeline.updateAutoPipelineStage('idle');
          notify(outcome.notifyType, outcome.message);
          pipeline.optimization.setJobId(null);
          void loadCandidates().then(() => onCandidatePoolUpdated?.());
          return;
        }
        if (outcome.kind === 'success') {
          pipeline.optimization.setState('success');
          pipeline.optimization.setJobId(null);
          const result = event.result as CandidateOptimizationResult | undefined;
          const optimizedRows = Array.isArray(result?.candidates) ? result.candidates : [];
          notify(
            outcome.notifyType,
            `候选本地优化完成: ${Number(result?.returned_count ?? optimizedRows.length)} 个子候选回池。`
          );
          void loadCandidates().then((loaded) => {
            onCandidatePoolUpdated?.();
            if (loaded?.snapshot.deficit && loaded.snapshot.deficit > 0) {
              notify(
                'info',
                `本地优化已回池；主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。`
              );
              if (generateCandidates) {
                void generateCandidates(loaded.snapshot);
              }
              return;
            }
            pipeline.resetAutoPipelineStageIfCurrent('await_optimization');
          });
          return;
        }
        pipeline.optimization.setState('progress');
      } catch (err) {
        console.error('SSE event handler error:', err);
        pipeline.optimization.setError('事件处理异常');
      }
    },
    [generateCandidates, loadCandidates, notify, onCandidatePoolUpdated, pipeline]
  );

  const handleOptimizationStreamExhausted = useCallback(() => {
    if (!pipeline.optimization.jobId) return;
    const cancelledJobId = pipeline.optimization.jobId;
    const message = '候选本地优化进度暂时不可确认，正在请求后台自动中断；请刷新状态后再重试。';
    pipeline.optimization.setState('error');
    pipeline.optimization.setError(message);
    pipeline.updateAutoPipelineStage('idle');
    pipeline.optimization.setJobId(null);
    void requestJobCancel({ jobId: cancelledJobId, reason: 'sse_exhausted', message }).then(
      (result) => {
        const cancelExperience = cancelResultExperience(result, {
          confirmed: '候选本地优化进度暂时不可确认，已确认后台停止本次优化。',
          missing: '候选本地优化监控对象已找不到，请刷新候选列表后再重试。',
          unconfirmed: '候选本地优化进度暂时不可确认，已请求后台自动中断，但取消未确认。',
        });
        pipeline.optimization.setError(cancelExperience.message);
        pipeline.optimization.setProgress((current) => ({
          ...(current || {}),
          ...cancelExperience.progressPatch,
          phase: current?.phase || 'candidate_optimization',
          status_message: cancelExperience.message,
          percent_complete: 100,
        }));
        notify(cancelExperience.notifyType, cancelExperience.message);
      }
    );
    notify('warning', message);
    void loadCandidates();
  }, [loadCandidates, notify, pipeline]);

  return {
    startOptimization,
    handleOptimizationEvent,
    handleOptimizationStreamExhausted,
    MAX_AUTO_OPTIMIZATION_CYCLES,
    AUTO_SIMULATION_BATCH_SIZE,
    optimizationCandidatesForPool,
  };
}
