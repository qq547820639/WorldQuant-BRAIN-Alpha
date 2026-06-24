/** Job monitor with SSE — Terminal Precision v2.0 */
import { hasCredentials } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, UnifiedProgress } from "@/types";
import type { JobState } from "@/hooks/useJobState";
import { useJobMonitor } from "@/hooks/useJobMonitor";
import JobStatusCard from "@/components/JobMonitor/JobStatusCard";
import JobProgressBar from "@/components/JobMonitor/JobProgressBar";
import JobActions from "@/components/JobMonitor/JobActions";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  onNeedCredentials?: () => void;
  jobState?: JobState;
}

interface ViewProps {
  credentialSource: string;
  validationId: string | null;
  running: boolean;
  connected: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  status: JobStatus | null;
  events: string[];
  loading?: boolean;
  showCredentialWarning: boolean;
  reconnectAttempts?: number;
  onStart: () => void;
  onResume: () => void;
  onStop: () => void;
  onCredentialClick?: () => void;
  onRetry?: () => void;
  sseRetryExhausted?: boolean;
  sseRetryCountdown?: number;
  onSseExhaustedRetry?: () => void;
}

function JobMonitorView({
  credentialSource, validationId, running, connected, progress, error, status, events,
  loading, showCredentialWarning, reconnectAttempts = 0,
  onStart, onResume, onStop, onCredentialClick, onRetry,
  sseRetryExhausted = false, sseRetryCountdown = 0, onSseExhaustedRetry,
}: ViewProps) {
  const hasEvidence = Boolean(status?.job_id || validationId);

  return (
    <div className="panel mb-4">
      <JobStatusCard
        credentialSource={credentialSource}
        validationId={validationId}
        running={running}
        connected={connected}
        showCredentialWarning={showCredentialWarning}
        reconnectAttempts={reconnectAttempts}
      />
      <div className="panel-body-padded">
        <JobActions
          running={running}
          sseRetryExhausted={sseRetryExhausted}
          sseRetryCountdown={sseRetryCountdown}
          onStart={onStart}
          onResume={onResume}
          onStop={onStop}
          onCredentialClick={onCredentialClick}
          onSseExhaustedRetry={onSseExhaustedRetry}
          showCredentialWarning={showCredentialWarning}
        />

        <JobProgressBar
          running={running}
          loading={loading}
          progress={progress}
          error={error}
          status={status}
          hasEvidence={hasEvidence}
        />

        {events.length > 0 && (
          <div className="mt-3 panel" style={{ maxHeight: 160, overflow: "auto" }}>
            <div className="panel-body-padded p-2">
              {events.map((e, i) => (
                <div key={i} className="flex gap-2 text-sm py-1 border-b border-border-subtle last:border-0 text-text-secondary">
                  <span className="status-dot status-dot-active mt-1.5 shrink-0" />
                  <span className="min-w-0 break-words">{e}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function JobMonitor({ notify, credentials, onNeedCredentials, jobState: external }: Props) {
  if (external) {
    return (
      <JobMonitorView
        credentialSource={hasCredentials(credentials) ? "页面凭证" : "托管凭证"}
        validationId={external.jobId}
        running={external.running}
        connected={external.connected}
        progress={external.progress}
        error={external.error}
        status={external.status}
        events={external.events}
        showCredentialWarning={!hasCredentials(credentials)}
        onStart={() => external.startJob(false)}
        onResume={() => external.startJob(true)}
        onStop={external.stopJob}
        onCredentialClick={onNeedCredentials}
        onRetry={external.error ? () => external.startJob(false) : undefined}
        reconnectAttempts={external.reconnectAttempts}
      />
    );
  }

  const {
    jobId,
    status,
    running,
    connected,
    progress,
    error,
    events,
    loading,
    reconnectAttempts,
    sseRetryExhausted,
    sseRetryCountdown,
    startJob,
    stopJob,
    onSseExhaustedRetry,
  } = useJobMonitor({ notify, credentials });

  return (
    <JobMonitorView
      credentialSource={hasCredentials(credentials) ? "页面凭证" : "托管凭证"}
      validationId={status?.job_id || jobId}
      running={running}
      connected={connected}
      progress={progress}
      error={error}
      status={status}
      events={events}
      loading={loading}
      showCredentialWarning={!hasCredentials(credentials)}
      onStart={() => startJob(false)}
      onResume={() => startJob(true)}
      onStop={stopJob}
      onCredentialClick={onNeedCredentials}
      onRetry={error ? () => startJob(false) : undefined}
      reconnectAttempts={reconnectAttempts}
      sseRetryExhausted={sseRetryExhausted}
      sseRetryCountdown={sseRetryCountdown}
      onSseExhaustedRetry={onSseExhaustedRetry}
    />
  );
}
