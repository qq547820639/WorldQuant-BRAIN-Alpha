import type { SnapshotRow } from './utils';
import { displayKind, statusBadge } from './utils';

interface Props {
  rows: SnapshotRow[];
  emptyMessage: string;
  title: string;
}

export default function SnapshotDesktopTable({ rows, emptyMessage, title }: Props) {
  return (
    <div className="hidden max-w-full overflow-auto md:block">
      <table className="data-table min-w-[820px] w-full text-sm" aria-label={`${title}表格`}>
        <thead>
          <tr
            className="text-left text-xs uppercase tracking-wider"
            style={{ borderBottom: '1px solid', borderColor: 'var(--color-border-medium)' }}
          >
            <th scope="col" className="p-3 text-text-tertiary">
              类型
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              名称
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              状态
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              指标
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              详情
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              时间
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="p-6 text-center text-text-tertiary">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={`${row.kind}_${row.id}_${index}`}
                className="transition-colors"
                style={{ borderBottom: '1px solid', borderColor: 'var(--color-border-faded)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor =
                    'var(--color-surface-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor = '';
                }}
              >
                <td className="p-3 text-xs text-text-tertiary">{displayKind(row.kind)}</td>
                <td className="p-3 font-mono-value text-xs text-accent">
                  {row.title || row.id || '-'}
                </td>
                <td className="p-3">
                  <span className={`badge text-xs ${statusBadge(row.status)}`}>
                    {row.status || '-'}
                  </span>
                </td>
                <td className="p-3 font-mono-value text-xs">{row.metric || '-'}</td>
                <td
                  className="p-3 text-xs text-text-secondary max-w-md truncate"
                  title={row.detail}
                >
                  {row.detail || '-'}
                </td>
                <td className="p-3 font-mono-value text-xs text-text-tertiary">
                  {row.timestamp || '-'}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
