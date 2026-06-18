/** Operation log display component. */

import { type OperationLogEntry, logTone, logDotTone } from "./utils";

interface Props {
  logs: OperationLogEntry[];
}

export default function OperationLog({ logs }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>操作日志</span>
        <span className="badge badge-neutral">{logs.length}</span>
      </div>
      <div className="panel-body-padded max-h-60 overflow-y-auto">
        {logs.length === 0 ? (
          <p className="text-sm text-text-tertiary">暂无操作记录。</p>
        ) : (
          <ul className="space-y-1">
            {logs.map((entry, index) => (
              <li key={index} className="flex items-start gap-2 text-xs">
                <span className={logDotTone(entry.tone)} />
                <span className="font-mono text-text-tertiary">{entry.time}</span>
                <span className={logTone(entry.tone)}>{entry.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
