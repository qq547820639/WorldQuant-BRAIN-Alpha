/** Dashboard — Progressive flow with step-based guidance v3.2 */
import { type ReactNode } from "react";
import { useDashboard } from "@/hooks/useDashboard";
import KpiCard from "@/components/KpiCard";
import TrendPanel from "@/components/TrendPanel";
import ResumeWork from "@/components/ResumeWork";
import Skeleton from "./Skeleton";
import ErrorCard from "./ErrorCard";
import { computeTrendChange } from "@/components/DashboardTrendData";
import { generateReportMarkdown, DashboardReportModal } from "@/components/DashboardReportModal";
import { formatSyncAge, DashboardCloudSnapshot } from "@/components/DashboardCloudSnapshot";
import { StepProgressBar } from "@/components/DashboardStepProgress";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  connected: boolean;
  contextFresh: boolean;
  phaseStatus?: "loading" | "error" | "ready";
  onNavigateToSync: () => void;
  onOpenSync?: () => void;
  onNavigateToCandidates?: () => void;
  jobRunning?: boolean;
  jobStatusMessage?: string;
  jobCycle?: number;
  onStartJob?: (resume?: boolean) => void;
  children?: ReactNode;
}

export default function Dashboard({
  notify,
  connected,
  contextFresh,
  phaseStatus = "ready",
  onNavigateToSync,
  onOpenSync,
  onNavigateToCandidates,
  jobRunning = false,
  jobStatusMessage,
  jobCycle,
  onStartJob,
  children,
}: Props) {
  const {
    snapshotExpanded,
    showReport,
    reportMarkdown,
    setReportMarkdown,
    trendCandidates,
    trendSubmissions,
    status,
    memory,
    cloudSummaryData,
    cloudPreviewRows,
    cloud,
    cloudLoading,
    cloudError,
    errors,
    loading,
    showGuide,
    phasePending,
    phaseFailed,
    currentStep,
    stepLabel,
    openManualSync,
    retryAll,
    dismissGuide,
    toggleGuide,
    toggleSnapshot,
    openReport,
    closeReport,
  } = useDashboard({
    connected,
    contextFresh,
    phaseStatus,
    onNavigateToSync,
    onOpenSync,
    jobRunning,
  });

  const handleGenerateReport = () => {
    const md = generateReportMarkdown({
      trendCandidates,
      trendSubmissions,
      cloudSummary: cloudSummaryData,
      memory,
      status,
      cloudPreviewRows,
    });
    setReportMarkdown(md);
    openReport();
  };

  return (
    <div className="animate-fade-in">
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

      <StepProgressBar currentStep={currentStep} />

      <GuidePanel
        show={showGuide}
        currentStep={currentStep}
        phasePending={phasePending}
        phaseFailed={phaseFailed}
        contextFresh={contextFresh}
        connected={connected}
        onDismiss={dismissGuide}
        onReshow={toggleGuide}
      />

      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-xl font-medium text-text-primary mb-1">运行总览</h1>
          <p className="text-sm text-text-tertiary">
            当前阶段：<span className="text-accent font-medium">{stepLabel}</span>
            {" · "}上次更新:{" "}
            {new Date().toLocaleTimeString("zh-CN", {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </p>
        </div>
        {connected && contextFresh && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={openManualSync}>
            手动同步
          </button>
        )}
      </div>

      {(phasePending || phaseFailed) && <PhaseStatusNotice failed={phaseFailed} />}

      {!connected && !contextFresh && !phasePending && !phaseFailed && (
        <div className="mb-6">{children}</div>
      )}

      {connected && !contextFresh && <SyncCloudCTA onNavigateToSync={onNavigateToSync} />}

      {contextFresh && (
        <>
          {connected && children}
          {!connected && (children || <CacheModeNotice />)}

          {loading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
              <Skeleton variant="card" className="hover:shadow-md transition-shadow" />
            </div>
          )}

          {!loading && errors.length > 0 && (
            <ErrorCard
              title="仪表盘数据需要关注"
              details={errors.join("；")}
              severity="error"
              onRetry={retryAll}
              className="mb-4"
            />
          )}

          {!loading && !errors.length && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
              <TrendPanel
                title="候选总数"
                data={trendCandidates}
                unit="个"
                color="#3b82f6"
                currentValue={
                  memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0
                }
                change={computeTrendChange(trendCandidates)}
              />
              <KpiCard
                label="云端 Alpha"
                value={cloudSummaryData.count ?? "--"}
                subtitle={
                  cloud
                    ? `${cloudSummaryData.submitted_count ?? 0} 已提交 · ${formatSyncAge(
                        cloudSummaryData.age_seconds,
                        cloudSummaryData.loaded_at,
                      )}`
                    : "等待刷新"
                }
                trend={cloud && (cloudSummaryData.submitted_count ?? 0) > 0 ? "up" : "neutral"}
                className="hover:shadow-md transition-shadow"
              />
              <KpiCard
                label="回测数"
                value={status?.progress?.backtests_completed ?? "--"}
                subtitle={status ? `${status.progress?.backtests_pending ?? 0} 待处理` : undefined}
                className="hover:shadow-md transition-shadow"
              />
              <TrendPanel
                title="提交数"
                data={trendSubmissions}
                unit="个"
                color="#f59e0b"
                currentValue={
                  status?.progress?.submissions ?? cloudSummaryData.submitted_count ?? 0
                }
                change={computeTrendChange(trendSubmissions)}
              />
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap mb-4">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={toggleSnapshot}
              aria-expanded={snapshotExpanded}
            >
              <span
                className="inline-block transition-transform duration-200"
                style={{ transform: snapshotExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
              >
                ▶
              </span>
              <span className="ml-1.5">
                数据快照
                {snapshotExpanded ? "" : ` (${cloudSummaryData.count ?? "--"} 条 Alpha)`}
              </span>
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={handleGenerateReport}>
              📋 生成报告
            </button>
          </div>

          {snapshotExpanded && (
            <>
              <DashboardCloudSnapshot
                cloud={cloud}
                loading={cloudLoading}
                error={cloudError}
                onRetry={retryAll}
                onOpenSync={openManualSync}
              />

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <MemoryPanel title="热门家族" items={memory?.families} />
                <MemoryPanel title="热门字段" items={memory?.fields} />
                <FailurePatternsPanel items={memory?.failure_patterns} />
              </div>
            </>
          )}
        </>
      )}

      <DashboardReportModal show={showReport} onClose={closeReport} markdown={reportMarkdown} />
    </div>
  );
}

interface GuidePanelProps {
  show: boolean;
  currentStep: number;
  phasePending: boolean;
  phaseFailed: boolean;
  contextFresh: boolean;
  connected: boolean;
  onDismiss: () => void;
  onReshow: () => void;
}

function GuidePanel({
  show,
  currentStep,
  phasePending,
  phaseFailed,
  contextFresh,
  connected,
  onDismiss,
  onReshow,
}: GuidePanelProps) {
  if (show) {
    return (
      <div className="panel mb-4 guide-panel">
        <div className="panel-body-padded flex justify-between items-start gap-3">
          <div>
            <p className="text-sm font-medium text-info mb-2">首次使用？按顺序完成以下步骤</p>
            <div className="grid gap-1 text-xs text-text-secondary guide-steps">
              <StepLabel step={1} currentStep={currentStep} />
              <span>
                {phasePending
                  ? "正在读取本地缓存和账户状态"
                  : phaseFailed
                    ? "状态读取失败，请刷新页面或重新打开本地控制台"
                    : contextFresh && !connected
                      ? "检测到本地缓存，可先以缓存模式继续"
                      : (
                          <>
                            填写账户邮箱和密码，点击 <strong>测试连接</strong>
                            {connected ? " ✓" : ""}
                          </>
                        )}
              </span>
              <StepLabel step={2} currentStep={currentStep} />
              <span>
                本地无缓存时点击 <strong>开始首次同步</strong>
                ；已有缓存会直接使用，可稍后手动刷新
                {currentStep > 2 ? " ✓" : ""}
              </span>
              <StepLabel step={3} currentStep={currentStep} />
              <span>同步完成后，在下方点击 <strong>运行非提交验证</strong> 开始生产搜索</span>
              <StepLabel step={4} currentStep={currentStep} />
              <span>在侧边栏「候选发现」「评估与验证」「提交就绪」中继续后续流程</span>
            </div>
          </div>
          <button
            onClick={onDismiss}
            className="btn btn-ghost btn-sm flex-shrink-0"
            aria-label="关闭引导"
          >
            ✕
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="mb-4 text-right">
      <button
        type="button"
        className="text-xs text-text-tertiary hover:text-text-secondary underline cursor-pointer bg-transparent border-none p-0"
        onClick={onReshow}
        aria-label="重新显示首次使用引导"
      >
        ? 重新显示首次引导
      </button>
    </div>
  );
}

function StepLabel({ step, currentStep }: { step: number; currentStep: number }) {
  const className =
    currentStep === step
      ? "text-info-text font-medium text-right"
      : currentStep > step
        ? "text-positive-text font-medium text-right"
        : "text-text-disabled font-medium text-right";
  return <span className={className}>{step}.</span>;
}

interface MemoryItem {
  name: string;
  count: number;
  success_rate?: number;
}

function MemoryPanel({ title, items }: { title: string; items?: MemoryItem[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>{title}</span>
      </div>
      <div className="panel-body">
        {items?.slice(0, 5).map((item) => (
          <div
            key={item.name}
            className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0"
          >
            <span className="text-text-secondary">{item.name}</span>
            <span className="tabular text-text-tertiary">
              n={item.count} {item.success_rate?.toFixed(2)}
            </span>
          </div>
        )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无数据</div>}
      </div>
    </div>
  );
}

function FailurePatternsPanel({
  items,
}: {
  items?: { reason: string; count: number }[];
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>失败模式</span>
      </div>
      <div className="panel-body">
        {items?.slice(0, 5).map((fp) => (
          <div
            key={fp.reason}
            className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0"
          >
            <span className="text-negative/80">{fp.reason}</span>
            <span className="tabular text-text-tertiary">x{fp.count}</span>
          </div>
        )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无失败记录</div>}
      </div>
    </div>
  );
}

function SyncCloudCTA({ onNavigateToSync }: { onNavigateToSync: () => void }) {
  return (
    <div className="panel panel-warning mb-6">
      <div className="p-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{ background: "var(--color-panel-warning-bg)" }}
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-warning-icon)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
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
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              className="mr-2"
            >
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
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
