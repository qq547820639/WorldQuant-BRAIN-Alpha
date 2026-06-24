import { useState, useCallback, useMemo } from "react";

export type SortDirection = "asc" | "desc";

export interface UseSortingOptions<T extends string> {
  initialSortKey?: T;
  initialSortAsc?: boolean;
}

export interface UseSortingResult<T extends string> {
  sortKey: T;
  sortAsc: boolean;
  sortDirection: SortDirection;
  handleSort: (key: T) => void;
  setSortKey: (key: T) => void;
  setSortAsc: (asc: boolean) => void;
  toggleSortDirection: () => void;
  sortItems: <U extends Record<T, any>>(items: U[]) => U[];
}

export function useSorting<T extends string>(
  options: UseSortingOptions<T> = {}
): UseSortingResult<T> {
  const { initialSortKey, initialSortAsc = false } = options;

  const [sortKey, setSortKey] = useState<T>(initialSortKey as T);
  const [sortAsc, setSortAsc] = useState<boolean>(initialSortAsc);

  const sortDirection: SortDirection = sortAsc ? "asc" : "desc";

  const handleSort = useCallback(
    (key: T) => {
      if (sortKey === key) {
        setSortAsc((prev) => !prev);
      } else {
        setSortKey(key);
        setSortAsc(false);
      }
    },
    [sortKey]
  );

  const toggleSortDirection = useCallback(() => {
    setSortAsc((prev) => !prev);
  }, []);

  const sortItems = useCallback(
    <U extends Record<T, any>>(items: U[]): U[] => {
      if (!sortKey || items.length === 0) return items;

      return [...items].sort((a, b) => {
        const aVal = a[sortKey];
        const bVal = b[sortKey];

        if (aVal === bVal) return 0;

        let comparison = 0;
        if (typeof aVal === "number" && typeof bVal === "number") {
          comparison = aVal - bVal;
        } else if (
          typeof aVal === "object" &&
          aVal !== null &&
          typeof (aVal as any).getTime === "function" &&
          typeof bVal === "object" &&
          bVal !== null &&
          typeof (bVal as any).getTime === "function"
        ) {
          comparison = (aVal as any).getTime() - (bVal as any).getTime();
        } else {
          comparison = String(aVal).localeCompare(String(bVal));
        }

        return sortAsc ? comparison : -comparison;
      });
    },
    [sortKey, sortAsc]
  );

  return {
    sortKey,
    sortAsc,
    sortDirection,
    handleSort,
    setSortKey,
    setSortAsc,
    toggleSortDirection,
    sortItems,
  };
}
