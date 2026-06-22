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
  case "pending":  return "badge badge-warning";
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
  const isBlocked = statusTone === "pending" || statusTone === "blocked";

  return (
    <div className="phase-shell" data-phase={phaseId} role="region" aria-label={`${phaseLabel} — ${statusLabel}`}>
      <div className="phase-shell-header">
        <div>
          <div className="phase-shell-title">{phaseLabel}</div>
          <div className="phase-shell-subtitle">{unlockCondition}</div>
        </div>
        <span className={statusBadgeClass(statusTone)}>{statusLabel}</span>
      </div>

      {/* Blocked / pending warning banner */}
      {isBlocked && (
        <div style={{
          margin: "0 16px 8px", padding: "8px 14px", borderRadius: 6,
          border: "1px solid", borderColor: "var(--color-panel-negative-border)",
          background: "var(--color-warning-banner-bg)",
          fontSize: 13, color: "var(--color-warning-banner-text)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ flexShrink: 0 }}>
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/>
          </svg>
          <span>
            {statusTone === "blocked" ? "此阶段已被阻断，请先解决阻断问题。" : "完成前置阶段后解锁。当前阶段尚未就绪，以下内容仅供参考。"}
          </span>
        </div>
      )}

      <StepGuide steps={steps} />

      <div className="phase-shell-body" style={isBlocked ? { opacity: 0.45, filter: "grayscale(0.3)" } : undefined}>
        {children}
      </div>
    </div>
  );
});
