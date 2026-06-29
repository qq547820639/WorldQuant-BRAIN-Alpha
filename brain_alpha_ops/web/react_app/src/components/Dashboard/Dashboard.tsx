/** Dashboard — Progressive flow with step-based guidance v3.2 */
import { type ReactNode } from 'react';
import { useGlobalData } from '@/hooks/useGlobalData';
import { useDashboard } from '@/hooks/useDashboard';
import KpiCard from '@/components/KpiCard';
import TrendPanel from '@/components/TrendPanel';
import ResumeWork from '@/components/ResumeWork';
import Skeleton from '@/components/Skeleton';
import ErrorCard from '@/components/ErrorCard';
import EmptyState from '@/components/EmptyState';
import { computeTrendChange } from '@/components/DashboardTrendData';
import { generateReportMarkdown, DashboardReportModal } from '@/components/DashboardReportModal';
import { formatSyncAge, DashboardCloudSnapshot } from '@/components/DashboardCloudSnapshot';
import { StepProgressBar } from '@/components/DashboardStepProgress';
import { GuidePanel } from '@/components/Dashboard/DashboardGuides';
import { MemoryPanel, FailurePatternsPanel } from '@/components/Dashboard/DashboardPanels';
import {
  SyncCloudCTA,
  CacheModeNotice,
  PhaseStatusNotice,
} from '@/components/Dashboard/DashboardNotices';

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  connected: boolean;
  contextFresh: boolean;
  phaseStatus?: 'loading' | 'error' | 'ready';
  onNavigateToSync: () => void;
  onOpenSync?: () => void;
  onNavigateToCandidates?: () => void;
  jobRunning?: boolean;
  jobStatusMessage?: string;
  jobCycle?: number;
  onStartJob?: (resume?: boolean) => void;
  children?: ReactNode;
}

export default function Dashboard({
  notify,
  connected,
  contextFresh,
  phaseStatus = 'ready',
  onNavigateToSync,
  onOpenSync,
  onNavigateToCandidates,
  jobRunning = false,
  jobStatusMessage,
  jobCycle,
  onStartJob,
  children,
}: Props) {
  const { lastUpdated } = useGlobalData();
  const {
    snapshotExpanded,
    showReport,
    reportMarkdown,
    setReportMarkdown,
    trendCandidates,
    trendSubmissions,
    status,
    memory,
    cloudSummaryData,
    cloudPreviewRows,
    cloud,
    cloudLoading,
    cloudError,
    errors,
    loading,
    showGuide,
    phasePending,
    phaseFailed,
    currentStep,
    stepLabel,
    openManualSync,
    retryAll,
    dismissGuide,
    toggleGuide,
    toggleSnapshot,
    openReport,
    closeReport,
  } = useDashboard({
    connected,
    contextFresh,
    phaseStatus,
    onNavigateToSync,
    onOpenSync,
    jobRunning,
  });

  const handleGenerateReport = () => {
    const md = generateReportMarkdown({
      trendCandidates,
      trendSubmissions,
      cloudSummary: cloudSummaryData,
      memory,
      status,
      cloudPreviewRows,
    });
    setReportMarkdown(md);
    openReport();
  };

  return (
    <div className="animate-fade-in">
      {onNavigateToCandidates && onStartJob && (
        <ResumeWork
          notify={notify}
          connected={connected}
          contextFresh={contextFresh}
          phaseStatus={phaseStatus}
          onNavigateToSync={onNavigateToSync}
          onNavigateToCandidates={onNavigateToCandidates}
          jobRunning={jobRunning}
          jobStatusMessage={jobStatusMessage}
          jobCycle={jobCycle}
          onStartJob={onStartJob}
        />
      )}

      <StepProgressBar currentStep={currentStep} />

      <GuidePanel
        show={showGuide}
        currentStep={currentStep}
        phasePending={phasePending}
        phaseFailed={phaseFailed}
        contextFresh={contextFresh}
        connected={connected}
        onDismiss={dismissGuide}
        onReshow={toggleGuide}
      />

      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-xl font-medium text-text-primary mb-1">运行总览</h1>
          <p className="text-sm text-text-tertiary">
            当前阶段：<span className="text-accent font-medium">{stepLabel}</span>
            {' · '}上次更新:{' '}
            {lastUpdated
              ? new Date(lastUpdated).toLocaleTimeString('zh-CN', {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
              : '--:--:--'}
          </p>
        </div>
        {connected && contextFresh && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={openManualSync}>
            手动同步
          </button>
        )}
      </div>

      {(phasePending || phaseFailed) && <PhaseStatusNotice failed={phaseFailed} />}

      {!connected && !contextFresh && !phasePending && !phaseFailed && (
        <div className="mb-6">{children}</div>
      )}

      {connected && !contextFresh && <SyncCloudCTA onNavigateToSync={onNavigateToSync} />}

      {contextFresh && (
        <>
          {connected && children}
          {!connected && (children || <CacheModeNotice />)}

          {loading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
            </div>
          )}

          {!loading && errors.length > 0 && (
            <ErrorCard
              title="仪表盘数据需要关注"
              details={errors.join('；')}
              severity="error"
              onRetry={retryAll}
              className="mb-4"
            />
          )}

          {!loading && !errors.length && (
            <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
              <TrendPanel
                title="候选总数"
                data={trendCandidates}
                unit="个"
                color="#3b82f6"
                currentValue={
                  memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0
                }
                change={computeTrendChange(trendCandidates)}
              />
              <KpiCard
                label="云端 Alpha"
                value={cloudSummaryData.count ?? '--'}
                subtitle={
                  cloud
                    ? `${cloudSummaryData.submitted_count ?? 0} 已提交 · ${formatSyncAge(
                        cloudSummaryData.age_seconds,
                        cloudSummaryData.loaded_at
                      )}`
                    : '等待刷新'
                }
                trend={cloud && (cloudSummaryData.submitted_count ?? 0) > 0 ? 'up' : 'neutral'}
                className="hover:shadow-md transition-shadow"
              />
              <KpiCard
                label="回测数"
                value={status?.progress?.backtests_completed ?? '--'}
                subtitle={status ? `${status.progress?.backtests_pending ?? 0} 待处理` : undefined}
                className="hover:shadow-md transition-shadow"
              />
              <TrendPanel
                title="提交数"
                data={trendSubmissions}
                unit="个"
                color="#f59e0b"
                currentValue={
                  status?.progress?.submissions ?? cloudSummaryData.submitted_count ?? 0
                }
                change={computeTrendChange(trendSubmissions)}
              />
            </div>

            {!loading &&
              !memory?.total_candidates &&
              !cloudSummaryData.count &&
              !status?.progress?.backtests_completed &&
              !status?.progress?.submissions && (
                <EmptyState
                  title="还没有运行数据"
                  description="当前没有候选、回测或提交记录。前往「候选管理」页面启动自动推进候选池，系统将自动完成生产搜索、模拟和质量检查。"
                  className="mb-4"
                >
                  {onNavigateToCandidates && (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={onNavigateToCandidates}
                    >
                      前往候选管理 →
                    </button>
                  )}
                </EmptyState>
              )}
            </>
          )}

          <div className="flex items-center gap-2 flex-wrap mb-4">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={toggleSnapshot}
              aria-expanded={snapshotExpanded}
            >
              <span
                className="inline-block transition-transform duration-200"
                style={{ transform: snapshotExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
              >
                ▶
              </span>
              <span className="ml-1.5">
                数据快照
                {snapshotExpanded ? '' : ` (${cloudSummaryData.count ?? '--'} 条 Alpha)`}
              </span>
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleGenerateReport}
            >
              📋 生成报告
            </button>
          </div>

          {snapshotExpanded && (
            <>
              <DashboardCloudSnapshot
                cloud={cloud}
                loading={cloudLoading}
                error={cloudError}
                onRetry={retryAll}
                onOpenSync={openManualSync}
              />

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <MemoryPanel title="热门家族" items={memory?.families} />
                <MemoryPanel title="热门字段" items={memory?.fields} />
                <FailurePatternsPanel items={memory?.failure_patterns} />
              </div>
            </>
          )}
        </>
      )}

      <DashboardReportModal show={showReport} onClose={closeReport} markdown={reportMarkdown} />
    </div>
  );
}
