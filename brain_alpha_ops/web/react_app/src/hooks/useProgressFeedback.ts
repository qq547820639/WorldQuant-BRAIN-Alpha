import { useEffect, useMemo, useState, useRef } from "react";
import { classifyProgressState, type JobStateClassification } from "@/helpers/runPayload";
import type { ProgressLifecycle, UnifiedProgress } from "@/types";
import {
  normalizedPercent,
  progressUserFacingError,
  safeProgressMessage,
  isOpenEndedCloudScan,
  openEndedScanStatusMessage,
  scanCountText,
  etaSecondsFromProgress,
  estimatedEtaSeconds,
  fmtDuration,
  displayProgressPhase,
} from "@/components/ProgressFeedback/progressUtils";

export interface UseProgressFeedbackOptions {
  state: ProgressLifecycle;
  title?: string;
  progress?: UnifiedProgress | null;
  error?: string | null;
  idleText?: string;
  successText?: string;
}

export interface UseProgressFeedbackResult {
  remaining: number;
  elapsed: number;
  lastUpdatedAt: Date | null;
  progressState: JobStateClassification;
  rawPercent: number | null;
  percent: number | null;
  roundedPercent: number;
  isBusy: boolean;
  showProgressBar: boolean;
  isDeterminate: boolean;
  label: string;
  message: string;
  openEndedCloudScan: boolean;
  displayMessage: string;
  displayError: string;
  eta: string;
  isStalled: boolean;
  scanCount: string | null;
}

export function useProgressFeedback({
  state,
  title = "进度",
  progress,
  error,
  idleText = "就绪",
  successText = "完成",
}: UseProgressFeedbackOptions): UseProgressFeedbackResult {
  const [remaining, setRemaining] = useState(() => etaSecondsFromProgress(progress));
  const [elapsed, setElapsed] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const startedAtRef = useRef(Date.now());

  useEffect(() => {
    setRemaining(etaSecondsFromProgress(progress));
  }, [progress?.eta_deadline_at_ms, progress?.eta_seconds, progress?.task_id, progress?.job_id]);

  useEffect(() => {
    if (state === "idle") { startedAtRef.current = Date.now(); return; }
    if (state === "loading" || state === "progress") {
      if (lastUpdatedAt === null) startedAtRef.current = Date.now();
    }
    setLastUpdatedAt(new Date());
  }, [error, progress?.message, progress?.phase, progress?.status, progress?.status_message, progress?.percent, progress?.percent_complete, state]);

  useEffect(() => {
    if (state !== "loading" && state !== "progress") return;
    if (!remaining || remaining <= 0) return;
    const timer = setInterval(() => {
      const deadlineRemaining = etaSecondsFromProgress(progress, { deadlineOnly: true });
      setRemaining((v) => deadlineRemaining > 0 ? deadlineRemaining : Math.max(0, v - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [progress?.eta_deadline_at_ms, remaining, state]);

  useEffect(() => {
    if (state !== "loading" && state !== "progress") { setElapsed(0); return; }
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [state]);

  const progressState = useMemo(() => classifyProgressState(state, progress), [progress, state]);
  const rawPercent = useMemo(() => normalizedPercent(progress, progressState), [progress, progressState]);
  const percent = state === "success" && rawPercent == null ? 100 : rawPercent;
  const roundedPercent = percent == null ? 0 : Math.round(percent);
  const isBusy = state === "loading" || state === "progress";
  const showProgressBar = isBusy || state === "success" || (state === "error" && percent != null);
  const isDeterminate = showProgressBar && percent != null;
  const label = displayProgressPhase(progress, title);
  const message = safeProgressMessage(progress, state, idleText, successText);
  const openEndedCloudScan = isOpenEndedCloudScan(progress);
  const displayMessage = openEndedCloudScan ? openEndedScanStatusMessage(progress, message) : message;
  const structuredError = useMemo(() => progressUserFacingError(progress), [progress]);
  const displayError = structuredError || error || "操作失败。";
  const estimatedEta = estimatedEtaSeconds(progress, elapsed, remaining);
  const eta = estimatedEta > 0 ? fmtDuration(estimatedEta) : "";
  const isStalled = isBusy && !isDeterminate && !openEndedCloudScan && elapsed > 10;
  const scanCount = scanCountText(progress, openEndedCloudScan);

  return {
    remaining,
    elapsed,
    lastUpdatedAt,
    progressState,
    rawPercent,
    percent,
    roundedPercent,
    isBusy,
    showProgressBar,
    isDeterminate,
    label,
    message,
    openEndedCloudScan,
    displayMessage,
    displayError,
    eta,
    isStalled,
    scanCount,
  };
}
