/** OfficialOperations sync workflow hooks: sync operations and readiness checks. */

import { useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import { classifyJobState } from '@/helpers/runPayload';
import type { ApiMeta } from '@/hooks/useApi';
import type { BrainCredentials, JobStatus, SubmitReadinessResponse } from '@/types';
import type { OperationLogEntry, OperationMode } from './utils';
import {
  POLL_INTERVAL_MS,
  SYNC_STATUS_FAILURE_LIMIT,
  checkResultCount,
  clearStoredSyncJobId,
  credentialsPayload,
  hasPageCredentials,
  numberField,
  operationFailureMessage,
  operationStatusMessage,
  requestDeadline,
  saveStoredSyncJobId,
  shortOperationId,
} from './utils';

interface UseSyncOperationsDeps {
  syncJobId: string;
  setSyncStatus: Dispatch<SetStateAction<JobStatus | null>>;
  syncRunning: boolean;
  setSyncRunning: Dispatch<SetStateAction<boolean>>;
  syncRange: string;
  setContextOnlyMode: Dispatch<SetStateAction<boolean>>;
  stoppingSinceMs: number;
  setStoppingSinceMs: Dispatch<SetStateAction<number>>;
  syncPollInFlightRef: React.MutableRefObject<boolean>;
  activeSyncJobIdRef: React.MutableRefObject<string>;
  syncPollGenerationRef: React.MutableRefObject<number>;
  syncPollFailureCountRef: React.MutableRefObject<number>;
  autoStartConsumedRef: React.MutableRefObject<boolean>;
  syncStartApi: {
    call: <R = unknown>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>;
    reset: () => void;
    data: unknown;
    error: string | null;
    loading: boolean;
  };
  syncStatusApi: {
    call: <R = JobStatus>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>;
    data: JobStatus | null;
    error: string | null;
    loading: boolean;
  };
  updateSyncJobId: (jobId: string) => void;
  resetSyncProgressMonitor: () => void;
  inspectSyncProgressMonitor: (
    result: JobStatus
  ) => { level: 'warning' | 'stop'; message: string } | null;
  appendLog: (tone: OperationLogEntry['tone'], message: string) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  credentials?: BrainCredentials;
  connectionReady?: boolean;
  autoStart?: boolean;
  onAutoStartConsumed?: () => void;
  onSyncCompleted?: () => void;
  setMode: Dispatch<SetStateAction<OperationMode>>;
  interruptOfficialContextRefresh: (message: string) => Promise<void>;
}

export function useSyncOperations(deps: UseSyncOperationsDeps) {
  const {
    syncJobId,
    setSyncStatus,
    syncRunning,
    setSyncRunning,
    syncRange,
    setContextOnlyMode,
    stoppingSinceMs,
    setStoppingSinceMs,
    syncPollInFlightRef,
    activeSyncJobIdRef,
    syncPollGenerationRef,
    syncPollFailureCountRef,
    autoStartConsumedRef,
    syncStartApi,
    syncStatusApi,
    updateSyncJobId,
    resetSyncProgressMonitor,
    inspectSyncProgressMonitor,
    appendLog,
    notify,
    credentials,
    connectionReady,
    autoStart,
    onAutoStartConsumed,
    onSyncCompleted,
    setMode,
    interruptOfficialContextRefresh,
  } = deps;

  const callSyncStart = syncStartApi.call;
  const resetSyncStart = syncStartApi.reset;
  const callSyncStatus = syncStatusApi.call;

  const startOfficialContextRefresh = useCallback(
    async (options?: { contextOnly?: boolean }) => {
      const contextOnly = Boolean(options?.contextOnly);
      setContextOnlyMode(contextOnly);
      if (!connectionReady && !hasPageCredentials(credentials)) {
        const message =
          '未检测到可用 BRAIN 凭证。请先在 Dashboard 测试 BRAIN 连接，或在系统配置里填写本次会话凭证。';
        appendLog('error', message);
        notify('warning', message);
        return;
      }
      updateSyncJobId('');
      clearStoredSyncJobId();
      setMode('context_refresh');
      setSyncRunning(true);
      setStoppingSinceMs(0);
      resetSyncProgressMonitor();
      syncPollFailureCountRef.current = 0;
      setSyncStatus({
        job_id: '',
        task_id: '',
        status: 'queued',
        phase: 'queued',
        progress: {
          phase: 'queued',
          phase_label: '等待启动',
          context_only: contextOnly,
          status_message: contextOnly ? '官方上下文局部重试正在排队。' : '官方上下文刷新正在排队。',
          percent_complete: 0,
        },
      });
      appendLog(
        'info',
        contextOnly ? '已发送仅重试官方上下文请求。' : '已发送官方上下文刷新请求。'
      );
      const endpoint = contextOnly ? '/api/sync_context_only' : '/api/sync_alphas';
      const result = await callSyncStart<{
        job_id?: string;
        task_id?: string;
        status_url?: string;
      }>(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          syncRange,
          refreshOfficialContext: true,
          userFacingOperation: 'official_operations_context_refresh',
          ...(contextOnly ? { contextOnly: true } : {}),
          ...credentialsPayload(credentials),
        }),
      });
      const jobId = String(result?.job_id || result?.task_id || '');
      if (!result?.ok && jobId) {
        const message = operationFailureMessage(
          result,
          '已有官方上下文刷新正在运行，已接管当前任务状态。'
        );
        saveStoredSyncJobId(jobId);
        resetSyncStart();
        updateSyncJobId(jobId);
        setSyncRunning(true);
        syncPollFailureCountRef.current = 0;
        setSyncStatus({
          job_id: jobId,
          task_id: jobId,
          status: 'running',
          phase: 'running',
          progress: {
            job_id: jobId,
            task_id: jobId,
            phase: 'running',
            phase_label: '已接管',
            context_only: contextOnly,
            status_message: message,
          },
        });
        appendLog('warning', `${message}: ${shortOperationId(jobId)}`);
        notify('info', '已接管正在运行的官方上下文刷新');
        return;
      }
      if (!result?.ok || !jobId) {
        const message = operationFailureMessage(
          result,
          '官方上下文刷新启动失败。请重试；若连续失败，请重新打开页面或联系维护者。'
        );
        setSyncRunning(false);
        setSyncStatus((previous) => ({
          ...(previous || { job_id: '', status: 'failed' }),
          status: 'failed',
          phase: 'failed',
          error: message,
          progress: {
            ...(previous?.progress || {}),
            phase: 'failed',
            context_only: contextOnly,
            status_message: message,
            percent_complete: 100,
          },
        }));
        appendLog('error', message);
        notify('error', message);
        return;
      }
      updateSyncJobId(jobId);
      saveStoredSyncJobId(jobId);
      setSyncStatus({
        job_id: jobId,
        task_id: jobId,
        status: 'queued',
        phase: 'queued',
        progress: {
          job_id: jobId,
          task_id: jobId,
          phase: 'queued',
          phase_label: '已排队',
          context_only: contextOnly,
          status_message: contextOnly
            ? '官方上下文局部重试已排队，正在等待页面进度更新。'
            : '官方上下文刷新已排队，正在等待页面进度更新。',
          percent_complete: 0,
        },
      });
      appendLog('success', `刷新流程已启动: ${shortOperationId(jobId)}`);
      notify('info', contextOnly ? '官方上下文局部重试已启动' : '官方上下文刷新已启动');
    },
    [
      appendLog,
      callSyncStart,
      connectionReady,
      credentials,
      notify,
      resetSyncProgressMonitor,
      resetSyncStart,
      setContextOnlyMode,
      setMode,
      setStoppingSinceMs,
      setSyncRunning,
      setSyncStatus,
      syncPollFailureCountRef,
      syncRange,
      updateSyncJobId,
    ]
  );

  const startContextOnlyRefresh = useCallback(() => {
    void startOfficialContextRefresh({ contextOnly: true });
  }, [startOfficialContextRefresh]);

  useEffect(() => {
    if (!autoStart || autoStartConsumedRef.current) return;
    if (syncRunning || syncJobId) return;
    autoStartConsumedRef.current = true;
    onAutoStartConsumed?.();
    void startOfficialContextRefresh();
  }, [
    autoStart,
    autoStartConsumedRef,
    onAutoStartConsumed,
    startOfficialContextRefresh,
    syncJobId,
    syncRunning,
  ]);

  const pollSyncStatus = useCallback(async () => {
    if (!syncJobId) return;
    if (syncPollInFlightRef.current) return;
    const requestedJobId = syncJobId;
    const pollGeneration = syncPollGenerationRef.current;
    syncPollInFlightRef.current = true;
    try {
      const result = await callSyncStatus<JobStatus>(
        `/api/sync_status?job_id=${encodeURIComponent(requestedJobId)}&compact=1`
      );
      if (
        activeSyncJobIdRef.current !== requestedJobId ||
        syncPollGenerationRef.current !== pollGeneration
      ) {
        return;
      }
      if (!result?.ok) {
        const message = operationFailureMessage(result, '刷新状态读取失败。');
        const failures = syncPollFailureCountRef.current + 1;
        syncPollFailureCountRef.current = failures;
        appendLog(
          'warning',
          `刷新状态读取失败 (${failures}/${SYNC_STATUS_FAILURE_LIMIT}): ${message}`
        );
        if (failures >= SYNC_STATUS_FAILURE_LIMIT) {
          await interruptOfficialContextRefresh(
            '连续读取刷新状态失败，已自动停止本次刷新。请检查网络或稍后重试。'
          );
        }
        return;
      }
      syncPollFailureCountRef.current = 0;
      setSyncStatus(result);
      const stall = inspectSyncProgressMonitor(result);
      if (stall?.level === 'warning') {
        appendLog('warning', stall.message);
        notify('warning', stall.message);
      } else if (stall?.level === 'stop') {
        await interruptOfficialContextRefresh(stall.message);
        return;
      }
      const resultState = classifyJobState(result);
      if (resultState.successful) {
        clearStoredSyncJobId();
        setSyncRunning(false);
        setStoppingSinceMs(0);
        syncPollFailureCountRef.current = 0;
        resetSyncProgressMonitor();
        appendLog(resultState.warning ? 'warning' : 'success', operationStatusMessage(result));
        notify(resultState.warning ? 'warning' : 'success', '官方上下文刷新完成');
        onSyncCompleted?.();
      } else if (resultState.failed || resultState.interrupted || resultState.missing) {
        clearStoredSyncJobId();
        setSyncRunning(false);
        setStoppingSinceMs(0);
        syncPollFailureCountRef.current = 0;
        resetSyncProgressMonitor();
        appendLog(
          resultState.failed || resultState.missing ? 'error' : 'warning',
          operationStatusMessage(result)
        );
        notify(
          resultState.failed || resultState.missing ? 'error' : 'warning',
          operationStatusMessage(result)
        );
      } else if (resultState.status === 'stopping') {
        const since =
          numberField(result.progress, 'stopping_since_ms') || stoppingSinceMs || Date.now();
        setStoppingSinceMs(since);
      }
    } finally {
      if (syncPollGenerationRef.current === pollGeneration) {
        syncPollInFlightRef.current = false;
      }
    }
  }, [
    appendLog,
    callSyncStatus,
    activeSyncJobIdRef,
    inspectSyncProgressMonitor,
    interruptOfficialContextRefresh,
    notify,
    onSyncCompleted,
    resetSyncProgressMonitor,
    setStoppingSinceMs,
    setSyncRunning,
    setSyncStatus,
    stoppingSinceMs,
    syncJobId,
    syncPollFailureCountRef,
    syncPollGenerationRef,
    syncPollInFlightRef,
  ]);

  useEffect(() => {
    if (!syncRunning || !syncJobId) return;
    const timer = window.setInterval(() => {
      void pollSyncStatus();
    }, POLL_INTERVAL_MS);
    void pollSyncStatus();
    return () => window.clearInterval(timer);
  }, [pollSyncStatus, syncJobId, syncRunning]);

  return {
    startOfficialContextRefresh,
    startContextOnlyRefresh,
    pollSyncStatus,
  };
}

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
}

interface UseReadinessChecksDeps {
  setMode: Dispatch<SetStateAction<OperationMode>>;
  readinessApi: {
    call: <R = SubmitReadinessResponse>(
      url: string,
      options?: RequestInit
    ) => Promise<(R & ApiMeta) | null>;
    data: SubmitReadinessResponse | null;
    error: string | null;
    loading: boolean;
  };
  checkResultsApi: {
    call: <R = CheckResultsResponse>(
      url: string,
      options?: RequestInit
    ) => Promise<(R & ApiMeta) | null>;
    data: CheckResultsResponse | null;
    error: string | null;
    loading: boolean;
  };
  appendLog: (tone: OperationLogEntry['tone'], message: string) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
}

export function useReadinessChecks(deps: UseReadinessChecksDeps) {
  const { setMode, readinessApi, checkResultsApi, appendLog, notify } = deps;

  const callReadiness = readinessApi.call;
  const callCheckResults = checkResultsApi.call;

  const loadReadiness = useCallback(async () => {
    setMode('readiness');
    appendLog('info', '正在读取提交前阻断复核证据。');
    const deadline = requestDeadline();
    try {
      const result = await callReadiness<SubmitReadinessResponse>('/api/submit_readiness', {
        signal: deadline.signal,
      });
      if (!result?.ok) {
        const message = operationFailureMessage(
          result,
          '提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。'
        );
        appendLog('error', message);
        notify('error', message);
        return;
      }
      const ready = Boolean((result as SubmitReadinessResponse).ready_to_submit);
      appendLog(
        ready ? 'success' : 'warning',
        ready ? '已检测到可进入人工复核的候选证据。' : '当前仍未达到提交前阻断复核通过标准。'
      );
      notify(ready ? 'success' : 'warning', ready ? '阻断复核通过' : '阻断复核仍未通过');
    } finally {
      deadline.clear();
    }
  }, [appendLog, callReadiness, notify, setMode]);

  const loadChecks = useCallback(async () => {
    setMode('checks');
    appendLog('info', '正在读取质量检查结果。');
    const deadline = requestDeadline();
    try {
      const result = await callCheckResults<CheckResultsResponse>('/api/check_results', {
        signal: deadline.signal,
      });
      if (!result?.ok) {
        const message = operationFailureMessage(
          result,
          '质量检查结果读取失败。请重试；若连续失败，请重新打开页面或联系维护者。'
        );
        appendLog('error', message);
        notify('error', message);
        return;
      }
      appendLog('success', `质量检查结果已加载: ${checkResultCount(result)} 条。`);
      notify('success', '质量检查结果已加载');
    } finally {
      deadline.clear();
    }
  }, [appendLog, callCheckResults, notify, setMode]);

  return {
    loadReadiness,
    loadChecks,
  };
}
