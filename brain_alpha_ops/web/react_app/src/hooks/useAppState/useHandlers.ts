/**
 * useHandlers — navigation, dashboard-sync, official-ops sync, reconnect,
 * candidate-pool refresh, and scoring-entry action handlers.
 */

import { useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Candidate, CardViewId, PhaseData } from '@/types';
import type { useGlobalData } from '@/hooks/useGlobalData';
import type { useApi } from '@/hooks/useApi';

export interface HandlersOptions {
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
  setSelectedCandidate: Dispatch<SetStateAction<Candidate | null>>;
  setOfficialOpsAutoStart: Dispatch<SetStateAction<boolean>>;
  phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
  globalData: ReturnType<typeof useGlobalData>;
}

export interface HandlersResult {
  handleNavigate: (view: CardViewId) => void;
  handleDashboardSyncStart: () => void;
  handleDashboardSyncOpen: () => void;
  handleOfficialSyncCompleted: () => void;
  handleOfficialReconnectRequested: () => void;
  handleCandidatePoolUpdated: () => void;
  openScoring: (candidate: Candidate) => void;
}

export function useHandlers({
  setActiveView,
  setSelectedCandidate,
  setOfficialOpsAutoStart,
  phaseApiCall,
  globalData,
}: HandlersOptions): HandlersResult {
  const handleNavigate = useCallback(
    (view: CardViewId) => {
      setActiveView(view);
    },
    [setActiveView]
  );

  const handleDashboardSyncStart = useCallback(() => {
    setOfficialOpsAutoStart(true);
    setActiveView('official_operations');
  }, [setOfficialOpsAutoStart, setActiveView]);

  const handleDashboardSyncOpen = useCallback(() => {
    setOfficialOpsAutoStart(false);
    setActiveView('official_operations');
  }, [setOfficialOpsAutoStart, setActiveView]);

  const handleOfficialSyncCompleted = useCallback(() => {
    void phaseApiCall('/api/phase_state');
    globalData.refreshAll();
  }, [phaseApiCall, globalData]);

  const handleOfficialReconnectRequested = useCallback(() => {
    setActiveView('dashboard');
  }, [setActiveView]);

  const handleCandidatePoolUpdated = useCallback(() => {
    globalData.refreshAll();
    void phaseApiCall('/api/phase_state');
  }, [phaseApiCall, globalData]);

  const openScoring = useCallback(
    (candidate: Candidate) => {
      setSelectedCandidate(candidate);
      setActiveView('scoring');
    },
    [setSelectedCandidate, setActiveView]
  );

  return {
    handleNavigate,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    openScoring,
  };
}
