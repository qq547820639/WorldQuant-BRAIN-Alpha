/**
 * BRAIN Alpha Ops — UI Design System v3.0
 * 应用外壳：侧边栏(阶段组) + 顶栏(连接+阶段) + PhaseShell + 移动端Tab
 * 渐进式 4 阶段导航，基于新架构重新实现
 */

import { Suspense, useState, useCallback, useRef, useEffect, useMemo } from "react";
import type {
  BrainCredentials,
  Candidate,
  CardViewId,
  PhaseData,
  PhaseId,
} from "@/types";
import { useApi } from "@/hooks/useApi";
import type { ApiMeta } from "@/hooks/useApi";
import { apiErrorMessage, nextActionLabel, safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { useToast } from "@/hooks/useToast";
import { useJobState } from "@/hooks/useJobState";
import { usePhaseState, type PhaseApiStatus } from "@/hooks/usePhaseState";
import ToastContainer from "@/components/ToastContainer";
import Sidebar from "@/components/Sidebar";
// Dashboard imported via renderView
// import Dashboard from "@/components/Dashboard";
// CredentialQuickStart imported via renderView
// import CredentialQuickStart from "./components/CredentialQuickStart";  // S-01: deduplicated from inline
// JobMonitor imported via renderView
// import JobMonitor from "@/components/JobMonitor";
// CandidateTable imported via renderView
// import CandidateTable from "@/components/CandidateTable";
// ErrorBoundary imported via renderView
// import ErrorBoundary from "@/components/ErrorBoundary";
import { FlowGuide } from "./components/FlowGuide";
import PhaseShell from "@/components/PhaseShell";
import MobileTabBar from "@/components/MobileTabBar";
import { useKeyboardShortcuts, KeyboardShortcutsHelp } from "@/hooks/useKeyboardShortcuts";
import { reportIgnoredError } from "@/utils/reportIgnoredError";
import { renderActiveView, type RenderViewProps } from "@/components/views/renderView";
import { topbarConnectionStatus, fmtEta, formatBacktestBadge, formatCloudBadge, cloudBadgeTotal } from "@/components/views/helpers";
import { useGlobalData } from "@/hooks/useGlobalData";


// ── Config ──────────────────────────────────────────────────────────────────

const VIEW_LABELS: Record<string, string> = {
  dashboard: "运行总览",
  official_operations: "官方操作",
  candidates: "候选管理",
  official_backtests: "回测监控",
  scoring: "科学评分",
  quality_check: "质量门禁",
  submission_confirm: "阻断复核",
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

// ── App Shell ───────────────────────────────────────────────────────────────

export default function App() {
  const [activeView, setActiveView] = useState<CardViewId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  // B-09 (R3 — FIXED): password cleared from JS heap immediately after successful auth
  const [credentials, setCredentials] = useState<BrainCredentials>({ username: "", password: "", token: "" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set(["connect"]));
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    try {
      return (localStorage.getItem("brain_alpha_theme") as "dark" | "light") || "dark";
    } catch {
      return "dark";
    }
  });
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }, secondaryAction?: { label: string; onClick: () => void }) => {
      addToast(type, msg, 5000, action, secondaryAction);
    }, [addToast],
  );

  const jobState = useJobState(notify, credentials);
  // SA-1: Multiple components independently call the same API endpoints.
  // Consider a global data-fetching layer (React Context + SWR or Zustand)
  // for cache deduplication and stale-while-revalidate patterns.


  // P0-7 fix: replaced 4 independent useApi hooks with single GlobalDataProvider
  const globalData = useGlobalData();

  const lastCandidatesErrorRef = useRef<string>('');
  const lastSlotsErrorRef = useRef<string>('');
  const lastCloudErrorRef = useRef<string>('');
  const lastConfigErrorRef = useRef<string>('');

  useEffect(() => {
    // P1-4: build toast action buttons from the backend's next_action hint.
    const buildAction = (meta: ApiMeta | null, retryFn: () => void) => {
      const nextAction = meta?.user_error?.next_action || meta?.next_action;
      const label = meta?.user_error?.action_label || nextActionLabel(nextAction);
      if (!nextAction || !label) return undefined;
      switch (nextAction) {
        case "reconnect_session":
          return { label, onClick: () => handleOfficialReconnectRequested() };
        case "refresh_cache":
          return { label, onClick: () => { globalData.refreshAll(); void phaseApi.call("/api/phase_state"); } };
        case "wait_and_retry":
          return { label, onClick: () => { notify("info", "5 秒后将自动重试…"); setTimeout(() => retryFn(), 5000); } };
        case "check_config":
          return { label, onClick: () => setActiveView("config") };
        default:
          return { label, onClick: () => retryFn() };
      }
    };

    const gd = globalData;
    if (gd.candidates.error && gd.candidates.error !== lastCandidatesErrorRef.current) {
      lastCandidatesErrorRef.current = gd.candidates.error;
      notify("warning", `候选数据加载失败: ${safeDisplayErrorMessage(gd.candidates.error)}`, buildAction(gd.candidates.lastErrorMeta, () => { gd.refreshAll(); }));
    }
    if (gd.slots.error && gd.slots.error !== lastSlotsErrorRef.current) {
      lastSlotsErrorRef.current = gd.slots.error;
      notify("warning", `回测槽位加载失败: ${safeDisplayErrorMessage(gd.slots.error)}`, buildAction(gd.slots.lastErrorMeta, () => { gd.refreshAll(); }));
    }
    if (gd.cloud.error && gd.cloud.error !== lastCloudErrorRef.current) {
      lastCloudErrorRef.current = gd.cloud.error;
      notify("warning", `云端快照加载失败: ${safeDisplayErrorMessage(gd.cloud.error)}`, buildAction(gd.cloud.lastErrorMeta, () => { gd.refreshAll(); }));
    }
    if (gd.config.error && gd.config.error !== lastConfigErrorRef.current) {
      lastConfigErrorRef.current = gd.config.error;
      notify("warning", `配置状态加载失败: ${safeDisplayErrorMessage(gd.config.error)}`, buildAction(gd.config.lastErrorMeta, () => { gd.refreshAll(); }));
    }
  }, [globalData, notify]);

  // Theme: sync document.documentElement class and localStorage
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("brain_alpha_theme", theme); } catch { console.warn("App: scheduled refresh skipped — backend unavailable"); }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onNavigateDashboard: () => setActiveView("dashboard"),
    onNavigateCandidates: () => setActiveView("candidates"),
    onNavigateConfig: () => setActiveView("config"),
    onToggleSidebar: () => setSidebarOpen((v) => !v),
    onRefresh: () => { void phaseApi.call("/api/phase_state"); },
    onEscape: () => setSidebarOpen(false),
  });

  const [connectionOverride, setConnectionOverride] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [officialOpsAutoStart, setOfficialOpsAutoStart] = useState(false);

  // Phase state from backend (poll every 10s)
  const phaseApi = useApi<PhaseData>();

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
  const candidatesCount = phaseData?.candidates_count ?? globalData.candidates.data?.total ?? 0;
  const scoredCount = phaseData?.scored_count ?? 0;
  const readinessPassed = phaseData?.readiness_passed ?? false;
  const managedCredentialsAvailable = Boolean(
    globalData.config.data?.config?.credentials?.managed_credentials_available,
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
    candidates: globalData.candidates.data?.total ?? globalData.candidates.data?.candidates?.length,
    official_backtests: formatBacktestBadge(globalData.slots.data),
    cloud: formatCloudBadge(cloudBadgeTotal(globalData.cloud.data)),
  };

  const handleNavigate = useCallback((view: CardViewId) => {
    setActiveView(view);
  }, []);

  const handleConnectionTested = useCallback((ok: boolean, err: string | null) => {
    setConnectionOverride(ok);
    setConnectionError(err);
    if (ok) {
      setCredentials((prev) => ({ ...prev, password: "" }));
    }
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
    globalData.refreshAll();
  }, [phaseApi.call]);

  const handleOfficialReconnectRequested = useCallback(() => {
    setActiveView("dashboard");
  }, []);

  const handleCandidatePoolUpdated = useCallback(() => {
    globalData.refreshAll();
    void phaseApi.call("/api/phase_state");
  }, [phaseApi.call]);

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

  const viewProps: RenderViewProps = useMemo(() => ({
    activeView, selectedCandidate, credentials, notify,
    connected, contextFresh, phaseApiStatus, managedCredentialsAvailable,
    officialOpsAutoStart, jobState,
    onOpenScoring: openScoring,
    onNavigate: handleNavigate,
    onConnectionTested: handleConnectionTested,
    onCredentialsChange: setCredentials,
    onDashboardSyncStart: handleDashboardSyncStart,
    onDashboardSyncOpen: handleDashboardSyncOpen,
    onOfficialSyncCompleted: handleOfficialSyncCompleted,
    onOfficialReconnectRequested: handleOfficialReconnectRequested,
    onCandidatePoolUpdated: handleCandidatePoolUpdated,
    onLocalSessionLoggedOut: handleLocalSessionLoggedOut,
    onAutoStartConsumed: () => setOfficialOpsAutoStart(false),
    phaseData: phaseData,
  }), [
    activeView, selectedCandidate, credentials, notify,
    connected, contextFresh, phaseApiStatus, managedCredentialsAvailable,
    officialOpsAutoStart, jobState, phaseData,
    openScoring, handleNavigate, handleConnectionTested,
    handleDashboardSyncStart, handleDashboardSyncOpen,
    handleOfficialSyncCompleted, handleOfficialReconnectRequested,
    handleCandidatePoolUpdated, handleLocalSessionLoggedOut,
  ]);

  const detailContent = renderActiveView(viewProps);

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
          <span style={{ color: "var(--color-text-dim)", fontSize: 12 }}>·</span>
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
          {/* Theme toggle */}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
            title={theme === "dark" ? "浅色模式" : "深色模式"}
          >
            {theme === "dark" ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5"/>
                <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
            )}
          </button>
          {/* Keyboard shortcuts help */}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setShortcutsHelpOpen(true)}
            aria-label="键盘快捷键帮助"
            title="键盘快捷键"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </button>
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
            <FlowGuide currentPhase={currentPhase} />
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

      {/* Keyboard Shortcuts Help Modal */}
      {shortcutsHelpOpen && (
        <KeyboardShortcutsHelp onClose={() => setShortcutsHelpOpen(false)} />
      )}
    </div>);
}
