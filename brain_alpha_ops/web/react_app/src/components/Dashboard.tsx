/** Dashboard — Progressive flow with step-based guidance v3.1 */
import { useEffect, useState, type ReactNode } from "react";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, CloudAlpha, CloudAlphaSummary, ResearchMemorySummary } from "@/types";
import KpiCard from "@/components/KpiCard";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  /** Whether the user has successfully tested BRAIN connection */
  connected: boolean;
  /** Whether local cloud Alpha and official context cache are available */
  contextFresh: boolean;
  /** Navigate to the sync/official operations page and start the first sync */
  onNavigateToSync: () => void;
  /** Open the manual sync page without auto-starting a refresh */
  onOpenSync?: () => void;
  /** Step 1: CredentialQuickStart (always rendered when not connected) */
  children?: ReactNode;
}

export default function Dashboard({ notify, connected, contextFresh, onNavigateToSync, onOpenSync, children }: Props) {
  const [snapshotExpanded, setSnapshotExpanded] = useState(false);
  const statusApi = useApi<JobStatus>();
  const cloudApi = useApi<CloudSnapshotPayload>();
  const memoryApi = useApi<ResearchMemorySummary>();

  useEffect(() => {
    statusApi.call("/api/production-validation/status");
    cloudApi.call("/api/snapshot/cloud");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
  }, [statusApi.call, cloudApi.call, memoryApi.call]);

  const status = statusApi.data;
  const cloud = cloudApi.data;
  const memory = memoryApi.data;
  const cloudSummary = cloudSnapshotSummary(cloud);
  const cloudPreviewRows = cloudSnapshotPreviewRows(cloud);

  const retryAll = () => {
    statusApi.call("/api/production-validation/status");
    cloudApi.call("/api/snapshot/cloud");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
  };

  const errors = [
    statusApi.error ? `Status: ${statusApi.error}` : "",
    cloudApi.error ? `Cloud: ${cloudApi.error}` : "",
    memoryApi.error ? `Memory: ${memoryApi.error}` : "",
  ].filter(Boolean);
  const loading = statusApi.loading || cloudApi.loading || memoryApi.loading;
  const [showGuide, setShowGuide] = useState(() => !localStorage.getItem("brain_alpha_guide_dismissed"));

  const dismissGuide = () => {
    localStorage.setItem("brain_alpha_guide_dismissed", "1");
    setShowGuide(false);
  };

  // ── Determine current step ──────────────────────────────────────────────
  const currentStep = !connected ? 1 : !contextFresh ? 2 : 3;
  const stepLabel = currentStep === 1 ? "连接 BRAIN"
    : currentStep === 2 ? "准备本地缓存"
    : "开始验证";
  const openManualSync = onOpenSync || onNavigateToSync;

  return (
    <div className="animate-fade-in">
      {/* ═══ Progressive Flow Indicator ═══ */}
      <StepProgressBar currentStep={currentStep} />

      {/* First-time guide */}
      {showGuide && (
        <div className="panel mb-4" style={{ borderColor: "oklch(0.58 0.12 245 / 0.30)", background: "oklch(0.58 0.06 245 / 0.08)" }}>
          <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <div>
              <p className="text-sm font-medium text-info mb-2">首次使用？按顺序完成以下步骤</p>
              <div className="grid gap-1 text-xs text-text-secondary" style={{ gridTemplateColumns: "auto 1fr", columnGap: 8, alignItems: "baseline" }}>
                <span style={{ color: currentStep === 1 ? "oklch(0.68 0.10 248)" : "oklch(0.48 0.04 160)", fontWeight: 500, textAlign: "right" }}>1.</span>
                <span>填写账户邮箱和密码，点击 <strong>测试连接</strong>{currentStep > 1 ? " ✓" : ""}</span>
                <span style={{ color: currentStep === 2 ? "oklch(0.68 0.10 248)" : currentStep > 2 ? "oklch(0.48 0.04 160)" : "oklch(0.38 0.006 45)", fontWeight: 500, textAlign: "right" }}>2.</span>
                <span>本地无缓存时点击 <strong>开始首次同步</strong>；已有缓存会直接使用，可稍后手动刷新{currentStep > 2 ? " ✓" : ""}</span>
                <span style={{ color: currentStep === 3 ? "oklch(0.68 0.10 248)" : "oklch(0.38 0.006 45)", fontWeight: 500, textAlign: "right" }}>3.</span>
                <span>同步完成后，在下方点击 <strong>运行非提交验证</strong> 开始生产搜索</span>
                <span style={{ color: currentStep > 3 ? "oklch(0.48 0.04 160)" : currentStep >= 3 ? "oklch(0.68 0.10 248)" : "oklch(0.38 0.006 45)", fontWeight: 500, textAlign: "right" }}>4.</span>
                <span>在侧边栏「候选发现」「评估与验证」「提交就绪」中继续后续流程</span>
              </div>
            </div>
            <button onClick={dismissGuide} className="btn btn-ghost btn-sm" aria-label="关闭引导" style={{ flexShrink: 0 }}>✕</button>
          </div>
        </div>
      )}

      {/* ═══ Page heading ═══ */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 4 }}>
        <div>
          <h1 className="text-xl font-medium text-text-primary mb-1">运行总览</h1>
          <p className="text-sm text-text-tertiary">
            当前阶段：<span className="text-accent font-medium">{stepLabel}</span>
            {" · "}上次更新: {new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </p>
        </div>
        {connected && contextFresh && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={openManualSync}>
            手动同步
          </button>
        )}
      </div>

      {/* ═══ Step 1: Credential + Connection Test ═══ */}
      {!connected && (
        <div className="mb-6">{children}</div>
      )}

      {/* ═══ Step 2: Sync Cloud CTA ═══ */}
      {connected && !contextFresh && (
        <SyncCloudCTA onNavigateToSync={onNavigateToSync} />
      )}

      {/* ═══ Step 3: Production Validation (children: JobMonitor) ═══ */}
      {connected && contextFresh && (
        <>
          {children}

          {/* Error banner */}
          {errors.length > 0 && (
            <div className="panel mb-4" style={{ borderColor: "oklch(0.48 0.08 22 / 0.30)", background: "oklch(0.48 0.06 22 / 0.08)" }} role="alert">
              <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <p className="text-sm font-medium text-negative mb-1">仪表盘数据需要关注</p>
                  {errors.map((e) => <p key={e} className="text-xs text-negative/80">{e}</p>)}
                </div>
                <button onClick={retryAll} className="btn btn-secondary btn-sm">重试</button>
              </div>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <ProgressFeedback
              state="loading"
              title="仪表盘数据"
              progress={{ phase: "dashboard_load", status_message: "正在刷新仪表盘快照。" }}
              compact
            />
          )}

          {/* KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <KpiCard
              label="候选总数"
              value={memory?.total_candidates ?? status?.progress?.candidates_generated ?? "--"}
              subtitle={memory ? `${memory.families?.length ?? 0} 个家族` : "等待刷新"}
            />
            <KpiCard
              label="云端 Alpha"
              value={cloudSummary.count ?? "--"}
              subtitle={cloud ? `${cloudSummary.submitted_count ?? 0} 已提交 · ${formatSyncAge(cloudSummary.age_seconds, cloudSummary.loaded_at)}` : "等待刷新"}
              trend={cloud && (cloudSummary.submitted_count ?? 0) > 0 ? "up" : "neutral"}
            />
            <KpiCard
              label="回测数"
              value={status?.progress?.backtests_completed ?? "--"}
              subtitle={status ? `${status.progress?.backtests_pending ?? 0} 待处理` : undefined}
            />
            <KpiCard
              label="提交数"
              value={status?.progress?.submissions ?? cloudSummary.submitted_count ?? "--"}
              trend={cloud && cloudSummary.passed_unsubmitted_count ? cloudSummary.passed_unsubmitted_count > 0 ? "up" : "neutral" : "neutral"}
            />
          </div>

          {/* Collapsible data snapshots */}
          <div className="mb-4">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setSnapshotExpanded((v) => !v)}
              aria-expanded={snapshotExpanded}
            >
              <span style={{ transform: snapshotExpanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 200ms", display: "inline-block" }}>▶</span>
              <span style={{ marginLeft: 6 }}>数据快照{snapshotExpanded ? "" : ` (${cloudSummary.count ?? "--"} 条 Alpha)`}</span>
            </button>
          </div>

          {snapshotExpanded && (<>

          {/* Cloud Alpha Summary Panel */}
          <div className="panel mb-4">
            <div className="panel-header">
              <span>云端 Alpha 缓存</span>
              {cloud && <span className="badge badge-neutral">{cloudSummary.count ?? "--"} 条</span>}
            </div>
            <div className="panel-body-padded">
              {cloudApi.loading ? (
                <ProgressFeedback state="loading" title="云端 Alpha" progress={{ phase: "cloud", status_message: "加载中..." }} compact />
              ) : cloudApi.error ? (
                <ProgressFeedback state="error" title="云端 Alpha" error={cloudApi.error} onRetry={() => cloudApi.call("/api/snapshot/cloud")} compact />
              ) : cloud ? (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
                    <div><span className="text-text-tertiary">缓存总数</span><p className="font-mono-value text-base text-text-primary">{cloudSummary.count ?? 0}</p></div>
                    <div><span className="text-text-tertiary">已提交</span><p className="font-mono-value text-base text-positive">{cloudSummary.submitted_count ?? 0}</p></div>
                    <div><span className="text-text-tertiary">已通过（未提交）</span><p className="font-mono-value text-base text-warning">{cloudSummary.passed_unsubmitted_count ?? 0}</p></div>
                    <div>
                      <span className="text-text-tertiary">缓存状态</span>
                      <p className={`text-sm ${cloudSummary.is_stale ? "font-medium text-warning" : "text-text-secondary"}`}>
                        {cloudSummary.is_stale ? "已过期" : "有效"}
                      </p>
                      {cloudSummary.is_stale && (
                        <button type="button" className="mt-1 text-xs text-accent underline" onClick={openManualSync}>
                          去手动同步
                        </button>
                      )}
                    </div>
                  </div>
                  {cloudPreviewRows.length > 0 && (
                    <div style={{ maxHeight: 200, overflowY: "auto" }}>
                      <p className="mb-2 text-xs text-text-tertiary">下方仅为页面预览；同步缓存总数以上方统计为准。</p>
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Alpha ID</th>
                            <th>状态</th>
                            <th className="is-sortable num">Sharpe</th>
                            <th className="is-sortable num">Fitness</th>
                            <th className="is-sortable num">Turnover</th>
                          </tr>
                        </thead>
                        <tbody>
                          {cloudPreviewRows.slice(0, 10).map((a, i) => (
                            <tr key={i}>
                              <td className="id">{cloudAlphaId(a)}</td>
                              <td><span className={`badge ${cloudAlphaPassFail(a) === "PASS" ? "badge-positive" : "badge-negative"}`}>{cloudAlphaPassFail(a) || "--"}</span></td>
                              <td className="num">{formatMetric(cloudAlphaMetric(a, "sharpe"))}</td>
                              <td className="num">{formatMetric(cloudAlphaMetric(a, "fitness"))}</td>
                              <td className="num">{formatMetric(cloudAlphaMetric(a, "turnover"))}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>

          {/* Research Memory Panels */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Top Families */}
            <div className="panel">
              <div className="panel-header"><span>热门家族</span></div>
              <div className="panel-body">
                {memory?.families?.slice(0, 5).map((f) => (
                  <div key={f.name} className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0">
                    <span className="text-text-secondary">{f.name}</span>
                    <span className="tabular text-text-tertiary">n={f.count} {f.success_rate?.toFixed(2)}</span>
                  </div>
                )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无数据</div>}
              </div>
            </div>

            {/* Top Fields */}
            <div className="panel">
              <div className="panel-header"><span>热门字段</span></div>
              <div className="panel-body">
                {memory?.fields?.slice(0, 5).map((f) => (
                  <div key={f.name} className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0">
                    <span className="text-text-secondary">{f.name}</span>
                    <span className="tabular text-text-tertiary">n={f.count} {f.success_rate?.toFixed(2)}</span>
                  </div>
                )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无数据</div>}
              </div>
            </div>

            {/* Failure Patterns */}
            <div className="panel">
              <div className="panel-header"><span>失败模式</span></div>
              <div className="panel-body">
                {memory?.failure_patterns?.slice(0, 5).map((fp) => (
                  <div key={fp.reason} className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0">
                    <span className="text-negative/80">{fp.reason}</span>
                    <span className="tabular text-text-tertiary">x{fp.count}</span>
                  </div>
                )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无失败记录</div>}
              </div>
            </div>
          </div>
          </>)}
        </>
      )}
    </div>
  );
}

type CloudSnapshotPayload = Partial<CloudAlphaSummary> & Record<string, unknown> & {
  alphas?: Array<CloudAlpha | Record<string, unknown>>;
  summary?: Partial<CloudAlphaSummary> & Record<string, unknown>;
};

function cloudSnapshotSummary(cloud: CloudSnapshotPayload | null) {
  const summary = cloud?.summary || {};
  return {
    count: numberOrUndefined(summary.count ?? summary.total ?? summary.total_count),
    submitted_count: numberOrUndefined(cloud?.submitted_count ?? summary.submitted_count),
    passed_unsubmitted_count: numberOrUndefined(cloud?.passed_unsubmitted_count ?? summary.passed_unsubmitted_count),
    is_stale: Boolean(cloud?.is_stale ?? summary.is_stale),
    loaded_at: stringOrUndefined(cloud?.loaded_at ?? summary.loaded_at),
    age_seconds: numberOrUndefined(cloud?.age_seconds ?? summary.age_seconds),
  };
}

function cloudSnapshotPreviewRows(cloud: CloudSnapshotPayload | null): Array<CloudAlpha | Record<string, unknown>> {
  const rows = cloud?.sample_alphas || cloud?.alphas || [];
  return Array.isArray(rows) ? rows : [];
}

function cloudAlphaId(row: CloudAlpha | Record<string, unknown>) {
  const data = row as Record<string, unknown>;
  return String(data.alpha_id || data.id || "-");
}

function cloudAlphaPassFail(row: CloudAlpha | Record<string, unknown>) {
  const data = row as Record<string, unknown>;
  const metrics = (data.metrics && typeof data.metrics === "object" ? data.metrics : {}) as Record<string, unknown>;
  return String(data.pass_fail || metrics.pass_fail || "");
}

function cloudAlphaMetric(row: CloudAlpha | Record<string, unknown>, key: string) {
  const data = row as Record<string, unknown>;
  const metrics = (data.metrics && typeof data.metrics === "object" ? data.metrics : {}) as Record<string, unknown>;
  return numberOrUndefined(data[key] ?? metrics[key]);
}

function formatMetric(value: number | undefined) {
  return value == null ? "--" : value.toFixed(2);
}

function numberOrUndefined(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function stringOrUndefined(value: unknown) {
  const text = typeof value === "string" ? value.trim() : "";
  return text || undefined;
}

function formatSyncAge(ageSeconds?: number, loadedAt?: string) {
  if (typeof ageSeconds === "number" && Number.isFinite(ageSeconds) && ageSeconds >= 0) {
    if (ageSeconds < 60) return "刚刚同步";
    if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)} 分钟前`;
    if (ageSeconds < 86400) return `${Math.floor(ageSeconds / 3600)} 小时前`;
    return `${Math.floor(ageSeconds / 86400)} 天前`;
  }
  if (loadedAt) {
    const timestamp = Date.parse(loadedAt);
    if (Number.isFinite(timestamp)) {
      return new Date(timestamp).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  }
  return "未同步";
}

// ── Step Progress Bar ─────────────────────────────────────────────────────

function StepProgressBar({ currentStep }: { currentStep: number }) {
  const steps = [
    { num: 1, label: "连接 BRAIN", desc: "填写凭证并测试连接" },
    { num: 2, label: "本地缓存", desc: "首次同步后默认使用本地缓存" },
    { num: 3, label: "开始验证", desc: "运行非提交生产验证流水线" },
  ];

  return (
    <div className="panel mb-4" style={{ borderColor: "oklch(0.35 0.02 240 / 0.20)" }}>
      <div className="panel-body-padded" style={{ padding: "10px 14px", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
          {steps.map((step, i) => {
            const isComplete = currentStep > step.num;
            const isActive = currentStep === step.num;
            const isPending = currentStep < step.num;
            return (
              <div key={step.num} style={{ display: "flex", alignItems: "center", flex: i < steps.length - 1 ? 1 : "0 0 auto", minWidth: 0 }}>
                {/* Step circle */}
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: isComplete ? "oklch(0.48 0.10 160)"
                    : isActive ? "oklch(0.58 0.12 245)"
                    : "oklch(0.22 0.007 45)",
                  color: isPending ? "oklch(0.50 0.006 45)" : "#fff",
                  fontWeight: 600, fontSize: 12, transition: "background-color 0.3s",
                }}>
                  {isComplete ? "✓" : step.num}
                </div>
                {/* Step label — full text on md+, abbreviated on sm, hidden on xs */}
                <div style={{ marginLeft: 6, minWidth: 0, overflow: "hidden" }}>
                  <p className={`text-xs font-medium truncate hidden sm:block ${isPending ? "text-text-tertiary" : "text-text-primary"}`}
                    style={{ lineHeight: 1.3 }}>
                    {step.label}
                  </p>
                  <p className="text-xs text-text-tertiary hidden md:block truncate" style={{ lineHeight: 1.2 }}>
                    {step.desc}
                  </p>
                  <p className={`sm:hidden text-[10px] font-medium truncate ${isPending ? "text-text-tertiary" : "text-text-primary"}`}
                    style={{ lineHeight: 1.2 }} aria-hidden="true">
                    {step.label.replace(" ", "")}
                  </p>
                </div>
                {/* Connector line */}
                {i < steps.length - 1 && (
                  <div style={{
                    flex: 1, height: 2, minWidth: 8, maxWidth: 60, margin: "0 6px",
                    backgroundColor: isComplete ? "oklch(0.48 0.10 160)" : "oklch(0.22 0.007 45)",
                    transition: "background-color 0.3s",
                  }} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Sync Cloud CTA (shown when connected but not synced) ──────────────────

function SyncCloudCTA({ onNavigateToSync }: { onNavigateToSync: () => void }) {
  return (
    <div className="panel mb-6" style={{
      borderColor: "oklch(0.65 0.14 80 / 0.40)",
      background: "oklch(0.65 0.06 80 / 0.08)",
    }}>
      <div className="panel-body-padded" style={{ padding: "24px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 12 }}>
          {/* Icon */}
          <div style={{
            width: 56, height: 56, borderRadius: "50%",
            background: "oklch(0.65 0.14 80 / 0.15)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="oklch(0.68 0.12 82)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-accent">连接成功！未检测到本地缓存</h2>
            <p className="text-sm text-text-secondary mt-1 max-w-md">
              BRAIN 连接正常。首次使用需要拉取云端 Alpha 列表和官方能力集；同步完成后，后续登录会默认直接读取本地缓存。
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onNavigateToSync}
            style={{ padding: "10px 32px", fontSize: 15, fontWeight: 600 }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ marginRight: 8 }}>
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
            开始首次同步
          </button>
          <p className="text-xs text-text-tertiary">
            后续刷新改为手动触发 · 同步过程中会显示实时进度和已等待时间
          </p>
        </div>
      </div>
    </div>
  );
}
