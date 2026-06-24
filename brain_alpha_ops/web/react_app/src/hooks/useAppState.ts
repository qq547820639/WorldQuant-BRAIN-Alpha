/**
 * useAppState — App-level state management hook
 *
 * Centralizes all core application state and logic that was previously in App.tsx.
 * This keeps App.tsx focused on rendering and layout.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import type {
  BrainCredentials,
  Candidate,
  CardViewId,
  PhaseData,
  PhaseId,
  PhaseGroup,
} from "@/types";
import { useApi } from "@/hooks/useApi";
import type { ApiMeta } from "@/hooks/useApi";
import { nextActionLabel, safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { useToast } from "@/hooks/useToast";
import { useJobState } from "@/hooks/useJobState";
import { usePhaseState, type PhaseApiStatus } from "@/hooks/usePhaseState";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { reportIgnoredError } from "@/utils/reportIgnoredError";
import { useGlobalData } from "@/hooks/useGlobalData";
import { formatBacktestBadge, formatCloudBadge, cloudBadgeTotal } from "@/components/views/helpers";

interface SidebarBadges {
  candidates?: number;
  official_backtests?: string;
  scoring?: number;
  checkpoint_status?: number;
  cloud?: string;
}

export interface AppState {
  activeView: CardViewId;
  selectedCandidate: Candidate | null;
  credentials: BrainCredentials;
  sidebarOpen: boolean;
  expandedPhases: Set<string>;
  shortcutsHelpOpen: boolean;
  connectionOverride: boolean | null;
  connectionError: string | null;
  officialOpsAutoStart: boolean;
  toasts: ReturnType<typeof useToast>["toasts"];
  notify: (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }, secondaryAction?: { label: string; onClick: () => void }) => void;
  dismissToast: (id: string) => void;
  jobState: ReturnType<typeof useJobState>;
  globalData: ReturnType<typeof useGlobalData>;
  phaseApi: ReturnType<typeof useApi<PhaseData>>;
  phaseData: PhaseData | null;
  phaseApiStatus: PhaseApiStatus;
  phaseConnected: boolean;
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  managedCredentialsAvailable: boolean;
  phaseState: ReturnType<typeof usePhaseState>["phaseState"];
  steps: ReturnType<typeof usePhaseState>["steps"];
  currentPhase: PhaseId;
  sidebarPhases: PhaseGroup[];
  sidebarBadges: SidebarBadges;
  setActiveView: (view: CardViewId) => void;
  setSelectedCandidate: (candidate: Candidate | null) => void;
  setCredentials: (credentials: BrainCredentials) => void;
  setSidebarOpen: (open: boolean) => void;
  setExpandedPhases: (phases: Set<string> | ((prev: Set<string>) => Set<string>)) => void;
  setShortcutsHelpOpen: (open: boolean) => void;
  setOfficialOpsAutoStart: (value: boolean) => void;
  handleTogglePhase: (phaseId: string) => void;
  handleNavigate: (view: CardViewId) => void;
  handleConnectionTested: (ok: boolean, err: string | null) => void;
  handleDashboardSyncStart: () => void;
  handleDashboardSyncOpen: () => void;
  handleOfficialSyncCompleted: () => void;
  handleOfficialReconnectRequested: () => void;
  handleCandidatePoolUpdated: () => void;
  handleLocalSessionLoggedOut: () => void;
  handleMobileNavigate: (target: PhaseId | "tools") => void;
  openScoring: (candidate: Candidate) => void;
}

export function useAppState(): AppState {
  const [activeView, setActiveView] = useState<CardViewId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [credentials, setCredentials] = useState<BrainCredentials>({ username: "", password: "", token: "" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set(["connect"]));
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }, secondaryAction?: { label: string; onClick: () => void }) => {
      addToast(type, msg, 5000, action, secondaryAction);
    }, [addToast],
  );

  const jobState = useJobState(notify, credentials);
  const globalData = useGlobalData();

  const lastCandidatesErrorRef = useRef<string>('');
  const lastSlotsErrorRef = useRef<string>('');
  const lastCloudErrorRef = useRef<string>('');
  const lastConfigErrorRef = useRef<string>('');

  const [connectionOverride, setConnectionOverride] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [officialOpsAutoStart, setOfficialOpsAutoStart] = useState(false);

  const phaseApi = useApi<PhaseData>();

  useEffect(() => {
    void phaseApi.call("/api/phase_state");
    const interval = setInterval(() => {
      void phaseApi.call("/api/phase_state");
    }, 10_000);
    return () => clearInterval(interval);
  }, [phaseApi.call]);

  const buildAction = useCallback((meta: ApiMeta | null, retryFn: () => void) => {
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
  }, [globalData, phaseApi.call, notify]);

  useEffect(() => {
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
  }, [globalData, notify, buildAction]);

  useKeyboardShortcuts({
    onNavigateToDashboard: () => setActiveView("dashboard"),
    onNavigateToConfig: () => setActiveView("config"),
    onRefresh: () => { void phaseApi.call("/api/phase_state"); globalData.refreshAll(); },
    onShowHelp: () => setShortcutsHelpOpen(true),
    onEscape: () => {
      setSidebarOpen(false);
      setShortcutsHelpOpen(false);
    },
  });

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

  const sidebarPhases = useMemo(() => {
    return Object.values(phaseState.phases).map((pg) => ({
      ...pg,
      expanded: expandedPhases.has(pg.id),
    }));
  }, [phaseState.phases, expandedPhases]);

  const handleNavigate = useCallback((view: CardViewId) => {
    setActiveView(view);
  }, []);

  const handleConnectionTested = useCallback((ok: boolean, err: string | null) => {
    setConnectionOverride(ok);
    setConnectionError(err);
    setCredentials((prev) => ({ ...prev, password: "" }));
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
  }, [phaseApi.call, globalData]);

  const handleOfficialReconnectRequested = useCallback(() => {
    setActiveView("dashboard");
  }, []);

  const handleCandidatePoolUpdated = useCallback(() => {
    globalData.refreshAll();
    void phaseApi.call("/api/phase_state");
  }, [phaseApi.call, globalData]);

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

  const sidebarBadges: SidebarBadges = {
    candidates: globalData.candidates.data?.total ?? globalData.candidates.data?.candidates?.length,
    official_backtests: globalData.slots.data ? formatBacktestBadge(globalData.slots.data) : undefined,
    cloud: globalData.cloud.data ? formatCloudBadge(cloudBadgeTotal(globalData.cloud.data)) : undefined,
  };

  return {
    activeView,
    selectedCandidate,
    credentials,
    sidebarOpen,
    expandedPhases,
    shortcutsHelpOpen,
    connectionOverride,
    connectionError,
    officialOpsAutoStart,
    toasts,
    notify,
    dismissToast,
    jobState,
    globalData,
    phaseApi,
    phaseData,
    phaseApiStatus,
    phaseConnected,
    connected,
    contextFresh,
    candidatesCount,
    scoredCount,
    readinessPassed,
    managedCredentialsAvailable,
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    sidebarBadges,
    setActiveView,
    setSelectedCandidate,
    setCredentials,
    setSidebarOpen,
    setExpandedPhases,
    setShortcutsHelpOpen,
    setOfficialOpsAutoStart,
    handleTogglePhase,
    handleNavigate,
    handleConnectionTested,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    handleLocalSessionLoggedOut,
    handleMobileNavigate,
    openScoring,
  };
}
