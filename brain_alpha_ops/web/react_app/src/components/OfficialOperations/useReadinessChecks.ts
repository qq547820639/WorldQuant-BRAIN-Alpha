import { useCallback, type Dispatch, type SetStateAction } from 'react';
import type { ApiMeta } from '@/hooks/useApi';
import type { SubmitReadinessResponse } from '@/types';
import type { OperationMode } from './constants';
import type { OperationLogEntry } from './utils';
import {
  operationFailureMessage,
  requestDeadline,
  checkResultCount,
} from './utils';

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
}

interface UseReadinessChecksDeps {
  setMode: Dispatch<SetStateAction<OperationMode>>;
  readinessApi: { call: <R = SubmitReadinessResponse>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>; data: SubmitReadinessResponse | null; error: string | null; loading: boolean };
  checkResultsApi: { call: <R = CheckResultsResponse>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>; data: CheckResultsResponse | null; error: string | null; loading: boolean };
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
