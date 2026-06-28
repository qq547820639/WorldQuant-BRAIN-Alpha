import { useState, useMemo, useEffect, useCallback } from 'react';

export interface UsePaginationOptions {
  totalItems: number;
  initialPage?: number;
  pageSize?: number;
}

export interface UsePaginationResult {
  currentPage: number;
  pageSize: number;
  totalPages: number;
  totalItems: number;
  startIndex: number;
  endIndex: number;
  goToPage: (page: number) => void;
  nextPage: () => void;
  prevPage: () => void;
  resetPage: () => void;
  setCurrentPage: (page: number | ((prev: number) => number)) => void;
}

export function usePagination(options: UsePaginationOptions): UsePaginationResult {
  const { totalItems, initialPage = 1, pageSize = 20 } = options;

  const [currentPage, setCurrentPage] = useState(initialPage);

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(totalItems / pageSize));
  }, [totalItems, pageSize]);

  const startIndex = useMemo(() => {
    return totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  }, [currentPage, pageSize, totalItems]);

  const endIndex = useMemo(() => {
    return Math.min(currentPage * pageSize, totalItems);
  }, [currentPage, pageSize, totalItems]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- totalPages 收缩时夹紧当前页（函数式更新已在范围内返回原值，React 会 bail-out；不把 currentPage 加入 deps 以避免循环）
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const goToPage = useCallback(
    (page: number) => {
      setCurrentPage(() => {
        const next = Math.max(1, Math.min(page, totalPages));
        return next;
      });
    },
    [totalPages]
  );

  const nextPage = useCallback(() => {
    setCurrentPage((prev) => Math.min(prev + 1, totalPages));
  }, [totalPages]);

  const prevPage = useCallback(() => {
    setCurrentPage((prev) => Math.max(prev - 1, 1));
  }, []);

  const resetPage = useCallback(() => {
    setCurrentPage(1);
  }, []);

  return {
    currentPage,
    pageSize,
    totalPages,
    totalItems,
    startIndex,
    endIndex,
    goToPage,
    nextPage,
    prevPage,
    resetPage,
    setCurrentPage,
  };
}
