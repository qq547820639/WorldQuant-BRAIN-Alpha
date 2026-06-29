import { useCallback, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { resolveJobEventState } from '@/helpers/runPayload';
import {
  isSSECandidateData,
  type SSEEvent,
  type JobStatus,
  type SSECandidateEventData,
} from '@/types';
import { sendCompletionNotification } from '@/hooks/useJobNotifications';
import { SSE_RETRY_DELAYS, SSE_MAX_RETRIES } from './constants';
import type { NotifyFn } from './types';

export interface UseSseEventHandlerOptions {
  notify: NotifyFn;
  onResume: () => void;
  onExhausted: (message: string) => void;
  setStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setRunning: Dispatch<SetStateAction<boolean>>;
  setJobId: Dispatch<SetStateAction<string | null>>;
  setProgressError: Dispatch<SetStateAction<string | null>>;
  setEvents: Dispatch<SetStateAction<string[]>>;
  setPollFailures: Dispatch<SetStateAction<number>>;
  clearTransientProgressError: () => void;
}

export interface SseEventHandler {
  handleSSEEvent: (event: SSEEvent) => void;
  sseRetryCountdown: number;
  sseRetryExhausted: boolean;
  clearSseRetryTimers: () => void;
  resetSseRetryState: () => void;
  handleStreamExhausted: () => void;
  handleSseExhaustedManualRetry: () => void;
}

export function useSseEventHandler({
  notify,
  onResume,
  onExhausted,
  setStatus,
  setRunning,
  setJobId,
  setProgressError,
  setEvents,
  setPollFailures,
  clearTransientProgressError,
}: UseSseEventHandlerOptions): SseEventHandler {
  // Phase 3.1: SSE retry state, absorbed from useSseRetryState.
  const sseRetryCountRef = useRef(0);
  const sseRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sseRetryCountdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sseRetryCountdown, setSseRetryCountdown] = useState(0);
  const [sseRetryExhausted, setSseRetryExhausted] = useState(false);

  const clearSseRetryTimers = useCallback(() => {
    if (sseRetryTimerRef.current) {
      clearTimeout(sseRetryTimerRef.current);
      sseRetryTimerRef.current = null;
    }
    if (sseRetryCountdownIntervalRef.current) {
      clearInterval(sseRetryCountdownIntervalRef.current);
      sseRetryCountdownIntervalRef.current = null;
    }
  }, []);

  const resetSseRetryState = useCallback(() => {
    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(false);
    clearSseRetryTimers();
  }, [clearSseRetryTimers]);

  const handleStreamExhausted = useCallback(() => {
    const retryCount = sseRetryCountRef.current;
    if (retryCount < SSE_MAX_RETRIES) {
      sseRetryCountRef.current = retryCount + 1;
      const delay = SSE_RETRY_DELAYS[retryCount];
      const delaySeconds = Math.ceil(delay / 1000);
      setSseRetryCountdown(delaySeconds);
      notify(
        'warning',
        `同步进度通道中断，${delaySeconds}秒后自动重试 (${retryCount + 1}/${SSE_MAX_RETRIES})`
      );

      sseRetryCountdownIntervalRef.current = setInterval(() => {
        setSseRetryCountdown((c) => {
          if (c <= 1) {
            if (sseRetryCountdownIntervalRef.current) {
              clearInterval(sseRetryCountdownIntervalRef.current);
              sseRetryCountdownIntervalRef.current = null;
            }
            return 0;
          }
          return c - 1;
        });
      }, 1000);

      sseRetryTimerRef.current = setTimeout(() => {
        sseRetryTimerRef.current = null;
        setSseRetryCountdown(0);
        onResume();
      }, delay);
      return;
    }

    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(true);
    const msg = `同步进度通道已中断 ${SSE_MAX_RETRIES} 次自动重试均未恢复，正在请求自动中断。`;
    notify('warning', msg);
    onExhausted(msg);
  }, [notify, onResume, onExhausted]);

  const handleSseExhaustedManualRetry = useCallback(() => {
    sseRetryCountRef.current = 0;
    setSseRetryExhausted(false);
    setSseRetryCountdown(0);
    clearSseRetryTimers();
    onResume();
  }, [clearSseRetryTimers, onResume]);

  const handleSSEEvent = useCallback(
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
          // U-008: foreground completion triggers a system notification when
          // the tab is hidden and the user previously granted permission.
          sendCompletionNotification('BRAIN Alpha Ops', '管线运行完成！');
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

  return {
    handleSSEEvent,
    sseRetryCountdown,
    sseRetryExhausted,
    clearSseRetryTimers,
    resetSseRetryState,
    handleStreamExhausted,
    handleSseExhaustedManualRetry,
  };
}
