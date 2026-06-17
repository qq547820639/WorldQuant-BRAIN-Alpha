/**
 * BRAIN Alpha Ops — UI Design System v3.0
 * 应用外壳：侧边栏(阶段组) + 顶栏(连接+阶段) + PhaseShell + 移动端Tab
 * 渐进式 4 阶段导航，基于新架构重新实现
 */

import { useState, useCallback, useRef, useEffect, lazy, Suspense, useMemo } from "react";
import type {
  BacktestSlotsResponse,
  BrainCredentials,
  Candidate,
  CardViewId,
  CloudAlphaCache,
  OfficialContextCache,
  PhaseId,
} from "@/types";
import { useApi } from "@/hooks/useApi";
import { apiErrorMessage, safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { useToast } from "@/hooks/useToast";
import { useJobState } from "@/hooks/useJobState";
import { usePhaseState, type PhaseApiStatus } from "@/hooks/usePhaseState";
import ToastContainer from "@/components/ToastContainer";
import Sidebar from "@/components/Sidebar";
import Dashboard from "@/components/Dashboard";
import CredentialQuickStart from "./components/CredentialQuickStart";  // S-01: deduplicated from inline
import JobMonitor from "@/components/JobMonitor";
import CandidateTable from "@/components/CandidateTable";
import ErrorBoundary from "@/components/ErrorBoundary";
import PhaseShell from "@/components/PhaseShell";
import MobileTabBar from "@/components/MobileTabBar";
import { reportIgnoredError } from "@/utils/reportIgnoredError";
import { backtestActiveCount, backtestSlotLimit } from "@/utils/backtestSlots";

// Lazy-loaded: non-critical pages loaded on demand
const OfficialOperationsPanel = lazy(() => import("@/components/OfficialOperationsPanel"));
const OfficialBacktestSlots  = lazy(() => import("@/components/OfficialBacktestSlots"));
const QualityCheckPanel      = lazy(() => import("@/components/QualityCheckPanel"));
const ScoringPanel           = lazy(() => import("@/components/ScoringPanel"));
const SubmissionConfirmPanel = lazy(() => import("@/components/SubmissionConfirmPanel"));
const ConfigPanel            = lazy(() => import("@/components/ConfigPanel"));
const SnapshotPanel          = lazy(() => import("@/components/SnapshotPanel"));

/** Lightweight loading fallback for lazy pages */
function PageLoader() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem" }}>
      <span className="spinner" />
      <span className="text-text-tertiary text-sm ml-3">加载中...</span>
    </div>
  );
}

// ── Config ──────────────────────────────────────────────────────────────────

const VIEW_LABELS: Record<string, string> = {
  dashboard: "运行总览",
  official_operations: "官方操作",
  candidates: "候选管理",
  official_backtests: "回测监控",
  scoring: "科学评分",
  quality_check: "质量门禁",
  submission_confirm: "阻断复核",
  submission: "阻断复核",
  checkpoint_status: "续跑记录",
  robustness: "稳健性证据",
  config: "系统配置",
  cloud: "云端快照",
};

const PHASE_LABELS: Record<PhaseId, string> = {
  connect: "准备与就绪",
  discover: "候选发现",
  evaluate: "评估与验证",
  ready: "提交就绪",
};

// ── Types ───────────────────────────────────────────────────────────────────

interface SidebarBadges {
  candidates?: number;
  official_backtests?: string;
  scoring?: number;
  checkpoint_status?: number;
  cloud?: string;
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
      borderColor: "oklch(0.58 0.10 65 / 0.30)",
      background: "oklch(0.58 0.06 65 / 0.10)",
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

// ── App Shell ───────────────────────────────────────────────────────────────

export default function App() {
  const [activeView, setActiveView] = useState<CardViewId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  // B-09 (R3): password held in React state / JS heap — visible to DevTools
  // TODO: use crypto.subtle.digest() client-side hash or clear after submit
  const [credentials, setCredentials] = useState<BrainCredentials>({ username: "", password: "", token: "" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set(["connect"]));
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }) => {
      addToast(type, msg, 5000, action);
    }, [addToast],
  );

  const jobState = useJobState(notify, credentials);
  // SA-1: Multiple components independently call the same API endpoints.
  // Consider a global data-fetching layer (React Context + SWR or Zustand)
  // for cache deduplication and stale-while-revalidate patterns.


  const candidatesApi = useApi<{ candidates?: Candidate[]; total?: number }>();
  const slotsApi = useApi<BacktestSlotsResponse>();
  const cloudApi = useApi<{ count?: number; total?: number; summary?: Record<string, unknown> }>();
  const configApi = useApi<{ config?: { credentials?: { managed_credentials_available?: boolean } } }>();

  useEffect(() => {
    void candidatesApi.call("/api/candidates?summary=true");
    void slotsApi.call("/api/backtest_slots");
    void cloudApi.call("/api/snapshot/cloud");
    void configApi.call("/api/config");
  }, [candidatesApi.call, slotsApi.call, cloudApi.call, configApi.call]);

  useEffect(() => {
    // Independently notify about each API error so the user knows which feature is affected
    if (candidatesApi.error) notify("warning", `候选数据加载失败: ${safeDisplayErrorMessage(candidatesApi.error)}`);
    if (slotsApi.error) notify("warning", `回测槽位加载失败: ${safeDisplayErrorMessage(slotsApi.error)}`);
    if (cloudApi.error) notify("warning", `云端快照加载失败: ${safeDisplayErrorMessage(cloudApi.error)}`);
    if (configApi.error) notify("warning", `配置状态加载失败: ${safeDisplayErrorMessage(configApi.error)}`);
  }, [candidatesApi.error, slotsApi.error, cloudApi.error, configApi.error, notify]);

  const [connectionOverride, setConnectionOverride] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [officialOpsAutoStart, setOfficialOpsAutoStart] = useState(false);

  // Phase state from backend (poll every 10s)
  const phaseApi = useApi<{
    current_phase: string; operation_mode?: "cache_only" | "connected" | "needs_setup"; connected: boolean; context_fresh: boolean;
    candidates_count: number; scored_count: number; readiness_passed: boolean;
    sync: { in_progress: boolean; scanned: number; total: number; elapsed_seconds: number; stalled: boolean };
    official_context_cache?: OfficialContextCache;
    cloud_alpha_cache?: CloudAlphaCache;
    readiness: { eligible_count: number; ready: boolean };
  }>();

  useEffect(() => {
    void phaseApi.call("/api/phase_state");
    const interval = setInterval(() => {
      void phaseApi.call("/api/phase_state");
    }, 10_000);
    return () => clearInterval(interval);
  }, [phaseApi.call]);

  // Phase state computation
  const phaseData = phaseApi.data;
  const phaseApiStatus: PhaseApiStatus = phaseData ? "ready" : phaseApi.error ? "error" : "loading";
  const phaseConnected = Boolean(phaseData?.connected);
  const connected = Boolean(connectionOverride ?? phaseConnected) && !connectionError;
  const contextFresh = phaseData?.context_fresh ?? false;
  const candidatesCount = phaseData?.candidates_count ?? candidatesApi.data?.total ?? 0;
  const scoredCount = phaseData?.scored_count ?? 0;
  const readinessPassed = phaseData?.readiness_passed ?? false;
  const managedCredentialsAvailable = Boolean(
    configApi.data?.config?.credentials?.managed_credentials_available,
  );

  const { phaseState, steps, currentPhase } = usePhaseState({
    connected,
    contextFresh,
    candidatesCount,
    scoredCount,
    readinessPassed,
    activeView,
    phaseStatus: phaseApiStatus,
  });

  // Auto-expand current phase
  useEffect(() => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      next.add(currentPhase);
      return next;
    });
  }, [currentPhase]);

  const handleTogglePhase = useCallback((phaseId: string) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phaseId)) next.delete(phaseId);
      else next.add(phaseId);
      return next;
    });
  }, []);

  // Build phases for Sidebar
  const sidebarPhases = useMemo(() => {
    return Object.values(phaseState.phases).map((pg) => ({
      ...pg,
      expanded: expandedPhases.has(pg.id),
    }));
  }, [phaseState.phases, expandedPhases]);

  const sidebarBadges: SidebarBadges = {
    candidates: candidatesApi.data?.total ?? candidatesApi.data?.candidates?.length,
    official_backtests: formatBacktestBadge(slotsApi.data),
    cloud: formatCloudBadge(cloudBadgeTotal(cloudApi.data)),
  };

  const handleNavigate = useCallback((view: CardViewId) => {
    setActiveView(view);
  }, []);

  const handleConnectionTested = useCallback((ok: boolean, err: string | null) => {
    setConnectionOverride(ok);
    setConnectionError(err);
    try {
      sessionStorage.removeItem("brain_alpha_connection_tested");
    } catch (storageErr) {
      reportIgnoredError("legacy connection sessionStorage cleanup failed", storageErr);
    }
    void phaseApi.call("/api/phase_state");
  }, [phaseApi.call]);

  const handleDashboardSyncStart = useCallback(() => {
    setOfficialOpsAutoStart(true);
    setActiveView("official_operations");
  }, []);

  const handleDashboardSyncOpen = useCallback(() => {
    setOfficialOpsAutoStart(false);
    setActiveView("official_operations");
  }, []);

  const handleOfficialSyncCompleted = useCallback(() => {
    void phaseApi.call("/api/phase_state");
    void cloudApi.call("/api/snapshot/cloud");
  }, [cloudApi.call, phaseApi.call]);

  const handleOfficialReconnectRequested = useCallback(() => {
    setActiveView("dashboard");
  }, []);

  const handleCandidatePoolUpdated = useCallback(() => {
    void candidatesApi.call("/api/candidates?summary=true");
    void phaseApi.call("/api/phase_state");
  }, [candidatesApi.call, phaseApi.call]);

  const handleLocalSessionLoggedOut = useCallback(() => {
    setCredentials({ username: "", password: "", token: "" });
    setConnectionOverride(false);
    setConnectionError(null);
    void phaseApi.call("/api/phase_state");
  }, [phaseApi.call]);

  useEffect(() => {
    if (connectionOverride === true && phaseConnected) setConnectionOverride(null);
    if (connectionOverride === false && !phaseConnected) setConnectionOverride(null);
  }, [connectionOverride, phaseConnected]);

  const handleMobileNavigate = useCallback((target: PhaseId | "tools") => {
    if (target === "tools") {
      setActiveView("dashboard");
    } else {
      const phase = phaseState.phases[target as PhaseId];
      if (phase && phase.items.length > 0) {
        setActiveView(phase.items[0].id);
      }
    }
  }, [phaseState.phases]);

  const openScoring = useCallback((candidate: Candidate) => {
    setSelectedCandidate(candidate);
    setActiveView("scoring");
  }, []);

  const detailContent = useMemo(() => {
    switch (activeView) {
    case "dashboard":
      return <Dashboard notify={notify} connected={connected} contextFresh={contextFresh} phaseStatus={phaseApiStatus} onNavigateToSync={handleDashboardSyncStart} onOpenSync={handleDashboardSyncOpen}>
        {!connected && contextFresh && <LocalCacheSessionCard notify={notify} onLoggedOut={handleLocalSessionLoggedOut} />}
        {!connected && !contextFresh && <CredentialQuickStart credentials={credentials} managedCredentialsAvailable={managedCredentialsAvailable} onCredentialsChange={setCredentials} notify={notify} onConnectionTested={handleConnectionTested} />}
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
          onAutoStartConsumed={() => setOfficialOpsAutoStart(false)}
          onSyncCompleted={handleOfficialSyncCompleted}
          onReconnectRequested={handleOfficialReconnectRequested}
          onNavigateToCandidates={() => setActiveView("candidates")}
        />
      );
    case "candidates":
      return (
        <ErrorBoundary key="candidates">
          <CandidateTable notify={notify} showProductionControls showRowActions
            onScore={openScoring} credentials={credentials} onCandidatePoolUpdated={handleCandidatePoolUpdated} />
        </ErrorBoundary>
      );
    case "official_backtests":
      return <OfficialBacktestSlots notify={notify} />;
    case "scoring":
      return selectedCandidate
        ? <ScoringPanel notify={notify} candidate={selectedCandidate} />
        : <ScoringPlaceholder onPickCandidate={() => setActiveView("candidates")} />;
    case "quality_check":
      return <QualityCheckPanel notify={notify} />;
    case "submission_confirm":
    case "submission":
      return <SubmissionConfirmPanel notify={notify} />;
    case "checkpoint_status":
      return <SnapshotPanel key="checkpoint_status" notify={notify} viewMode="checkpoint_status" onNavigate={handleNavigate} />;
    case "robustness":
      return <SnapshotPanel key="robustness" notify={notify} viewMode="robustness" onNavigate={handleNavigate} />;
    case "config":
      return (
        <ConfigPanel
          notify={notify}
          credentials={credentials}
          onCredentialsChange={setCredentials}
          onConnectionTested={handleConnectionTested}
          connected={connected}
          contextFresh={contextFresh}
          managedCredentialsAvailable={managedCredentialsAvailable}
          onLoggedOut={handleLocalSessionLoggedOut}
        />
      );
    case "cloud":
      return <SnapshotPanel key="cloud" notify={notify} viewMode="cloud" onNavigate={handleNavigate} />;
    default:
      return (
        <div className="panel">
          <div className="panel-body-padded" style={{ textAlign: "center", padding: "3rem" }}>
            <p className="text-text-tertiary">未知视图</p>
          </div>
        </div>
      );
  }
  }, [
    activeView,
    selectedCandidate,
    credentials,
    notify,
    openScoring,
    handleNavigate,
    handleConnectionTested,
    connected,
    contextFresh,
    phaseApiStatus,
    jobState,
    managedCredentialsAvailable,
    officialOpsAutoStart,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    handleLocalSessionLoggedOut,
  ]);

  const viewLabel = VIEW_LABELS[activeView] || activeView;
  const currentPhaseObj = phaseState.phases[currentPhase];
  const topbarStatus = topbarConnectionStatus({ connected, contextFresh, phaseStatus: phaseApiStatus });
  const phaseShellStatusLabel = phaseApiStatus === "loading"
    ? "读取中"
    : phaseApiStatus === "error"
      ? "读取失败"
      : currentPhaseObj?.status === "complete" ? "已完成"
      : currentPhaseObj?.status === "active" ? "进行中"
      : currentPhaseObj?.status === "blocked" ? "已阻断"
      : "待解锁";
  const phaseShellStatusTone = phaseApiStatus === "loading" || phaseApiStatus === "error"
    ? "active"
    : currentPhaseObj?.status === "complete" ? "complete"
    : currentPhaseObj?.status === "blocked" ? "blocked"
    : currentPhaseObj?.status === "active" ? "active"
    : "pending";

  return (
    <div className="app-shell">

      {/* ═══ Top Bar (v3.0 redesign) ═══ */}
      <header className="app-topbar">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            className="btn btn-ghost btn-sm lg:hidden"
            onClick={() => setSidebarOpen((prev) => !prev)}
            aria-label="切换导航菜单"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          {/* Connection state */}
          <span className={`topbar-connection ${topbarStatus.tone}`} title={topbarStatus.title}>
            <span className={`status-dot ${topbarStatus.dotClass}`} />
            {topbarStatus.label}
          </span>
          <span style={{ color: "oklch(0.38 0.006 45)", fontSize: 12 }}>·</span>
          {/* Phase indicator */}
          <span className="topbar-phase">
            Phase {steps.findIndex((s) => s.status === "active") + 1 || "?"} · <strong>{currentPhaseObj?.label || viewLabel}</strong>
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {jobState.running && (
            <span className="badge badge-warning" style={{ fontFamily: "var(--font-mono)", fontSize: 10, cursor: "pointer" }}
              title={`${safeDisplayErrorMessage(jobState.progress?.status_message, "任务状态待确认")} · ${jobState.progress?.percent_complete != null ? Math.round(jobState.progress.percent_complete) + "%" : ""}`}
              onClick={() => setActiveView("dashboard")}
            >
              {jobState.progress?.percent_complete != null ? `${Math.round(jobState.progress.percent_complete)}%` : "..."} {(jobState.progress?.eta_seconds || 0) > 0 ? fmtEta(jobState.progress!.eta_seconds!) : ""}
            </span>
          )}
          <span className="badge badge-positive" style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
            PRODUCTION
          </span>
        </div>
      </header>

      {/* ═══ Sidebar (v3.0 phase groups) ═══ */}
      <Sidebar
        className={sidebarOpen ? "is-open" : ""}
        activeView={activeView}
        badges={sidebarBadges}
        onNavigate={handleNavigate}
        onClose={() => setSidebarOpen(false)}
        onTogglePhase={handleTogglePhase}
        phases={sidebarPhases}
      />
      {sidebarOpen && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 150, backgroundColor: "rgba(0,0,0,0.4)" }}
          onClick={() => setSidebarOpen(false)}
          className="lg:hidden"
          aria-hidden="true"
        />
      )}

      {/* ═══ Main Content ═══ */}
      <main className="app-main" id="main-content" tabIndex={-1}>
        <a href="#app-main-start" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[999] focus:px-4 focus:py-2 focus:bg-accent focus:text-text-inverse focus:rounded-md focus:font-medium focus:text-sm">
          跳到主内容
        </a>
        <div id="app-main-start" />

        {/* PhaseShell wrapper (v3.0) */}
        {currentPhaseObj && (
          <PhaseShell
            phaseId={currentPhase}
            phaseLabel={currentPhaseObj.label}
            statusLabel={phaseShellStatusLabel}
            statusTone={phaseShellStatusTone}
            unlockCondition={currentPhaseObj.unlockCondition}
            steps={steps}
          >
            <div className="animate-fade-in">
              <Suspense fallback={<PageLoader />}>
                {detailContent}
              </Suspense>
            </div>
          </PhaseShell>
        )}

        {/* No phase: just show content */}
        {!currentPhaseObj && (
          <div className="animate-fade-in">
            <Suspense fallback={<PageLoader />}>
              {detailContent}
            </Suspense>
          </div>
        )}
      </main>

      {/* ═══ Status Bar ═══ */}
      <footer className="app-statusbar">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className="status-dot status-dot-active" />
          <span>BRAIN API</span>
          <span>runtime: production</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span>v3.0 · Phase Navigation</span>
          <span>本地非提交页面</span>
        </div>
      </footer>

      {/* ═══ Mobile Tab Bar (v3.0) ═══ */}
      <MobileTabBar activePhase={currentPhase} onNavigate={handleMobileNavigate} />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function ScoringPlaceholder({ onPickCandidate }: { onPickCandidate: () => void }) {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: 16 }}>
      <div style={{
        width: 64, height: 64, borderRadius: "50%",
        background: "oklch(0.58 0.10 248 / 0.12)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="oklch(0.62 0.10 250)" strokeWidth="2" strokeLinecap="round">
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

function formatBacktestBadge(data?: BacktestSlotsResponse | null): string | undefined {
  if (!data) return undefined;
  const limit = backtestSlotLimit(data, 0);
  if (limit <= 0) return undefined;
  const active = backtestActiveCount(data);
  return `${active}/${limit}`;
}

function formatCloudBadge(total?: number): string | undefined {
  if (total == null) return undefined;
  return total >= 1000 ? `${(total / 1000).toFixed(1)}k` : String(total);
}

function cloudBadgeTotal(payload?: { count?: number; total?: number; summary?: Record<string, unknown> } | null): number | undefined {
  const summary = payload?.summary || {};
  return numericBadgeValue(payload?.count ?? payload?.total ?? summary.count ?? summary.total ?? summary.total_count);
}

function numericBadgeValue(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function topbarConnectionStatus({ connected, contextFresh, phaseStatus = "ready" }: { connected: boolean; contextFresh: boolean; phaseStatus?: PhaseApiStatus }) {
  if (phaseStatus === "loading") {
    return {
      label: "状态读取中",
      tone: "loading",
      dotClass: "status-dot-pending",
      title: "正在读取本地 session 与缓存状态；读取完成前不判定为未连接。",
    };
  }
  if (phaseStatus === "error") {
    return {
      label: "状态读取失败",
      tone: "read-error",
      dotClass: "status-dot-warning",
      title: "暂时无法确认 BRAIN 账户连接和本地缓存状态。",
    };
  }
  if (connected && contextFresh) {
    return {
      label: "已连接 · 本地缓存可用",
      tone: "connected",
      dotClass: "status-dot-active",
      title: "BRAIN 账户已连接，本地缓存也可用。",
    };
  }
  if (connected) {
    return {
      label: "已连接 · 待同步",
      tone: "connected",
      dotClass: "status-dot-warning",
      title: "BRAIN 账户已连接，但还没有完整本地缓存。",
    };
  }
  if (contextFresh) {
    return {
      label: "缓存模式 · 本地缓存可用",
      tone: "cache-ready",
      dotClass: "status-dot-warning",
      title: "BRAIN 账户未连接；本地缓存可用于非提交候选流程，官方同步、回测和提交前复核仍需连接。",
    };
  }
  return {
    label: "账户未连接",
    tone: "disconnected",
    dotClass: "status-dot-error",
    title: "BRAIN 账户未连接，且未检测到完整本地缓存。",
  };
}

function fmtEta(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}
