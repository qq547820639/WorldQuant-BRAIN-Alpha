import type { ProgressLifecycle, UnifiedProgress } from "@/types";
import type { JobStateClassification } from "@/helpers/runPayload";
import { progressStatusBadge } from "./progressUtils";

interface ProgressHeaderProps {
  title: string;
  label: string;
  state: ProgressLifecycle;
  progress?: UnifiedProgress | null;
  progressState: JobStateClassification;
  percent: number | null;
  roundedPercent: number;
  isBusy: boolean;
  showProgressBar: boolean;
}

export default function ProgressHeader({
  title,
  label,
  state,
  progress,
  progressState,
  percent,
  roundedPercent,
  isBusy,
  showProgressBar,
}: ProgressHeaderProps) {
  const badge = progressStatusBadge(state, progress, progressState, percent);

  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
      <div style={{ minWidth: 0 }}>
        <p className="text-base font-medium text-text-primary">{title}</p>
        <p className="text-sm text-text-tertiary mt-1">{label}</p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <span className={`badge ${badge.className}`}>{badge.label}</span>
        {isBusy && percent == null && <span className="spinner" />}
        {showProgressBar && percent != null && state !== "success" && (
          <span className="text-sm tabular text-accent font-medium">{roundedPercent}%</span>
        )}
        {state === "success" && (
          <span style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--color-success-check-bg)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-status-complete-text)", fontSize: 12, fontWeight: 600 }} aria-hidden="true">&#10003;</span>
        )}
      </div>
    </div>
  );
}
