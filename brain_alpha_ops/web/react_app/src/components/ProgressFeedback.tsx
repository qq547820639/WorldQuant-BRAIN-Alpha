/** Unified progress and loading feedback — Terminal Precision design */
import { memo } from "react";
import type { ProgressLifecycle, UnifiedProgress } from "@/types";
import { useProgressFeedback } from "@/hooks/useProgressFeedback";
import ProgressHeader from "@/components/ProgressFeedback/ProgressHeader";
import ProgressBar from "@/components/ProgressFeedback/ProgressBar";
import ProgressBody from "@/components/ProgressFeedback/ProgressBody";
import ProgressFooter from "@/components/ProgressFeedback/ProgressFooter";

interface Props {
  state: ProgressLifecycle;
  title?: string;
  progress?: UnifiedProgress | null;
  error?: string | null;
  idleText?: string;
  successText?: string;
  retryLabel?: string;
  compact?: boolean;
  onRetry?: () => void;
}

export default memo(function ProgressFeedback({
  state, title = "进度", progress, error,
  idleText = "就绪", successText = "完成",
  retryLabel = "重试", compact = false, onRetry,
}: Props) {
  const {
    lastUpdatedAt,
    progressState,
    percent,
    roundedPercent,
    isBusy,
    showProgressBar,
    isDeterminate,
    label,
    displayMessage,
    displayError,
    eta,
    isStalled,
    scanCount,
    elapsed,
  } = useProgressFeedback({ state, title, progress, error, idleText, successText });

  if (state === "idle" && compact) return null;

  const errorBorder = state === "error" ? { borderColor: "var(--color-error-border)", background: "var(--color-error-bg)" } : {};
  const successBorder = state === "success" ? { borderColor: "var(--color-success-border)", background: "var(--color-success-bg)" } : {};
  const stallBorder = isStalled ? { borderColor: "var(--color-stall-border)", background: "var(--color-stall-bg)" } : {};

  return (
    <div
      className="panel animate-fade-in"
      style={{ marginBottom: 16, ...errorBorder, ...successBorder, ...stallBorder }}
      role={isBusy ? "status" : undefined}
      aria-live={state === "error" ? "assertive" : "polite"}
    >
      <div className={`panel-body-${compact ? "compact" : "padded"}`}>
        <ProgressHeader
          title={title}
          label={label}
          state={state}
          progress={progress}
          progressState={progressState}
          percent={percent}
          roundedPercent={roundedPercent}
          isBusy={isBusy}
          showProgressBar={showProgressBar}
        />

        <ProgressBar
          title={title}
          label={label}
          state={state}
          progress={progress}
          progressState={progressState}
          percent={percent}
          roundedPercent={roundedPercent}
          showProgressBar={showProgressBar}
          isDeterminate={isDeterminate}
          isStalled={isStalled}
        />

        <ProgressBody
          state={state}
          displayMessage={displayMessage}
          displayError={displayError}
          scanCount={scanCount}
          elapsed={elapsed}
          eta={eta}
          isStalled={isStalled}
        />

        <ProgressFooter
          state={state}
          lastUpdatedAt={lastUpdatedAt}
          displayError={displayError}
          displayMessage={displayMessage}
          progress={progress}
          onRetry={onRetry}
          retryLabel={retryLabel}
        />
      </div>
    </div>
  );
});
