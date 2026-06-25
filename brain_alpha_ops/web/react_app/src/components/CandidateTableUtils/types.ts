import type {
  Candidate,
  LifecycleMetric,
  LifecycleMetricProps,
  LifecycleReplayPanelProps,
} from '@/types';

export type { LifecycleMetric, LifecycleMetricProps, LifecycleReplayPanelProps };

export type CandidateQueueView =
  | 'candidates'
  | 'pending_backtest'
  | 'running_backtest'
  | 'backtest_rework'
  | 'passed'
  | 'submittable'
  | 'submitted'
  | 'failed';

export type CandidateCheckResult = {
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  status?: string;
  passed?: boolean;
  submittable?: boolean;
  is_stale?: boolean;
  score?: number;
  failed_reasons?: string[];
  checked_at?: string;
};

export type CandidateListMeta = {
  returned: number;
  total: number;
};

export type SimulationResultSummary = {
  completed: number;
  failed: number;
  total: number;
};

export type CandidatePoolSnapshot = {
  eligibleCount: number;
  retainedCount: number;
  deficit: number;
  retainedCandidates: Candidate[];
  workflowPlan?: CandidateWorkflowPlan | null;
};

export type CandidateWorkflowPlan = {
  producer?: { deficit?: number; candidate_ids?: string[]; next_candidate_ids?: string[] };
  validator?: { deficit?: number; candidate_ids?: string[]; next_candidate_ids?: string[] };
  rework?: { deficit?: number; candidate_ids?: string[]; next_candidate_ids?: string[] };
  review?: { deficit?: number; candidate_ids?: string[]; next_candidate_ids?: string[] };
};
