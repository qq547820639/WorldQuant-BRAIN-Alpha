/**
 * View renderer extracted from App.tsx detailContent (Phase 2.1).
 * Maps activeView ID to the correct page component.
 * Workstream E2.1: prop-drilling is legacy — prefer renderActiveViewFromContext().
 */
import { lazy } from 'react';
import type { BrainCredentials, Candidate, CardViewId, PhaseData } from '@/types';
import type { JobState } from '@/hooks/useJobState';
import { safeDisplayErrorMessage, apiErrorMessage } from '@/helpers/errorExperience';
import { useApi } from '@/hooks/useApi';
import Dashboard from '@/components/Dashboard';
import CredentialQuickStart from '../CredentialQuickStart';
import JobMonitor from '@/components/JobMonitor';
import CandidateTable from '@/components/CandidateTable';
import ErrorBoundary from '@/components/ErrorBoundary';
import { LocalCacheSessionCard, ScoringPlaceholder } from './_renderViewHelpers';

const OfficialOperationsPanel = lazy(() => import('@/components/OfficialOperationsPanel'));
const OfficialBacktestSlots = lazy(() => import('@/components/OfficialBacktestSlots'));
const QualityCheckPanel = lazy(() => import('@/components/QualityCheckPanel'));
const ScoringPanel = lazy(() => import('@/components/ScoringPanel'));
const SubmissionConfirmPanel = lazy(() => import('@/components/SubmissionConfirmPanel'));
const ConfigPanel = lazy(() => import('@/components/ConfigPanel'));
const SnapshotPanel = lazy(() => import('@/components/SnapshotPanel'));

export interface RenderViewProps {
  activeView: CardViewId;
  selectedCandidate: Candidate | null;
  credentials: BrainCredentials;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  connected: boolean;
  contextFresh: boolean;
  phaseApiStatus: 'ready' | 'error' | 'loading';
  managedCredentialsAvailable: boolean;
  officialOpsAutoStart: boolean;
  jobState: JobState;
  onOpenScoring: (candidate: Candidate) => void;
  onNavigate: (view: CardViewId) => void;
  onConnectionTested: (ok: boolean, err: string | null) => void;
  onCredentialsChange: (credentials: BrainCredentials) => void;
  onDashboardSyncStart: () => void;
  onDashboardSyncOpen: () => void;
  onOfficialSyncCompleted: () => void;
  onOfficialReconnectRequested: () => void;
  onCandidatePoolUpdated: () => void;
  onLocalSessionLoggedOut: () => void;
  onAutoStartConsumed: () => void;
  phaseData?: PhaseData | null;
}

export function PageLoader() {
  return (
    <div
      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '3rem' }}
    >
      <span className="spinner" />
      <span className="text-text-tertiary text-sm ml-3">加载中...</span>
    </div>
  );
}

export function renderActiveView(props: RenderViewProps): React.ReactNode {
  const {
    activeView,
    selectedCandidate,
    credentials,
    notify,
    connected,
    contextFresh,
    phaseApiStatus,
    managedCredentialsAvailable,
    officialOpsAutoStart,
    jobState,
    onOpenScoring,
    onNavigate,
    onConnectionTested,
    onCredentialsChange,
    onDashboardSyncStart,
    onDashboardSyncOpen,
    onOfficialSyncCompleted,
    onOfficialReconnectRequested,
    onCandidatePoolUpdated,
    onLocalSessionLoggedOut,
    onAutoStartConsumed,
    phaseData,
  } = props;

  switch (activeView) {
    case 'dashboard':
      return (
        <ErrorBoundary
          key="dashboard"
          level="section"
          title="运行总览加载失败"
          description="仪表盘模块渲染时发生错误，请重试"
        >
          <Dashboard
            notify={notify}
            connected={connected}
            contextFresh={contextFresh}
            phaseStatus={phaseApiStatus}
            onNavigateToSync={onDashboardSyncStart}
            onOpenSync={onDashboardSyncOpen}
            onNavigateToCandidates={() => onNavigate('candidates')}
            jobRunning={jobState.running}
            jobStatusMessage={
              typeof jobState.progress?.status_message === 'string'
                ? jobState.progress.status_message
                : undefined
            }
            jobCycle={jobState.status?.cycle}
            onStartJob={jobState.startJob}
          >
            {!connected && contextFresh && (
              <LocalCacheSessionCard notify={notify} onLoggedOut={onLocalSessionLoggedOut} />
            )}
            {!connected && !contextFresh && (
              <CredentialQuickStart
                credentials={credentials}
                managedCredentialsAvailable={managedCredentialsAvailable}
                onCredentialsChange={onCredentialsChange}
                notify={notify}
                onConnectionTested={onConnectionTested}
              />
            )}
            {connected && contextFresh && (
              <div className="animate-fade-in">
                <JobMonitor notify={notify} credentials={credentials} jobState={jobState} />
              </div>
            )}
          </Dashboard>
        </ErrorBoundary>
      );
    case 'official_operations':
      return (
        <ErrorBoundary
          key="official_operations"
          level="section"
          title="官方操作加载失败"
          description="官方操作模块渲染时发生错误，请重试"
        >
          <OfficialOperationsPanel
            notify={notify}
            credentials={credentials}
            autoStart={officialOpsAutoStart}
            connectionReady={connected || managedCredentialsAvailable}
            officialContextCache={phaseData?.official_context_cache}
            cloudAlphaCache={phaseData?.cloud_alpha_cache}
            onAutoStartConsumed={onAutoStartConsumed}
            onSyncCompleted={onOfficialSyncCompleted}
            onReconnectRequested={onOfficialReconnectRequested}
            onNavigateToCandidates={() => onNavigate('candidates')}
          />
        </ErrorBoundary>
      );
    case 'candidates':
      return (
        <ErrorBoundary
          key="candidates"
          level="section"
          title="候选管理加载失败"
          description="候选列表模块渲染时发生错误，请重试"
        >
          <CandidateTable
            notify={notify}
            showProductionControls
            showRowActions
            onScore={onOpenScoring}
            credentials={credentials}
            onCandidatePoolUpdated={onCandidatePoolUpdated}
          />
        </ErrorBoundary>
      );
    case 'official_backtests':
      return (
        <ErrorBoundary
          key="official_backtests"
          level="section"
          title="回测监控加载失败"
          description="回测槽位模块渲染时发生错误，请重试"
        >
          <OfficialBacktestSlots notify={notify} />
        </ErrorBoundary>
      );
    case 'scoring':
      return selectedCandidate ? (
        <ErrorBoundary
          key="scoring"
          level="section"
          title="科学评分加载失败"
          description="评分模块渲染时发生错误，请重试"
        >
          <ScoringPanel notify={notify} candidate={selectedCandidate} />
        </ErrorBoundary>
      ) : (
        <ScoringPlaceholder onPickCandidate={() => onNavigate('candidates')} />
      );
    case 'quality_check':
      return (
        <ErrorBoundary
          key="quality_check"
          level="section"
          title="质量门禁加载失败"
          description="质量检查模块渲染时发生错误，请重试"
        >
          <QualityCheckPanel notify={notify} />
        </ErrorBoundary>
      );
    case 'submission_confirm':
      return (
        <ErrorBoundary
          key="submission_confirm"
          level="section"
          title="阻断复核加载失败"
          description="提交复核模块渲染时发生错误，请重试"
        >
          <SubmissionConfirmPanel notify={notify} onNavigate={onNavigate} />
        </ErrorBoundary>
      );
    case 'checkpoint_status':
      return (
        <ErrorBoundary
          key="checkpoint_status"
          level="section"
          title="续跑记录加载失败"
          description="续跑记录模块渲染时发生错误，请重试"
        >
          <SnapshotPanel notify={notify} viewMode="checkpoint_status" onNavigate={onNavigate} />
        </ErrorBoundary>
      );
    case 'robustness':
      return (
        <ErrorBoundary
          key="robustness"
          level="section"
          title="稳健性证据加载失败"
          description="稳健性模块渲染时发生错误，请重试"
        >
          <SnapshotPanel notify={notify} viewMode="robustness" onNavigate={onNavigate} />
        </ErrorBoundary>
      );
    case 'config':
      return (
        <ErrorBoundary
          key="config"
          level="section"
          title="系统配置加载失败"
          description="配置模块渲染时发生错误，请重试"
        >
          <ConfigPanel
            notify={notify}
            credentials={credentials}
            onCredentialsChange={onCredentialsChange}
            onConnectionTested={onConnectionTested}
            connected={connected}
            contextFresh={contextFresh}
            managedCredentialsAvailable={managedCredentialsAvailable}
            onLoggedOut={onLocalSessionLoggedOut}
          />
        </ErrorBoundary>
      );
    case 'cloud':
      return (
        <ErrorBoundary
          key="cloud"
          level="section"
          title="云端快照加载失败"
          description="云端快照模块渲染时发生错误，请重试"
        >
          <SnapshotPanel notify={notify} viewMode="cloud" onNavigate={onNavigate} />
        </ErrorBoundary>
      );
    default:
      return (
        <div className="panel">
          <div className="panel-body-padded" style={{ textAlign: 'center', padding: '3rem' }}>
            <p className="text-text-tertiary">未知视图</p>
          </div>
        </div>
      );
  }
}
