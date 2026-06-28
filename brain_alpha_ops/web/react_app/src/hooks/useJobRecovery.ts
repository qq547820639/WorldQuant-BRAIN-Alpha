/**
 * useJobRecovery — Session recovery on mount.
 *
 * Checks sessionStorage for a previously-running job, fetches its status
 * from the backend, and either marks it terminal or reconnects SSE.
 */

import { useState, useEffect, useRef } from 'react';
import type { JobStatus } from '@/types';
import { classifyJobState } from '@/helpers/runPayload';
import { reportIgnoredError } from '@/utils/reportIgnoredError';
import { saveResumeState } from '@/utils/resumeState';

const SESSION_KEY_JOB_ID = 'brain_alpha_active_job_id';
const RECOVERY_TIMEOUT_MS = 8000;

export function loadSavedJobId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY_JOB_ID);
  } catch (err) {
    reportIgnoredError('job state sessionStorage load failed', err);
    return null;
  }
}

export function clearSavedJobId(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY_JOB_ID);
  } catch (err) {
    reportIgnoredError('job state sessionStorage clear failed', err);
  }
}

export function saveJobId(id: string): void {
  try {
    sessionStorage.setItem(SESSION_KEY_JOB_ID, id);
  } catch (err) {
    reportIgnoredError('job state sessionStorage save failed', err);
  }
}

interface RecoveryCallbacks {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  callApi: <T>(url: string) => Promise<T | null>;
  onRecovered: (savedId: string, status: JobStatus) => void;
  onTerminal: (status: JobStatus) => void;
  addEvent: (msg: string) => void;
}

export function useJobRecovery({
  notify,
  callApi,
  onRecovered,
  onTerminal,
  addEvent,
}: RecoveryCallbacks) {
  const [recovering, setRecovering] = useState(false);
  const recoveryAttemptedRef = useRef(false);

  useEffect(() => {
    if (recoveryAttemptedRef.current) return;
    recoveryAttemptedRef.current = true;
    let recoveryTimedOut = false;
    const recoveryTimer = window.setTimeout(() => {
      recoveryTimedOut = true;
      clearSavedJobId();
      setRecovering(false);
      addEvent('恢复超时，已清除挂起的任务会话。');
    }, RECOVERY_TIMEOUT_MS);
    const savedId = loadSavedJobId();
    if (!savedId) {
      window.clearTimeout(recoveryTimer);
      return;
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect -- 挂载时启动恢复流程（一次性初始化）
    setRecovering(true);
    addEvent('正在检查任务状态…');

    void (async () => {
      const result = await callApi<JobStatus>(
        `/api/production-validation/status?job_id=${encodeURIComponent(savedId)}`
      );
      if (recoveryTimedOut) {
        window.clearTimeout(recoveryTimer);
        return;
      }
      if (!result || !result.status) {
        clearSavedJobId();
        window.clearTimeout(recoveryTimer);
        setRecovering(false);
        addEvent('任务状态已失效，已清除挂起的任务会话。');
        return;
      }
      const resultState = classifyJobState(result);
      if (resultState.terminal) {
        clearSavedJobId();
        window.clearTimeout(recoveryTimer);
        setRecovering(false);
        onTerminal(result);
        return;
      }
      addEvent('正在重新连接 SSE 进度流…');
      window.clearTimeout(recoveryTimer);
      onRecovered(savedId, result);
      addEvent('正在恢复任务上下文…');
      saveResumeState({ lastPipelineJob: savedId, lastPhase: 'evaluate', lastConnectionOk: true });
      notify('info', '已恢复正在运行的任务。');
      addEvent('任务会话已恢复，正在监听进度。');
      setRecovering(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { recovering };
}
