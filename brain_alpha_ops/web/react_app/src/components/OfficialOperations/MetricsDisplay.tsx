/** Metrics and stats display for official operations. */

import { OperationMetric, OverviewCard } from "./OfficialOperations/index";
import type { JobStatus, OfficialContextCache, CloudAlphaCache } from "@/types";
import {
  syncContextStatus,
  contextCacheComplete,
  syncDataOverview,
  syncStatusForDisplay,
} from "./utils";

interface Props {
  syncRunning: boolean;
  syncStatus: JobStatus | null;
  officialContextCache?: OfficialContextCache;
  cloudAlphaCache?: CloudAlphaCache;
  readinessEligibleCount?: number;
  readinessReadyToSubmit?: boolean;
  checkRowsCount: number;
}

export default function MetricsDisplay({
  syncRunning,
  syncStatus,
  officialContextCache,
  cloudAlphaCache,
  readinessEligibleCount,
  readinessReadyToSubmit,
  checkRowsCount,
}: Props) {
  const displaySyncStatus = syncStatusForDisplay(syncStatus, officialContextCache);
  const displaySyncState = { successful: false };
  const syncOverview = syncDataOverview(displaySyncStatus, syncRunning, cloudAlphaCache);

  return (
    <>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:min-w-[420px]">
        <OperationMetric
          label="官方上下文"
          value={syncContextStatus(displaySyncStatus)}
          tone={
            syncRunning
              ? "warning"
              : contextCacheComplete(displaySyncStatus?.official_context_cache) ||
                  displaySyncState.successful
                ? "success"
                : "neutral"
          }
        />
        <OperationMetric
          label="复核候选"
          value={String(readinessEligibleCount ?? "-")}
          tone={readinessReadyToSubmit ? "success" : "warning"}
        />
        <OperationMetric
          label="检查记录"
          value={String(checkRowsCount || "-")}
        />
        <OperationMetric label="真实提交" value="关闭" tone="success" />
      </div>

      <section
        className="grid gap-3 md:grid-cols-3"
        aria-label="官方同步数据总览"
      >
        <OverviewCard
          label="同步状态"
          value={syncOverview.statusValue}
          detail={syncOverview.statusDetail}
          tone={syncOverview.statusTone}
        />
        <OverviewCard
          label="更新时间"
          value={syncOverview.updatedAtValue}
          detail={syncOverview.updatedAtDetail}
        />
        <OverviewCard
          label="分页拉取"
          value={syncOverview.totalValue}
          detail={syncOverview.totalDetail}
          tone={syncOverview.totalTone}
        />
      </section>

      {syncRunning && syncOverview.hasLiveMetrics && (
        <section
          className="grid gap-3 md:grid-cols-2"
          aria-label="同步实时指标"
        >
          <OverviewCard
            label={syncOverview.etaLabel}
            value={syncOverview.etaValue}
            detail={syncOverview.etaDetail}
            tone="warning"
          />
          <OverviewCard
            label={syncOverview.rateLabel}
            value={syncOverview.rateValue}
            detail={syncOverview.rateDetail}
          />
        </section>
      )}
    </>
  );
}
