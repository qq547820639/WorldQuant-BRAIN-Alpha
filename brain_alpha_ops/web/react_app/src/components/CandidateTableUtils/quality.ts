import type { Candidate } from '@/types';
import type { CandidateCheckResult } from './types';
import { SUBMIT_ONLY_BLOCKER_CODES } from './constants';
import { candidateText, record, candidateIds } from './base';

export function candidateStatus(candidate: Candidate) {
  const normalized = candidateText(
    candidate.lifecycle_status || candidate.quality_diagnosis?.status || candidate.gate?.status
  );
  return normalized.toLowerCase();
}

export function candidateStage(candidate: Candidate) {
  const submission = record(candidate.submission);
  return candidateText(
    submission.stage || submission.status || candidate.lifecycle_status
  ).toLowerCase();
}

export function candidateLocalValid(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (typeof diagnosis.local_candidate_valid === 'boolean') {
    return diagnosis.local_candidate_valid;
  }
  return candidate.local_quality?.passed === true;
}

export function candidateHasBlockingQuality(candidate: Candidate) {
  return candidateHasLocalBlockingQuality(candidate) || candidateNeedsOptimization(candidate);
}

export function candidateHasLocalBlockingQuality(candidate: Candidate) {
  const localCodes = candidateBlockingCodes(candidate).filter(
    (code) => !isSubmitOnlyBlockerText(code)
  );
  const gateHardCodes = (candidate.gate?.failed_reasons || [])
    .map((reason) => candidateText(reason).trim())
    .filter((code) => code && !isSubmitOnlyBlockerText(code));
  return Boolean(
    localCodes.length ||
    candidate.local_quality?.passed === false ||
    candidate.local_quality?.local_backtest?.pass_local === false ||
    gateHardCodes.length
  );
}

export function candidateHasSubmitOnlyBlockers(candidate: Candidate) {
  return (
    candidateBlockingCodes(candidate).some(isSubmitOnlyBlockerText) ||
    (candidate.gate?.failed_reasons || []).some((reason) =>
      isSubmitOnlyBlockerText(candidateText(reason).trim())
    )
  );
}

export function candidateNeedsOptimization(candidate: Candidate) {
  if (candidateSubmissionReady(candidate) || candidateHasLocalBlockingQuality(candidate))
    return false;
  if (
    candidate.production_decision?.action === 'optimize' ||
    candidate.decision_action === 'optimize'
  )
    return true;
  const band = candidateText(candidate.scorecard?.decision_band || candidate.decision_band);
  return Boolean(
    (band && band !== 'submit_candidate') ||
    candidateBlockingCodes(candidate).some(isSubmitOnlyBlockerText)
  );
}

export function candidateBlockingCodes(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const codes = new Set<string>();
  const primary = record(diagnosis.primary_reason);
  const primaryCode = candidateText(primary.code);
  if (primaryCode) codes.add(primaryCode);
  for (const reason of diagnosis.blocking_reasons || []) {
    const code = candidateText(reason).trim();
    if (code) codes.add(code);
  }
  for (const row of diagnosis.reasons || []) {
    if (row?.severity && row.severity !== 'blocking') continue;
    const code = candidateText(row?.code).trim();
    if (code) codes.add(code);
  }
  for (const reason of candidate.local_quality?.reasons || []) {
    const code = candidateText(reason).split(':', 1)[0].trim();
    if (code) codes.add(code);
  }
  return [...codes];
}

export function isSubmitOnlyBlockerText(value: string) {
  const normalized = value.trim().toLowerCase().replace(/\s+/g, '_');
  if (SUBMIT_ONLY_BLOCKER_CODES.has(normalized)) return true;
  return (
    (normalized.includes('decision_band') && normalized.includes('not_submit_candidate')) ||
    (normalized.includes('gate') && normalized.includes('not_submission_ready')) ||
    (normalized.includes('human') && normalized.includes('confirmation')) ||
    (normalized.includes('official_alpha_id') && normalized.includes('missing')) ||
    (normalized.includes('official') &&
      normalized.includes('metric') &&
      normalized.includes('missing'))
  );
}

export function candidateSubmissionReady(candidate: Candidate) {
  const status = candidateStatus(candidate);
  return Boolean(
    status === 'submission_ready' ||
    candidate.quality_diagnosis?.submission_ready === true ||
    candidate.gate?.submission_ready === true
  );
}

export function candidatePoolRankScore(candidate: Candidate) {
  const fallbackScore = (candidate as { score?: unknown }).score;
  const score = Number(candidate.scorecard?.total_score ?? fallbackScore ?? 0);
  return Number.isFinite(score) ? score : 0;
}

export function candidateRetainedPoolEligible(candidate: Candidate) {
  const status = candidateStatus(candidate);
  if (
    candidate.production_decision?.action === 'archive' ||
    candidate.decision_action === 'archive'
  )
    return false;
  if (
    status === 'submitted' ||
    status === 'submission_ready' ||
    status.includes('simulation_failed') ||
    status.includes('official_standard_rejected') ||
    status.includes('local_prefilter_rejected') ||
    status.includes('local_standard_rejected') ||
    status.includes('candidate_pool_pruned') ||
    status.includes('high_cloud_similarity') ||
    status.includes('rejected') ||
    status.includes('failed')
  ) {
    return false;
  }
  if (status.includes('blocked') && !candidateHasSubmitOnlyBlockers(candidate)) {
    return false;
  }
  return !candidateHasLocalBlockingQuality(candidate);
}

export function indexCheckResults(rows: CandidateCheckResult[]) {
  const index = new Map<string, CandidateCheckResult>();
  for (const row of rows) {
    for (const id of candidateIds(row)) index.set(id, row);
  }
  return index;
}

export function checkResultForCandidate(
  candidate: Candidate,
  checkResults: Map<string, CandidateCheckResult>
) {
  for (const id of candidateIds(candidate)) {
    const result = checkResults.get(id);
    if (result) return result;
  }
  return undefined;
}
