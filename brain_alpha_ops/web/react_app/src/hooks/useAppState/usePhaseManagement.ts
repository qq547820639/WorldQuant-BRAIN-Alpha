/**
 * usePhaseManagement — phase-state derivation, sidebar phase groups,
 * expand/collapse toggling, and mobile navigation mapping.
 */

import { useCallback, useEffect, useMemo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { CardViewId, PhaseId, PhaseGroup } from '@/types';
import { usePhaseState } from '@/hooks/usePhaseState';
import type { PhaseApiStatus } from '@/hooks/usePhaseState';

export interface PhaseManagementOptions {
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  activeView: CardViewId;
  phaseApiStatus: PhaseApiStatus;
  expandedPhases: Set<string>;
  setExpandedPhases: Dispatch<SetStateAction<Set<string>>>;
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
}

export interface PhaseManagementResult {
  phaseState: ReturnType<typeof usePhaseState>['phaseState'];
  steps: ReturnType<typeof usePhaseState>['steps'];
  currentPhase: PhaseId;
  sidebarPhases: PhaseGroup[];
  handleTogglePhase: (phaseId: string) => void;
  handleMobileNavigate: (target: PhaseId | 'tools') => void;
}

export function usePhaseManagement({
  connected,
  contextFresh,
  candidatesCount,
  scoredCount,
  readinessPassed,
  activeView,
  phaseApiStatus,
  expandedPhases,
  setExpandedPhases,
  setActiveView,
}: PhaseManagementOptions): PhaseManagementResult {
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
  }, [currentPhase, setExpandedPhases]);

  const handleTogglePhase = useCallback(
    (phaseId: string) => {
      setExpandedPhases((prev) => {
        const next = new Set(prev);
        if (next.has(phaseId)) next.delete(phaseId);
        else next.add(phaseId);
        return next;
      });
    },
    [setExpandedPhases]
  );

  const sidebarPhases = useMemo(() => {
    return Object.values(phaseState.phases).map((pg) => ({
      ...pg,
      expanded: expandedPhases.has(pg.id),
    }));
  }, [phaseState.phases, expandedPhases]);

  const handleMobileNavigate = useCallback(
    (target: PhaseId | 'tools') => {
      if (target === 'tools') {
        setActiveView('dashboard');
      } else {
        const phase = phaseState.phases[target];
        if (phase && phase.items.length > 0) {
          setActiveView(phase.items[0].id);
        }
      }
    },
    [phaseState.phases, setActiveView]
  );

  return {
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    handleTogglePhase,
    handleMobileNavigate,
  };
}
