/** Read-only pre-submit confirmation surface.
 *
 * P0-1: When submission is blocked, renders a structured "Next Steps Guidance"
 * panel with actionable exit paths instead of a dead-end error message.
 * Each blocking reason maps to a specific action (navigate, external link, etc.).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import { useApi } from "@/hooks/useApi";
import type { Candidate, SubmitReadinessResponse } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import StatusFlowDiagram from "@/components/StatusFlowDiagram";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onNavigate?: (view: string) => void;
}

interface CheckResult {
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
}

interface ConfirmationRow {
  id: string;
  expression: string;
  status: string;
  score: string;
  reasons: string;
  checkedAt: string;
}

export default function SubmissionConfirmPanel({ notify, onNavigate }: Props) {
  const candidatesApi = useApi<{ candidates?: Candidate[]; items?: Candidate[] }>();
  const checksApi = useApi<{ items?: CheckResult[] }>();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const callCandidates = candidatesApi.call;
  const callChecks = checksApi.call;
  const callReadiness = readinessApi.call;

  const load = useCallback(async () => {
    const [candidatesResult, checksResult, readinessResult] = await Promise.all([
      callCandidates<{ candidates?: Candidate[]; items?: Candidate[] }>("/api/candidates"),
      callChecks<{ items?: CheckResult[] }>("/api/check_results"),
      callReadiness<SubmitReadinessResponse>("/api/submit_readiness"),
    ]);
    if (candidatesResult?.error) notify("error", apiErrorMessage(candidatesResult, "候选数据加载失败"));
    if (checksResult?.error) notify("error", apiErrorMessage(checksResult, "检查结果加载失败"));
    if (readinessResult?.error) notify("error", apiErrorMessage(readinessResult, "提交阻断复核加载失败"));
  }, [callCandidates, callChecks, callReadiness, notify]);

  useEffect(() => { void load(); }, [load]);

  // P2-5: 就绪后自动轮询 /api/submit_readiness，检测真实提交发生
  const prevRealSubmitRef = useRef<boolean | undefined>(undefined);
  const readiness = readinessApi.data;
  const readyToSubmit = readiness?.ready_to_submit;

  useEffect(() => {
    if (!readyToSubmit) return;
    // 记录进入就绪状态时的 real_submit_performed 初始值
    if (prevRealSubmitRef.current === undefined) {
      prevRealSubmitRef.current = readiness?.real_submit_performed ?? false;
    }
    const POLL_INTERVAL_MS = 30_000;
    let timer: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const res = await fetch("/api/submit_readiness");
        if (!res.ok) return;
        const json: unknown = await res.json();
        if (!json || typeof json !== "object") return;
        const data = json as Record<string, unknown>;
        const currentPerformed = Boolean(data.real_submit_performed);
        if (currentPerformed && prevRealSubmitRef.current === false) {
          // 检测到真实提交从未发生变为已发生
          prevRealSubmitRef.current = true;
          notify("success", "检测到真实提交已完成！正在自动刷新数据。");
          await load();
        } else {
          prevRealSubmitRef.current = currentPerformed;
        }
      } catch { console.warn("SubmissionConfirm: polling failed, will retry"); }
    };

    timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timer !== null) clearInterval(timer);
    };
  }, [readyToSubmit, readiness?.real_submit_performed, load, notify]);

  const candidates = candidatesApi.data?.candidates || candidatesApi.data?.items || [];
  const checks = checksApi.data?.items || [];
  const rows = useMemo(() => buildRows(candidates, checks), [candidates, checks]);

  // P1-6: Simulation submission drill state
  const [drillOpen, setDrillOpen] = useState(false);
  const drillSteps = useMemo(() => [
    { id: 1, label: "确认候选 ID", description: "确认要提交的 Alpha ID 无误，并与 BRAIN 平台一致" },
    { id: 2, label: "打开 BRAIN 平台", description: "在浏览器中打开 platform.worldquantbrain.com/alphas" },
    { id: 3, label: "粘贴表达式", description: "将候选表达式复制粘贴到 BRAIN 平台的 Alpha 编辑器中" },
    { id: 4, label: "设置参数", description: "配置区域、股票池、延迟、中性化等参数与本地一致" },
    { id: 5, label: "确认提交", description: "在 BRAIN 平台上点击提交按钮完成真实 Alpha 提交流程" },
  ], []);
  const [drillChecks, setDrillChecks] = useState<Set<number>>(new Set());
  const drilledAllChecked = drillChecks.size === drillSteps.length;
  const readyRows = rows.filter((row) => row.status === "READY");
  const blockedRows = rows.filter((row) => row.status !== "READY");
  const readyCount = readiness?.eligible_count ?? readyRows.length;
  const readinessCandidateCount = readiness?.job_family_candidate_count ?? readiness?.candidate_count ?? rows.length;
  const blockedCount = readiness ? Math.max(0, readinessCandidateCount - readyCount) : blockedRows.length;
  const loading = (candidatesApi.loading || checksApi.loading || readinessApi.loading)
    && !candidatesApi.data
    && !checksApi.data
    && !readinessApi.data;
      const error = candidatesApi.error || checksApi.error || readinessApi.error;

  // Flow stages for StatusFlowDiagram
  const flowStages = useMemo(() => {
      // P2-5 [C15]: deduplicate checks that are both passed AND submittable
  const checked = new Set(checks.filter((c) => c.passed || c.submittable).map(c => c.alpha_id || c.official_alpha_id || c.simulation_id || JSON.stringify(c))).size;
    const ready = readyCount;
    return [
      { label: "批量检查", count: checked, status: checked > 0 ? "complete" as const : "active" as const },
      { label: "阻断复核", count: ready, status: ready > 0 ? "complete" as const : checked > 0 ? "active" as const : "pending" as const },
      { label: "可提交", count: readiness?.ready_to_submit ? ready : 0, status: readiness?.ready_to_submit ? "complete" as const : blockedCount > 0 ? "blocked" as const : "pending" as const },
    ];
  }, [checks, readyCount, blockedCount, readiness?.ready_to_submit]);

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="提交前阻断复核"
        progress={{ phase: "submission_confirm_load", status_message: "正在加载提交前检查记录。" }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-text-primary">提交前阻断复核</h2>
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          复核候选 {readyCount} · 阻断 {blockedCount}
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-[oklch(0.48_0.08_22/0.30)] bg-[oklch(0.48_0.06_22/0.08)] p-4" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-negative">提交前阻断复核数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <StatusFlowDiagram stages={flowStages} />

      <ReadinessSummary readiness={readiness} onNavigate={onNavigate} />

      <ConfirmationTable
        title="预检查通过"
        empty="暂无通过预提交检查的 Alpha"
        rows={readyRows}
      />

      <ConfirmationTable
        title="阻断与待处理"
        empty="暂无阻断记录"
        rows={blockedRows}
      />

      {/* P1-6: 模拟提交演练 Modal */}
      {drillOpen && <DrillModal steps={drillSteps} checks={drillChecks} onToggle={(id) => {
        setDrillChecks((prev) => {
          const next = new Set(prev);
          if (next.has(id)) { next.delete(id); } else { next.add(id); }
          return next;
        });
      }} allChecked={drilledAllChecked} onClose={() => setDrillOpen(false)} />
    </div>
  );
}

/**
 * P0-1: Maps a blocking reason code to a suggested action and optional navigation target.
 * Every blocker now has an actionable path so the user is never stuck in a dead end.
 */
interface BlockerAction {
  label: string;
  description: string;
  view?: string;
  url?: string;
  action_type: "navigate" | "external_link" | "info";
}

const BLOCKER_ACTION_MAP: Record<string, BlockerAction> = {
  missing_official_alpha_id: {
    label: "运行官方验证",
    description: "前往候选管理，对该候选运行官方验证以获取官方 Alpha ID",
    view: "candidates",
    action_type: "navigate",
  },
  missing_official_metrics: {
    label: "运行官方仿真",
    description: "前往候选管理，对该候选运行官方仿真获取完整指标",
    view: "candidates",
    action_type: "navigate",
  },
  missing_official_metric_fields: {
    label: "补充官方指标",
    description: "前往候选管理，为该候选补充缺失的官方指标字段",
    view: "candidates",
    action_type: "navigate",
  },
  official_pass_fail_not_pass: {
    label: "优化候选",
    description: "该候选的官方检查为 NOT PASS，需要继续优化",
    view: "candidates",
    action_type: "navigate",
  },
  decision_band_not_submit_candidate: {
    label: "继续评分与筛选",
    description: "当前候选尚未进入提交候选带，需要继续评分和筛选",
    view: "scoring",
    action_type: "navigate",
  },
  missing_quality_diagnosis: {
    label: "运行质量检查",
    description: "运行质量诊断以获取完整的阻断原因分析",
    view: "quality_check",
    action_type: "navigate",
  },
  high_cloud_similarity: {
    label: "多样化表达式",
    description: "云端相似度过高，需要生成与众不同的表达式",
    view: "candidates",
    action_type: "navigate",
  },
  missing_scientific_audit: {
    label: "补齐科学审计",
    description: "前往候选管理补齐科学审计证据",
    view: "candidates",
    action_type: "navigate",
  },
  no_submit_ready_candidate: {
    label: "继续候选生成与验证",
    description: "暂无提交就绪候选，需要继续生成、验证、仿真流程",
    view: "candidates",
    action_type: "navigate",
  },
  not_submission_ready: {
    label: "完成提交前检查",
    description: "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查",
    view: "quality_check",
    action_type: "navigate",
  },
  production_decision_blocked: {
    label: "复核生产决策",
    description: "生产决策仍阻断，需要复核并处理阻断原因",
    view: "candidates",
    action_type: "navigate",
  },
  local_quality_failed: {
    label: "修复本地质量问题",
    description: "本地质量检查未通过，需要修复后重新评估",
    view: "candidates",
    action_type: "navigate",
  },
  local_backtest_failed: {
    label: "修复本地回测",
    description: "本地回测未通过，检查表达式和数据集后重试",
    view: "candidates",
    action_type: "navigate",
  },
  missing_cloud_similarity: {
    label: "同步云端数据",
    description: "缺少云端相似度证据，请先同步云端 Alpha 数据",
    view: "official_operations",
    action_type: "navigate",
  },
  lifecycle_history_blocked: {
    label: "处理归档候选",
    description: "存在历史归档风险，需要先归档或清理",
    view: "lifecycle",
    action_type: "navigate",
  },
  lifecycle_history_failed: {
    label: "返工失败候选",
    description: "存在历史返工风险，需要先处理失败记录",
    view: "lifecycle",
    action_type: "navigate",
  },
  official_context_proof_failed: {
    label: "刷新官方上下文",
    description: "官方上下文证明未通过，前往官方同步页面刷新",
    view: "official_operations",
    action_type: "navigate",
  },
  score_below_official_simulation_threshold: {
    label: "优化候选分数",
    description: "未达到官方仿真分数门槛，需要继续优化",
    view: "candidates",
    action_type: "navigate",
  },
};

const BRAIN_PLATFORM_URL = "https://platform.worldquantbrain.com/alphas";

function blockerActionForReason(reason: string): BlockerAction {
  return BLOCKER_ACTION_MAP[reason] || {
    label: "查看阻断详情",
    description: readinessReasonLabel(reason),
    view: "quality_check",
    action_type: "navigate",
  };
}

function blockerActionForProductionGap(
  finding: { code?: unknown; message?: unknown },
): BlockerAction {
  const code = String(finding.code || finding.message || "").trim();
  if (code && BLOCKER_ACTION_MAP[code]) {
    return BLOCKER_ACTION_MAP[code];
  }
  return {
    label: "修复生产缺口",
    description: readinessProductionGapLabel(finding),
    view: "candidates",
    action_type: "navigate",
  };
}

function ReadinessSummary({
  readiness,
  onNavigate,
}: {
  readiness: SubmitReadinessResponse | null;
  onNavigate?: (view: string) => void;
}) {
  const summary = readiness?.summary_counts || {};
  const allBlockers = readiness?.top_blocking_reasons || [];
  const allFamilyBlockers = readiness?.top_family_blocking_reasons || [];
  const allProductionGaps = readiness?.production_gaps || [];
  const allNextSteps = readiness?.required_next_steps || [];
  const best = readiness?.best_candidate || {};
  const hasBlockers = allBlockers.length > 0 || allFamilyBlockers.length > 0 || allProductionGaps.length > 0;
  const hasBestCandidate = Boolean(best.alpha_id);
  const ready = readiness?.ready_to_submit;

  // P0-1: Decide which guidance panel to show
  const showManualSubmitGuidance = ready && !hasBlockers;
  const showBlockedGuidance = !ready;

  return (
    <>
      {/* ── Quick metrics bar ─────────────────────────────────────────── */}
      <section className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] px-3 py-3">
        <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <ReadinessMetric label="阻断复核" value={ready ? "通过" : "未通过"} tone={ready ? "text-positive" : "text-warning"} />
          <ReadinessMetric label="复核候选" value={formatCount(readiness?.eligible_count)} />
          <ReadinessMetric label="官方仿真" value={formatCount(summary.officially_simulated)} />
          <ReadinessMetric label="官方接口" value={readiness?.official_api_called ? "已调用" : "未调用"} />
          <ReadinessMetric label="最佳 Alpha" value={best.alpha_id || "-"} mono />
          <ReadinessMetric label="真实提交" value={readiness?.real_submit_performed ? "真实提交已发生" : "未执行真实提交"} tone={readiness?.real_submit_performed ? "text-negative" : "text-positive"} />
        </dl>
        <div className="mt-3 space-y-1 text-xs text-text-tertiary">
          <p className="break-words">
            提交就绪声明: {readiness?.submit_ready_claim_allowed ? "可按验证结果继续人工复核" : "不可声明提交就绪"}
          </p>
          <p className="break-words">
            判定来源: {readiness?.authoritative_stop_rule || readiness?.validation_command || readiness?.source || "check_live_submit_readiness.py"}
          </p>
        </div>
      </section>

      {/* ── P0-1: All gates passed → guide to manual BRAIN platform submit ── */}
      {showManualSubmitGuidance && (
        <section className="rounded-md border border-[oklch(0.55_0.12_85/0.35)] bg-[oklch(0.55_0.10_85/0.08)] p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 text-lg" aria-hidden="true">✅</span>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-text-primary">
                所有门禁均已通过 — 需通过 BRAIN 平台手动提交
              </h3>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                您的候选已通过全部质量门禁。Web 控制台仅负责就绪复核，不执行真实提交。
                请前往 BRAIN 平台控制台完成最终提交。
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <a
                  href={BRAIN_PLATFORM_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary text-sm inline-flex items-center gap-1.5"
                >
                  前往 BRAIN 平台控制台
                  <span aria-hidden="true">↗</span>
                </a>
                {/* P1-6: 模拟提交演练 */}
                <button
                  type="button"
                  className="btn btn-secondary text-sm"
                  onClick={() => { setDrillOpen(true); setDrillChecks(new Set()); }}
                >
                  模拟提交演练
                </button>
                {onNavigate && (
                  <button
                    type="button"
                    className="btn btn-secondary text-sm"
                    onClick={() => onNavigate("candidates")}
                  >
                    返回候选管理
                  </button>
                )}
              </div>
              {hasBestCandidate && (
                <div className="mt-3 rounded bg-[oklch(0.10_0.005_45/0.50)] px-3 py-2 text-xs text-text-tertiary">
                  <span className="font-mono-value text-accent">{best.alpha_id || "-"}</span>
                  {" · "}
                  生命周期 {best.lifecycle_status || "-"}
                  {best.score != null && ` · 得分 ${Number(best.score).toFixed(2)}`}
                  {best.decision_band && ` · ${best.decision_band}`}
                </div>
              )}
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-text-tertiary hover:text-text-secondary">
                  下一步参考步骤
                </summary>
                <ol className="mt-2 ml-4 list-decimal space-y-1 text-xs text-text-tertiary">
                  <li>打开 BRAIN 平台控制台 (platform.worldquantbrain.com/alphas)</li>
                  <li>找到对应的 Alpha 并完成人工提交审批</li>
                  <li>提交完成后，可回到本页面同步云端数据确认状态</li>
                </ol>
              </details>
            </div>
          </div>
        </section>
      )}

      {/* ── P0-1: Blocked → structured guidance with actionable items ──── */}
      {showBlockedGuidance && (
        <section className="rounded-md border border-[oklch(0.48_0.10_32/0.30)] bg-[oklch(0.48_0.08_32/0.06)] p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 text-lg" aria-hidden="true">🚧</span>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-text-primary">
                提交前仍有 {allBlockers.length + allFamilyBlockers.length + allProductionGaps.length} 项阻断需要处理
              </h3>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                以下列出每条阻断原因及其建议操作。点击操作按钮可跳转到对应页面。
              </p>
            </div>
          </div>

          {/* Blocking reasons grid */}
          <div className="mt-4 space-y-3">
            {allBlockers.length > 0 && (
              <BlockerGuidanceList
                title="当前阻断原因"
                items={allBlockers.map((row) => ({
                  reason: readinessReasonLabel(row.reason),
                  count: row.count,
                  action: blockerActionForReason(row.reason),
                }))}
                onNavigate={onNavigate}
              />
            )}

            {allFamilyBlockers.length > 0 && (
              <BlockerGuidanceList
                title="候选族阻断原因"
                items={allFamilyBlockers.map((row) => ({
                  reason: readinessReasonLabel(row.reason),
                  count: row.count,
                  action: blockerActionForReason(row.reason),
                }))}
                onNavigate={onNavigate}
              />
            )}

            {allProductionGaps.length > 0 && (
              <BlockerGuidanceList
                title="生产缺口"
                items={allProductionGaps.map((gap) => ({
                  reason: readinessProductionGapLabel(gap),
                  count: undefined,
                  action: blockerActionForProductionGap(gap),
                }))}
                onNavigate={onNavigate}
              />
            )}
          </div>

          {/* Next steps summary */}
          {allNextSteps.length > 0 && (
            <div className="mt-4 border-t border-border-subtle pt-3">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wide">
                建议下一步操作
              </p>
              <ul className="mt-2 space-y-1">
                {allNextSteps.map((step, index) => (
                  <li key={index} className="text-xs text-text-secondary flex items-start gap-2">
                    <span className="mt-0.5 shrink-0 text-accent">→</span>
                    <span>{readinessNextActionLabel(step)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* BRAIN platform fallback */}
          <div className="mt-4 border-t border-border-subtle pt-3">
            <p className="text-xs text-text-tertiary">
              如果所有阻断原因均已处理但仍无法提交，请直接前往{" "}
              <a
                href={BRAIN_PLATFORM_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent underline hover:text-accent/80"
              >
                BRAIN 平台控制台
              </a>
              {" "}手动提交。
            </p>
          </div>
        </section>
      )}

      {/* ── Best candidate detail (always shown when available) ────────── */}
      {hasBestCandidate && !showManualSubmitGuidance && (
        <section className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] px-3 py-3 text-xs text-text-tertiary">
          <p className="font-semibold text-text-secondary">最佳候选</p>
          <div className="mt-1 space-y-0.5">
            <p>Alpha: <span className="font-mono-value text-accent">{best.alpha_id || "-"}</span></p>
            <p>决策: {readinessReasonLabel(best.decision_band || "")}</p>
            <p>分数: {best.score != null ? Number(best.score).toFixed(2) : "-"}</p>
            <p>相似度: {best.max_similarity != null ? Number(best.max_similarity).toFixed(4) : "-"}</p>
            {best.blocking_reasons && best.blocking_reasons.length > 0 && (
              <p>阻断: {best.blocking_reasons.map((r) => readinessReasonLabel(r)).join(" · ")}</p>
            )}
          </div>
        </section>
      )}
    </>
  );
}

/** P0-1: Renders a list of blockers, each with a count (optional) and an action button. */
function BlockerGuidanceList({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: { reason: string; count?: number; action: BlockerAction }[];
  onNavigate?: (view: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wide mb-2">
        {title}（{items.length}）
      </p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li
            key={`${title}_${index}`}
            className="flex flex-wrap items-start justify-between gap-2 rounded bg-[oklch(0.10_0.005_45/0.50)] px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <span className="text-xs text-text-secondary">{item.reason}</span>
              {item.count !== undefined && (
                <span className="ml-1.5 text-xs text-text-tertiary">({item.count})</span>
              )}
              <p className="mt-0.5 text-xs text-text-tertiary">{item.action.description}</p>
            </div>
            <BlockerActionButton action={item.action} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** P0-1: Renders the appropriate action button based on the action type. */
function BlockerActionButton({
  action,
  onNavigate,
}: {
  action: BlockerAction;
  onNavigate?: (view: string) => void;
}) {
  if (action.action_type === "external_link" && action.url) {
    return (
      <a
        href={action.url}
        target="_blank"
        rel="noopener noreferrer"
        className="btn btn-secondary text-xs shrink-0 inline-flex items-center gap-1"
      >
        {action.label}
        <span aria-hidden="true">↗</span>
      </a>
    );
  }
  if (action.action_type === "navigate" && onNavigate && action.view) {
    return (
      <button
        type="button"
        className="btn btn-secondary text-xs shrink-0"
        onClick={() => onNavigate(action.view!)}
      >
        {action.label}
      </button>
    );
  }
  return (
    <span className="text-xs text-text-tertiary shrink-0">{action.label}</span>
  );
}

function ReadinessMetric({ label, value, tone = "text-text-primary", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className={`mt-0.5 truncate font-medium ${tone} ${mono ? "font-mono-value" : ""}`} title={value}>{value}</dd>
    </div>
  );
}

function countLabel(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

function ConfirmationTable({ title, empty, rows }: { title: string; empty: string; rows: ConfirmationRow[] }) {
  return (
    <section className="min-w-0 space-y-3">
      <h3 className="text-sm font-semibold text-text-secondary">{title}</h3>
      <div className="space-y-3 md:hidden" aria-label={`${title} 移动端卡片`}>
        {rows.length === 0 ? (
          <div className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-4 text-center text-sm text-text-tertiary">{empty}</div>
        ) : (
          rows.map((row) => (
            <article key={`${title}_mobile_${row.id}`} className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-4 text-sm">
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-all font-mono-value text-xs text-accent">{row.id}</p>
                  <p className="mt-1 break-words font-mono-value text-xs text-text-secondary">{row.expression || "-"}</p>
                </div>
                <span className={`badge shrink-0 text-xs ${row.status === "READY" ? "badge-positive" : "badge-warning"}`}>
                  {readinessStatusLabel(row.status)}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <dt className="text-text-tertiary">得分</dt>
                  <dd className="mt-1 font-mono-value text-text-primary">{row.score}</dd>
                </div>
                <div>
                  <dt className="text-text-tertiary">检查时间</dt>
                  <dd className="mt-1 break-words font-mono-value text-text-primary">{row.checkedAt || "-"}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-text-tertiary">原因</dt>
                  <dd className="mt-1 break-words text-text-secondary">{row.reasons || "-"}</dd>
                </div>
              </dl>
            </article>
          ))
        )}
      </div>
      <div className="hidden min-w-0 overflow-hidden md:block rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)]">
        <div className="max-w-full overflow-auto">
          <table className="min-w-[760px] w-full text-sm" aria-label={title}>
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs uppercase tracking-wider text-text-tertiary">
                <th scope="col" className="p-3">Alpha ID</th>
                <th scope="col" className="p-3">表达式</th>
                <th scope="col" className="p-3">状态</th>
                <th scope="col" className="p-3">得分</th>
                <th scope="col" className="p-3">原因</th>
                <th scope="col" className="p-3">检查时间</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-text-tertiary">{empty}</td></tr>
              ) : (
                rows.map((row) => (
                  <tr key={`${title}_${row.id}`} className="border-b border-border-subtle">
                    <td className="p-3 font-mono-value text-xs text-accent">{row.id}</td>
                    <td className="max-w-xs truncate p-3 font-mono-value text-xs" title={row.expression}>{row.expression || "-"}</td>
                    <td className="p-3"><span className={`badge text-xs ${row.status === "READY" ? "badge-positive" : "badge-warning"}`}>{readinessStatusLabel(row.status)}</span></td>
                    <td className="p-3 font-mono-value text-xs">{row.score}</td>
                    <td className="max-w-sm break-words p-3 text-xs text-text-secondary" title={row.reasons}>{row.reasons || "-"}</td>
                    <td className="p-3 font-mono-value text-xs text-text-tertiary">{row.checkedAt || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function readinessStatusLabel(status: string) {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "READY") return "可复核";
  if (normalized === "BLOCKED") return "阻断";
  if (normalized === "FAILED") return "失败";
  if (normalized === "PENDING") return "待检查";
  return normalized ? "状态待确认" : "-";
}

function buildRows(candidates: Candidate[], checks: CheckResult[]) {
  const candidatesById = new Map<string, Candidate>();
  for (const candidate of candidates) {
    for (const id of candidateIds(candidate)) {
      candidatesById.set(id, candidate);
    }
  }
  return checks.map((check, index): ConfirmationRow => {
    const id = candidateIds(check)[0] || `check_${index + 1}`;
    const candidate = candidatesById.get(id);
    const ready = check.is_stale !== true && Boolean(check.submittable ?? check.passed);
    return {
      id,
      expression: candidate?.expression || "",
      status: ready ? "READY" : String(check.status || "BLOCKED").toUpperCase(),
      score: check.score == null ? "-" : Number(check.score).toFixed(2),
      reasons: (check.failed_reasons || []).map((reason) => readinessReasonLabel(reason)).join("; "),
      checkedAt: String(check.checked_at || ""),
    };
  });
}

function candidateIds(row: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CheckResult) {
  return [row.alpha_id, row.official_alpha_id, row.simulation_id]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return String(Math.max(0, Math.trunc(number)));
}

/** P1-6: 模拟提交演练 — 5-step checklist modal. Pure frontend, no API calls. */
interface DrillStep {
  id: number;
  label: string;
  description: string;
}

function DrillModal({
  steps,
  checks,
  onToggle,
  allChecked,
  onClose,
}: {
  steps: DrillStep[];
  checks: Set<number>;
  onToggle: (id: number) => void;
  allChecked: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className="drill-modal-overlay"
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "oklch(0 0 0 / 0.55)", backdropFilter: "blur(3px)",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="模拟提交演练"
    >
      <div
        className="drill-modal-content"
        style={{
          background: "oklch(0.115 0.007 45)", borderRadius: 8,
          border: "0.5px solid oklch(0.22 0.007 45)",
          maxWidth: 480, width: "calc(100% - 32px)", maxHeight: "90vh",
          overflow: "auto", padding: "24px 20px 20px",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <h3 className="text-base font-semibold text-text-primary">模拟提交演练</h3>
            <p className="text-xs text-text-tertiary mt-1">
              逐项确认提交步骤，帮助你在 BRAIN 平台上顺利完成真实提交。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="关闭"
            style={{ padding: "2px 6px", fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        {/* Progress bar */}
        <div className="progress-bar" style={{ marginBottom: 16 }} role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={checks.size}>
          <div className="progress-bar-fill positive" style={{ width: `${(checks.size / steps.length) * 100}%` }} />
        </div>

        {/* Checklist */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((step) => {
            const checked = checks.has(step.id);
            return (
              <label
                key={step.id}
                style={{
                  display: "flex", alignItems: "flex-start", gap: 12,
                  padding: "10px 12px", borderRadius: 6,
                  cursor: "pointer",
                  background: checked ? "oklch(0.55 0.08 85 / 0.08)" : "oklch(0.10 0.005 45 / 0.50)",
                  border: `0.5px solid ${checked ? "oklch(0.55 0.10 85 / 0.30)" : "oklch(0.22 0.007 45)"}`,
                  transition: "all 0.15s",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(step.id)}
                  style={{ marginTop: 2, flexShrink: 0, accentColor: "oklch(0.65 0.14 80)" }}
                />
                <div>
                  <span
                    className="text-sm font-medium"
                    style={{
                      color: checked ? "oklch(0.75 0.10 85)" : "oklch(0.62 0.01 45)",
                      textDecoration: checked ? "line-through" : "none",
                    }}
                  >
                    {step.id}. {step.label}
                  </span>
                  <p className="text-xs text-text-tertiary mt-0.5">{step.description}</p>
                </div>
              </label>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
            {allChecked ? "完成演练" : "关闭"}
          </button>
          {!allChecked && (
            <span className="text-xs text-text-tertiary self-center">
              已完成 {checks.size}/{steps.length} 步
            </span>
          )}
          {allChecked && (
            <span className="text-xs text-positive self-center" role="status">
              ✅ 全部步骤已确认
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function formatNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2);
}
