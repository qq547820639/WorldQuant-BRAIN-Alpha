import type { BlockerAction } from './constants';

export function BlockerActionButton({
  action,
  onNavigate,
}: {
  action: BlockerAction;
  onNavigate?: (view: string) => void;
}) {
  if (action.action_type === 'external_link' && action.url) {
    return (
      <a
        href={action.url}
        target="_blank"
        rel="noopener noreferrer"
        className="btn btn-secondary text-xs shrink-0 inline-flex items-center gap-1"
      >
        {action.label}
        <span aria-hidden="true">↗</span>
      </a>
    );
  }
  if (action.action_type === 'navigate' && onNavigate && action.view) {
    const view = action.view;
    return (
      <button
        type="button"
        className="btn btn-secondary text-xs shrink-0"
        onClick={() => onNavigate(view)}
      >
        {action.label}
      </button>
    );
  }
  return <span className="text-xs text-text-tertiary shrink-0">{action.label}</span>;
}

export function BlockerGuidanceList({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: { reason: string; count?: number; action: BlockerAction }[];
  onNavigate?: (view: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wide mb-2">
        {title}（{items.length}）
      </p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li
            key={`${title}_${index}`}
            className="flex flex-wrap items-start justify-between gap-2 rounded bg-[var(--color-layer-header-bg)] px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <span className="text-xs text-text-secondary">{item.reason}</span>
              {item.count !== undefined && (
                <span className="ml-1.5 text-xs text-text-tertiary">({item.count})</span>
              )}
              <p className="mt-0.5 text-xs text-text-tertiary">{item.action.description}</p>
            </div>
            <BlockerActionButton action={item.action} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </div>
  );
}
