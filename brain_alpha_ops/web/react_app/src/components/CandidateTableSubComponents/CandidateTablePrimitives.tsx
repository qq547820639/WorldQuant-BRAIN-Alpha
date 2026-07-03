/** Small UI primitives for CandidateTable: sort header, quality summary item,
 *  empty-state placeholder, and the shared SortKey type.
 *
 *  Merges the previously separate SortHeader.tsx, QualitySummaryItem.tsx,
 *  EmptyState.tsx, and types.ts into a single module. All component
 *  implementations are preserved verbatim; only the module boundary changed. */

import { memo } from 'react';

export type SortKey = 'score' | 'status' | 'created';

// ──────────────────────────────────────────────────────────────────────────
// SortHeader — sortable column header for the candidate table
// ──────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────
// QualitySummaryItem — KPI card for the quality summary bar
// ──────────────────────────────────────────────────────────────────────────

export const QualitySummaryItem = memo(function QualitySummaryItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className="font-mono-value text-base font-medium text-text-primary">{value}</p>
    </div>
  );
});

// ──────────────────────────────────────────────────────────────────────────
// EmptyState — placeholder shown when the candidate table has no rows
// ──────────────────────────────────────────────────────────────────────────

export const EmptyState = memo(function EmptyState({
  filter,
  showProductionControls,
}: {
  filter: boolean;
  showProductionControls: boolean;
}) {
  if (filter) {
    return (
      <div style={{ padding: '2rem 0', color: 'var(--color-text-muted)', fontSize: 13 }}>
        <p>没有匹配的候选</p>
        <p style={{ marginTop: 4, fontSize: 12 }}>尝试调整筛选条件，或清除筛选查看全部候选。</p>
      </div>
    );
  }

  if (showProductionControls) {
    return (
      <div
        style={{
          padding: '1.5rem 0',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: '50%',
            background: 'var(--color-search-ring-bg)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--color-icon-warning)"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>
        <div>
          <p style={{ color: 'var(--color-text-light)', fontSize: 14, fontWeight: 500 }}>
            暂无候选记录
          </p>
          <p
            style={{
              color: 'var(--color-text-muted)',
              fontSize: 12,
              marginTop: 4,
              lineHeight: 1.5,
              maxWidth: 320,
            }}
          >
            候选 Alpha
            通过顶部「自动推进候选池」启动生产搜索、预筛与本地排序；官方验证队列和质量检查单独推进。
            全流程保持非提交边界，提交仍需人工确认。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '1.5rem 0',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <p style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>暂无候选记录</p>
      <p
        style={{
          color: 'var(--color-text-extra-dim)',
          fontSize: 12,
          lineHeight: 1.5,
          maxWidth: 280,
        }}
      >
        请先运行非提交验证产生候选，或从候选管理页面选择一个候选进入评分。
      </p>
    </div>
  );
});
