import { useCallback, useState } from 'react';
import type { OperationLogEntry } from './utils';
import { MAX_LOG_ROWS, formatClock } from './utils';

export function useOperationLog() {
  const [logs, setLogs] = useState<OperationLogEntry[]>([
    {
      time: formatClock(),
      tone: 'info',
      message: '官方操作已就绪。请选择要执行的操作。',
    },
  ]);

  const appendLog = useCallback((tone: OperationLogEntry['tone'], message: string) => {
    setLogs((previous) => [
      ...previous.slice(-(MAX_LOG_ROWS - 1)),
      { time: formatClock(), tone, message },
    ]);
  }, []);

  return {
    logs,
    setLogs,
    appendLog,
  };
}
