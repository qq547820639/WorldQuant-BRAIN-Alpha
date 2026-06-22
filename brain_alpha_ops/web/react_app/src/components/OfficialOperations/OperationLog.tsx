/** Operation log display component. */

import { type OperationLogEntry, logTone, logDotTone } from "./utils";

interface Props {
  logs: OperationLogEntry[];
  onClear?: () => void;
}

export default function OperationLog({ logs, onClear }: Props) {
  return (
    <details className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-3">
      <summary className="cursor-pointer text-sm font-semibold text-text-primary">
        操作日志（{logs.length} 条）
      </summary>
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-xs text-text-tertiary">系统动作会写成可读事件，不展示命令或路径。</p>
        {onClear && (
          <button type="button" className="btn btn-secondary text-sm" onClick={onClear}>
            清空
          </button>
        )}
      </div>
      <div className="mt-3 max-h-40 min-w-0 overflow-y-auto rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3 text-sm leading-6 text-text-secondary" role="status" aria-live="polite" aria-label="官方操作时间线">
        {logs.length ? logs.map((entry, index) => (
          <div key={`${entry.time}_${index}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-l border-border-subtle pb-3 pl-3 last:pb-0">
            <span className={`mt-1 ${logDotTone(entry.tone)}`} aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-xs text-text-tertiary">{entry.time}</p>
              <p className={`break-words ${logTone(entry.tone)}`}>{entry.message}</p>
            </div>
          </div>
        )) : (
          <div className="text-text-tertiary">事件已清空。</div>
        )}
      </div>
    </details>
  );
}
