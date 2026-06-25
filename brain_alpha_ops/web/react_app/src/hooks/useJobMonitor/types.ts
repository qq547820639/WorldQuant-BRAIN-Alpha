import type { BrainCredentials, JobStatus, UnifiedProgress } from '@/types';

export type NotifyFn = (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;

export interface UseJobMonitorOptions {
  notify: NotifyFn;
  credentials?: BrainCredentials;
}

export interface UseJobMonitorResult {
  jobId: string | null;
  status: JobStatus | null;
  running: boolean;
  connected: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  events: string[];
  loading: boolean;
  reconnectAttempts: number;
  sseRetryExhausted: boolean;
  sseRetryCountdown: number;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
  onSseExhaustedRetry: () => void;
}
