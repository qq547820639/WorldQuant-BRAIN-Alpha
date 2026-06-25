import { useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { resolveJobEventState } from '@/helpers/runPayload';
import {
  isSSECandidateData,
  type SSEEvent,
  type JobStatus,
  type SSECandidateEventData,
} from '@/types';
import type { NotifyFn } from './types';

export interface UseSseEventHandlerOptions {
  notify: NotifyFn;
  setStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setRunning: Dispatch<SetStateAction<boolean>>;
  setJobId: Dispatch<SetStateAction<string | null>>;
  setProgressError: Dispatch<SetStateAction<string | null>>;
  setEvents: Dispatch<SetStateAction<string[]>>;
  setPollFailures: Dispatch<SetStateAction<number>>;
  clearTransientProgressError: () => void;
}

export function useSseEventHandler({
  notify,
  setStatus,
  setRunning,
  setJobId,
  setProgressError,
  setEvents,
  setPollFailures,
  clearTransientProgressError,
}: UseSseEventHandlerOptions) {
  return useCallback(
    (event: SSEEvent) => {
      const eventOutcome = resolveJobEventState(event, event.progress || event.data, {
        failed: '验证流程错误',
        interrupted: '验证流程已停止，结果未确认完成。',
        success: '验证流程已完成',
      });
      if (eventOutcome.terminal) {
        setRunning(false);
        setPollFailures(0);
        setJobId(null);
        const eventFailed = eventOutcome.kind === 'failed';
        const eventInterrupted = eventOutcome.kind === 'interrupted';
        const nextStatus: JobStatus['status'] = eventOutcome.nextStatus;
        if (eventFailed || eventInterrupted) {
          const message = eventOutcome.message;
          setProgressError(message);
          setEvents((prev) => [...prev, eventInterrupted ? message : `错误: ${message}`]);
          notify(eventOutcome.notifyType, message);
        } else {
          setProgressError(null);
          notify(eventOutcome.notifyType, eventOutcome.message);
          setEvents((prev) => [...prev, eventOutcome.message]);
        }
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                job_id: event.job_id || event.task_id || prev.job_id,
                task_id: event.task_id || event.job_id || prev.task_id,
                status: nextStatus,
                phase: event.phase || event.progress?.phase || prev.phase,
                result: event.result,
                error: eventFailed || eventInterrupted ? eventOutcome.message : prev.error,
                progress: event.progress || prev.progress,
              }
            : {
                job_id: event.job_id || event.task_id || '',
                task_id: event.task_id || event.job_id,
                status: nextStatus,
                phase: event.phase || event.progress?.phase,
                result: event.result,
                error: eventFailed || eventInterrupted ? eventOutcome.message : undefined,
                progress: event.progress || event.data,
              }
        );
      } else if (event.type === 'progress') {
        setPollFailures(0);
        clearTransientProgressError();
        setStatus((prev) => ({
          ...(prev || { job_id: event.job_id || event.task_id || '', status: 'running' }),
          job_id: event.job_id || event.task_id || prev?.job_id || '',
          task_id: event.task_id || event.job_id || prev?.task_id,
          status: 'running',
          phase: event.phase || event.progress?.phase || prev?.phase,
          percent_complete: event.percent_complete,
          eta_seconds: event.eta_seconds,
          status_message: event.status_message,
          progress: event.progress || event.data,
        }));
      } else if (event.type === 'candidate') {
        const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
        setEvents((prev) => [...prev.slice(-50), `候选 ${d.alpha_id || '?'} 得分 ${d.score || 0}`]);
      } else if (event.type === 'submission') {
        const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
        notify('warning', `检测到真实提交安全事件: ${d.alpha_id || '未知'}`);
        setEvents((prev) => [...prev.slice(-50), `真实提交安全事件 ${d.alpha_id || '?'}`]);
      }
    },
    [clearTransientProgressError, notify]
  );
}
