import { useCallback } from 'react';
import { cancelResultExperience, requestJobCancel } from '@/api/jobCancel';
import { apiErrorMessage } from '@/helpers/errorExperience';
import { resolveJobEventState } from '@/helpers/runPayload';
import type { SSEEvent, Candidate } from '@/types';
import type { CandidatePoolSnapshot } from '@/components/CandidateTableUtils';
import type { CandidatePipeline } from './useCandidatePipeline';

type AsyncJobStart = { ok?: boolean; job_id?: string; task_id?: string; error?: string };

export interface CandidateGenerationDeps {
  pipeline: CandidatePipeline;
  callApi: <T>(url: string, opts?: RequestInit) => Promise<T & { ok?: boolean; error?: string }>;
  loadCandidates: () => Promise<{
    rows: Candidate[];
    mainPoolCandidates: Candidate[] | null;
    snapshot: CandidatePoolSnapshot;
    workflowPlan?: import('@/components/CandidateTableUtils').CandidateWorkflowPlan | null;
  } | null>;
  onCandidatePoolUpdated?: () => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  poolEligibleCandidates: Candidate[];
  retainedPoolCandidates: Candidate[];
  targetPoolSize: number;
}

export function useCandidateGeneration(deps: CandidateGenerationDeps) {
  const {
    pipeline,
    callApi,
    loadCandidates,
    onCandidatePoolUpdated,
    notify,
    poolEligibleCandidates,
    retainedPoolCandidates,
    targetPoolSize,
  } = deps;

  const generateCandidates = useCallback(
    async (poolSnapshot?: CandidatePoolSnapshot) => {
      const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;
      const retainedPoolSize = poolSnapshot?.retainedCount ?? retainedPoolCandidates.length;
      const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);
      pipeline.setAutoOptimizationCycles((cycles) =>
        pipeline.autoPipelineStageRef.current === 'idle' ? 0 : cycles
      );
      pipeline.task.setState('loading');
      pipeline.task.setError(null);
      pipeline.setTaskSuccessBanner(null);
      pipeline.updateAutoPipelineStage('await_generation');
      pipeline.task.setProgress({
        phase: 'candidate_generation',
        status_message: '正在启动候选池自动推进。',
      });

      const result = await callApi<AsyncJobStart>('/api/generate_candidates', {
        method: 'POST',
        body: JSON.stringify({
          automation_mode: 'maintain_candidate_pool',
          auto_simulate_after_generation: false,
          auto_check_after_simulation: false,
          target_pool_size: targetPoolSize,
          existing_pool_size: existingPoolSize,
          retained_pool_size: retainedPoolSize,
          pool_deficit: nextDeficit,
        }),
      });
      const nextTaskId = String(result?.task_id || result?.job_id || '');
      if (result?.ok && nextTaskId) {
        pipeline.task.setJobId(nextTaskId);
        pipeline.task.setState('progress');
        notify('info', '候选池自动推进已启动，会按目标池容量补充、预筛并继续非提交验证。');
      } else {
        pipeline.task.setState('error');
        pipeline.updateAutoPipelineStage('idle');
        pipeline.task.setError(apiErrorMessage(result, '启动候选池自动推进失败'));
        notify('error', apiErrorMessage(result, '启动候选池自动推进失败'));
      }
    },
    [
      callApi,
      notify,
      poolEligibleCandidates.length,
      retainedPoolCandidates.length,
      targetPoolSize,
      pipeline,
    ]
  );

  const handleTaskEvent = useCallback(
    (event: SSEEvent) => {
      try {
        const progress = event.progress || event.data || {};
        pipeline.task.setProgress(progress);
        const outcome = resolveJobEventState(event, progress, {
          failed: '候选池自动推进失败',
          interrupted: '候选池自动推进已停止，结果未确认完成。',
        });
        if (outcome.kind === 'failed') {
          pipeline.task.setState('error');
          pipeline.task.setError(outcome.message);
          pipeline.setTaskSuccessBanner(null);
          pipeline.updateAutoPipelineStage('idle');
          notify(outcome.notifyType, outcome.message);
          return;
        }
        if (outcome.kind === 'interrupted') {
          pipeline.task.setState('error');
          pipeline.task.setError(outcome.message);
          pipeline.updateAutoPipelineStage('idle');
          notify(outcome.notifyType, outcome.message);
          pipeline.task.setJobId(null);
          void loadCandidates().then(() => onCandidatePoolUpdated?.());
          return;
        }
        if (outcome.kind === 'success') {
          pipeline.task.setState('success');
          const result = event.result as
            | {
                candidates?: Candidate[];
                candidates_preview?: Candidate[];
                count?: number;
                new_candidates?: Candidate[];
                optimized_candidates?: Candidate[];
              }
            | undefined;
          const rows = result?.candidates || [];
          if (rows.length) {
          }
          const newCount = Array.isArray(result?.new_candidates)
            ? result.new_candidates.length
            : rows.length > 0
              ? rows.length
              : 0;
          const optimizedCount = Array.isArray(result?.optimized_candidates)
            ? result.optimized_candidates.length
            : 0;
          pipeline.setTaskSuccessBanner({
            newCount,
            optimizedCount,
            message: outcome.message,
          });
          notify(
            outcome.notifyType,
            `候选池自动推进完成${result?.count ? `: ${result.count}` : ''}`
          );
          void loadCandidates().then(() => {
            onCandidatePoolUpdated?.();
            pipeline.resetAutoPipelineStageIfCurrent('await_generation');
          });
          pipeline.task.setJobId(null);
          return;
        }
        pipeline.task.setState('progress');
      } catch (err) {
        console.error('SSE event handler error:', err);
        pipeline.task.setError('事件处理异常');
      }
    },
    [loadCandidates, notify, onCandidatePoolUpdated, pipeline]
  );

  const handleTaskStreamExhausted = useCallback(() => {
    if (!pipeline.task.jobId) return;
    const cancelledTaskId = pipeline.task.jobId;
    const message =
      '候选池自动推进进度暂时不可确认，正在请求后台自动中断；取消确认前请刷新状态后再重试。';
    pipeline.task.setState('error');
    pipeline.task.setError(message);
    pipeline.updateAutoPipelineStage('idle');
    pipeline.task.setJobId(null);
    pipeline.task.setProgress((current) => ({
      ...(current || {}),
      phase: current?.phase || 'candidate_generation',
      status_message: message,
      percent_complete: 100,
    }));
    void requestJobCancel({ jobId: cancelledTaskId, reason: 'sse_exhausted', message }).then(
      (result) => {
        const cancelExperience = cancelResultExperience(result, {
          confirmed:
            '候选池自动推进进度暂时不可确认，已确认后台停止本次推进。请刷新候选列表后再重试。',
          missing: '候选池自动推进监控对象已找不到，请刷新候选列表后再重试。',
          unconfirmed:
            '候选池自动推进进度暂时不可确认，已请求后台自动中断，但取消未确认。请刷新状态或稍后重试。',
        });
        pipeline.task.setError(cancelExperience.message);
        pipeline.task.setProgress((current) => ({
          ...(current || {}),
          ...cancelExperience.progressPatch,
          phase: current?.phase || 'candidate_generation',
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
    generateCandidates,
    handleTaskEvent,
    handleTaskStreamExhausted,
  };
}
