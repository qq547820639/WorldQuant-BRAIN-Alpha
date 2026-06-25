/**
 * usePhaseConnection — phase-state polling, connection override tracking,
 * derived connection/phase flags, and session lifecycle handlers.
 */

import { useState, useCallback, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { BrainCredentials, PhaseData } from '@/types';
import { useApi } from '@/hooks/useApi';
import type { useGlobalData } from '@/hooks/useGlobalData';
import { reportIgnoredError } from '@/utils/reportIgnoredError';
import type { PhaseApiStatus } from '@/hooks/usePhaseState';

export interface PhaseConnectionOptions {
  setCredentials: Dispatch<SetStateAction<BrainCredentials>>;
  globalData: ReturnType<typeof useGlobalData>;
}

export interface PhaseConnectionResult {
  connectionOverride: boolean | null;
  connectionError: string | null;
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
  handleConnectionTested: (ok: boolean, err: string | null) => void;
  handleLocalSessionLoggedOut: () => void;
}

export function usePhaseConnection({
  setCredentials,
  globalData,
}: PhaseConnectionOptions): PhaseConnectionResult {
  const [connectionOverride, setConnectionOverride] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const phaseApi = useApi<PhaseData>();

  useEffect(() => {
    void phaseApi.call('/api/phase_state');
    const interval = setInterval(() => {
      void phaseApi.call('/api/phase_state');
    }, 10_000);
    return () => clearInterval(interval);
  }, [phaseApi.call]);

  const phaseData = phaseApi.data;
  const phaseApiStatus: PhaseApiStatus = phaseData ? 'ready' : phaseApi.error ? 'error' : 'loading';
  const phaseConnected = Boolean(phaseData?.connected);
  const connected = Boolean(connectionOverride ?? phaseConnected) && !connectionError;
  const contextFresh = phaseData?.context_fresh ?? false;
  const candidatesCount = phaseData?.candidates_count ?? globalData.candidates.data?.total ?? 0;
  const scoredCount = phaseData?.scored_count ?? 0;
  const readinessPassed = phaseData?.readiness_passed ?? false;
  const managedCredentialsAvailable = Boolean(
    globalData.config.data?.config?.credentials?.managed_credentials_available
  );

  const handleConnectionTested = useCallback(
    (ok: boolean, err: string | null) => {
      setConnectionOverride(ok);
      setConnectionError(err);
      setCredentials((prev) => ({ ...prev, password: '' }));
      try {
        sessionStorage.removeItem('brain_alpha_connection_tested');
      } catch (storageErr) {
        reportIgnoredError('legacy connection sessionStorage cleanup failed', storageErr);
      }
      void phaseApi.call('/api/phase_state');
    },
    [phaseApi.call, setCredentials]
  );

  const handleLocalSessionLoggedOut = useCallback(() => {
    setCredentials({ username: '', password: '', token: '' });
    setConnectionOverride(false);
    setConnectionError(null);
    void phaseApi.call('/api/phase_state');
  }, [phaseApi.call, setCredentials]);

  useEffect(() => {
    if (connectionOverride === true && phaseConnected) setConnectionOverride(null);
    if (connectionOverride === false && !phaseConnected) setConnectionOverride(null);
  }, [connectionOverride, phaseConnected]);

  return {
    connectionOverride,
    connectionError,
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
    handleConnectionTested,
    handleLocalSessionLoggedOut,
  };
}
