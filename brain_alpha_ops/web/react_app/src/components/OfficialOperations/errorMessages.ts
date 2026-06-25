import { knownApiErrorMessage } from '@/helpers/errorExperience';
import type { JobStatus } from '@/types';

export function isSessionInvalidResult(
  result: ({ ok?: boolean; error_code?: string; error?: string } & Partial<JobStatus>) | null
) {
  if (!result || result.ok !== false) return false;
  const errorCode = String(result.error_code || '').toUpperCase();
  const error = String(result.error || '').toLowerCase();
  return (
    errorCode === 'SESSION_INVALID' ||
    error.includes('session_invalid') ||
    error.includes('invalid local session')
  );
}

export function syncHistoryReadErrorTitle(raw: unknown) {
  return readableBackendText(raw) || '同步历史读取受限，无法展示原始错误详情。';
}

export function readableBackendText(raw: unknown) {
  const value = String(raw || '').trim();
  const sharedMessage = knownApiErrorMessage(value);
  if (sharedMessage) return sharedMessage;
  const fieldRefreshMatch = value.match(/^Updating official fields cache:\s*(.+)$/);
  if (fieldRefreshMatch) return `正在刷新官方字段缓存: ${fieldRefreshMatch[1]}`;
  const operatorRefreshMatch = value.match(/^Updating official operators cache:\s*(.+)$/);
  if (operatorRefreshMatch) return `正在刷新官方算子缓存: ${operatorRefreshMatch[1]}`;
  const labels: Record<string, string> = {
    'Official context refreshed.': '官方上下文已刷新。',
    'candidate family lacks official simulation metrics': '候选族缺少官方仿真指标',
    'official context timeout': '官方上下文刷新超时，请稍后重试。',
    'unknown sync job': '找不到本次同步任务，请重新启动刷新。',
    'unknown job': '找不到本次任务，请重新启动流程。',
    JOB_NOT_FOUND: '找不到本次任务，请重新启动流程。',
    SESSION_INVALID:
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    'invalid local session':
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: '官方上下文刷新超时，请稍后重试。',
  };
  if (labels[value]) return labels[value];
  if (isAllowedOfficialStatusText(value)) return value;
  return null;
}

function isAllowedOfficialStatusText(value: string) {
  if (!value) return false;
  return [
    /^官方上下文已刷新/,
    /^官方上下文刷新/,
    /^官方上下文刷新已停止/,
    /^正在刷新官方字段缓存/,
    /^正在刷新官方算子缓存/,
    /^云端同步完成/,
    /^连续读取刷新状态失败/,
    /^用户已停止本次官方上下文刷新/,
  ].some((pattern) => pattern.test(value));
}
