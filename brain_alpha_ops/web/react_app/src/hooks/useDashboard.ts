import { useEffect, useState, useRef } from "react";
import { useApi } from "@/hooks/useApi";
import { useGlobalData } from "@/hooks/useGlobalData";
import type { JobStatus, ResearchMemorySummary, TrendApiResponse } from "@/types";
import type { TrendData } from "@/components/TrendPanel";
import { safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { saveResumeState } from "@/utils/resumeState";
import {
  loadTrendData,
  appendTrendPoint,
  syncTrendToBackend,
  TREND_KEY,
} from "@/components/DashboardTrendData";
import {
  cloudSnapshotSummary,
  cloudSnapshotPreviewRows,
} from "@/components/DashboardCloudSnapshot";

interface UseDashboardOptions {
  connected: boolean;
  contextFresh: boolean;
  phaseStatus?: "loading" | "error" | "ready";
  onNavigateToSync: () => void;
  onOpenSync?: () => void;
  jobRunning?: boolean;
}

export function useDashboard({
  connected,
  contextFresh,
  phaseStatus = "ready",
  onNavigateToSync,
  onOpenSync,
  jobRunning = false,
}: UseDashboardOptions) {
  const [snapshotExpanded, setSnapshotExpanded] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [trendCandidates, setTrendCandidates] = useState<TrendData[]>(() =>
    loadTrendData(TREND_KEY.CANDIDATES),
  );
  const [trendSubmissions, setTrendSubmissions] = useState<TrendData[]>(() =>
    loadTrendData(TREND_KEY.SUBMISSIONS),
  );
  const [showGuide, setShowGuide] = useState(
    () => !localStorage.getItem("brain_alpha_guide_dismissed"),
  );

  const statusApi = useApi<JobStatus>();
  const memoryApi = useApi<ResearchMemorySummary>();
  const { cloud: cloudGlobal, refreshAll } = useGlobalData();

  const status = statusApi.data;
  const cloud = cloudGlobal.data;
  const memory = memoryApi.data;
  const cloudSummaryData = cloudSnapshotSummary(cloud);
  const cloudPreviewRows = cloudSnapshotPreviewRows(cloud);

  const prevJobRunningRef = useRef(jobRunning);

  const errors = [
    statusApi.error ? `Status: ${safeDisplayErrorMessage(statusApi.error)}` : "",
    cloudGlobal.error ? `Cloud: ${safeDisplayErrorMessage(cloudGlobal.error)}` : "",
    memoryApi.error ? `Memory: ${safeDisplayErrorMessage(memoryApi.error)}` : "",
  ].filter(Boolean);

  const loading = statusApi.loading || cloudGlobal.loading || memoryApi.loading;

  const phasePending = phaseStatus === "loading";
  const phaseFailed = phaseStatus === "error";
  const currentStep = phasePending || phaseFailed
    ? 1
    : !contextFresh
      ? !connected
        ? 1
        : 2
      : 3;
  const stepLabel = phasePending
    ? "读取本地状态"
    : phaseFailed
      ? "状态读取失败"
      : currentStep === 1
        ? "连接 BRAIN"
        : currentStep === 2
          ? "准备本地缓存"
          : connected
            ? "开始验证"
            : "缓存模式";
  const openManualSync = onOpenSync || onNavigateToSync;

  useEffect(() => {
    statusApi.call("/api/production-validation/status");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
  }, [statusApi.call, memoryApi.call]);

  useEffect(() => {
    const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
    if (poolSize != null && poolSize > 0) {
      saveResumeState({ lastPoolSize: poolSize });
    }
  }, [memory?.total_candidates, status?.progress?.candidates_generated]);

  useEffect(() => {
    if (cloud != null && !cloudGlobal.loading && !cloudGlobal.error) {
      const syncTime = cloudSnapshotSummary(cloud).loaded_at || new Date().toISOString();
      saveResumeState({ lastSyncTime: syncTime });
    }
  }, [cloud != null, cloudGlobal.loading]);

  useEffect(() => {
    let cancelled = false;
    async function fetchTrends() {
      try {
        const res = await fetch("/api/trends?days=30");
        if (!res.ok) return;
        const json = (await res.json()) as TrendApiResponse;
        if (!json || typeof json !== "object" || !json.ok) return;
        const data = json.data;
        if (!Array.isArray(data) || data.length === 0) return;
        const candidatesPoints: TrendData[] = [];
        const submissionsPoints: TrendData[] = [];
        for (const row of data) {
          const date = typeof row.date === "string" ? row.date : "";
          const c = Number(row.candidates);
          const s = Number(row.submissions);
          if (date && Number.isFinite(c)) {
            candidatesPoints.push({ date, value: c });
          }
          if (date && Number.isFinite(s)) {
            submissionsPoints.push({ date, value: s });
          }
        }
        if (!cancelled) {
          if (candidatesPoints.length > 0) setTrendCandidates(candidatesPoints.slice(-7));
          if (submissionsPoints.length > 0)
            setTrendSubmissions(submissionsPoints.slice(-7));
        }
      } catch {
        console.warn("Dashboard: API unavailable, fallback to localStorage");
      }
    }
    fetchTrends();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
    if (poolSize != null && poolSize > 0) {
      const updated = appendTrendPoint(TREND_KEY.CANDIDATES, poolSize);
      setTrendCandidates(updated);
    }
    const submissions = status?.progress?.submissions ?? cloudSummaryData?.submitted_count;
    if (submissions != null) {
      const updated = appendTrendPoint(TREND_KEY.SUBMISSIONS, submissions);
      setTrendSubmissions(updated);
    }
    const syncCandidates = (memory?.total_candidates ??
      status?.progress?.candidates_generated ??
      0) as number;
    const syncSubmissions = (status?.progress?.submissions ??
      cloudSummaryData?.submitted_count ??
      0) as number;
    const syncCycles = (status?.progress?.completed_cycles ?? 0) as number;
    if (syncCandidates > 0 || syncSubmissions > 0) {
      syncTrendToBackend(syncCandidates, syncSubmissions, syncCycles);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    status?.progress?.candidates_generated,
    status?.progress?.submissions,
    cloudSummaryData?.submitted_count,
    memory?.total_candidates,
  ]);

  useEffect(() => {
    if (prevJobRunningRef.current && !jobRunning) {
      const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
      if (poolSize != null && poolSize > 0) {
        const updated = appendTrendPoint(TREND_KEY.CANDIDATES, poolSize);
        setTrendCandidates(updated);
      }
      const submissions = status?.progress?.submissions ?? cloudSummaryData?.submitted_count;
      if (submissions != null) {
        const updated = appendTrendPoint(TREND_KEY.SUBMISSIONS, submissions);
        setTrendSubmissions(updated);
      }
      const syncCandidates = (memory?.total_candidates ??
        status?.progress?.candidates_generated ??
        0) as number;
      const syncSubmissions = (status?.progress?.submissions ??
        cloudSummaryData?.submitted_count ??
        0) as number;
      const syncCycles = (status?.progress?.completed_cycles ?? 0) as number;
      if (syncCandidates > 0 || syncSubmissions > 0) {
        syncTrendToBackend(syncCandidates, syncSubmissions, syncCycles);
      }
    }
    prevJobRunningRef.current = jobRunning;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobRunning]);

  const retryAll = () => {
    statusApi.call("/api/production-validation/status");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
    refreshAll();
  };

  const dismissGuide = () => {
    localStorage.setItem("brain_alpha_guide_dismissed", "1");
    setShowGuide(false);
  };

  const toggleGuide = () => {
    localStorage.removeItem("brain_alpha_guide_dismissed");
    setShowGuide(true);
  };

  const toggleSnapshot = () => {
    setSnapshotExpanded((v) => !v);
  };

  const closeReport = () => {
    setShowReport(false);
  };

  const cloudLoading = cloudGlobal.loading;
  const cloudError = cloudGlobal.error ? safeDisplayErrorMessage(cloudGlobal.error) : null;

  return {
    snapshotExpanded,
    showReport,
    reportMarkdown,
    setReportMarkdown,
    trendCandidates,
    trendSubmissions,
    status,
    cloud,
    memory,
    cloudSummaryData,
    cloudPreviewRows,
    cloudLoading,
    cloudError,
    errors,
    loading,
    showGuide,
    phasePending,
    phaseFailed,
    currentStep,
    stepLabel,
    openManualSync,
    retryAll,
    dismissGuide,
    toggleGuide,
    toggleSnapshot,
    openReport: () => setShowReport(true),
    closeReport,
  };
}
