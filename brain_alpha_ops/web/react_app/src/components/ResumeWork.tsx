/**
 * ResumeWork — "一键恢复上次工作状态" banner (P0-4).
 *
 * Reads the pipeline snapshot stored by resumeState.ts and displays a
 * prominent card at the top of the Dashboard offering to restore the
 * previous session.
 */

import { useState, useEffect, useCallback, memo } from 'react';
import { getResumeState, hasResumeHistory, type ResumeState } from '@/utils/resumeState';

// ── Props ──────────────────────────────────────────────────────────────────

export interface ResumeWorkProps {
  /** Callback to show toast notifications. */
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  /** Whether the BRAIN connection is currently active. */
  connected: boolean;
  /** Whether local cache (cloud Alpha + official context) is fresh. */
  contextFresh: boolean;
  /** Current phase API status. */
  phaseStatus?: 'loading' | 'error' | 'ready';
  /** Navigate to the sync/official operations page. */
  onNavigateToSync: () => void;
  /** Navigate to the candidate management page. */
  onNavigateToCandidates: () => void;
  /** Whether a pipeline job is currently running. */
  jobRunning: boolean;
  /** Current job status for the running job. */
  jobStatusMessage?: string;
  /** Current cycle number (if running). */
  jobCycle?: number;
  /** Start / resume the pipeline job. */
  onStartJob: (resume?: boolean) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const PHASE_LABELS: Record<string, string> = {
  connect: '准备与就绪',
  discover: '候选发现',
  evaluate: '评估与验证',
  ready: '提交就绪',
};

function formatSessionAge(iso: string): string {
  if (!iso) return '';
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return '';
  const diffMs = Date.now() - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} 天前`;
}

function formatSyncAge(iso: string | null): string {
  if (!iso) return '从未同步';
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return '从未同步';
  const diffMs = Date.now() - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚同步';
  if (diffMin < 60) return `${diffMin} 分钟前同步`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前同步`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} 天前同步`;
}

// ── Component ──────────────────────────────────────────────────────────────

export default memo(function ResumeWork({
  notify,
  connected,
  contextFresh,
  phaseStatus = 'ready',
  onNavigateToSync,
  onNavigateToCandidates,
  jobRunning,
  jobStatusMessage,
  jobCycle,
  onStartJob,
}: ResumeWorkProps) {
  const [resumeState, setResumeState] = useState<ResumeState | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Load resume state on mount
  useEffect(() => {
    if (hasResumeHistory()) {
      setResumeState(getResumeState());
    }
  }, []);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
  }, []);

  const handleRestore = useCallback(async () => {
    setRestoring(true);
    try {
      // Step 1: Test connection (skip if cached as OK and recent)
      if (!connected) {
        notify('info', '请先测试 BRAIN 连接后再恢复工作状态。');
        setRestoring(false);
        return;
      }

      // Step 2: Check sync freshness
      if (!contextFresh) {
        notify('info', '本地缓存已过期，正在跳转到同步页面…');
        onNavigateToSync();
        setRestoring(false);
        return;
      }

      // Step 3: Restore candidate pool state — navigate to candidates
      if (resumeState && resumeState.lastPhase !== 'connect') {
        notify('info', '已恢复上次工作状态，跳转到候选管理页面。');
        onNavigateToCandidates();
      } else {
        // Step 4: If was in connect phase, just show the dashboard
        notify('success', '已恢复连接状态，请继续从运行总览开始。');
      }

      setDismissed(true);
    } catch (err) {
      notify('error', `恢复工作状态时出错: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRestoring(false);
    }
  }, [connected, contextFresh, notify, onNavigateToSync, onNavigateToCandidates, resumeState]);

  // ═══ Active job banner — takes priority ═══
  if (jobRunning) {
    return (
      <div
        className="panel mb-4 animate-fade-in"
        style={{
          borderColor: 'var(--color-info-border)',
          background: 'var(--color-info-bg)',
        }}
      >
        <div
          className="panel-body-padded"
          style={{ display: 'flex', alignItems: 'center', gap: 12 }}
        >
          {/* Pulsing indicator */}
          <div className="w-2.5 h-2.5 rounded-full bg-info animate-pulse flex-shrink-0" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p className="text-sm font-medium text-info">
              任务运行中{jobCycle != null ? `，第 ${jobCycle} 轮` : ''}…
            </p>
            {jobStatusMessage && (
              <p className="text-xs text-text-secondary mt-0.5 truncate">{jobStatusMessage}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ═══ Loading phase — don't show anything ═══
  if (phaseStatus === 'loading') {
    return null;
  }

  // ═══ First-time user or dismissed — no card ═══
  if (!resumeState || dismissed) {
    return null;
  }

  const phaseLabel = PHASE_LABELS[resumeState.lastPhase] || resumeState.lastPhase || '连接';
  const hasError = Boolean(resumeState.lastError);
  const hasInterruptedJob = Boolean(resumeState.lastPipelineJob) && hasError;
  const sessionAge = formatSessionAge(resumeState.lastSessionDate);

  // ═══ Resume card ═══
  return (
    <div
      className="panel mb-4 animate-fade-in"
      style={{
        borderColor: hasError ? 'var(--color-error-border)' : 'var(--color-warning-border)',
        background: hasError ? 'var(--color-error-bg-faint)' : 'var(--color-warning-bg)',
      }}
    >
      <div
        className="panel-body-padded"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        {/* Left: status info */}
        <div style={{ flex: '1 1 320px', minWidth: 0 }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            {/* Icon */}
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                flexShrink: 0,
                background: hasError
                  ? 'var(--color-error-bg-subtle)'
                  : 'var(--color-warning-bg-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {hasError ? (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--color-icon-error)"
                  strokeWidth="2"
                  strokeLinecap="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              ) : (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--color-icon-warning)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
                </svg>
              )}
            </div>

            <div>
              <p className="text-sm font-medium text-text-primary">
                {hasInterruptedJob ? '欢迎回来！检测到中断任务' : '欢迎回来！上次你在这里中断了'}
              </p>
              <p className="text-xs text-text-tertiary">{sessionAge}</p>
            </div>
          </div>

          {/* Status details */}
          <div
            className="grid gap-x-4 gap-y-1 mt-2"
            style={{
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              fontSize: 12,
            }}
          >
            <div>
              <span className="text-text-tertiary">上次阶段：</span>
              <span className="text-text-secondary font-medium">{phaseLabel}</span>
            </div>
            {resumeState.totalCyclesCompleted > 0 && (
              <div>
                <span className="text-text-tertiary">完成轮次：</span>
                <span className="text-text-secondary font-medium">
                  {resumeState.totalCyclesCompleted}
                </span>
              </div>
            )}
            <div>
              <span className="text-text-tertiary">候选池：</span>
              <span className="text-text-secondary font-medium">
                {resumeState.lastPoolSize > 0 ? `${resumeState.lastPoolSize} 个` : '空'}
              </span>
            </div>
            <div>
              <span className="text-text-tertiary">上次同步：</span>
              <span className="text-text-secondary font-medium">
                {formatSyncAge(resumeState.lastSyncTime)}
              </span>
            </div>
            <div>
              <span className="text-text-tertiary">连接状态：</span>
              <span
                className={
                  resumeState.lastConnectionOk
                    ? 'text-positive font-medium'
                    : 'text-negative font-medium'
                }
              >
                {resumeState.lastConnectionOk ? '正常' : '异常'}
              </span>
            </div>
          </div>

          {/* Interrupted task warning */}
          {hasInterruptedJob && resumeState.lastError && (
            <div
              className="mt-2"
              style={{
                padding: '6px 10px',
                borderRadius: 6,
                background: 'var(--color-error-bg-medium)',
                border: '1px solid var(--color-error-border-subtle)',
              }}
            >
              <p className="text-xs text-negative/90 font-medium mb-0.5">上次中断原因</p>
              <p className="text-xs text-text-secondary" style={{ lineHeight: 1.4 }}>
                {resumeState.lastError}
              </p>
            </div>
          )}

          {/* Resume prompt */}
          {hasInterruptedJob && (
            <p className="text-xs text-warning mt-2 font-medium">检测到中断任务，是否恢复？</p>
          )}
        </div>

        {/* Right: actions */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            flexShrink: 0,
            alignSelf: 'flex-start',
          }}
        >
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleRestore}
            disabled={restoring}
            style={{ padding: '8px 20px', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}
          >
            {restoring ? (
              <>
                <span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />
                恢复中…
              </>
            ) : (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ marginRight: 6 }}
                >
                  <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
                </svg>
                一键恢复
              </>
            )}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={handleDismiss}
            style={{ fontSize: 11 }}
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
});
