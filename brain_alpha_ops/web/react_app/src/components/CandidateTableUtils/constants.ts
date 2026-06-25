export const MIN_TARGET_POOL_SIZE = 1;
export const MAX_TARGET_POOL_SIZE = 100;

export const DEFAULT_TARGET_POOL_SIZE = 10;
export const MAX_FILTER_LENGTH = 200;

export const SUBMIT_ONLY_BLOCKER_CODES = new Set([
  'decision_band_not_submit_candidate',
  'gate_not_submission_ready',
  'human_confirmation_required',
  'manual_confirmation_required',
  'missing_official_alpha_id',
  'missing_official_metrics',
  'missing_official_metric_fields',
  'needs_human_confirmation',
  'official_pass_fail_not_pass',
  'expression_too_nested',
]);
