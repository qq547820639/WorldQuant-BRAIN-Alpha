import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import type { SubmitReadinessResponse } from "@/types";
import { formatCount, blockerActionForReason, blockerActionForProductionGap } from "./utils";
import { ReadinessMetric } from "./SubmissionMetrics";
import { BlockerGuidanceList } from "./BlockerAction";

const BRAIN_PLATFORM_URL = "https://platform.worldquantbrain.com/alphas";

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
                所有门禁均已通过 — 需通过 BRAIN 平台人工复核提交
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
              {" "}人工复核提交。
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
