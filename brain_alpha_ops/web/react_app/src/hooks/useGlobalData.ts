/**
 * P0-7 fix: Global data context that consolidates shared API calls.
 *
 * Before: App.tsx, Dashboard, CandidateTable, ScoringPanel, and other
 * components independently called the same endpoints (/api/candidates,
 * /api/backtest_slots, /api/snapshot/cloud, /api/config), resulting in
 * redundant network requests and potential view inconsistencies.
 *
 * After: App.tsx fetches all shared data once via GlobalDataProvider.
 * Child components consume from useGlobalData() context instead of
 * creating their own useApi hooks for these endpoints.
 */

import React, { createContext, useContext, useCallback, useEffect, useMemo } from "react";
import type { BacktestSlotsResponse, Candidate } from "@/types";
import { useApi } from "@/hooks/useApi";
import type { ApiMeta } from "@/hooks/useApi";

export interface GlobalDataState {
  candidates: {
    data: {
      candidates?: Candidate[];
      items?: Candidate[];
      main_pool_candidates?: Candidate[];
      workflow_plan?: Record<string, unknown> | null;
      candidate_workflow?: Record<string, unknown> | null;
      pool_summary?: Record<string, unknown>;
      total?: number;
      returned_count?: number;
      total_count?: number;
    } | null;
    error: string | null;
    loading: boolean;
    lastErrorMeta: ApiMeta | null;
  };
  slots: {
    data: BacktestSlotsResponse | null;
    error: string | null;
    loading: boolean;
    lastErrorMeta: ApiMeta | null;
  };
  cloud: {
    data: { count?: number; total?: number; summary?: Record<string, unknown> } | null;
    error: string | null;
    loading: boolean;
    lastErrorMeta: ApiMeta | null;
  };
  config: {
    data: { config?: { credentials?: { managed_credentials_available?: boolean } } } | null;
    error: string | null;
    loading: boolean;
    lastErrorMeta: ApiMeta | null;
  };
  refreshAll: () => void;
}

const GlobalDataContext = createContext<GlobalDataState | null>(null);

export function GlobalDataProvider({ children }: { children: React.ReactNode }) {
  const candidatesApi = useApi<{
    candidates?: Candidate[];
    items?: Candidate[];
    main_pool_candidates?: Candidate[];
    workflow_plan?: Record<string, unknown> | null;
    candidate_workflow?: Record<string, unknown> | null;
    pool_summary?: Record<string, unknown>;
    total?: number;
    returned_count?: number;
    total_count?: number;
  }>();
  const slotsApi = useApi<BacktestSlotsResponse>();
  const cloudApi = useApi<{ count?: number; total?: number; summary?: Record<string, unknown> }>();
  const configApi = useApi<{ config?: { credentials?: { managed_credentials_available?: boolean } } }>();

  const refreshAll = useCallback(() => {
    void candidatesApi.call("/api/candidates");
    void slotsApi.call("/api/backtest_slots");
    void cloudApi.call("/api/snapshot/cloud");
    void configApi.call("/api/config");
  }, [candidatesApi.call, slotsApi.call, cloudApi.call, configApi.call]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const interval = setInterval(() => {
      refreshAll();
    }, 30000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  const value: GlobalDataState = useMemo(() => ({
    candidates: {
      data: candidatesApi.data,
      error: candidatesApi.error,
      loading: candidatesApi.loading,
      lastErrorMeta: candidatesApi.lastErrorMeta,
    },
    slots: {
      data: slotsApi.data,
      error: slotsApi.error,
      loading: slotsApi.loading,
      lastErrorMeta: slotsApi.lastErrorMeta,
    },
    cloud: {
      data: cloudApi.data,
      error: cloudApi.error,
      loading: cloudApi.loading,
      lastErrorMeta: cloudApi.lastErrorMeta,
    },
    config: {
      data: configApi.data,
      error: configApi.error,
      loading: configApi.loading,
      lastErrorMeta: configApi.lastErrorMeta,
    },
    refreshAll,
  }), [
    candidatesApi.data, candidatesApi.error, candidatesApi.loading, candidatesApi.lastErrorMeta,
    slotsApi.data, slotsApi.error, slotsApi.loading, slotsApi.lastErrorMeta,
    cloudApi.data, cloudApi.error, cloudApi.loading, cloudApi.lastErrorMeta,
    configApi.data, configApi.error, configApi.loading, configApi.lastErrorMeta,
    refreshAll,
  ]);

  return React.createElement(GlobalDataContext.Provider, { value }, children);
}

export function useGlobalData(): GlobalDataState {
  const ctx = useContext(GlobalDataContext);
  if (!ctx) {
    throw new Error("useGlobalData must be used within a GlobalDataProvider");
  }
  return ctx;
}
