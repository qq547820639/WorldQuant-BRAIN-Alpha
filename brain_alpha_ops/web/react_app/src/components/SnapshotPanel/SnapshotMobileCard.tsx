import type { SnapshotRow } from './utils';
import { displayKind, statusBadge } from './utils';

interface Props {
  row: SnapshotRow;
}

export default function SnapshotMobileCard({ row }: Props) {
  return (
    <article
      className="rounded-md p-4 text-sm"
      style={{
        border: '1px solid',
        borderColor: 'var(--color-border-medium-alpha)',
        backgroundColor: 'var(--color-surface-deep-alpha)',
      }}
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-text-tertiary">
            {displayKind(row.kind || 'snapshot')}
          </p>
          <p className="mt-1 break-words font-mono-value text-xs text-accent">
            {row.title || row.id || '-'}
          </p>
        </div>
        <span className={`badge shrink-0 text-xs ${statusBadge(row.status)}`}>
          {row.status || '-'}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-xs">
        <div>
          <dt className="text-text-tertiary">指标</dt>
          <dd className="mt-1 break-words font-mono-value text-text-primary">
            {row.metric || '-'}
          </dd>
        </div>
        <div>
          <dt className="text-text-tertiary">详情</dt>
          <dd className="mt-1 break-words text-text-secondary">{row.detail || '-'}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">时间</dt>
          <dd className="mt-1 break-words font-mono-value text-text-tertiary">
            {row.timestamp || '-'}
          </dd>
        </div>
      </dl>
    </article>
  );
}
