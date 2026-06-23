/**
 * View renderer extracted from App.tsx detailContent (Phase 2.1).
 * Maps activeView ID to the correct page component.
 */

import { lazy, Suspense } from "react";
import type { BrainCredentials, Candidate, CardViewId, PhaseData } from "@/types";
import { safeDisplayErrorMessage, apiErrorMessage } from "@/helpers/errorExperience";
import { useApi } from "@/hooks/useApi";
import Dashboard from "@/components/Dashboard";
import CredentialQuickStart from "../CredentialQuickStart";
import JobMonitor from "@/components/JobMonitor";
import CandidateTable from "@/components/CandidateTable";
import ErrorBoundary from "@/components/ErrorBoundary";

const OfficialOperationsPanel = lazy(() => import("@/components/OfficialOperationsPanel"));
const OfficialBacktestSlots  = lazy(() => import("@/components/OfficialBacktestSlots"));
const QualityCheckPanel      = lazy(() => import("@/components/QualityCheckPanel"));
const ScoringPanel           = lazy(() => import("@/components/ScoringPanel"));
const SubmissionConfirmPanel = lazy(() => import("@/components/SubmissionConfirmPanel"));
const ConfigPanel            = lazy(() => import("@/components/ConfigPanel"));
const SnapshotPanel          = lazy(() => import("@/components/SnapshotPanel"));

export interface RenderViewProps {
  activeView: CardViewId;
  selectedCandidate: Candidate | null;
  credentials: BrainCredentials;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  connected: boolean;
  contextFresh: boolean;
  phaseApiStatus: "ready" | "error" | "loading";
  managedCredentialsAvailable: boolean;
  officialOpsAutoStart: boolean;
  jobState: {
    running: boolean;
    progress?: { status_message?: string; percent_complete?: number; eta_seconds?: number };
    status?: { cycle?: number };
    startJob: () => void;
  };
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

function PageLoader() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem" }}>
      <span className="spinner" />
      <span className="text-text-tertiary text-sm ml-3">加载中...</span>
    </div>
  );
}

function ScoringPlaceholder({ onPickCandidate }: { onPickCandidate: () => void }) {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: 16 }}>
      <div style={{
        width: 64, height: 64, borderRadius: "50%",
        background: "var(--color-scoring-placeholder-bg)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-scoring-placeholder-stroke)" strokeWidth="2" strokeLinecap="round">
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
          <rect x="9" y="3" width="6" height="4" rx="1"/>
          <path d="M9 12h6"/><path d="M9 16h4"/>
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-text-primary">尚未选择候选</h2>
      <p className="text-sm text-text-secondary max-w-xs text-center" style={{ lineHeight: 1.6 }}>
        科学评分需要先选择一个候选 Alpha。
        <br />请在候选管理中选择要评分的 Alpha。
      </p>
      <button type="button" className="btn btn-primary" onClick={onPickCandidate}>
        前往候选管理
      </button>
    </div>
  );
}

function LocalCacheSessionCard({
  notify,
  onLoggedOut,
}: {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onLoggedOut: () => void;
}) {
  const logoutApi = useApi<{ ok: boolean; error?: string; error_code?: string }>();
  const logoutErrorMessage = logoutApi.error ? safeDisplayErrorMessage(logoutApi.error) : null;

  const logout = async () => {
    const result = await logoutApi.call("/api/logout", { method: "POST" });
    if (!result?.ok) {
      notify("error", safeDisplayErrorMessage(apiErrorMessage(result, "退出本地会话失败")));
      return;
    }
    onLoggedOut();
    notify("success", "已退出本地会话并清空页面凭证");
  };

  return (
    <div className="panel mb-4" style={{
      borderColor: "var(--color-deferred-border)",
      background: "var(--color-deferred-bg)",
    }}>
      <div className="panel-header">
        <span>本地缓存会话</span>
        <span className="badge badge-positive">缓存可用</span>
      </div>
      <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div style={{ minWidth: 240, flex: "1 1 320px" }}>
          <p className="text-sm font-medium text-warning mb-1">当前使用本地缓存，不需要重新登录</p>
          <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
            页面会继续读取本地 Alpha 快照和官方上下文缓存；退出只清空当前页面会话与临时凭证，不删除本地缓存。
          </p>
          {logoutErrorMessage && (
            <p className="text-xs text-negative mt-2" role="alert">退出失败: {logoutErrorMessage}</p>
          )}
        </div>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={logout}
          disabled={logoutApi.loading}
        >
          {logoutApi.loading ? "退出中..." : "退出本地会话"}
        </button>
      </div>
    </div>
  );
}

export function renderActiveView(props: RenderViewProps): React.ReactNode {
  const { activeView, selectedCandidate, credentials, notify, connected, contextFresh,
    phaseApiStatus, managedCredentialsAvailable, officialOpsAutoStart,
    jobState, onOpenScoring, onNavigate, onConnectionTested, onCredentialsChange,
    onDashboardSyncStart, onDashboardSyncOpen, onOfficialSyncCompleted,
    onOfficialReconnectRequested, onCandidatePoolUpdated, onLocalSessionLoggedOut,
    onAutoStartConsumed, phaseData,
  } = props;

  switch (activeView) {
  case "dashboard":
    return <Dashboard
      notify={notify}
      connected={connected}
      contextFresh={contextFresh}
      phaseStatus={phaseApiStatus}
      onNavigateToSync={onDashboardSyncStart}
      onOpenSync={onDashboardSyncOpen}
      onNavigateToCandidates={() => onNavigate("candidates")}
      jobRunning={jobState.running}
      jobStatusMessage={typeof jobState.progress?.status_message === "string" ? jobState.progress.status_message : undefined}
      jobCycle={jobState.status?.cycle}
      onStartJob={jobState.startJob}
    >
      {!connected && contextFresh && <LocalCacheSessionCard notify={notify} onLoggedOut={onLocalSessionLoggedOut} />}
      {!connected && !contextFresh && <CredentialQuickStart credentials={credentials} managedCredentialsAvailable={managedCredentialsAvailable} onCredentialsChange={onCredentialsChange} notify={notify} onConnectionTested={onConnectionTested} />}
      {connected && contextFresh && (
        <div className="animate-fade-in">
          <JobMonitor notify={notify} credentials={credentials} jobState={jobState} />
        </div>
      )}
    </Dashboard>;
  case "official_operations":
    return (
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
        onNavigateToCandidates={() => onNavigate("candidates")}
      />
    );
  case "candidates":
    return (
      <ErrorBoundary key="candidates">
        <CandidateTable notify={notify} showProductionControls showRowActions
          onScore={onOpenScoring} credentials={credentials} onCandidatePoolUpdated={onCandidatePoolUpdated} />
      </ErrorBoundary>
    );
  case "official_backtests":
    return <OfficialBacktestSlots notify={notify} />;
  case "scoring":
    return selectedCandidate
      ? <ScoringPanel notify={notify} candidate={selectedCandidate} />
      : <ScoringPlaceholder onPickCandidate={() => onNavigate("candidates")} />;
  case "quality_check":
    return <QualityCheckPanel notify={notify} />;
  case "submission_confirm":
    return <SubmissionConfirmPanel notify={notify} onNavigate={onNavigate} />;
  case "checkpoint_status":
    return <SnapshotPanel key="checkpoint_status" notify={notify} viewMode="checkpoint_status" onNavigate={onNavigate} />;
  case "robustness":
    return <SnapshotPanel key="robustness" notify={notify} viewMode="robustness" onNavigate={onNavigate} />;
  case "config":
    return (
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
    );
  case "cloud":
    return <SnapshotPanel key="cloud" notify={notify} viewMode="cloud" onNavigate={onNavigate} />;
  default:
    return (
      <div className="panel">
        <div className="panel-body-padded" style={{ textAlign: "center", padding: "3rem" }}>
          <p className="text-text-tertiary">未知视图</p>
        </div>
      </div>
    );
  }
}
