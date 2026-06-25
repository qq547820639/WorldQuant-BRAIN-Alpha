import { useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { buildRunPayload, hasCredentials, jobStatusMessage } from '@/helpers/runPayload';
import type { BrainCredentials, JobStatus } from '@/types';
import { useApi } from '@/hooks/useApi';
import type { NotifyFn } from './types';

type ApiInstance = ReturnType<typeof useApi>;

export interface UseJobControlOptions {
  notify: NotifyFn;
  credentials?: BrainCredentials;
  api: ApiInstance;
  jobId: string | null;
  setStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setRunning: Dispatch<SetStateAction<boolean>>;
  setJobId: Dispatch<SetStateAction<string | null>>;
  setProgressError: Dispatch<SetStateAction<string | null>>;
  setEvents: Dispatch<SetStateAction<string[]>>;
  setPollFailures: Dispatch<SetStateAction<number>>;
  clearAutoCancelRequests: () => void;
  resetSseRetryState: () => void;
}

export interface JobControl {
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
}

export function useJobControl({
  notify,
  credentials,
  api,
  jobId,
  setStatus,
  setRunning,
  setJobId,
  setProgressError,
  setEvents,
  setPollFailures,
  clearAutoCancelRequests,
  resetSseRetryState,
}: UseJobControlOptions): JobControl {
  const startJob = useCallback(
    async (resume = false) => {
      if (!hasCredentials(credentials))
        notify('info', '未填写页面凭证，将使用维护者配置的托管凭证启动非提交验证。');
      setRunning(true);
      clearAutoCancelRequests();
      setPollFailures(0);
      setProgressError(null);
      resetSseRetryState();
      setStatus({
        job_id: '',
        task_id: '',
        status: 'running',
        phase: 'queued',
        progress: {
          phase: 'queued',
          status_message: '正在启动非提交流水线验证。',
          percent_complete: 0,
        },
      });
      const result = await api.call<{ job_id: string }>('/api/run', {
        method: 'POST',
        body: JSON.stringify(buildRunPayload(resume, credentials)),
      });
      const jid = String(result?.job_id || '');
      if (result?.ok && jid) {
        setJobId(jid);
        setRunning(true);
        setPollFailures(0);
        setProgressError(null);
        setStatus({
          job_id: jid,
          task_id: jid,
          status: 'running',
          phase: 'queued',
          progress: {
            phase: 'queued',
            status_message: '非提交流水线已排队。',
            percent_complete: 0,
          },
        });
        notify('info', `${resume ? '非提交续跑' : '非提交验证'}已启动`);
      } else {
        setRunning(false);
        setPollFailures(0);
        const message = result
          ? jobStatusMessage(result, '启动验证流程失败')
          : '网络错误，请检查连接后重试';
        setProgressError(message);
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                status: 'failed',
                error: message,
                progress: {
                  ...(prev.progress || {}),
                  phase: 'failed',
                  status_message: message,
                  percent_complete: 100,
                },
              }
            : prev
        );
        notify('error', message);
        setJobId(null);
      }
    },
    [api, credentials, notify, clearAutoCancelRequests, resetSseRetryState]
  );

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call<{ ok?: boolean; error?: string; error_code?: string }>(
      '/api/production-validation/stop',
      { method: 'POST', body: JSON.stringify({ job_id: stoppedJobId }) }
    );
    if (!result || result.ok === false) {
      const message = result
        ? jobStatusMessage(result, '停止请求失败，后台状态仍未确认。')
        : '停止请求失败，后台状态仍未确认。';
      setProgressError(message);
      setStatus((prev) => ({
        ...(prev || {}),
        job_id: stoppedJobId,
        status: 'running',
        progress: {
          ...(prev?.progress || {}),
          phase: prev?.progress?.phase || prev?.phase || 'running',
          status_message: message,
          percent_complete: prev?.progress?.percent_complete,
        },
      }));
      setEvents((prev) => [...prev.slice(-50), `停止失败: ${message}`]);
      notify('error', message);
      return;
    }
    setRunning(false);
    setStatus((prev) => ({
      ...(prev || {}),
      job_id: stoppedJobId,
      status: 'stopped',
      progress: {
        ...(prev?.progress || {}),
        phase: 'stopped',
        status_message: '验证流程已停止',
        percent_complete: prev?.progress?.percent_complete,
      },
    }));
    setProgressError(null);
    setEvents((prev) => [...prev.slice(-50), '停止请求已发送']);
    notify('info', '验证流程已停止');
  }, [api, jobId, notify]);

  return { startJob, stopJob };
}
