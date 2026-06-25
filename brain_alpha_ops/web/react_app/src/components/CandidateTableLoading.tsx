import { CandidateTableToolbar } from './CandidateTableToolbar';
import Skeleton from './Skeleton';
import type { CandidateQueueView } from './CandidateTableUtils';

interface CandidateTableLoadingProps {
  title: string;
  viewMode: CandidateQueueView;
  targetPoolSize: number;
  showProductionControls: boolean;
  onTargetPoolSizeChange: (value: string) => void;
  onRetryLoad: () => void;
}

const loadingDetailPanel = {
  showProductionControls: false,
  taskState: 'idle' as const,
  taskProgress: null,
  taskError: null,
  taskStreamExhausted: false,
  onRetryTask: () => {},
  simState: 'idle' as const,
  simProgress: null,
  simError: null,
  onRetrySim: () => {},
  optimizationState: 'idle' as const,
  optimizationProgress: null,
  optimizationError: null,
  onRetryOptimization: () => {},
  checkState: 'idle' as const,
  checkProgress: null,
  checkError: null,
  onRetryCheck: () => {},
};

export default function CandidateTableLoading({
  title,
  viewMode,
  targetPoolSize,
  showProductionControls,
  onTargetPoolSizeChange,
  onRetryLoad,
}: CandidateTableLoadingProps) {
  return (
    <div className="animate-fade-in">
      <CandidateTableToolbar
        title={title}
        viewMode={viewMode}
        retainedCount={0}
        targetPoolSize={targetPoolSize}
        poolEligibleCount={0}
        rawQueueCount={0}
        sortedCount={0}
        candidateMeta={{ returned: 0, total: 0 }}
        filter=""
        remoteTruncated={false}
        showProductionControls={showProductionControls}
        candidateWorkflowBusy={false}
        taskState="idle"
        simState="idle"
        optimizationState="idle"
        onTargetPoolSizeChange={onTargetPoolSizeChange}
        onGenerateCandidates={() => {}}
        onStartValidationQueue={() => {}}
        onStartOptimization={() => {}}
        qualitySummary={{ retained: '0', promotable: 0, rework: 0, blocked: 0, outputMode: '-' }}
        lifecycleHistory={null}
        lifecycleError={null}
        lifecycleLoading={false}
        visibleLifecycleTraces={[]}
        detailPanel={loadingDetailPanel}
        loadError={null}
        apiLoading={true}
        onRetryLoad={onRetryLoad}
        onFilterChange={() => {}}
        showStarredOnly={false}
        onToggleStarFilter={() => {}}
        selectedIds={new Set()}
        selectedCount={0}
        onClearSelection={() => {}}
        onBatchScore={() => {}}
        onBatchCheck={() => {}}
        onBatchSimulate={() => {}}
        sortedCandidates={[]}
      />

      <div className="panel">
        <div
          className="hidden md:block overflow-auto"
          style={{ maxWidth: '100%', height: 'min(640px, 70vh)' }}
        >
          <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
            <thead>
              <tr className="bg-surface-2">
                <th
                  className="px-3 py-2 text-left text-xs font-medium text-text-secondary"
                  style={{ width: '7rem' }}
                >
                  加载中...
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-text-secondary">ID</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-text-secondary">
                  表达式
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-text-secondary">
                  家族
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-text-secondary">
                  状态
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-text-secondary">
                  评分
                </th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 8 }).map((_, index) => (
                <tr key={`skeleton-${index}`} className="border-b border-border-subtle">
                  <td className="px-3 py-3" colSpan={6}>
                    <Skeleton variant="table-row" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel-body md:hidden">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={`skeleton-mobile-${index}`} className="panel" style={{ padding: '12px' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Skeleton variant="avatar" className="w-8 h-8 rounded-full" />
                    <Skeleton variant="text" className="w-24 h-3" />
                  </div>
                  <Skeleton variant="text" className="w-16 h-5 rounded-full" />
                </div>
                <div
                  style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}
                >
                  <Skeleton variant="text" className="w-full h-3" />
                  <Skeleton variant="text" className="w-full h-3" />
                  <Skeleton variant="text" className="w-full h-3 col-span-2" />
                  <Skeleton variant="text" className="w-full h-3 col-span-2" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
