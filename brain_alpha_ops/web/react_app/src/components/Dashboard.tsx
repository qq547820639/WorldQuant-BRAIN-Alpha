/** Dashboard — Terminal Precision v3.0 */
import { useEffect, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, CloudAlphaSummary, ResearchMemorySummary } from "@/types";
import KpiCard from "@/components/KpiCard";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function Dashboard({ notify }: Props) {
  const [snapshotExpanded, setSnapshotExpanded] = useState(false);
  const statusApi = useApi<JobStatus>();
  const cloudApi = useApi<CloudAlphaSummary>();
  const memoryApi = useApi<ResearchMemorySummary>();

  useEffect(() => {
    statusApi.call("/api/production-validation/status");
    cloudApi.call("/api/snapshot/cloud?limit=10");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
  }, [statusApi.call, cloudApi.call, memoryApi.call]);

  const status = statusApi.data;
  const cloud = cloudApi.data;
  const memory = memoryApi.data;

  const retryAll = () => {
    statusApi.call("/api/production-validation/status");
    cloudApi.call("/api/snapshot/cloud?limit=10");
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

  return (
    <div className="animate-fade-in">
      {/* First-time guide */}
      {showGuide && (
        <div className="panel mb-4" style={{ borderColor: "oklch(0.58 0.12 245 / 0.30)", background: "oklch(0.58 0.06 245 / 0.08)" }}>
          <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <div>
              <p className="text-sm font-medium text-info mb-2">首次使用？按顺序完成以下步骤</p>
              <div className="grid gap-1 text-xs text-text-secondary" style={{ gridTemplateColumns: "auto 1fr", columnGap: 8 }}>
                <span style={{ color: "oklch(0.68 0.10 248)", fontWeight: 500 }}>1.</span><span>填写账户邮箱和密码，点击 <strong>测试连接</strong></span>
                <span style={{ color: "oklch(0.68 0.10 248)", fontWeight: 500 }}>2.</span><span>进入 <strong>连接与就绪</strong> 阶段，点击 <strong>开始刷新</strong> 同步云端</span>
                <span style={{ color: "oklch(0.68 0.10 248)", fontWeight: 500 }}>3.</span><span>进入 <strong>候选发现</strong> 阶段，点击 <strong>生产搜索</strong> 生成候��</span>
                <span style={{ color: "oklch(0.68 0.10 248)", fontWeight: 500 }}>4.</span><span>在 <strong>评估与验证</strong> 中评分、检查质量门禁</span>
                <span style={{ color: "oklch(0.68 0.10 248)", fontWeight: 500 }}>5.</span><span>通过阻断复核后进入 <strong>提交就绪</strong></span>
              </div>
            </div>
            <button onClick={dismissGuide} className="btn btn-ghost btn-sm" aria-label="关闭引导" style={{ flexShrink: 0 }}>✕</button>
          </div>
        </div>
      )}

      {/* Page heading */}
      <h1 className="text-xl font-medium text-text-primary mb-1">运行总览</h1>
      <p className="text-sm text-text-tertiary mb-4">
        流水线状态 · 云端数据 · 本地指标 — 上次更新: {new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </p>

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
          value={cloud?.count ?? "--"}
          subtitle={cloud ? `${cloud.submitted_count} 已提交` : "等待刷新"}
          trend={cloud && cloud.submitted_count > 0 ? "up" : "neutral"}
        />
        <KpiCard
          label="回测数"
          value={status?.progress?.backtests_completed ?? "--"}
          subtitle={status ? `${status.progress?.backtests_pending ?? 0} 待处理` : undefined}
        />
        <KpiCard
          label="提交数"
          value={status?.progress?.submissions ?? cloud?.submitted_count ?? "--"}
          trend={cloud && cloud.passed_unsubmitted_count ? cloud.passed_unsubmitted_count > 0 ? "up" : "neutral" : "neutral"}
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
          <span style={{ marginLeft: 6 }}>数据快照{snapshotExpanded ? "" : ` (${cloud ? cloud.count : "--"} 条 Alpha)`}</span>
        </button>
      </div>

      {snapshotExpanded && (<>

      {/* Cloud Alpha Summary Panel */}
      <div className="panel mb-4">
        <div className="panel-header">
          <span>云端 Alpha 缓存</span>
          {cloud && <span className="badge badge-neutral">{cloud.count} 条</span>}
        </div>
        <div className="panel-body-padded">
          {cloudApi.loading ? (
            <ProgressFeedback state="loading" title="云端 Alpha" progress={{ phase: "cloud", status_message: "加载中..." }} compact />
          ) : cloudApi.error ? (
            <ProgressFeedback state="error" title="云端 Alpha" error={cloudApi.error} onRetry={() => cloudApi.call("/api/snapshot/cloud?limit=10")} compact />
          ) : cloud ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
                <div><span className="text-text-tertiary">缓存总数</span><p className="font-mono-value text-base text-text-primary">{cloud.count}</p></div>
                <div><span className="text-text-tertiary">已提交</span><p className="font-mono-value text-base text-positive">{cloud.submitted_count}</p></div>
                <div><span className="text-text-tertiary">已通过（未提交）</span><p className="font-mono-value text-base text-warning">{cloud.passed_unsubmitted_count}</p></div>
                <div><span className="text-text-tertiary">缓存状态</span><p className="text-sm text-text-secondary">{cloud.is_stale ? "已过期" : "有效"}</p></div>
              </div>
              {cloud.sample_alphas && cloud.sample_alphas.length > 0 && (
                <div style={{ maxHeight: 200, overflowY: "auto" }}>
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
                      {cloud.sample_alphas.slice(0, 10).map((a, i) => (
                        <tr key={i}>
                          <td className="id">{a.alpha_id}</td>
                          <td><span className={`badge ${a.pass_fail === "PASS" ? "badge-positive" : "badge-negative"}`}>{a.pass_fail || "--"}</span></td>
                          <td className="num">{a.sharpe?.toFixed(2) ?? "--"}</td>
                          <td className="num">{a.fitness?.toFixed(2) ?? "--"}</td>
                          <td className="num">{a.turnover?.toFixed(2) ?? "--"}</td>
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
    </div>
  );
}
