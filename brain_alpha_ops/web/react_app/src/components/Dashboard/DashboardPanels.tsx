interface MemoryItem {
  name: string;
  count: number;
  success_rate?: number;
}

export function MemoryPanel({ title, items }: { title: string; items?: MemoryItem[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>{title}</span>
      </div>
      <div className="panel-body">
        {items?.slice(0, 5).map((item) => (
          <div
            key={item.name}
            className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0"
          >
            <span className="text-text-secondary">{item.name}</span>
            <span className="tabular text-text-tertiary">
              n={item.count} {item.success_rate?.toFixed(2)}
            </span>
          </div>
        )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无数据</div>}
      </div>
    </div>
  );
}

export function FailurePatternsPanel({ items }: { items?: { reason: string; count: number }[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>失败模式</span>
      </div>
      <div className="panel-body">
        {items?.slice(0, 5).map((fp) => (
          <div
            key={fp.reason}
            className="flex justify-between text-xs py-2 px-3.5 border-b border-border-subtle last:border-0"
          >
            <span className="text-negative/80">{fp.reason}</span>
            <span className="tabular text-text-tertiary">x{fp.count}</span>
          </div>
        )) || <div className="panel-body-padded text-xs text-text-tertiary">暂无失败记录</div>}
      </div>
    </div>
  );
}
