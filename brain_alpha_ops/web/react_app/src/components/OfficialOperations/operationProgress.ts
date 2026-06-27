import type { OperationMode } from './constants';
import {
  booleanField,
  checkResultCount,
  firstPositiveNumber,
  numberField,
  operationFailureMessage,
  resultNumberField,
  stringField,
} from './formatters';
import {
  boundedProgressPercent,
  isSuccessfulSyncStatus,
  isTerminalSyncStatus,
  normalizedProgressPercent,
  operationStatusMessage,
} from './syncProgress';
import { phaseLabel, syncStageMetric } from './syncStage';
import { classifyJobState } from '@/helpers/runPayload';
import type {
  JobStatus,
  ProgressLifecycle,
  SubmitReadinessResponse,
  UnifiedProgress,
} from '@/types';

function userErrorField(source: Record<string, unknown> | undefined) {
  const value = source?.user_error;
  return value && typeof value === 'object' ? (value as UnifiedProgress['user_error']) : undefined;
}

export function operationProgress(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  readiness: SubmitReadinessResponse | null,
  checks: { count?: number; items?: unknown; checks?: unknown } | null
): UnifiedProgress {
  if (mode === 'context_refresh') {
    const stage = syncStageMetric(syncStatus);
    const terminal = isTerminalSyncStatus(syncStatus);
    const successful = isSuccessfulSyncStatus(syncStatus);
    const terminalFailure = terminal && !successful;
    const scanStillRunning = stage.kind === 'scan' && !terminal;
    const hasStageTotal = stage.total > 0;
    const syncProgress = syncStatus?.progress;
    const stagePercent = terminalFailure
      ? null
      : stage.total > 0
        ? boundedProgressPercent((stage.current / stage.total) * 100, terminal)
        : terminal
          ? normalizedProgressPercent(syncStatus)
          : null;
    return {
      operation: scanStillRunning ? 'sync_alphas' : undefined,
      status_code: scanStillRunning ? 'SCAN' : stringField(syncProgress, 'status_code'),
      status: syncStatus?.status,
      status_kind: syncStatus?.status_kind || stringField(syncProgress, 'status_kind'),
      terminal: syncStatus?.terminal ?? booleanField(syncProgress, 'terminal'),
      active: syncStatus?.active ?? booleanField(syncProgress, 'active'),
      interrupted: syncStatus?.interrupted ?? booleanField(syncProgress, 'interrupted'),
      recoverable: syncStatus?.recoverable ?? booleanField(syncProgress, 'recoverable'),
      retryable: syncStatus?.retryable ?? booleanField(syncProgress, 'retryable'),
      error: syncStatus?.error || stringField(syncProgress, 'error'),
      error_code: stringField(syncProgress, 'error_code'),
      user_error: syncStatus?.user_error || userErrorField(syncProgress),
      user_error_kind: syncStatus?.user_error_kind || stringField(syncProgress, 'user_error_kind'),
      user_message: syncStatus?.user_message || stringField(syncProgress, 'user_message'),
      next_action: syncStatus?.next_action || stringField(syncProgress, 'next_action'),
      phase: scanStillRunning
        ? 'scan'
        : syncStatus?.phase || syncStatus?.progress?.phase || 'context_refresh',
      phase_label: phaseLabel(syncStatus),
      status_message: operationStatusMessage(syncStatus),
      percent_complete: scanStillRunning ? null : stagePercent,
      eta_seconds: terminalFailure ? null : stage.etaSeconds || null,
      eta_deadline_at_ms:
        stage.kind === 'scan' || terminalFailure || !hasStageTotal
          ? null
          : firstPositiveNumber(
              numberField(syncStatus?.progress, 'eta_deadline_at_ms'),
              resultNumberField(syncStatus, 'eta_deadline_at_ms')
            ) || null,
      done: stage.kind === 'scan' ? undefined : stage.current || undefined,
      scanned: stage.kind === 'scan' && !terminalFailure ? stage.current : undefined,
      total: stage.kind === 'scan' || terminalFailure || stage.total <= 0 ? undefined : stage.total,
      api_reported_total: numberField(syncStatus?.progress, 'api_reported_total') || undefined,
      remaining_items: numberField(syncStatus?.progress, 'remaining_items') || undefined,
      has_more:
        typeof syncStatus?.progress?.has_more === 'boolean'
          ? syncStatus.progress.has_more
          : undefined,
      pagination_complete:
        typeof syncStatus?.progress?.pagination_complete === 'boolean'
          ? syncStatus.progress.pagination_complete
          : undefined,
      pagination_target:
        typeof syncStatus?.progress?.pagination_target === 'string'
          ? syncStatus.progress.pagination_target
          : undefined,
      stop_reason:
        typeof syncStatus?.progress?.stop_reason === 'string'
          ? syncStatus.progress.stop_reason
          : undefined,
      page_number: stage.pageNumber || undefined,
      pages_fetched: stage.pageNumber || undefined,
      expected_pages: stage.expectedPages || undefined,
      page_size: stage.pageSize || undefined,
      page_limit: stage.pageLimit || undefined,
      next_offset: stage.nextOffset || undefined,
      new_unique_items: stage.newUniqueItems || undefined,
      unique_items: stage.uniqueItems || undefined,
      confirming_total_boundary: stage.confirmingTotalBoundary || undefined,
      indeterminate: scanStillRunning || undefined,
      open_ended: scanStillRunning || undefined,
      job_id: syncStatus?.job_id,
      task_id: syncStatus?.task_id,
    };
  }
  if (mode === 'readiness') {
    return {
      phase: 'submit_readiness',
      phase_label: '阻断复核',
      status_message: readiness
        ? `阻断复核 ${readiness.eligible_count ?? 0} / 候选 ${readiness.candidate_count ?? 0}`
        : '正在读取提交前阻断复核证据。',
      percent_complete: readiness ? 100 : 35,
      checked: readiness?.candidate_count ?? 0,
      total: readiness?.candidate_count ?? 0,
    };
  }
  if (mode === 'checks') {
    const count = checkResultCount(checks);
    return {
      phase: 'check_results',
      phase_label: '检查结果',
      status_message: checks ? `已加载 ${count} 条检查结果。` : '正在读取检查结果。',
      percent_complete: checks ? 100 : 35,
      checked: count,
      total: count,
    };
  }
  return {
    phase: 'idle',
    phase_label: '等待操作',
    status_message: '选择一个操作后，系统会在这里展示真实进度。',
    percent_complete: 0,
  };
}

export function progressState(
  mode: OperationMode,
  syncRunning: boolean,
  syncStatus: JobStatus | null,
  readinessLoading: boolean,
  checksLoading: boolean,
  error: string | null
): ProgressLifecycle {
  if (error) return 'error';
  if (syncRunning || readinessLoading || checksLoading) return 'progress';
  const syncState = classifyJobState(syncStatus);
  if (
    mode === 'context_refresh' &&
    (syncState.failed || syncState.missing || syncState.interrupted)
  )
    return 'error';
  if (mode !== 'idle') return 'success';
  return 'idle';
}

export function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: {
    syncStart: string | null;
    syncStatus: string | null;
    readiness: string | null;
    checks: string | null;
  }
) {
  if (mode === 'context_refresh') {
    const syncState = classifyJobState(syncStatus);
    const stopped = syncState.interrupted;
    const recoverableMessage = stopped
      ? syncStatus?.progress?.status_message ||
        syncStatus?.status_message ||
        '官方上下文刷新已停止，可重新刷新。'
      : '';
    if (syncStatus && (syncState.failed || syncState.missing || syncState.interrupted)) {
      return (
        operationFailureMessage(syncStatus, '') ||
        operationFailureMessage(errors.syncStart || errors.syncStatus || recoverableMessage, '')
      );
    }
    return operationFailureMessage(
      syncStatus?.error || errors.syncStart || errors.syncStatus || recoverableMessage,
      ''
    );
  }
  if (mode === 'readiness') return operationFailureMessage(errors.readiness, '');
  if (mode === 'checks') return operationFailureMessage(errors.checks, '');
  return null;
}
