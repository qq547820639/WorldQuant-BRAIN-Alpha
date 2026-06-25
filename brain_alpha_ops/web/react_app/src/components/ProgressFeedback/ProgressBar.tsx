import { memo } from "react";
import type { ProgressLifecycle, UnifiedProgress } from "@/types";
import type { JobStateClassification } from "@/helpers/runPayload";
import { progressFillClass } from "./progressUtils";

interface ProgressBarProps {
  title: string;
  label: string;
  state: ProgressLifecycle;
  progress?: UnifiedProgress | null;
  progressState: JobStateClassification;
  percent: number | null;
  roundedPercent: number;
  showProgressBar: boolean;
  isDeterminate: boolean;
  isStalled: boolean;
}

function ProgressBar({
  title,
  label,
  state,
  progress,
  progressState,
  percent,
  roundedPercent,
  showProgressBar,
  isDeterminate,
  isStalled,
}: ProgressBarProps) {
  if (!showProgressBar) return null;

  const fillClass = progressFillClass(state, progress, progressState, isStalled);

  return (
    <div className={`progress-bar ${isDeterminate ? "" : "indeterminate"}`}
      role="progressbar"
      aria-label={`${title}: ${label}`}
      aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={isDeterminate ? roundedPercent : undefined}
      style={{ marginBottom: 12 }}
    >
      <div className={`progress-bar-fill ${fillClass}`} style={isDeterminate ? { width: `${percent}%` } : undefined} />
    </div>
  );
}

export default memo(ProgressBar);
