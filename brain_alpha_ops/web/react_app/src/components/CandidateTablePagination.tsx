/**
 * Pagination controls for CandidateTable (Phase 2.2).
 * Extracted from CandidateTable.tsx to reduce module size.
 */

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  visibleStart: number;
  visibleEnd: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export default function CandidateTablePagination({
  currentPage,
  totalPages,
  visibleStart,
  visibleEnd,
  totalItems,
  pageSize,
  onPageChange,
}: PaginationProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border-subtle px-3.5 py-3">
      <div className="text-sm text-text-tertiary" role="status" aria-live="polite">
        显示 {visibleStart}-{visibleEnd}，共 {totalItems} 条
      </div>
      {totalItems > pageSize && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage === 1}
            className="btn btn-ghost btn-sm"
          >
            上一页
          </button>
          <span className="text-sm text-text-secondary">
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
            disabled={currentPage === totalPages}
            className="btn btn-ghost btn-sm"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
