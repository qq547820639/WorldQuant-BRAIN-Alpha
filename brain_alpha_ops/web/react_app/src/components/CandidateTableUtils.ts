/**
 * Utility functions for CandidateTable component.
 * Extracted from CandidateTable.tsx for better code organization.
 */

import type { AlphaLifecycleTrace, Candidate, SSEEvent } from "@/types";
import { isRecord } from "@/types";
import { RAW_UNSAFE_DISPLAY_TEXT_PATTERN } from "@/helpers/errorExperience";

const MIN_TARGET_POOL_SIZE = 1;
const MAX_TARGET_POOL_SIZE = 100;

export const DEFAULT_TARGET_POOL_SIZE = 10;
export const MAX_FILTER_LENGTH = 200;
export type CandidateQueueView =
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed";

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
  producer?: { deficit?: number };
};

export const SUBMIT_ONLY_BLOCKER_CODES = new Set([
  "decision_band_not_submit_candidate",
  "gate_not_submission_ready",
  "human_confirmation_required",
  "manual_confirmation_required",
  "missing_official_alpha_id",
  "missing_official_metrics",
  "missing_official_metric_fields",
  "needs_human_confirmation",
  "official_pass_fail_not_pass",
  "expression_too_nested",
]);

export function candidateIdentity(candidate: Candidate) {
  return candidateIds(candidate)[0] || "";
}

export function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CandidateCheckResult) {
  return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

export function candidateStatus(candidate: Candidate) {
  const normalized = candidateText(candidate.lifecycle_status || candidate.quality_diagnosis?.status || candidate.gate?.status);
  return normalized.toLowerCase();
}

export function candidateStage(candidate: Candidate) {
  const submission = record(candidate.submission);
  return candidateText(submission.stage || submission.status || candidate.lifecycle_status).toLowerCase();
}

export function candidateText(value: unknown) {
  return String(value || "");
}

export function safeCandidateDisplayText(value: unknown, fallback: string) {
  const text = candidateText(value).trim();
  if (!text) return fallback;
  return RAW_UNSAFE_DISPLAY_TEXT_PATTERN.test(text) ? fallback : text;
}

export function candidateCreatedAt(candidate: Candidate) {
  return new Date(candidate.created_at || candidate.updated_at || 0).getTime();
}

export function candidateQualitySearchText(candidate: Candidate) {
  return [
    candidateBlockerText(candidate),
    candidateOutputSummary(candidate),
    candidateOutputDetail(candidate),
    candidate.official_alpha_id,
    candidate.simulation_id,
    candidate.dataset_id,
  ].filter(Boolean).join(" ");
}

export function candidateQualityBadge(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (candidateSubmissionReady(candidate)) {
    return { label: "达标", tone: "badge-positive", title: "符合提交前质量复核条件" };
  }
  if (candidateHasLocalBlockingQuality(candidate)) {
    return { label: "阻断", tone: "badge-negative", title: candidateBlockerText(candidate) };
  }
  if (diagnosis.qualified) {
    return { label: "待确认", tone: "badge-warning", title: "质量达标，但仍有提交前阻断需要处理" };
  }
  if (candidateNeedsOptimization(candidate)) {
    return { label: "需优化", tone: "badge-warning", title: candidateBlockerText(candidate) };
  }
  if (candidateLocalValid(candidate) || candidateRetainedPoolEligible(candidate)) {
    return { label: "可推进", tone: "badge-warning", title: "本地候选可继续补证据或挑战主池排序" };
  }
  return { label: "未验证", tone: "badge-neutral", title: "缺少质量诊断" };
}

export function candidateBlockerText(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const primary = record(diagnosis.primary_reason);
  const primaryText = candidateText(primary.message || primary.code || primary.category);
  if (primaryText) return primaryText;
  const decisionEvidence = candidateDecisionEvidenceText(candidate);
  if (decisionEvidence) return decisionEvidence;
  if ((diagnosis.blocking_reasons || []).length) return (diagnosis.blocking_reasons || []).join("; ");
  if ((candidate.local_quality?.reasons || []).length) return candidate.local_quality?.reasons?.join("; ") || "";
  if ((candidate.gate?.failed_reasons || []).length) return candidate.gate?.failed_reasons?.join("; ") || "";
  if (candidate.local_quality?.passed === false) return "local_quality_failed";
  if (!candidate.quality_diagnosis) return "missing_quality_diagnosis";
  return "-";
}

export function candidateDecisionEvidenceText(candidate: Candidate) {
  const evidence = candidate.production_decision?.decision_evidence;
  const lifecycleRisk = evidence?.lifecycle_risk;
  if (lifecycleRisk?.reason_code) {
    const status = candidateText(lifecycleRisk.latest_status || lifecycleRisk.latest_status_category).trim();
    const action = candidateText(lifecycleRisk.action_hint) === "archive" ? "归档" : "返工优化";
    return `历史证据: ${status || lifecycleRisk.reason_code}，需先${action}`;
  }
  const auditReasons = evidence?.scientific_audit_policy_reasons || evidence?.hard_blocking_reasons || [];
  if (auditReasons.length) {
    return `科学审计阻断: ${auditReasons.join("; ")}`;
  }
  if (candidate.production_decision?.reason && candidate.production_decision.action === "archive") {
    return candidate.production_decision.reason;
  }
  return "";
}

export function candidateLocalValid(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (typeof diagnosis.local_candidate_valid === "boolean") {
    return diagnosis.local_candidate_valid;
  }
  return candidate.local_quality?.passed === true;
}

export function candidateHasBlockingQuality(candidate: Candidate) {
  return candidateHasLocalBlockingQuality(candidate) || candidateNeedsOptimization(candidate);
}

export function candidateHasLocalBlockingQuality(candidate: Candidate) {
  const localCodes = candidateBlockingCodes(candidate).filter((code) => !isSubmitOnlyBlockerText(code));
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
  return candidateBlockingCodes(candidate).some(isSubmitOnlyBlockerText) ||
    (candidate.gate?.failed_reasons || []).some((reason) => isSubmitOnlyBlockerText(candidateText(reason).trim()));
}

export function candidateNeedsOptimization(candidate: Candidate) {
  if (candidateSubmissionReady(candidate) || candidateHasLocalBlockingQuality(candidate)) return false;
  if (candidate.production_decision?.action === "optimize" || candidate.decision_action === "optimize") return true;
  const band = candidateText(candidate.scorecard?.decision_band || candidate.decision_band);
  return Boolean(
    (band && band !== "submit_candidate") ||
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
    if (row?.severity && row.severity !== "blocking") continue;
    const code = candidateText(row?.code).trim();
    if (code) codes.add(code);
  }
  for (const reason of candidate.local_quality?.reasons || []) {
    const code = candidateText(reason).split(":", 1)[0].trim();
    if (code) codes.add(code);
  }
  return [...codes];
}

export function isSubmitOnlyBlockerText(value: string) {
  const normalized = value.trim().toLowerCase().replace(/\s+/g, "_");
  if (SUBMIT_ONLY_BLOCKER_CODES.has(normalized)) return true;
  return (
    normalized.includes("decision_band") && normalized.includes("not_submit_candidate")
  ) || (
    normalized.includes("gate") && normalized.includes("not_submission_ready")
  ) || (
    normalized.includes("human") && normalized.includes("confirmation")
  ) || (
    normalized.includes("official_alpha_id") && normalized.includes("missing")
  ) || (
    normalized.includes("official") && normalized.includes("metric") && normalized.includes("missing")
  );
}

export function candidateOutputSummary(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  if (config.local_only === true) return "本地输出";
  if (config.official_api_called === true) return "官方证据";
  if (config.allow_submit === false) return "禁止提交";
  return config.alpha_type || candidate.decision_band || "-";
}

export function candidateOutputDetail(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  const settings = record(config.settings);
  const dataset = config.dataset_id || candidate.dataset_id || settings.dataset;
  const alphaType = config.alpha_type || settings.type;
  const official = config.official_api_called === true ? "official_called" : "official_not_called";
  return [dataset ? `dataset:${dataset}` : "", alphaType ? `type:${alphaType}` : "", official].filter(Boolean).join(" · ");
}

export function officialEvidenceText(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  const result = checkResultForCandidate(candidate, checkResults);
  if (result) {
    const status = result.status || (result.submittable ? "submittable" : result.passed ? "passed" : "blocked");
    const stale = result.is_stale ? " · stale" : "";
    return `${candidateText(result.official_alpha_id || candidate.official_alpha_id || "official:-")} · ${status}${stale}`;
  }
  return candidateText(candidate.official_alpha_id || "official:-");
}

export function summarizeCandidateQuality(candidates: Candidate[], retained: number, targetPoolSize: number) {
  const ready = candidates.filter(candidateSubmissionReady).length;
  const promotable = candidates.filter(candidateRetainedPoolEligible).length;
  const rework = candidates.filter(candidateNeedsOptimization).length;
  const blocked = candidates.filter(candidateHasLocalBlockingQuality).length;
  const outputModes = candidates.map(candidateOutputSummary).filter((value) => value && value !== "-");
  return {
    ready,
    retained: `${retained}/${targetPoolSize}`,
    promotable,
    rework,
    blocked,
    outputMode: mostCommon(outputModes) || "-",
  };
}

export function candidateSubmissionReady(candidate: Candidate) {
  const status = candidateStatus(candidate);
  return Boolean(
    status === "submission_ready" ||
    candidate.quality_diagnosis?.submission_ready === true ||
    candidate.gate?.submission_ready === true
  );
}

export function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("submitted") || normalized.includes("completed") || normalized.includes("candidate_pool_retained")) return "badge-positive";
  if (normalized.includes("failed") || normalized.includes("blocked") || normalized.includes("rejected")) return "badge-negative";
  if (normalized.includes("validat") || normalized.includes("simulat") || normalized.includes("running")) return "badge-warning";
  return "badge-neutral";
}

export function mostCommon(values: unknown[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    const text = candidateText(value);
    if (!text) continue;
    counts.set(text, (counts.get(text) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

export function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function rankPoolCandidates(candidates: Candidate[]) {
  return [...candidates].sort((a, b) => candidatePoolRankScore(b) - candidatePoolRankScore(a));
}

export function candidatePoolSnapshot(
  rows: Candidate[],
  mainPoolCandidates: Candidate[] | null,
  targetPoolSize: number,
  workflowPlan?: CandidateWorkflowPlan | null,
): CandidatePoolSnapshot {
  const eligible = mainPoolCandidates
    ? rankPoolCandidates(mainPoolCandidates)
    : rankPoolCandidates(rows.filter(candidateRetainedPoolEligible));
  const retained = eligible.slice(0, targetPoolSize);
  const producerDeficit = Number(workflowPlan?.producer?.deficit);
  return {
    eligibleCount: eligible.length,
    retainedCount: retained.length,
    deficit: Number.isFinite(producerDeficit) ? Math.max(0, Math.trunc(producerDeficit)) : Math.max(0, targetPoolSize - eligible.length),
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
  queueIds?: string[],
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

export function candidateManagementDisplayCandidates(rows: Candidate[], fallbackCandidates: Candidate[]) {
  return rows.length ? rows : fallbackCandidates;
}

export function optimizationCandidatesForPool(rows: Candidate[], retainedCandidates: Candidate[], queueIds?: string[]) {
  const retained = new Set(retainedCandidates.map((c) => candidateIdentity(c)));
  const selected = rows
    .filter((c) => !retained.has(candidateIdentity(c)))
    .filter(candidateRetainedPoolEligible);
  const queued = queueIds || [];
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

export function candidatePoolRankScore(candidate: Candidate) {
  const fallbackScore = (candidate as { score?: unknown }).score;
  const score = Number(candidate.scorecard?.total_score ?? fallbackScore ?? 0);
  return Number.isFinite(score) ? score : 0;
}

export function candidateRetainedPoolEligible(candidate: Candidate) {
  const status = candidateStatus(candidate);
  if (candidate.production_decision?.action === "archive" || candidate.decision_action === "archive") return false;
  if (
    status === "submitted" ||
    status === "submission_ready" ||
    status.includes("simulation_failed") ||
    status.includes("official_standard_rejected") ||
    status.includes("local_prefilter_rejected") ||
    status.includes("local_standard_rejected") ||
    status.includes("candidate_pool_pruned") ||
    status.includes("high_cloud_similarity") ||
    status.includes("rejected") ||
    status.includes("failed")
  ) {
    return false;
  }
  if (status.includes("blocked") && !candidateHasSubmitOnlyBlockers(candidate)) {
    return false;
  }
  return !candidateHasLocalBlockingQuality(candidate);
}

export function clampTargetPoolSize(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return MIN_TARGET_POOL_SIZE;
  return Math.min(Math.max(Math.trunc(parsed), MIN_TARGET_POOL_SIZE), MAX_TARGET_POOL_SIZE);
}

export function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

export function simulationResultSummary(event: SSEEvent): SimulationResultSummary {
  const result = record(event.result);
  const progress = record(event.progress);
  const data = record(progress.data);
  return {
    completed: numericResultField(result.completed ?? data.completed),
    failed: numericResultField(result.failed ?? data.failed),
    total: numericResultField(result.total ?? data.total),
  };
}

export function numericResultField(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.trunc(number)) : 0;
}

export function simulationCompletionMessage(result: SimulationResultSummary) {
  const total = result.total > 0 ? `，共 ${result.total} 个` : "";
  return `BRAIN模拟完成: ${result.completed} 成功, ${result.failed} 失败${total}`;
}

export function indexCheckResults(rows: CandidateCheckResult[]) {
  const index = new Map<string, CandidateCheckResult>();
  for (const row of rows) {
    for (const id of candidateIds(row)) index.set(id, row);
  }
  return index;
}

export function lifecycleTracesForCandidates(
  traces: AlphaLifecycleTrace[],
  candidates: Candidate[],
  filter: string,
) {
  const candidateIdSet = new Set<string>();
  for (const candidate of candidates) {
    candidateIds(candidate).forEach((id) => candidateIdSet.add(id));
  }
  const normalizedFilter = filter.trim().toLowerCase();
  return traces.filter((trace) => {
    const identities = lifecycleTraceIds(trace);
    const matchesCandidate = candidateIdSet.size === 0 || identities.some((id) => candidateIdSet.has(id));
    if (!matchesCandidate) return false;
    if (!normalizedFilter) return true;
    return lifecycleTraceSearchText(trace).includes(normalizedFilter);
  });
}

export function lifecycleTraceIds(trace: AlphaLifecycleTrace) {
  return [trace.alpha_id, trace.official_alpha_id, trace.simulation_id, trace.trace_key]
    .map((value) => candidateText(value).trim())
    .filter(Boolean);
}

export function lifecycleTraceSearchText(trace: AlphaLifecycleTrace) {
  return [
    ...lifecycleTraceIds(trace),
    trace.latest_stage,
    trace.latest_status,
    trace.status_category,
    trace.last_note,
    trace.next_action,
    trace.expression_digest,
    ...(trace.stages || []),
  ].map((value) => candidateText(value).toLowerCase()).join(" ");
}

export function lifecycleStatusBadgeClass(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === "blocked") return "badge-negative";
  if (category === "failed") return "badge-negative";
  if (category === "submitted") return "badge-positive";
  if (category === "passed") return "badge-positive";
  if (trace.submitted) return "badge-positive";
  if (trace.passed) return "badge-positive";
  if (trace.blocked || trace.failed) return "badge-negative";
  return "badge-neutral";
}

export function lifecycleStatusLabel(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === "blocked") return "阻断";
  if (category === "failed") return "失败";
  if (category === "submitted") return "已提交";
  if (category === "passed") return "通过";
  if (trace.submitted) return "已提交";
  if (trace.passed) return "通过";
  if (trace.blocked) return "阻断";
  if (trace.failed) return "失败";
  return category || "记录";
}

export function lifecycleNextActionLabel(action: unknown) {
  const normalized = candidateText(action);
  const labels: Record<string, string> = {
    collect_official_identity: "补官方ID",
    continue_validation: "继续验证",
    monitor_official_result: "监控结果",
    optimize_or_archive: "优化/归档",
    review_blockers: "复核阻断",
  };
  return labels[normalized] || normalized || "继续审查";
}

export function safeLifecycleNote(value: unknown) {
  const text = candidateText(value).trim();
  if (!text) return "";
  return text
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted]")
    .replace(/\b(username|account|email|password|passwd|pwd|token|auth_token|access_token|csrf_token|stream_token|session_id|cookie)\b\s*[:=]\s*[^,\s;]+/gi, "[redacted]")
    .replace(/\b(csrf-secret|session-secret|auth-secret|access-secret)\b/gi, "[redacted]")
    .replace(/\b(password|passwd|pwd|auth[_ -]?token|access[_ -]?token|csrf[_ -]?token|stream[_ -]?token|session[_ -]?id|cookie|secret)\b/gi, "[redacted]")
    .slice(0, 180);
}

export function lifecycleTraceTitle(trace: AlphaLifecycleTrace) {
  return lifecycleTraceIds(trace).join(" / ") || trace.expression_digest || "";
}

export function shortLifecycleTraceId(trace: AlphaLifecycleTrace) {
  const raw = lifecycleTraceIds(trace)[0] || trace.expression_digest || "unknown";
  return raw.length > 24 ? `${raw.slice(0, 24)}...` : raw;
}

export function checkResultForCandidate(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  for (const id of candidateIds(candidate)) {
    const result = checkResults.get(id);
    if (result) return result;
  }
  return undefined;
}

export function candidateMatchesQueueView(
  candidate: Candidate,
  viewMode: CandidateQueueView,
  checkResults: Map<string, CandidateCheckResult>,
) {
  if (viewMode === "candidates") return true;
  const status = candidateStatus(candidate);
  const stage = candidateStage(candidate);
  const result = checkResultForCandidate(candidate, checkResults);
  if (viewMode === "pending_backtest") return status === "pending_backtest";
  if (viewMode === "running_backtest") return status === "running_backtest" || status === "running";
  if (viewMode === "backtest_rework") return status === "backtest_rework" || status === "failed_backtest" || status === "rejected";
  if (viewMode === "passed") return candidateSubmissionReady(candidate);
  if (viewMode === "submittable") return status !== "submitted" && result?.is_stale !== true && Boolean(result?.submittable ?? result?.passed ?? candidate.quality_diagnosis?.submission_ready);
  if (viewMode === "submitted") return status === "submitted" || stage === "submitted";
  return (
    status === "failed" ||
    status === "rejected" ||
    status.includes("high_cloud_similarity") ||
    (status.includes("blocked") && !candidateHasSubmitOnlyBlockers(candidate)) ||
    candidateHasLocalBlockingQuality(candidate)
  );
}

export function queueViewLabel(viewMode: CandidateQueueView) {
  const labels: Record<CandidateQueueView, string> = {
    candidates: "全部候选",
    pending_backtest: "等待回测",
    running_backtest: "回测中",
    backtest_rework: "需返工",
    passed: "已达标",
    submittable: "复核预检",
    submitted: "已提交",
    failed: "失败/阻断",
  };
  return labels[viewMode];
}
