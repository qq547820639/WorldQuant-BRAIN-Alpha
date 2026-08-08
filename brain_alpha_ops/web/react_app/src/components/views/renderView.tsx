/**
 * View renderer extracted from App.tsx detailContent (Phase 2.1).
 * Maps activeView ID to the correct page component.
 * Workstream E2.1: prop-drilling is legacy — prefer renderActiveViewFromContext().
 */
import { lazy, Suspense, Component, type ComponentType } from 'react';
import type { BrainCredentials, Candidate, CardViewId, PhaseData } from '@/types';
import type { JobState } from '@/hooks/useJobState';
import Dashboard from '@/components/Dashboard';
import CredentialQuickStart from '../CredentialQuickStart';
import JobMonitor from '@/components/JobMonitor';
import CandidateTable from '@/components/CandidateTable';
import ErrorBoundary from '@/components/ErrorBoundary';
import { LocalCacheSessionCard, ScoringPlaceholder } from './_renderViewHelpers';

/**
 * Detects chunk loading failures (common after deployments when old
 * asset hashes become stale) and shows a friendly “refresh browser”
 * prompt instead of a generic error.
 */
function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message || '';
  return (
    msg.includes('Loading chunk') ||
    msg.includes('Loading CSS') ||
    msg.includes('Failed to fetch dynamically imported module') ||
    msg.includes('Importing a module script')
  );
}

function ChunkLoadFallback() {
  return (
    <div className="panel" role="alert">
      <div className="panel-body-padded" style={{ textAlign: 'center', padding: '2rem' }}>
        <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--color-text-bright)' }}>
          页面已更新
        </h3>
        <p className="text-sm mb-4 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
          应用已发布新版本，当前页面资源已过期。请点击下方按钮刷新浏览器以加载最新内容。
        </p>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => window.location.reload()}
        >
          刷新页面
        </button>
      </div>
    </div>
  );
}

interface ChunkErrorBoundaryProps {
  children: React.ReactNode;
  fallbackTitle?: string;
}

interface ChunkErrorBoundaryState {
  hasError: boolean;
  isChunkError: boolean;
}

class ChunkErrorBoundary extends Component<ChunkErrorBoundaryProps, ChunkErrorBoundaryState> {
  state: ChunkErrorBoundaryState = { hasError: false, isChunkError: false };

  static getDerivedStateFromError(error: Error): ChunkErrorBoundaryState {
    return { hasError: true, isChunkError: isChunkLoadError(error) };
  }

  componentDidCatch(error: Error) {
    if (!isChunkLoadError(error)) {
      console.error('ChunkErrorBoundary: non-chunk error caught:', error);
    }
  }

  render() {
    if (this.state.hasError && this.state.isChunkError) {
      return <ChunkLoadFallback />;
    }
    if (this.state.hasError) {
      return (
        <ErrorBoundary
          level="section"
          title={this.props.fallbackTitle || '加载失败'}
          description="模块渲染时发生错误，请重试"
        >
          {null}
        </ErrorBoundary>
      );
    }
    return this.props.children;
  }
}

/** Wraps a lazy component with Suspense + ChunkErrorBoundary. */
function withLazyGuard(
  LazyComponent: React.LazyExoticComponent<ComponentType<any>>,
  fallbackTitle?: string
) {
  return (props: Record<string, unknown>) => (
    <ChunkErrorBoundary fallbackTitle={fallbackTitle}>
      <Suspense fallback={<PageLoader />}>
        <LazyComponent {...props} />
      </Suspense>
    </ChunkErrorBoundary>
  );
}

const OfficialOperationsPanel = lazy(() => import('@/components/OfficialOperationsPanel'));
const OfficialBacktestSlots = lazy(() => import('@/components/OfficialBacktestSlots'));
const QualityCheckPanel = lazy(() => import('@/components/QualityCheckPanel'));
const ScoringPanel = lazy(() => import('@/components/ScoringPanel'));
const SubmissionConfirmPanel = lazy(() => import('@/components/SubmissionConfirmPanel'));
const ConfigPanel = lazy(() => import('@/components/ConfigPanel'));
const SnapshotPanel = lazy(() => import('@/components/SnapshotPanel'));

/** Lazy components wrapped with chunk-load guard. */
const SafeOfficialOperationsPanel = withLazyGuard(OfficialOperationsPanel, '官方操作加载失败');
const SafeOfficialBacktestSlots = withLazyGuard(OfficialBacktestSlots, '回测监控加载失败');
const SafeQualityCheckPanel = withLazyGuard(QualityCheckPanel, '质量门禁加载失败');
const SafeScoringPanel = withLazyGuard(ScoringPanel, '科学评分加载失败');
const SafeSubmissionConfirmPanel = withLazyGuard(SubmissionConfirmPanel, '阻断复核加载失败');
const SafeConfigPanel = withLazyGuard(ConfigPanel, '系统配置加载失败');
const SafeSnapshotPanel = withLazyGuard(SnapshotPanel, '面板加载失败');

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
        <SafeOfficialOperationsPanel
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
      return <SafeOfficialBacktestSlots notify={notify} />;
    case 'scoring':
      return selectedCandidate ? (
        <SafeScoringPanel notify={notify} candidate={selectedCandidate} />
      ) : (
        <ScoringPlaceholder onPickCandidate={() => onNavigate('candidates')} />
      );
    case 'quality_check':
      return <SafeQualityCheckPanel notify={notify} />;
    case 'submission_confirm':
      return (
        <SafeSubmissionConfirmPanel
          notify={notify}
          // SubmissionConfirmPanel emits known CardViewId strings ('scoring', 'candidates', ...);
          // cast back to CardViewId for the renderView navigation callback.
          onNavigate={(view: string) => onNavigate(view as CardViewId)}
        />
      );
    case 'checkpoint_status':
      return (
        <SafeSnapshotPanel notify={notify} viewMode="checkpoint_status" onNavigate={onNavigate} />
      );
    case 'robustness':
      return <SafeSnapshotPanel notify={notify} viewMode="robustness" onNavigate={onNavigate} />;
    case 'config':
      return (
        <SafeConfigPanel
          notify={notify}
          credentials={credentials}
          onCredentialsChange={onCredentialsChange}
          onConnectionTested={onConnectionTested}
          connected={connected}
          contextFresh={contextFresh}
          managedCredentialsAvailable={managedCredentialsAvailable}
          onLoggedOut={onLocalSessionLoggedOut}
        />
      );
    case 'cloud':
      return <SafeSnapshotPanel notify={notify} viewMode="cloud" onNavigate={onNavigate} />;
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
