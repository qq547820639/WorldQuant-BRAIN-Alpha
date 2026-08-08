/** Individual job status display card. */

import { memo } from 'react';
import { shortValidationId } from '@/helpers/runPayload/run';

interface Props {
  credentialSource: string;
  validationId: string | null;
  running: boolean;
  connected: boolean;
  showCredentialWarning: boolean;
  reconnectAttempts?: number;
}

export default memo(function JobStatusCard({
  credentialSource,
  validationId,
  running,
  connected,
  showCredentialWarning,
  reconnectAttempts = 0,
}: Props) {
  return (
    <>
      <div className="panel-header">
        <span>非提交生产验证</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="badge badge-neutral">非提交</span>
          <span className="badge badge-neutral">{credentialSource}</span>
          <span
            className={`status-dot ${connected ? 'status-dot-active' : running ? 'status-dot-error' : ''}`}
          />
          <span className={`badge ${running ? 'badge-positive' : 'badge-neutral'}`}>
            {running ? '运行中' : '空闲'}
          </span>
        </div>
      </div>
      <div className="panel-body-padded">
        {running && !connected && (
          <div
            className="mb-3"
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid',
              borderColor: 'var(--color-deferred-border)',
              background: 'var(--color-deferred-bg)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 13,
              color: 'var(--color-deferred-icon)',
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
              style={{ flexShrink: 0 }}
            >
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>
              实时连接已断开
              {reconnectAttempts > 0 ? `（第 ${reconnectAttempts} 次重连中…）` : '，正在重连…'}
              后台任务继续运行。
            </span>
          </div>
        )}
        <p className="text-sm text-text-secondary mb-4">
          生产配置下的非提交验证流程，系统会强制关闭自动提交并保留可回看的进度证据。
        </p>
        {validationId && (
          <div className="flex items-center gap-2 mb-4 text-xs">
            <span className="text-text-tertiary">验证编号</span>
            <span className="font-mono-value px-2 py-0.5 rounded-sm bg-surface-2 text-text-secondary">
              {shortValidationId(validationId)}
            </span>
          </div>
        )}
        {showCredentialWarning && (
          <div className="mb-4 px-3 py-2 text-sm rounded-md bg-warning-subtle text-warning">
            页面凭证为空。可以先填写并测试 BRAIN 账户，也可以继续使用维护者配置的托管凭证运行。
          </div>
        )}
      </div>
    </>
  );
});
