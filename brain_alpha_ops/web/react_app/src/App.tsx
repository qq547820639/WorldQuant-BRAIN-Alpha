/**
 * BRAIN Alpha Ops — UI Design System v3.0
 * 应用外壳：侧边栏(阶段组) + 顶栏(连接+阶段) + PhaseShell + 移动端Tab
 * 渐进式 4 阶段导航，基于新架构重新实现
 */

import { useState, useCallback, useRef, useEffect, lazy, Suspense, useMemo } from "react";
import type { BrainCredentials, Candidate, CardViewId, PhaseId } from "@/types";
import { useApi } from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { useJobState } from "@/hooks/useJobState";
import { usePhaseState } from "@/hooks/usePhaseState";
import ToastContainer from "@/components/ToastContainer";
import Sidebar from "@/components/Sidebar";
import Dashboard from "@/components/Dashboard";
import JobMonitor from "@/components/JobMonitor";
import CandidateTable from "@/components/CandidateTable";
import PhaseShell from "@/components/PhaseShell";
import MobileTabBar from "@/components/MobileTabBar";

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
  config: "系统配置",
  cloud: "云端快照",
};

const PHASE_LABELS: Record<PhaseId, string> = {
  connect: "连接与就绪",
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

// ── Sub-components ──────────────────────────────────────────────────────────

function CredentialQuickStart({
  credentials,
  onCredentialsChange,
  notify,
  onConnectionTested,
}: {
  credentials: BrainCredentials;
  onCredentialsChange: (c: BrainCredentials) => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onConnectionTested?: (success: boolean, error: string | null) => void;
}) {
  const connectionApi = useApi<{ ok: boolean; environment?: string; error?: string; error_code?: string }>();
  const usernameInputRef = useRef<HTMLInputElement | null>(null);
  const hasSession = Boolean(credentials.username || credentials.password || credentials.token);
  const credentialMode = credentials.token.trim()
    ? "Token" : credentials.username.trim() || credentials.password ? "账号密码" : "托管凭证";

  const updateCredential = <K extends keyof BrainCredentials>(key: K, value: BrainCredentials[K]) => {
    onCredentialsChange({ ...credentials, [key]: value });
  };

  const testConnection = async () => {
    const email = (credentials.username || "").trim();
    const password = credentials.password || "";
    const token = credentials.token.trim();
    const payload: Record<string, string> = {};
    if (token) {
      payload.token = token;
    } else if (email || password) {
      if (!email || email.indexOf("@") < 1) { notify("warning", "请填写有效的 BRAIN 账户邮箱。"); return; }
      if (!password.trim()) { notify("warning", "请填写 BRAIN 密码，或改用 Token / 托管凭证。"); return; }
      payload.username = email;
      payload.password = password;
    }
    if (!Object.keys(payload).length) {
      notify("info", "未填写页面凭证，将使用维护者配置的托管凭证测试 BRAIN 连接");
    }
    const result = await connectionApi.call("/api/test_connection", { method: "POST", body: JSON.stringify(payload) });
    if (!result?.ok) {
      const err = result?.error || result?.error_code || "BRAIN 连接测试失败";
      notify("error", err);
      onConnectionTested?.(false, err);
      return;
    }
    notify("success", "BRAIN 连接测试通过");
    onConnectionTested?.(true, null);
  };

  return (
    <div className="panel mb-4">
      <div className="panel-header">
        <span>凭证与连接</span>
        <div style={{ display: "flex", gap: 6 }}>
          <span className="badge badge-info">Step 1</span>
          <span className="badge badge-neutral">凭证: {credentialMode}</span>
        </div>
      </div>
      <div className="panel-body-padded">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            <span className="form-label">账户邮箱</span>
            <input
              ref={usernameInputRef}
              className="form-input"
              type="email"
              inputMode="email"
              autoComplete="username"
              value={credentials.username}
              onChange={(e) => updateCredential("username", e.target.value.trim())}
              placeholder="email@example.com"
              maxLength={160}
            />
          </label>
          <label className="block text-sm">
            <span className="form-label">密码</span>
            <input
              className="form-input"
              type="password"
              autoComplete="current-password"
              value={credentials.password}
              onChange={(e) => updateCredential("password", e.target.value)}
              placeholder="BRAIN 密码"
              maxLength={256}
            />
          </label>
          <label className="block text-sm md:col-span-2">
            <span className="form-label">Token（可选）</span>
            <input
              className="form-input"
              type="password"
              autoComplete="off"
              value={credentials.token}
              onChange={(e) => updateCredential("token", e.target.value.trim())}
              placeholder="已有 token 时可只填 token"
              maxLength={512}
            />
          </label>
        </div>
        <div style={{
          marginTop: 12, padding: "8px 12px", borderRadius: 4,
          background: "oklch(0.52 0.06 155 / 0.10)", fontSize: 13, color: "oklch(0.62 0.10 160)",
        }}>
          凭证只保留在当前页面，不写入文件或运行记录。
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <span className="text-xs text-text-tertiary" role="status">
            {connectionApi.error ? `连接失败: ${connectionApi.error}` :
             connectionApi.data?.ok ? `连接正常: ${connectionApi.data.environment || "production"}` :
             hasSession ? "凭证已填写，尚未测试" : "也可留空，使用托管凭证"}
          </span>
          <button type="button" className="btn btn-primary" onClick={testConnection} disabled={connectionApi.loading}>
            {connectionApi.loading ? "测试中..." : "测试连接"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── App Shell ───────────────────────────────────────────────────────────────

export default function App() {
  const [activeView, setActiveView] = useState<CardViewId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
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

  const candidatesApi = useApi<{ candidates?: Candidate[]; total?: number }>();
  const slotsApi = useApi<{ slot_limit?: number; slots?: Array<{ slot: number; status?: string }> }>();
  const cloudApi = useApi<{ count?: number; total?: number }>();

  useEffect(() => {
    void candidatesApi.call("/api/candidates?limit=1000");
    void slotsApi.call("/api/backtest_slots");
    void cloudApi.call("/api/snapshot/cloud?limit=5");
  }, [candidatesApi.call, slotsApi.call, cloudApi.call]);

  useEffect(() => {
    // Independently notify about each API error so the user knows which feature is affected
    if (candidatesApi.error) notify("warning", `候选数据加载失败: ${candidatesApi.error}`);
    if (slotsApi.error) notify("warning", `回测槽位加载失败: ${slotsApi.error}`);
    if (cloudApi.error) notify("warning", `云端快照加载失败: ${cloudApi.error}`);
  }, [candidatesApi.error, slotsApi.error, cloudApi.error, notify]);

  // Track actual connection test result — persist in sessionStorage so page
  // refresh doesn't force the user to re-test the connection.
  const [connectionTested, setConnectionTested] = useState(() => {
    try { return sessionStorage.getItem("brain_alpha_connection_tested") === "1"; } catch { return false; }
  });
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Phase state from backend (poll every 10s)
  const phaseApi = useApi<{
    current_phase: string; connected: boolean; context_fresh: boolean;
    candidates_count: number; scored_count: number; readiness_passed: boolean;
    sync: { in_progress: boolean; scanned: number; total: number; elapsed_seconds: number; stalled: boolean };
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
  const connected = connectionTested && !connectionError;
  const contextFresh = phaseData?.context_fresh ?? false;
  const candidatesCount = phaseData?.candidates_count ?? candidatesApi.data?.total ?? 0;
  const scoredCount = phaseData?.scored_count ?? 0;
  const readinessPassed = phaseData?.readiness_passed ?? false;

  const { phaseState, steps, currentPhase } = usePhaseState({
    connected,
    contextFresh,
    candidatesCount,
    scoredCount,
    readinessPassed,
    activeView,
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
    cloud: formatCloudBadge(cloudApi.data?.count ?? cloudApi.data?.total),
  };

  const handleNavigate = useCallback((view: CardViewId) => {
    setActiveView(view);
  }, []);

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
      return <Dashboard notify={notify} connected={connected} contextFresh={contextFresh} onNavigateToSync={() => setActiveView("official_operations")}>
        {!connected && <CredentialQuickStart credentials={credentials} onCredentialsChange={setCredentials} notify={notify} onConnectionTested={(ok, err) => { setConnectionTested(true); setConnectionError(err); if (ok) { try { sessionStorage.setItem("brain_alpha_connection_tested", "1"); } catch { /* ignore */ } } }} />}
        {connected && contextFresh && (
          <div className="animate-fade-in">
            <JobMonitor notify={notify} credentials={credentials} jobState={jobState} />
          </div>
        )}
      </Dashboard>;
    case "official_operations":
      return <OfficialOperationsPanel notify={notify} credentials={credentials} />;
    case "candidates":
      return (
        <CandidateTable key="candidates" notify={notify} showProductionControls showRowActions
          onScore={openScoring} credentials={credentials} />
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
    case "config":
      return <ConfigPanel notify={notify} credentials={credentials} onCredentialsChange={setCredentials} />;
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
  }, [activeView, selectedCandidate, credentials, notify, openScoring, handleNavigate, connected, contextFresh, jobState]);

  const viewLabel = VIEW_LABELS[activeView] || activeView;
  const currentPhaseObj = phaseState.phases[currentPhase];
  const connectionStatus = connected ? "已连接" : "未连接";
  const connectionTone = connected ? "connected" : "disconnected";

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
          <span className={`topbar-connection ${connectionTone}`}>
            <span className={`status-dot ${connected ? "status-dot-active" : "status-dot-error"}`} />
            {connectionStatus}
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
              title={`${jobState.progress?.status_message || ""} · ${jobState.progress?.percent_complete != null ? Math.round(jobState.progress.percent_complete) + "%" : ""}`}
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
            statusLabel={
              currentPhaseObj.status === "complete" ? "已完成"
              : currentPhaseObj.status === "active" ? "进行中"
              : currentPhaseObj.status === "blocked" ? "已阻断"
              : "待解锁"
            }
            statusTone={currentPhaseObj.status === "complete" ? "complete" : currentPhaseObj.status === "blocked" ? "blocked" : currentPhaseObj.status === "active" ? "active" : "pending"}
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

function formatBacktestBadge(data?: { slot_limit?: number; slots?: Array<{ slot: number; status?: string }> } | null): string | undefined {
  if (!data) return undefined;
  const slots = data.slots || [];
  const limit = data.slot_limit || 8;
  const active = slots.filter((s) => s.status && !["EMPTY", "COMPLETED", "FAILED", "ERROR"].includes(s.status)).length;
  return `${active}/${limit}`;
}

function formatCloudBadge(total?: number): string | undefined {
  if (total == null) return undefined;
  return total >= 1000 ? `${(total / 1000).toFixed(1)}k` : String(total);
}

function fmtEta(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}
