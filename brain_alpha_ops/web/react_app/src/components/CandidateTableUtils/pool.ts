import type { Candidate } from '@/types';
import type {
  CandidateCheckResult,
  CandidatePoolSnapshot,
  CandidateWorkflowPlan,
  CandidateQueueView,
} from './types';
import { candidateIdentity, candidateIds, candidateText, mostCommon } from './base';
import {
  candidatePoolRankScore,
  candidateRetainedPoolEligible,
  candidateSubmissionReady,
  candidateHasLocalBlockingQuality,
  candidateHasSubmitOnlyBlockers,
  candidateNeedsOptimization,
  candidateStatus,
  candidateStage,
  checkResultForCandidate,
} from './quality';
import { candidateOutputSummary } from './formatters';

export function rankPoolCandidates(candidates: Candidate[]) {
  return [...candidates].sort((a, b) => candidatePoolRankScore(b) - candidatePoolRankScore(a));
}

export function candidatePoolSnapshot(
  rows: Candidate[],
  mainPoolCandidates: Candidate[] | null,
  targetPoolSize: number,
  workflowPlan?: CandidateWorkflowPlan | null
): CandidatePoolSnapshot {
  const eligible = mainPoolCandidates
    ? rankPoolCandidates(mainPoolCandidates)
    : rankPoolCandidates(rows.filter(candidateRetainedPoolEligible));
  const retained = eligible.slice(0, targetPoolSize);
  const producerDeficit = Number(workflowPlan?.producer?.deficit);
  return {
    eligibleCount: eligible.length,
    retainedCount: retained.length,
    deficit: Number.isFinite(producerDeficit)
      ? Math.max(0, Math.trunc(producerDeficit))
      : Math.max(0, targetPoolSize - eligible.length),
    retainedCandidates: retained,
    workflowPlan,
  };
}

export function simulationCandidateIds(candidates: Candidate[], limit: number) {
  const ids: string[] = [];
  for (const candidate of candidates) {
    const id = candidateIdentity(candidate);
    if (id && !ids.includes(id)) ids.push(id);
    if (ids.length >= limit) break;
  }
  return ids;
}

export function workflowCandidatesForQueue(
  rows: Candidate[],
  fallbackCandidates: Candidate[],
  queueIds?: string[]
) {
  const ids = (queueIds || []).map((id) => candidateText(id).trim()).filter(Boolean);
  if (!ids.length) return fallbackCandidates;
  const byId = new Map<string, Candidate>();
  for (const candidate of [...rows, ...fallbackCandidates]) {
    for (const id of candidateIds(candidate)) {
      if (!byId.has(id)) byId.set(id, candidate);
    }
  }
  const queued = ids
    .map((id) => byId.get(id))
    .filter((candidate): candidate is Candidate => Boolean(candidate));
  return queued.length ? queued : fallbackCandidates;
}

export function candidateManagementDisplayCandidates(
  rows: Candidate[],
  fallbackCandidates: Candidate[]
) {
  return rows.length ? rows : fallbackCandidates;
}

export function optimizationCandidatesForPool(
  rows: Candidate[],
  retainedCandidates: Candidate[],
  _queueIds?: string[]
) {
  const retained = new Set(retainedCandidates.map((c) => candidateIdentity(c)));
  const selected = rows
    .filter((c) => !retained.has(candidateIdentity(c)))
    .filter(candidateRetainedPoolEligible);
  const selectedIds = new Set(selected.map((c) => candidateIdentity(c)));
  const extra = retainedCandidates.filter((c) => !selectedIds.has(candidateIdentity(c)));
  return [...selected, ...extra];
}

export function uniqueCandidatesByIdentity(candidates: Candidate[]) {
  const seen = new Set<string>();
  return candidates.filter((c) => {
    const id = candidateIdentity(c);
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

export function summarizeCandidateQuality(
  candidates: Candidate[],
  retained: number,
  targetPoolSize: number
) {
  const ready = candidates.filter(candidateSubmissionReady).length;
  const promotable = candidates.filter(candidateRetainedPoolEligible).length;
  const rework = candidates.filter(candidateNeedsOptimization).length;
  const blocked = candidates.filter(candidateHasLocalBlockingQuality).length;
  const outputModes = candidates
    .map(candidateOutputSummary)
    .filter((value) => value && value !== '-');
  return {
    ready,
    retained: `${retained}/${targetPoolSize}`,
    promotable,
    rework,
    blocked,
    outputMode: mostCommon(outputModes) || '-',
  };
}

export function candidateMatchesQueueView(
  candidate: Candidate,
  viewMode: CandidateQueueView,
  checkResults: Map<string, CandidateCheckResult>
) {
  if (viewMode === 'candidates') return true;
  const status = candidateStatus(candidate);
  const stage = candidateStage(candidate);
  const result = checkResultForCandidate(candidate, checkResults);
  if (viewMode === 'pending_backtest') return status === 'pending_backtest';
  if (viewMode === 'running_backtest') return status === 'running_backtest' || status === 'running';
  if (viewMode === 'backtest_rework')
    return status === 'backtest_rework' || status === 'failed_backtest' || status === 'rejected';
  if (viewMode === 'passed') return candidateSubmissionReady(candidate);
  if (viewMode === 'submittable')
    return (
      status !== 'submitted' &&
      result?.is_stale !== true &&
      Boolean(
        result?.submittable ?? result?.passed ?? candidate.quality_diagnosis?.submission_ready
      )
    );
  if (viewMode === 'submitted') return status === 'submitted' || stage === 'submitted';
  return (
    status === 'failed' ||
    status === 'rejected' ||
    status.includes('high_cloud_similarity') ||
    (status.includes('blocked') && !candidateHasSubmitOnlyBlockers(candidate)) ||
    candidateHasLocalBlockingQuality(candidate)
  );
}
