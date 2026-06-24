// ── UI State Types ────────────────────────────────────────────────────────

export type TabId =
  | "candidates"
  | "official_backtests"
  | "quality_check"
  | "submission_confirm"
  | "checkpoint_status"
  | "cloud"
  | "dashboard"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed"
  | "lifecycle"
  | "research_memory"
  | "research_knowledge"
  | "research_observability"
  | "prompt_runs"
  | "sqlite_indexes"
  | "robustness"
  | "scoring"
  | "submission"
  | "config"
  | "knowledge";

export interface Toast {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
  duration_ms?: number;
  action_label?: string;
  on_action?: () => void;
  secondary_action_label?: string;
  on_secondary_action?: () => void;
}

// ── Phase Navigation Types (UI Design System v3.0) ─────────────────────

export type PhaseId = "connect" | "discover" | "evaluate" | "ready";
export type PhaseStatus = "locked" | "pending" | "active" | "complete" | "blocked" | "loading" | "error" | "ready";

export interface PhaseGroup {
  id: PhaseId;
  label: string;
  status: PhaseStatus;
  items: PhaseNavItem[];
  expanded: boolean;
  unlockCondition: string;
}

export interface PhaseNavItem {
  id: CardViewId;
  label: string;
  icon: string;
  badge?: string | number;
  badgeTone?: "neutral" | "positive" | "warning" | "info";
}

export interface PhaseState {
  currentPhase: PhaseId;
  phases: Record<PhaseId, PhaseGroup>;
  overallProgress: number; // 0-4 steps completed
}

export interface StepGuideItem {
  id: string;
  label: string;
  status: "complete" | "active" | "pending";
  phase: PhaseId;
}

/**
 * Card-based navigation view identifier.
 * A subset of TabId used by the StateCards detail view routing.
 */
export type CardViewId =
  | "official_operations"
  | "dashboard"
  | "candidates"
  | "official_backtests"
  | "scoring"
  | "quality_check"
  | "submission_confirm"
  | "config"
  | "checkpoint_status"
  | "cloud"
  | "robustness";

// ── Aliases & additional shared types ────────────────────────────────────

export type PhaseApiStatus = PhaseStatus;

export interface LifecycleMetric {
  label: string;
  value: string | number;
  tone?: "positive" | "negative" | "warning" | "info" | "neutral";
  [key: string]: unknown;
}

export interface LifecycleMetricProps {
  metric: LifecycleMetric;
  [key: string]: unknown;
}

export interface LifecycleReplayPanelProps {
  alphaId?: string;
  [key: string]: unknown;
}

export interface QualitySummaryData {
  ready?: number;
  retained?: string;
  promotable?: number;
  rework?: number;
  blocked?: number;
  outputMode?: string;
  [key: string]: unknown;
}
