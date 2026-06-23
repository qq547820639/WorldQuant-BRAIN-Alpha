/** Start/stop/retry buttons and SSE banners. */

interface Props {
  running: boolean;
  sseRetryExhausted?: boolean;
  sseRetryCountdown?: number;
  onStart: () => void;
  onResume: () => void;
  onStop: () => void;
  onCredentialClick?: () => void;
  onSseExhaustedRetry?: () => void;
  showCredentialWarning: boolean;
}

function PlayIcon() {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M8 5v14l11-7L8 5Z" />
    </svg>
  );
}

function ResumeIcon() {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 3v6h6" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

export default function JobActions({
  running,
  sseRetryExhausted = false,
  sseRetryCountdown = 0,
  onStart,
  onResume,
  onStop,
  onCredentialClick,
  onSseExhaustedRetry,
  showCredentialWarning,
}: Props) {
  return (
    <>
      {sseRetryCountdown > 0 && (
        <div
          className="mb-3"
          style={{
            padding: "8px 12px",
            borderRadius: 6,
            border: "1px solid",
            borderColor: "var(--color-info-border)",
            background: "var(--color-info-bg-faint)",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            color: "var(--color-info-text)",
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            style={{ flexShrink: 0, animation: "spin 2s linear infinite" }}
          >
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </svg>
          <span>同步通道中断，{sseRetryCountdown}秒后自动重试…</span>
        </div>
      )}

      {sseRetryExhausted && (
        <div
          className="mb-3"
          style={{
            padding: "10px 12px",
            borderRadius: 6,
            border: "1px solid",
            borderColor: "var(--color-error-border)",
            background: "var(--color-error-bg)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            fontSize: 13,
          }}
        >
          <p className="text-sm text-negative font-medium">
            同步通道已中断，自动重试均已失败
          </p>
          <p className="text-xs text-text-secondary">
            建议检查网络连接后手动重试，或等待后台任务自行恢复。
          </p>
          {onSseExhaustedRetry && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={onSseExhaustedRetry}
              style={{ alignSelf: "flex-start" }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                style={{ marginRight: 6 }}
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
              </svg>
              手动重试
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {onCredentialClick && showCredentialWarning && (
          <button
            type="button"
            onClick={onCredentialClick}
            disabled={running}
            className="btn btn-secondary btn-sm"
          >
            填写凭证
          </button>
        )}
        <button
          onClick={onStart}
          disabled={running}
          className="btn btn-primary btn-sm"
        >
          <PlayIcon /> 运行非提交验证
        </button>
        <button
          onClick={onResume}
          disabled={running}
          className="btn btn-secondary btn-sm"
        >
          <ResumeIcon /> 继续上次验证
        </button>
        <button
          onClick={onStop}
          disabled={!running}
          className="btn btn-secondary btn-sm"
        >
          <StopIcon /> 停止
        </button>
      </div>
    </>
  );
}
