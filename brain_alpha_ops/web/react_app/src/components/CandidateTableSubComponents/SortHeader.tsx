import { memo } from 'react';
import type { SortKey } from './types';

export const SortHeader = memo(function SortHeader({
  column,
  label,
  sortKey,
  sortAsc,
  onSort,
}: {
  column: SortKey;
  label: string;
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (column: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th
      scope="col"
      className={active ? 'is-sorted' : 'is-sortable'}
      style={{ width: '7rem' }}
      aria-sort={active ? (sortAsc ? 'ascending' : 'descending') : 'none'}
    >
      <button type="button" className="flex items-center gap-1" onClick={() => onSort(column)}>
        {label}
        <span className="text-accent" aria-hidden="true">
          {active ? (sortAsc ? '\u2191' : '\u2193') : ''}
        </span>
      </button>
    </th>
  );
});
