/**
 * Progress feedback / operational detail panels for CandidateTable.
 *
 * Displays the real-time status of ongoing operations:
 * - Candidate pool auto-advance
 * - BRAIN official simulation
 * - Candidate local optimization
 * - Quality gate batch check
 *
 * Extracted from CandidateTable.tsx. This component shows the
 * "detail" views for each async pipeline stage.
 *
 * NOTE: A per-candidate expansion panel (scoring details, gate results,
 * attribution tree) does not yet exist in this codebase. This component
 * serves as the operational status panel and can be extended in the future.
 */

import { memo } from "react";
import type { UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

export interface CandidateDetailPanelProps {
  showProductionControls: boolean;

  // Auto-advance task
  taskState: "idle" | "loading" | "progress" | "success" | "error";
  taskProgress: UnifiedProgress | null;
  taskError: string | null;
  taskStreamExhausted: boolean;
  onRetryTask: () => void;

  // BRAIN simulation
  simState: "idle" | "loading" | "progress" | "success" | "error";
  simProgress: UnifiedProgress | null;
  simError: string | null;
  onRetrySim: () => void;

  // Optimization
  optimizationState: "idle" | "loading" | "progress" | "success" | "error";
  optimizationProgress: UnifiedProgress | null;
  optimizationError: string | null;
  onRetryOptimization: () => void;

  // Batch check
  checkState: "idle" | "loading" | "progress" | "success" | "error";
  checkProgress: UnifiedProgress | null;
  checkError: string | null;
  onRetryCheck: () => void;
}

export const CandidateDetailPanel = memo(function CandidateDetailPanel({
  showProductionControls,
  taskState,
  taskProgress,
  taskError,
  taskStreamExhausted,
  onRetryTask,
  simState,
  simProgress,
  simError,
  onRetrySim,
  optimizationState,
  optimizationProgress,
  optimizationError,
  onRetryOptimization,
  checkState,
  checkProgress,
  checkError,
  onRetryCheck,
}: CandidateDetailPanelProps) {
  if (!showProductionControls) {
    return null;
  }

  return (
    <>
      {taskState !== "idle" && (
        <ProgressFeedback
          state={taskStreamExhausted && taskState === "progress" ? "error" : taskState}
          title="候选池自动推进"
          progress={taskProgress}
          error={taskError || (taskStreamExhausted && taskState === "progress" ? "候选池自动推进状态不明确，取消未确认。" : null)}
          onRetry={onRetryTask}
          compact={taskState === "success"}
        />
      )}

      {simState !== "idle" && (
        <ProgressFeedback
          state={simState}
          title="BRAIN官方模拟"
          progress={simProgress}
          error={simError}
          onRetry={onRetrySim}
          compact={simState === "success"}
        />
      )}

      {optimizationState !== "idle" && (
        <ProgressFeedback
          state={optimizationState}
          title="候选本地优化"
          progress={optimizationProgress}
          error={optimizationError}
          onRetry={onRetryOptimization}
          compact={optimizationState === "success"}
        />
      )}

      {checkState !== "idle" && (
        <ProgressFeedback
          state={checkState}
          title="质量门槛检查"
          progress={checkProgress}
          error={checkError}
          onRetry={onRetryCheck}
          compact={checkState === "success"}
        />
      )}
    </>
  );
});
