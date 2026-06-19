/** Dashboard — Progressive flow with step-based guidance v3.1 */
import { useEffect, useState, useRef, type ReactNode } from "react";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, CloudAlpha, CloudAlphaSummary, ResearchMemorySummary } from "@/types";
import KpiCard from "@/components/KpiCard";
import TrendPanel, { type TrendData } from "@/components/TrendPanel";
import ProgressFeedback from "@/components/ProgressFeedback";
import ResumeWork from "@/components/ResumeWork";
import { safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { saveResumeState } from "@/utils/resumeState";

// ── Trend Data Helpers ────────────────────────────────────────────────────

const TREND_KEY_CANDIDATES = "trend_candidates";
const TREND_KEY_SUBMISSIONS = "trend_submissions";
const TREND_MAX_POINTS = 7;

function loadTrendData(key: string): TrendData[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (d): d is TrendData =>
        typeof d === "object" &&
        d !== null &&
        typeof (d as TrendData).date === "string" &&
        typeof (d as TrendData).value === "number" &&
        Number.isFinite((d as TrendData).value),
    ).slice(-TREND_MAX_POINTS);
  } catch {
    return [];
  }
}

function saveTrendData(key: string, data: TrendData[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(data.slice(-TREND_MAX_POINTS)));
  } catch { console.warn("Dashboard: localStorage full or unavailable"); }
}

function appendTrendPoint(key: string, value: number): TrendData[] {
  const existing = loadTrendData(key);
  const today = new Date().toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
  const newPoint: TrendData = { date: today, value };
  const updated = [...existing, newPoint].slice(-TREND_MAX_POINTS);
  saveTrendData(key, updated);
  return updated;
}

/** Compute change percentage between the oldest and newest trend data points. */
function computeTrendChange(data: TrendData[]): number | undefined {
  if (data.length < 2) return undefined;
  const first = data[0].value;
  const last = data[data.length - 1].value;
  if (first === 0) return last > 0 ? 100 : 0;
  return ((last - first) / Math.abs(first)) * 100;
}

/** P1-7: 将趋势数据异步同步到后端（fire-and-forget，不阻塞 UI）。 */
function syncTrendToBackend(candidates: number, submissions: number, cycles: number = 0): void {
  fetch("/api/trends", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidates, submissions, cycles }),
  }).catch(() => {
    console.warn("Dashboard trend sync unavailable — data preserved in localStorage");
  });
}

/** P2-6: 根据当前仪表盘数据生成工作日报 Markdown。 */
interface CloudSummaryData {
  count?: number;
  submitted_count?: number;
  passed_unsubmitted_count?: number;
  is_stale: boolean;
  loaded_at?: string;
  age_seconds?: number;
}

interface ReportInput {
  trendCandidates: TrendData[];
  trendSubmissions: TrendData[];
  cloudSummary: CloudSummaryData;
  memory: ResearchMemorySummary | null;
  status: JobStatus | null;
  cloudPreviewRows: Array<CloudAlpha | Record<string, unknown>>;
}

function generateReportMarkdown(input: ReportInput): string {
  const { trendCandidates, trendSubmissions, cloudSummary, memory, status, cloudPreviewRows } = input;
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - now.getDay() + 1); // 本周一
  const weekLabel = `${weekStart.getFullYear()}-${String(weekStart.getMonth() + 1).padStart(2, "0")}-${String(weekStart.getDate()).padStart(2, "0")}`;

  // 本周候选生成数（趋势中本周的数据点）
  const weekCandidatesTotal = trendCandidates
    .filter((d) => d.date >= weekLabel)
    .reduce((sum, d) => sum + d.value, 0);
  const weekSubmissionsTotal = trendSubmissions
    .filter((d) => d.date >= weekLabel)
    .reduce((sum, d) => sum + d.value, 0);

  // 通过率
  const totalCount = cloudSummary.count ?? 0;
  const submittedCount = cloudSummary.submitted_count ?? 0;
  const passRate = totalCount > 0 ? ((submittedCount / totalCount) * 100).toFixed(1) : "0.0";

  // Top 候选摘要
  const topAlphas = cloudPreviewRows.slice(0, 5);

  const lines: string[] = [];
  lines.push(`# BRAIN Alpha 工作日报`);
  lines.push("");
  lines.push(`**日期**: ${now.toLocaleDateString("zh-CN")}`);
  lines.push(`**报告周期**: ${weekLabel} ~ ${now.toLocaleDateString("zh-CN")}`);
  lines.push("");
  lines.push("## 核心指标");
  lines.push("");
  lines.push(`| 指标 | 数值 |`);
  lines.push(`|------|------|`);
  lines.push(`| 本周候选生成数 | ${weekCandidatesTotal} |`);
  lines.push(`| 本周提交数 | ${weekSubmissionsTotal} |`);
  lines.push(`| 云端 Alpha 总数 | ${totalCount} |`);
  lines.push(`| 已提交数 | ${submittedCount} |`);
  lines.push(`| 通过率 | ${passRate}% |`);
  lines.push(`| 当前候选池 | ${memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0} |`);
  lines.push(`| 回测完成数 | ${status?.progress?.backtests_completed ?? 0} |`);
  lines.push(`| 回测待处理 | ${status?.progress?.backtests_pending ?? 0} |`);
  lines.push("");

  if (topAlphas.length > 0) {
    lines.push("## Top 候选摘要");
    lines.push("");
    lines.push("| Alpha ID | 状态 | Sharpe | Fitness | Turnover |");
    lines.push("|----------|------|--------|---------|----------|");
    for (const a of topAlphas) {
      const id = cloudAlphaId(a);
      const pf = cloudAlphaPassFail(a);
      const sharpe = formatMetric(cloudAlphaMetric(a, "sharpe"));
      const fitness = formatMetric(cloudAlphaMetric(a, "fitness"));
      const turnover = formatMetric(cloudAlphaMetric(a, "turnover"));
      lines.push(`| ${id} | ${pf} | ${sharpe} | ${fitness} | ${turnover} |`);
    }
    lines.push("");
  }

  if (memory?.families && memory.families.length > 0) {
    lines.push("## 热门家族 Top 3");
    lines.push("");
    for (const f of memory.families.slice(0, 3)) {
      lines.push(`- **${f.name}**: n=${f.count}, 成功率=${(f.success_rate ?? 0).toFixed(2)}`);
    }
    lines.push("");
  }

  lines.push("---");
  lines.push(`*由 BRAIN-Alpha 本地控制台自动生成 · ${now.toISOString().slice(0, 19).replace("T", " ")}*`);

  return lines.join("\n");
}

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  /** Whether the user has successfully tested BRAIN connection */
  connected: boolean;
  /** Whether local cloud Alpha and official context cache are available */
  contextFresh: boolean;
  /** Whether backend phase/cache status has been read at least once */
  phaseStatus?: "loading" | "error" | "ready";
  /** Navigate to the sync/official operations page and start the first sync */
  onNavigateToSync: () => void;
  /** Open the manual sync page without auto-starting a refresh */
  onOpenSync?: () => void;
  /** Navigate to the candidate management page. */
  onNavigateToCandidates?: () => void;
  /** Whether a pipeline job is currently running. */
  jobRunning?: boolean;
  /** Current job status message (shown in the running banner). */
  jobStatusMessage?: string;
  /** Current cycle number for the running job. */
  jobCycle?: number;
  /** Start / resume the pipeline job. */
  onStartJob?: (resume?: boolean) => void;
  /** Step 1: CredentialQuickStart (always rendered when not connected) */
  children?: ReactNode;
}

export default function Dashboard({ notify, connected, contextFresh, phaseStatus = "ready", onNavigateToSync, onOpenSync, onNavigateToCandidates, jobRunning = false, jobStatusMessage, jobCycle, onStartJob, children }: Props) {
  const [snapshotExpanded, setSnapshotExpanded] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [reportCopied, setReportCopied] = useState(false);
  const [trendCandidates, setTrendCandidates] = useState<TrendData[]>(() => loadTrendData(TREND_KEY_CANDIDATES));
  const [trendSubmissions, setTrendSubmissions] = useState<TrendData[]>(() => loadTrendData(TREND_KEY_SUBMISSIONS));
  const statusApi = useApi<JobStatus>();
  const cloudApi = useApi<CloudSnapshotPayload>();
  const memoryApi = useApi<ResearchMemorySummary>();

  useEffect(() => {
    statusApi.call("/api/production-validation/status");
    cloudApi.call("/api/snapshot/cloud");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
    // P2-25 fix: useApi().call is a useCallback([], []) stable reference.
    // Including it in deps satisfies the lint rule without runtime harm,
    // but a future refactor that changes call's identity would trigger
    // infinite re-fetches.  The comment documents this invariant.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusApi.call, cloudApi.call, memoryApi.call]);

  // P0-4: persist candidate pool size after memory snapshot loads
  useEffect(() => {
    const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
    if (poolSize != null && poolSize > 0) {
      saveResumeState({ lastPoolSize: poolSize });
    }
  }, [memory?.total_candidates, status?.progress?.candidates_generated]);

  // P2-1: persist lastSyncTime when cloud snapshot loads successfully
  useEffect(() => {
    if (cloud != null && !cloudApi.loading && !cloudApi.error) {
      const syncTime = cloudSummary(cloud).loaded_at || new Date().toISOString();
      saveResumeState({ lastSyncTime: syncTime });
    }
    // Only run when cloud data transitions from null to non-null (initial load)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloud != null, cloudApi.loading]);

  // P1-7: 从后端 API 加载趋势数据，覆盖 localStorage 缓存
  useEffect(() => {
    let cancelled = false;
    async function fetchTrends() {
      try {
        const res = await fetch("/api/trends?days=30");
        if (!res.ok) return;
        const json: unknown = await res.json();
        if (
          !json ||
          typeof json !== "object" ||
          !("ok" in (json as Record<string, unknown>)) ||
          !(json as Record<string, unknown>).ok
        )
          return;
        const data = (json as { data?: Array<Record<string, unknown>> }).data;
        if (!Array.isArray(data) || data.length === 0) return;
        const candidatesPoints: TrendData[] = [];
        const submissionsPoints: TrendData[] = [];
        for (const row of data) {
          const date = typeof row.date === "string" ? row.date : "";
          const c = Number(row.candidates);
          const s = Number(row.submissions);
          if (date && Number.isFinite(c)) {
            candidatesPoints.push({ date, value: c });
          }
          if (date && Number.isFinite(s)) {
            submissionsPoints.push({ date, value: s });
          }
        }
        if (!cancelled) {
          if (candidatesPoints.length > 0) setTrendCandidates(candidatesPoints.slice(-TREND_MAX_POINTS));
          if (submissionsPoints.length > 0) setTrendSubmissions(submissionsPoints.slice(-TREND_MAX_POINTS));
        }
      } catch { console.warn("Dashboard: API unavailable, fallback to localStorage"); }
    }
    fetchTrends();
    return () => { cancelled = true; };
  }, []);

  // P1-2: accumulate trend data on Dashboard load
  useEffect(() => {
    const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
    if (poolSize != null && poolSize > 0) {
      const updated = appendTrendPoint(TREND_KEY_CANDIDATES, poolSize);
      setTrendCandidates(updated);
    }
    const submissions = status?.progress?.submissions ?? cloudSummary?.submitted_count;
    if (submissions != null) {
      const updated = appendTrendPoint(TREND_KEY_SUBMISSIONS, submissions);
      setTrendSubmissions(updated);
    }
    // P1-7: fire-and-forget 同步到后端
    const syncCandidates = memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0;
    const syncSubmissions = status?.progress?.submissions ?? cloudSummary?.submitted_count ?? 0;
    const syncCycles = status?.progress?.completed_cycles ?? 0;
    if (syncCandidates > 0 || syncSubmissions > 0) {
      syncTrendToBackend(syncCandidates, syncSubmissions, syncCycles);
    }
    // Only run on data load, not on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.progress?.candidates_generated, status?.progress?.submissions, cloudSummary?.submitted_count, memory?.total_candidates]);

  // P1-2: accumulate trend data when job finishes
  const prevJobRunningRef = useRef(jobRunning);
  useEffect(() => {
    // Job just finished (was running, now stopped)
    if (prevJobRunningRef.current && !jobRunning) {
      const poolSize = memory?.total_candidates ?? status?.progress?.candidates_generated;
      if (poolSize != null && poolSize > 0) {
        const updated = appendTrendPoint(TREND_KEY_CANDIDATES, poolSize);
        setTrendCandidates(updated);
      }
      const submissions = status?.progress?.submissions ?? cloudSummary?.submitted_count;
      if (submissions != null) {
        const updated = appendTrendPoint(TREND_KEY_SUBMISSIONS, submissions);
        setTrendSubmissions(updated);
      }
      // P1-7: fire-and-forget 同步到后端
      const syncCandidates = memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0;
      const syncSubmissions = status?.progress?.submissions ?? cloudSummary?.submitted_count ?? 0;
      const syncCycles = status?.progress?.completed_cycles ?? 0;
      if (syncCandidates > 0 || syncSubmissions > 0) {
        syncTrendToBackend(syncCandidates, syncSubmissions, syncCycles);
      }
    }
    prevJobRunningRef.current = jobRunning;
    // Only react to jobRunning transitions
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobRunning]);

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
    statusApi.error ? `Status: ${safeDisplayErrorMessage(statusApi.error)}` : "",
    cloudApi.error ? `Cloud: ${safeDisplayErrorMessage(cloudApi.error)}` : "",
    memoryApi.error ? `Memory: ${safeDisplayErrorMessage(memoryApi.error)}` : "",
  ].filter(Boolean);
  const loading = statusApi.loading || cloudApi.loading || memoryApi.loading;
  const [showGuide, setShowGuide] = useState(() => !localStorage.getItem("brain_alpha_guide_dismissed"));

  const dismissGuide = () => {
    localStorage.setItem("brain_alpha_guide_dismissed", "1");
    setShowGuide(false);
  };

  // ── Determine current step ──────────────────────────────────────────────
  const phasePending = phaseStatus === "loading";
  const phaseFailed = phaseStatus === "error";
  const currentStep = phasePending || phaseFailed ? 1 : !contextFresh ? (!connected ? 1 : 2) : 3;
  const stepLabel = phasePending ? "读取本地状态"
    : phaseFailed ? "状态读取失败"
    : currentStep === 1 ? "连接 BRAIN"
    : currentStep === 2 ? "准备本地缓存"
    : connected ? "开始验证" : "缓存模式";
  const openManualSync = onOpenSync || onNavigateToSync;

  return (
    <div className="animate-fade-in">
      {/* ═══ Resume Work Banner (P0-4) ═══ */}
      {onNavigateToCandidates && onStartJob && (
        <ResumeWork
          notify={notify}
          connected={connected}
          contextFresh={contextFresh}
          phaseStatus={phaseStatus}
          onNavigateToSync={onNavigateToSync}
          onNavigateToCandidates={onNavigateToCandidates}
          jobRunning={jobRunning}
          jobStatusMessage={jobStatusMessage}
          jobCycle={jobCycle}
          onStartJob={onStartJob}
        />
      )}

      {/* ═══ Progressive Flow Indicator ═══ */}
      <StepProgressBar currentStep={currentStep} />

      {/* First-time guide */}
      {showGuide && (
        <div className="panel mb-4 guide-panel">
          <div className="panel-body-padded flex justify-between items-start gap-3">
            <div>
              <p className="text-sm font-medium text-info mb-2">首次使用？按顺序完成以下步骤</p>
              <div className="grid gap-1 text-xs text-text-secondary guide-steps">
                <span className={currentStep === 1 ? "text-info-text font-medium text-right" : currentStep > 1 ? "text-positive-text font-medium text-right" : "text-text-disabled font-medium text-right"}>1.</span>
                <span>
                  {phasePending
                    ? "正在读取本地缓存和账户状态"
                    : phaseFailed
                      ? "状态读取失败，请刷新页面或重新打开本地控制台"
                      : contextFresh && !connected
                    ? "检测到本地缓存，可先以缓存模式继续"
                    : <>填写账户邮箱和密码，点击 <strong>测试连接</strong>{connected ? " ✓" : ""}</>}
                </span>
                <span className={currentStep === 2 ? "text-info-text font-medium text-right" : currentStep > 2 ? "text-positive-text font-medium text-right" : "text-text-disabled font-medium text-right"}>2.</span>
                <span>本地无缓存时点击 <strong>开始首次同步</strong>；已有缓存会直接使用，可稍后手动刷新{currentStep > 2 ? " ✓" : ""}</span>
                <span className={currentStep === 3 ? "text-info-text font-medium text-right" : "text-text-disabled font-medium text-right"}>3.</span>
                <span>同步完成后，在下方点击 <strong>运行非提交验证</strong> 开始生产搜索</span>
                <span className={currentStep > 3 ? "text-positive-text font-medium text-right" : currentStep >= 3 ? "text-info-text font-medium text-right" : "text-text-disabled font-medium text-right"}>4.</span>
                <span>在侧边栏「候选发现」「评估与验证」「提交就绪」中继续后续流程</span>
              </div>
            </div>
            <button onClick={dismissGuide} className="btn btn-ghost btn-sm flex-shrink-0" aria-label="关闭引导">✕</button>
          </div>
        </div>
      )}

      {/* Fix 1: 新手引导可恢复 — "重新显示引导" link */}
      {!showGuide && (
        <div className="mb-4 text-right">
          <button
            type="button"
            className="text-xs text-text-tertiary hover:text-text-secondary underline cursor-pointer bg-transparent border-none p-0"
            onClick={() => {
              localStorage.removeItem("brain_alpha_guide_dismissed");
              setShowGuide(true);
            }}
          >
            ? 重新显示首次引导
          </button>
        </div>
      )}

      {/* ═══ Page heading ═══ */}
      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
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

      {(phasePending || phaseFailed) && (
        <PhaseStatusNotice failed={phaseFailed} />
      )}

      {/* ═══ Step 1: Credential + Connection Test ═══ */}
      {!connected && !contextFresh && !phasePending && !phaseFailed && (
        <div className="mb-6">{children}</div>
      )}

      {/* ═══ Step 2: Sync Cloud CTA ═══ */}
      {connected && !contextFresh && (
        <SyncCloudCTA onNavigateToSync={onNavigateToSync} />
      )}

      {/* ═══ Step 3: Production inputs ready (children: JobMonitor when connected) ═══ */}
      {contextFresh && (
        <>
          {connected && children}
          {!connected && (children || <CacheModeNotice />)}

          {/* Error banner */}
          {errors.length > 0 && (
            <div className="panel panel-negative mb-4" role="alert">
              <div className="panel-body-padded flex justify-between items-start">
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
            <TrendPanel
              title="候选总数"
              data={trendCandidates}
              unit="个"
              color="#3b82f6"
              currentValue={memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0}
              change={computeTrendChange(trendCandidates)}
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
            <TrendPanel
              title="提交数"
              data={trendSubmissions}
              unit="个"
              color="#f59e0b"
              currentValue={status?.progress?.submissions ?? cloudSummary.submitted_count ?? 0}
              change={computeTrendChange(trendSubmissions)}
            />
          </div>

          {/* Collapsible data snapshots */}
          <div className="flex items-center gap-2 flex-wrap mb-4">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setSnapshotExpanded((v) => !v)}
              aria-expanded={snapshotExpanded}
            >
              <span className="inline-block transition-transform duration-200" style={{ transform: snapshotExpanded ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
              <span className="ml-1.5">数据快照{snapshotExpanded ? "" : ` (${cloudSummary.count ?? "--"} 条 Alpha)`}</span>
            </button>
            {/* P2-6: 工作日报生成按钮 */}
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                const md = generateReportMarkdown({
                  trendCandidates,
                  trendSubmissions,
                  cloudSummary,
                  memory,
                  status,
                  cloudPreviewRows,
                });
                setReportMarkdown(md);
                setReportCopied(false);
                setShowReport(true);
              }}
            >
              📋 生成报告
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
                <ProgressFeedback state="error" title="云端 Alpha" error={safeDisplayErrorMessage(cloudApi.error)} onRetry={() => cloudApi.call("/api/snapshot/cloud")} compact />
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
                    <div className="max-h-[200px] overflow-y-auto">
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

      {/* P2-6: 工作日报 Modal */}
      {showReport && (
        <div
          className="modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setShowReport(false); }}
          role="dialog"
          aria-modal="true"
          aria-label="工作日报"
        >
          <div className="flex flex-col rounded-lg shadow-lg border border-modal max-w-[640px] w-[calc(100%-32px)] max-h-[80vh]" style={{ backgroundColor: "var(--color-modal-bg)" }}>
            {/* Header */}
            <div className="flex justify-between items-center px-5 py-4 border-b border-modal-border">
              <h2 className="text-base font-semibold text-text-primary">📋 工作日报</h2>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowReport(false)}
                aria-label="关闭"
              >
                ✕
              </button>
            </div>

            {/* Body — Markdown preview */}
            <div className="flex-1 overflow-y-auto p-5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap border-y border-divider" style={{ color: "var(--color-report-text)", backgroundColor: "var(--color-report-bg)" }}>
              {reportMarkdown}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 px-5 py-3">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setShowReport(false)}
              >
                关闭
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(reportMarkdown);
                    setReportCopied(true);
                    setTimeout(() => setReportCopied(false), 2000);
                  } catch {
                    // 降级方案：使用 textarea
                    const ta = document.createElement("textarea");
                    ta.value = reportMarkdown;
                    ta.style.position = "fixed";
                    ta.style.opacity = "0";
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand("copy");
                    document.body.removeChild(ta);
                    setReportCopied(true);
                    setTimeout(() => setReportCopied(false), 2000);
                  }
                }}
              >
                {reportCopied ? "✓ 已复制" : "复制为 Markdown"}
              </button>
            </div>
          </div>
        </div>
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
    { num: 1, label: "账户/缓存", desc: "测试连接或使用已有本地缓存" },
    { num: 2, label: "本地缓存", desc: "首次同步后默认使用本地缓存" },
    { num: 3, label: "开始验证", desc: "运行非提交生产验证流水线" },
  ];

  return (
    <div className="panel panel-step-bar mb-4">
      <div className="flex items-center w-full px-3.5 py-2.5">
        {steps.map((step, i) => {
          const isComplete = currentStep > step.num;
          const isActive = currentStep === step.num;
          const isPending = currentStep < step.num;
          return (
            <div key={step.num} className="flex items-center min-w-0" style={{ flex: i < steps.length - 1 ? 1 : "0 0 auto" }}>
              {/* Step circle */}
              <div
                className="flex items-center justify-center w-7 h-7 rounded-full flex-shrink-0 text-xs font-semibold text-white transition-colors duration-300"
                style={{
                  backgroundColor: isComplete ? "var(--color-step-complete)"
                    : isActive ? "var(--color-step-active)"
                    : "var(--color-step-pending)",
                  color: isPending ? "var(--color-step-pending-text)" : "#fff",
                }}
              >
                {isComplete ? "✓" : step.num}
              </div>
              {/* Step label */}
              <div className="ml-1.5 min-w-0 overflow-hidden">
                <p className={`text-xs font-medium truncate hidden sm:block ${isPending ? "text-text-tertiary" : "text-text-primary"}`}>
                  {step.label}
                </p>
                <p className="text-xs text-text-tertiary hidden md:block truncate">
                  {step.desc}
                </p>
                <p className={`sm:hidden text-[10px] font-medium truncate ${isPending ? "text-text-tertiary" : "text-text-primary"}`} aria-hidden="true">
                  {step.label.replace(" ", "")}
                </p>
              </div>
              {/* Connector line */}
              {i < steps.length - 1 && (
                <div
                  className="flex-1 h-0.5 min-w-[8px] max-w-[60px] mx-1.5 transition-colors duration-300"
                  style={{
                    backgroundColor: isComplete ? "var(--color-step-complete)" : "var(--color-step-pending)",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Sync Cloud CTA (shown when connected but not synced) ──────────────────

function SyncCloudCTA({ onNavigateToSync }: { onNavigateToSync: () => void }) {
  return (
    <div className="panel panel-warning mb-6">
      <div className="p-6">
        <div className="flex flex-col items-center text-center gap-3">
          {/* Icon */}
          <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: "var(--color-panel-warning-bg)" }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning-icon)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="mr-2">
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

function CacheModeNotice() {
  return (
    <div className="panel panel-cache mb-4">
      <div className="panel-body-padded flex justify-between items-start gap-3">
        <div>
          <p className="text-sm font-medium text-warning mb-1">本地缓存可用，当前为缓存模式</p>
          <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
            可继续查看本地快照和候选信息；手动同步、官方回测和提交前复核需要先测试 BRAIN 连接。
          </p>
        </div>
      </div>
    </div>
  );
}

function PhaseStatusNotice({ failed }: { failed: boolean }) {
  return (
    <div className={`panel mb-6 ${failed ? "panel-negative" : "panel-info"}`}>
      <div className="panel-body-padded">
        <p className={`text-sm font-medium mb-1 ${failed ? "text-negative" : "text-info"}`}>
          {failed ? "状态读取失败" : "正在读取本地状态"}
        </p>
        <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
          {failed
            ? "暂时无法确认账户连接和本地缓存状态；请刷新页面或重新打开本地控制台。"
            : "正在确认本地 session、云端 Alpha 缓存和官方上下文缓存；读取完成前不会判定为未连接。"}
        </p>
      </div>
    </div>
  );
}
