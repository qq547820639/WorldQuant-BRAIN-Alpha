import type { ProgressLifecycle, UnifiedProgress } from "@/types";
import { fmtClock, interruptionText } from "./progressUtils";

interface ProgressFooterProps {
  state: ProgressLifecycle;
  lastUpdatedAt: Date | null;
  displayError: string;
  displayMessage: string;
  progress?: UnifiedProgress | null;
  onRetry?: () => void;
  retryLabel: string;
}

export default function ProgressFooter({
  state,
  lastUpdatedAt,
  displayError,
  displayMessage,
  progress,
  onRetry,
  retryLabel,
}: ProgressFooterProps) {
  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", marginTop: 8, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
        {lastUpdatedAt && <span>最后更新 {fmtClock(lastUpdatedAt)}</span>}
        {state === "error" && <span>{interruptionText(displayError || displayMessage, progress?.phase)}</span>}
      </div>

      {state === "error" && (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {onRetry && (
            <button type="button" className="btn btn-primary" onClick={onRetry}>
              {retryLabel}
            </button>
          )}
        </div>
      )}
    </>
  );
}
