/**
 * Column definitions for the CandidateTable desktop view.
 * Extracted from CandidateTable.tsx as a custom hook.
 *
 * Returns:
 * - columnCount: number of columns (10 or 11 depending on actions column, +1 for selection)
 * - renderHeader: renders the <thead> row with sortable column headers
 * - renderRow: renders a single <tbody> row for a given candidate
 */

import { useCallback } from "react";
import type { Candidate, CandidateCheckResult } from "@/types";
import { SortHeader } from "./CandidateTableSubComponents";
import { CandidateRow } from "./CandidateRow";
import { candidateIdentity } from "./CandidateTableUtils";

type SortKey = "score" | "status" | "created";

export interface UseCandidateColumnsParams {
  sortKey: SortKey;
  sortAsc: boolean;
  hasActions: boolean;
  checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean;
  showProductionControls: boolean;
  candidateWorkflowBusy: boolean;
  checkingAlphaId: string | null;
  onSort: (key: SortKey) => void;
  onScore?: (candidate: Candidate) => void;
  onSimulate?: (candidate: Candidate) => void;
  onCheck?: (candidate: Candidate) => void;
  // Batch selection
  allCurrentPageIds: string[];
  selectedIds: Set<string>;
  onToggleSelectAll: (ids: string[]) => void;
  onToggleSelect: (id: string) => void;
}

export function useCandidateColumns(params: UseCandidateColumnsParams) {
  // +1 for the selection checkbox column
  const columnCount = params.hasActions ? 11 : 10;

  const allSelected = params.allCurrentPageIds.length > 0
    && params.allCurrentPageIds.every((id) => params.selectedIds.has(id));

  const renderHeader = useCallback(() => (
    <tr>
      {/* Select-all checkbox header */}
      <th style={{ width: "2rem" }} aria-label="全选">
        <input
          type="checkbox"
          checked={allSelected}
          onChange={() => params.onToggleSelectAll(params.allCurrentPageIds)}
          aria-label="全选当前页候选"
        />
      </th>
      <th style={{ width: "2rem" }} aria-label="收藏">⭐</th>
      <th style={{ width: "8rem" }}>ID</th>
      <th style={{ width: "20rem" }}>表达式</th>
      <SortHeader column="score" label="评分" sortKey={params.sortKey} sortAsc={params.sortAsc} onSort={params.onSort} />
      <SortHeader column="status" label="状态" sortKey={params.sortKey} sortAsc={params.sortAsc} onSort={params.onSort} />
      <th style={{ width: "7rem" }}>质量</th>
      <th style={{ width: "14rem" }}>阻断原因</th>
      <th style={{ width: "18rem" }}>输出</th>
      <th style={{ width: "16rem" }}>官方证据</th>
      {params.hasActions && <th style={{ width: "10rem" }}>操作</th>}
    </tr>
  ), [allSelected, params.allCurrentPageIds, params.hasActions, params.onSort, params.onToggleSelectAll, params.sortAsc, params.sortKey]);

  const renderRow = useCallback((candidate: Candidate) => (
    <CandidateRow
      candidate={candidate}
      checkResults={params.checkResults}
      hasActions={params.hasActions}
      canShowRowActions={params.canShowRowActions}
      showProductionControls={params.showProductionControls}
      candidateWorkflowBusy={params.candidateWorkflowBusy}
      checkingAlphaId={params.checkingAlphaId}
      onScore={params.onScore}
      onSimulate={params.onSimulate}
      onCheck={params.onCheck}
      isSelected={params.selectedIds.has(candidateIdentity(candidate))}
      onToggleSelect={params.onToggleSelect}
    />
  ), [
    params.checkResults, params.hasActions, params.canShowRowActions,
    params.showProductionControls, params.candidateWorkflowBusy,
    params.checkingAlphaId, params.onScore, params.onSimulate, params.onCheck,
    params.selectedIds, params.onToggleSelect,
  ]);

  return { columnCount, renderHeader, renderRow };
}
