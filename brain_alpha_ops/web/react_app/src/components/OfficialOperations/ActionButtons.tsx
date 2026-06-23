/** Action buttons panel for sync/validate/submit operations. */

import { ActionPanel } from "./ActionPanel";
import type { OperationMode, SyncRange } from "./utils";
import type { SubmitReadinessResponse } from "@/types";

interface Props {
  mode: OperationMode;
  syncRange: SyncRange;
  syncRunning: boolean;
  syncStartLoading: boolean;
  syncNeedsRetry: boolean;
  readinessLoading: boolean;
  checkResultsLoading: boolean;
  checkRowsCount: number;
  readiness: SubmitReadinessResponse | undefined;
  contextOnlyMode: boolean;
  onSyncRangeChange: (range: SyncRange) => void;
  onStartRefresh: () => void;
  onStopRefresh: () => void;
  onLoadReadiness: () => void;
  onLoadChecks: () => void;
}

export default function ActionButtons({
  syncRange,
  syncRunning,
  syncStartLoading,
  syncNeedsRetry,
  readinessLoading,
  checkResultsLoading,
  checkRowsCount,
  readiness,
  contextOnlyMode,
  onSyncRangeChange,
  onStartRefresh,
  onStopRefresh,
  onLoadReadiness,
  onLoadChecks,
}: Props) {
  const refreshTitle = contextOnlyMode ? "仅刷新官方能力集" : "刷新官方能力集";
  const refreshDescription = contextOnlyMode
    ? "仅刷新官方字段、算子与 Dataset 上下文，不拉取云端 Alpha 快照。"
    : "同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。";

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <ActionPanel
        title={refreshTitle}
        description={refreshDescription}
        status={
          syncRunning ? "运行中" : "待启动"
        }
        primaryLabel={
          syncRunning
            ? "刷新中..."
            : syncNeedsRetry
              ? "重新刷新"
              : "开始刷新"
        }
        disabled={syncRunning || syncStartLoading}
        onPrimary={onStartRefresh}
        secondaryLabel="停止"
        secondaryDisabled={!syncRunning}
        onSecondary={onStopRefresh}
      >
        <label className="mt-3 block text-xs text-text-secondary">
          <span className="mb-1 block text-text-tertiary">同步范围</span>
          <select
            className="input w-full text-sm"
            value={syncRange}
            disabled={syncRunning || syncStartLoading}
            onChange={(event) =>
              onSyncRangeChange(event.target.value as SyncRange)
            }
            aria-label="同步范围"
          >
            <option value="all">全部（推荐）</option>
            <option value="3d">近 3 天（快速检查）</option>
            <option value="7d">近 7 天</option>
            <option value="recent">近期 30 天</option>
            <option value="6months">近 6 个月</option>
          </select>
          <span className="mt-1 block text-text-tertiary">
            默认完整同步；小范围同步更快，适合快速检查最近变化。
          </span>
        </label>
      </ActionPanel>
      <ActionPanel
        title="检查阻断复核"
        description="读取本地提交前阻断复核门禁，不调用真实提交。"
        status={
          readiness?.ready_to_submit ? "有候选" : readiness ? "仍阻断" : "待检查"
        }
        primaryLabel={readinessLoading ? "检查中..." : "读取复核"}
        disabled={readinessLoading}
        onPrimary={onLoadReadiness}
      />
      <ActionPanel
        title="回看检查结果"
        description="读取质量检查结果和阻断原因，方便继续迭代候选。"
        status={
          checkRowsCount > 0 ? `${checkRowsCount} 条记录` : "待读取"
        }
        primaryLabel={checkResultsLoading ? "加载中..." : "查看结果"}
        disabled={checkResultsLoading}
        onPrimary={onLoadChecks}
      />
    </div>
  );
}
