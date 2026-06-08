/**
 * PhaseShell — Phase wrapper component (UI Design System v3.0)
 * Shows current phase header with unlock condition, step guide progress bar,
 * and wraps page content.
 */
import { memo } from "react";
import type { PhaseId, StepGuideItem } from "@/types";
import StepGuide from "@/components/StepGuide";

interface Props {
  phaseId: PhaseId;
  phaseLabel: string;
  statusLabel: string;
  statusTone: "complete" | "active" | "pending" | "blocked";
  unlockCondition: string;
  steps: StepGuideItem[];
  children: React.ReactNode;
}

function statusBadgeClass(tone: string) {
  switch (tone) {
  case "complete": return "badge badge-positive";
  case "active":   return "badge badge-info";
  case "blocked":  return "badge badge-negative";
  default:         return "badge badge-neutral";
  }
}

export default memo(function PhaseShell({
  phaseId,
  phaseLabel,
  statusLabel,
  statusTone,
  unlockCondition,
  steps,
  children,
}: Props) {
  return (
    <div className="phase-shell" data-phase={phaseId} role="region" aria-label={`${phaseLabel} — ${statusLabel}`}>
      <div className="phase-shell-header">
        <div>
          <div className="phase-shell-title">{phaseLabel}</div>
          <div className="phase-shell-subtitle">{unlockCondition}</div>
        </div>
        <span className={statusBadgeClass(statusTone)}>{statusLabel}</span>
      </div>

      <StepGuide steps={steps} />

      <div className="phase-shell-body">
        {children}
      </div>
    </div>
  );
});
