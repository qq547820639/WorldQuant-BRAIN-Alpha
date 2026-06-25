/**
 * useAppState — shared type definitions
 *
 * Public surface: `AppState` (re-exported from index).
 * `SidebarBadges` is internal to this module.
 */

import type {
  BrainCredentials,
  Candidate,
  CardViewId,
  PhaseData,
  PhaseId,
  PhaseGroup,
} from '@/types';
import type { useToast } from '@/hooks/useToast';
import type { useJobState } from '@/hooks/useJobState';
import type { useGlobalData } from '@/hooks/useGlobalData';
import type { useApi } from '@/hooks/useApi';
import type { usePhaseState, PhaseApiStatus } from '@/hooks/usePhaseState';

export interface SidebarBadges {
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
  toasts: ReturnType<typeof useToast>['toasts'];
  notify: (
    type: 'success' | 'error' | 'warning' | 'info',
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void }
  ) => void;
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
  phaseState: ReturnType<typeof usePhaseState>['phaseState'];
  steps: ReturnType<typeof usePhaseState>['steps'];
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
  handleMobileNavigate: (target: PhaseId | 'tools') => void;
  openScoring: (candidate: Candidate) => void;
}
