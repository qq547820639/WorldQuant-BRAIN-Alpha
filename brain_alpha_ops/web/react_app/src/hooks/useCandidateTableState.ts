import { useCallback, useEffect, useMemo, useState } from "react";
import { useDebounce } from "@/hooks/useDebounce";
import { usePagination } from "@/hooks/usePagination";
import { useSorting } from "@/hooks/useSorting";
import {
  clampTargetPoolSize,
  sanitizeTextInput,
  MAX_FILTER_LENGTH,
  DEFAULT_TARGET_POOL_SIZE,
} from "@/components/CandidateTableUtils";

export type SortKey = "score" | "status" | "created";

export const PAGE_SIZE = 20;

interface UseCandidateTableStateOptions {
  totalItems: number;
  viewMode?: string;
}

export function useCandidateTableState(options: UseCandidateTableStateOptions) {
  const { totalItems, viewMode } = options;

  const [filterInput, setFilterInput] = useState("");
  const filter = useDebounce(filterInput, 300);

  const [showStarredOnly, setShowStarredOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [targetPoolSize, setTargetPoolSize] = useState(DEFAULT_TARGET_POOL_SIZE);

  const pagination = usePagination({
    totalItems,
    pageSize: PAGE_SIZE,
    initialPage: 1,
  });

  const sorting = useSorting<SortKey>({
    initialSortKey: "score",
    initialSortAsc: false,
  });

  const { currentPage, totalPages, startIndex: visibleStart, endIndex: visibleEnd, setCurrentPage } = pagination;
  const { sortKey, sortAsc, handleSort } = sorting;

  const selectedCount = useMemo(() => selectedIds.size, [selectedIds]);

  useEffect(() => {
    setCurrentPage(1);
  }, [filter, sortKey, sortAsc, viewMode, setCurrentPage]);

  const handleTargetPoolSizeChange = useCallback((value: string) => {
    setTargetPoolSize(clampTargetPoolSize(value));
  }, []);

  const handleFilterChange = useCallback((value: string) => {
    setFilterInput(sanitizeTextInput(value, MAX_FILTER_LENGTH));
  }, []);

  const handleToggleStarFilter = useCallback(() => {
    setShowStarredOnly((v) => !v);
  }, []);

  const handleToggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleToggleSelectAll = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  return {
    filterInput,
    filter,
    showStarredOnly,
    selectedIds,
    selectedCount,
    currentPage,
    sortKey,
    sortAsc,
    targetPoolSize,
    totalPages,
    visibleStart,
    visibleEnd,
    setCurrentPage,
    handleSort,
    handleTargetPoolSizeChange,
    handleFilterChange,
    handleToggleStarFilter,
    handleToggleSelect,
    handleToggleSelectAll,
    handleClearSelection,
    setFilterInput,
    setShowStarredOnly,
  };
}
