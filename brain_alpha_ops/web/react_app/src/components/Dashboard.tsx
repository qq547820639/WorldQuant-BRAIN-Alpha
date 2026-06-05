/** Main dashboard with KPIs, job monitor, and latest results. */

import { useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, CloudAlphaSummary, ResearchMemorySummary } from "@/types";
import KpiCard from "@/components/KpiCard";
import JobMonitor from "@/components/JobMonitor";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function Dashboard({ notify }: Props) {
  const statusApi = useApi<JobStatus>();
  const cloudApi = useApi<CloudAlphaSummary>();
  const memoryApi = useApi<ResearchMemorySummary>();

  useEffect(() => {
    statusApi.call("/api/status");
    cloudApi.call("/api/snapshot/cloud?limit=10");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const status = statusApi.data;
  const cloud = cloudApi.data;
  const memory = memoryApi.data;

  const retryAll = () => {
    statusApi.call("/api/status");
    cloudApi.call("/api/snapshot/cloud?limit=10");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
  };

  const errors = [
    statusApi.error ? `Status: ${statusApi.error}` : "",
    cloudApi.error ? `Cloud: ${cloudApi.error}` : "",
    memoryApi.error ? `Memory: ${memoryApi.error}` : "",
  ].filter(Boolean);
  const loading = statusApi.loading || cloudApi.loading || memoryApi.loading;

  return (
    <div className="space-y-6 animate-fade-in">
      {errors.length > 0 && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-danger mb-2">仪表盘数据需要关注</h3>
              {errors.map((err) => (
                <p key={err} className="text-xs text-danger/90">{err}</p>
              ))}
            </div>
            <button onClick={retryAll} className="btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <ProgressFeedback
        state={errors.length ? "error" : loading ? "loading" : "idle"}
        title="仪表盘数据"
        progress={{ phase: loading ? "dashboard_load" : "completed", status_message: loading ? "正在刷新仪表盘快照。" : "仪表盘快照已更新。" }}
        error={errors.join(" / ")}
        onRetry={retryAll}
        compact={!loading && errors.length === 0}
      />

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="候选总数"
          value={memory?.total_candidates ?? status?.progress?.candidates_generated ?? "-"}
          subtitle={memory ? `${memory.families?.length ?? 0} 个家族` : "等待刷新"}
        />
        <KpiCard
          label="云端Alpha"
          value={cloud?.count ?? "-"}
          subtitle={cloud ? `${cloud.submitted_count} 已提交` : "等待刷新"}
          trend={cloud && cloud.submitted_count > 0 ? "up" : "neutral"}
        />
        <KpiCard
          label="回测数"
          value={status?.progress?.backtests_completed ?? "-"}
          subtitle={status ? `${status.progress?.backtests_pending ?? 0} 待处理` : undefined}
        />
        <KpiCard
          label="提交数"
          value={status?.progress?.submissions ?? cloud?.submitted_count ?? "-"}
          trend={cloud && cloud.passed_unsubmitted_count > 0 ? "up" : "neutral"}
        />
      </div>

      {/* Job Monitor + Cloud */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <JobMonitor notify={notify} />

        {/* Cloud Alpha Summary */}
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold text-gray-200">云端Alpha缓存</h3>
          {cloudApi.loading ? (
            <ProgressFeedback
              state="loading"
              title="云端Alpha缓存"
              progress={{ phase: "cloud_cache", status_message: "正在加载缓存的云端Alpha。" }}
              compact
            />
          ) : cloudApi.error ? (
            <ProgressFeedback
              state="error"
              title="云端Alpha缓存"
              error={cloudApi.error}
              onRetry={() => cloudApi.call("/api/snapshot/cloud?limit=10")}
              compact
            />
          ) : cloud ? (
            <>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <span className="text-muted">缓存总数</span>
                <span className="text-right">{cloud.count}</span>
                <span className="text-muted">已提交</span>
                <span className="text-right text-success">{cloud.submitted_count}</span>
                <span className="text-muted">已通过（未提交）</span>
                <span className="text-right text-warning">{cloud.passed_unsubmitted_count}</span>
                <span className="text-muted">缓存过期</span>
                <span className="text-right">{cloud.is_stale ? "⚠ 是" : "✓ 否"}</span>
              </div>
              {cloud.sample_alphas && cloud.sample_alphas.length > 0 && (
                <div className="max-h-40 overflow-y-auto bg-gray-950 rounded-lg p-2 text-xs font-mono">
                  {cloud.sample_alphas.slice(0, 5).map((a, i) => (
                    <div key={i} className="flex justify-between py-1 border-b border-gray-800 last:border-0">
                      <span className="text-brand-400">{a.alpha_id}</span>
                      <span className={a.pass_fail === "PASS" ? "text-success" : "text-danger"}>{a.pass_fail}</span>
                      <span>S:{a.sharpe?.toFixed(2)} F:{a.fitness?.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>

      {/* Top Families & Fields */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">热门家族</h3>
          {memory?.families?.slice(0, 5).map((f) => (
            <div key={f.name} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-gray-300">{f.name}</span>
              <span className="text-muted">n={f.count} 成功率:{f.success_rate?.toFixed(2)}</span>
            </div>
          )) || <p className="text-xs text-muted">暂无数据</p>}
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">热门字段</h3>
          {memory?.fields?.slice(0, 5).map((f) => (
            <div key={f.name} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-gray-300">{f.name}</span>
              <span className="text-muted">n={f.count} 成功率:{f.success_rate?.toFixed(2)}</span>
            </div>
          )) || <p className="text-xs text-muted">暂无数据</p>}
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">失败模式</h3>
          {memory?.failure_patterns?.slice(0, 5).map((fp) => (
            <div key={fp.reason} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-danger/80">{fp.reason}</span>
              <span className="text-muted">x{fp.count}</span>
            </div>
          )) || <p className="text-xs text-muted">暂无失败记录</p>}
        </div>
      </div>
    </div>
  );
}
