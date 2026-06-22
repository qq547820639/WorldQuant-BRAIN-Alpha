import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import type { SubmitReadinessResponse } from "@/types";

const BRAIN_PLATFORM_URL = "https://platform.worldquantbrain.com/alphas";

interface BlockerAction {
  label: string;
  description: string;
  view?: string;
  url?: string;
  action_type: "navigate" | "external_link" | "info";
}

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

function ReadinessMetric({ label, value, tone = "text-text-primary", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className={`mt-0.5 truncate font-medium ${tone} ${mono ? "font-mono-value" : ""}`} title={value}>{value}</dd>
    </div>
  );
}

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
            className="flex flex-wrap items-start justify-between gap-2 rounded bg-[var(--color-layer-header-bg)] px-3 py-2"
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

export function ReadinessSummary({
  readiness,
  onNavigate,
  onDrillOpen,
}: {
  readiness: SubmitReadinessResponse | null;
  onNavigate?: (view: string) => void;
  onDrillOpen?: () => void;
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

  const showManualSubmitGuidance = ready && !hasBlockers;
  const showBlockedGuidance = !ready;

  return (
    <>
      <section className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] px-3 py-3">
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

      {showManualSubmitGuidance && (
        <section className="rounded-md border border-[var(--color-gate-passed-border)] bg-[var(--color-gate-passed-fg)] p-4">
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
                <button
                  type="button"
                  className="btn btn-secondary text-sm"
                  onClick={() => onDrillOpen?.()}
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
                <div className="mt-3 rounded bg-[var(--color-layer-header-bg)] px-3 py-2 text-xs text-text-tertiary">
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

      {showBlockedGuidance && (
        <section className="rounded-md border border-[var(--color-blocked-section-border)] bg-[var(--color-blocked-section-bg)] p-4">
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

      {hasBestCandidate && !showManualSubmitGuidance && (
        <section className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] px-3 py-3 text-xs text-text-tertiary">
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

function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return String(Math.max(0, Math.trunc(number)));
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
