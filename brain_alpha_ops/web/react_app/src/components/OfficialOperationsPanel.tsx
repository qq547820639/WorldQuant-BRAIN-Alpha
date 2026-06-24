import ProgressFeedback from "@/components/ProgressFeedback";
import {
  ActionButtons,
  MetricsDisplay,
  OperationsLog,
  SummarySections,
  SyncHistoryList,
  SummaryMetric,
  formatDuration,
  contextSummaryField,
  officialContextInlineSummary,
  useOfficialOperations,
} from "./OfficialOperations";
import type { BrainCredentials, CloudAlphaCache, OfficialContextCache } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  autoStart?: boolean;
  connectionReady?: boolean;
  officialContextCache?: OfficialContextCache;
  cloudAlphaCache?: CloudAlphaCache;
  onAutoStartConsumed?: () => void;
  onSyncCompleted?: () => void;
  onReconnectRequested?: () => void;
  onNavigateToCandidates?: () => void;
}

export default function OfficialOperationsPanel({
  notify,
  credentials,
  autoStart = false,
  connectionReady = true,
  officialContextCache,
  cloudAlphaCache,
  onAutoStartConsumed,
  onSyncCompleted,
  onReconnectRequested,
  onNavigateToCandidates,
}: Props) {
  const {
    mode,
    syncJobId,
    syncStatus,
    syncRunning,
    syncRange,
    setSyncRange,
    contextOnlyMode,
    logs,
    setLogs,
    syncStartApi,
    readinessApi,
    checkResultsApi,
    currentProgress,
    currentError,
    currentState,
    readiness,
    checkRows,
    displaySyncStatus,
    syncHistory,
    syncHistoryError,
    syncHistoryErrorTitle,
    canRetryContext,
    syncNeedsRetry,
    stoppingElapsedSeconds,
    loadReadiness,
    loadChecks,
    startOfficialContextRefresh,
    startContextOnlyRefresh,
    stopOfficialContextRefresh,
  } = useOfficialOperations({
    notify,
    credentials,
    autoStart,
    connectionReady,
    officialContextCache,
    cloudAlphaCache,
    onAutoStartConsumed,
    onSyncCompleted,
    onReconnectRequested,
    onNavigateToCandidates,
  });

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <section className="panel min-w-0 space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-info">官方操作入口</span>
              <span className="badge badge-neutral">按钮驱动</span>
              <span className="badge badge-neutral">非提交</span>
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text-primary">官方同步与阻断复核</h2>
            <p className="mt-2 max-w-4xl text-base leading-7 text-text-secondary">
              这里把官方上下文刷新、提交前阻断复核和质量结果放在同一个页面里：点击按钮、看进度、读记录、处理阻断。系统会自动处理请求，用户只需留在浏览器里查看进度和结果。
            </p>
          </div>
          <MetricsDisplay
            syncRunning={syncRunning}
            syncStatus={syncStatus}
            officialContextCache={officialContextCache}
            cloudAlphaCache={cloudAlphaCache}
            readinessEligibleCount={readiness?.eligible_count}
            readinessReadyToSubmit={readiness?.ready_to_submit}
            checkRowsCount={checkRows.length}
          />
        </div>

        <ActionButtons
          mode={mode}
          syncRange={syncRange}
          syncRunning={syncRunning}
          syncStartLoading={syncStartApi.loading}
          syncNeedsRetry={syncNeedsRetry}
          readinessLoading={readinessApi.loading}
          checkResultsLoading={checkResultsApi.loading}
          checkRowsCount={checkRows.length}
          readiness={readiness}
          contextOnlyMode={contextOnlyMode}
          onSyncRangeChange={setSyncRange}
          onStartRefresh={() => void startOfficialContextRefresh()}
          onStopRefresh={stopOfficialContextRefresh}
          onLoadReadiness={loadReadiness}
          onLoadChecks={loadChecks}
        />

        {(syncJobId || displaySyncStatus?.official_context_cache) && (
          <section className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] p-3" aria-label="官方上下文快速摘要">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <dl className="grid min-w-0 flex-1 grid-cols-3 gap-3 text-sm">
                <SummaryMetric label="字段" value={contextSummaryField(displaySyncStatus, "fields_count")} />
                <SummaryMetric label="算子" value={contextSummaryField(displaySyncStatus, "operators_count")} />
                <SummaryMetric label="数据集" value={contextSummaryField(displaySyncStatus, "datasets_count")} />
              </dl>
              {canRetryContext && (
                <button type="button" className="btn btn-secondary text-sm" onClick={startContextOnlyRefresh} disabled={syncRunning || syncStartApi.loading}>
                  仅重试上下文
                </button>
              )}
            </div>
            <p className="mt-2 text-sm leading-6 text-text-secondary">{officialContextInlineSummary(displaySyncStatus)}</p>
          </section>
        )}

        {(syncHistory.length > 0 || syncHistoryError) && (
          <section className="rounded-md border border-border-subtle bg-[var(--color-surface-deep)] p-4" aria-label="最近官方同步">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">最近官方同步</h3>
                <p className="mt-1 text-sm leading-6 text-text-secondary">
                  最近任务只展示状态摘要和增量，不展示请求载荷或凭证。
                </p>
              </div>
              {syncHistoryError && (
                <span className="badge badge-warning text-xs" title={syncHistoryErrorTitle}>历史读取受限</span>
              )}
            </div>
            {syncHistory.length > 0 ? (
              <SyncHistoryList rows={syncHistory} />
            ) : (
              <p className="mt-3 text-sm text-text-tertiary">暂无可展示的官方同步历史。</p>
            )}
          </section>
        )}

        {syncStatus?.status === "stopping" && (
          <div className="rounded-md border border-[var(--color-info-border-warm)] bg-warning-subtle p-3 text-sm leading-6 text-warning">
            停止请求已发送，等待当前官方接口返回后结束。已等待 {formatDuration(stoppingElapsedSeconds)}；通常在 15 秒内生效，超过 60 秒会自动重试一次。
          </div>
        )}

        {syncStatus?.phase === "session_invalid" && (
          <div className="rounded-md border border-[var(--color-session-invalid-border)] bg-negative-subtle p-3 text-sm leading-6 text-negative" role="alert">
            <p className="font-medium">本地会话需要重新连接</p>
            <p className="mt-1 text-text-secondary">
              同步任务可能仍在后台运行，但当前页面无法继续读取状态。请回到运行总览重新测试连接，再回到官方操作页恢复监控。
            </p>
            {onReconnectRequested && (
              <button type="button" className="btn btn-secondary mt-2 text-sm" onClick={onReconnectRequested}>
                前往运行总览重新连接
              </button>
            )}
          </div>
        )}

        <ProgressFeedback
          state={currentState}
          title="操作进度"
          progress={currentProgress}
          error={currentError}
          onRetry={mode === "context_refresh" ? (canRetryContext ? startContextOnlyRefresh : () => void startOfficialContextRefresh()) : mode === "readiness" ? loadReadiness : mode === "checks" ? loadChecks : undefined}
        />

        <OperationsLog logs={logs} onClear={() => setLogs([])} />

      </section>

      <SummarySections
        readiness={readiness}
        displaySyncStatus={displaySyncStatus}
        onNavigateToCandidates={onNavigateToCandidates}
      />
    </div>
  );
}
