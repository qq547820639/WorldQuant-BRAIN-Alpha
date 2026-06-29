/**
 * CredentialQuickStart — credential entry and connection testing panel.
 * Shown when the App is not connected and no context cache is available.
 */

import { useState, useCallback, useEffect, useRef, memo } from 'react';
import type { BrainCredentials } from '@/types';
import {
  getConnectionErrorGuide,
  type ConnectionErrorGuideEntry,
} from '@/helpers/connectionErrorGuide';
import { useApi } from '@/hooks/useApi';

interface Props {
  credentials: BrainCredentials | null;
  managedCredentialsAvailable: boolean;
  onCredentialsChange: (creds: BrainCredentials) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  onConnectionTested: (ok: boolean, err: string | null) => void;
}

export default memo(function CredentialQuickStart({
  credentials,
  managedCredentialsAvailable,
  onCredentialsChange,
  notify,
  onConnectionTested,
}: Props) {
  const [username, setUsername] = useState(credentials?.username || '');
  const [password, setPassword] = useState(credentials?.password || '');
  const [token, setToken] = useState(credentials?.token || '');
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    environment?: string;
    error?: string;
    error_code?: string;
    // U-002: backend conveys Retry-After via JSON `retry_after` (seconds).
    retry_after?: number;
  } | null>(null);
  const [testing, setTesting] = useState(false);
  const [managedTesting, setManagedTesting] = useState(false);

  // P1-1: useApi hook for CSRF-protected API calls
  const { call } = useApi<{
    ok: boolean;
    environment?: string;
    error?: string;
    error_code?: string;
    // U-002: backend conveys Retry-After via JSON `retry_after` (seconds).
    retry_after?: number;
  }>();

  // P1-2: countdown timer for delayed retry actions
  const [countdown, setCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (countdown <= 0) {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
      return;
    }
    countdownRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) return 0;
        return c - 1;
      });
    }, 1000);
    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [countdown]);

  // P1-2: resolve error guide from the last failed connection test
  const errorGuide: ConnectionErrorGuideEntry | undefined = getConnectionErrorGuide(
    testResult && !testResult.ok ? testResult.error_code : undefined
  );

  const handleTestConnection = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      onCredentialsChange({ username: username.trim(), password: '', token: token.trim() });
      const json = await call('/api/test_connection', {
        method: 'POST',
        body: JSON.stringify({
          username: username.trim(),
          password: password.trim(),
          token: token.trim(),
        }),
      });
      if (!json) {
        setTestResult({ ok: false, error: '网络错误，请检查连接后重试' });
        onConnectionTested(false, '网络错误');
      } else if (json.ok) {
        setTestResult({ ok: true, environment: json.environment || 'unknown' });
        onConnectionTested(true, null);
        notify('success', `连接正常: ${json.environment || 'unknown'}`);
      } else {
        setTestResult({
          ok: false,
          error: json.error || '连接失败',
          error_code: json.error_code || undefined,
          // U-002: capture backend-provided Retry-After (seconds) for countdown.
          retry_after: typeof json.retry_after === 'number' ? json.retry_after : undefined,
        });
        onConnectionTested(false, json.error || '连接失败');
      }
    } catch (err) {
      setTestResult({ ok: false, error: String(err) });
      onConnectionTested(false, String(err));
    } finally {
      setTesting(false);
    }
  }, [username, password, token, onCredentialsChange, onConnectionTested, notify, call]);

  // P1-1: managed credentials one-click test — sends no credentials body
  const handleManagedTestConnection = useCallback(async () => {
    setManagedTesting(true);
    setTestResult(null);
    try {
      const json = await call('/api/test_connection', { method: 'POST' });
      if (!json) {
        setTestResult({ ok: false, error: '网络错误，请检查连接后重试' });
        onConnectionTested(false, '网络错误');
      } else if (json.ok) {
        setTestResult({ ok: true, environment: json.environment || 'unknown' });
        onConnectionTested(true, null);
        notify('success', `托管凭证连接正常: ${json.environment || 'unknown'}`);
      } else {
        setTestResult({
          ok: false,
          error: json.error || '托管凭证连接失败',
          error_code: json.error_code || undefined,
          // U-002: capture backend-provided Retry-After (seconds) for countdown.
          retry_after: typeof json.retry_after === 'number' ? json.retry_after : undefined,
        });
        onConnectionTested(false, json.error || '托管凭证连接失败');
      }
    } catch (err) {
      setTestResult({ ok: false, error: String(err) });
      onConnectionTested(false, String(err));
    } finally {
      setManagedTesting(false);
    }
  }, [onConnectionTested, notify, call]);

  // P1-2: retry with countdown for delayed-recovery error codes
  // U-002: prefer backend-provided Retry-After (`retry_after`) over the
  // static `errorGuide.waitSeconds` so the countdown matches the real
  // cooldown window the server asked us to wait.
  const handleGuidedRetry = useCallback(() => {
    if (!errorGuide) return;
    const retryAfter = testResult?.retry_after;
    const waitSeconds =
      typeof retryAfter === 'number' && retryAfter > 0
        ? retryAfter
        : errorGuide.waitSeconds || 0;
    if (waitSeconds > 0) {
      setCountdown(waitSeconds);
      const timer = setTimeout(() => {
        handleTestConnection();
      }, waitSeconds * 1000);
      return () => clearTimeout(timer);
    }
    handleTestConnection();
  }, [errorGuide, testResult, handleTestConnection]);

  return (
    <div className="panel" style={{ padding: '1.5rem' }}>
      <h3 className="text-lg font-semibold mb-4">凭证与连接</h3>
      <div className="flex flex-col gap-3" style={{ maxWidth: 400 }}>
        <label className="flex flex-col gap-1">
          <span className="text-sm text-text-secondary">账户邮箱</span>
          <input
            type="text"
            className="form-input"
            aria-label="账户邮箱"
            autoComplete="off"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="your@email.com"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm text-text-secondary">密码</span>
          <input
            type="password"
            className="form-input"
            aria-label="密码"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm text-text-secondary">Token（可选）</span>
          <input
            type="text"
            className="form-input"
            aria-label="Token（可选）"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Bearer token (可选)"
          />
        </label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={testing || !username.trim() || !password.trim()}
            onClick={handleTestConnection}
          >
            {testing ? '测试中...' : '测试连接'}
          </button>
          {/* P1-1: managed credentials one-click button */}
          {managedCredentialsAvailable && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={managedTesting}
              onClick={handleManagedTestConnection}
            >
              {managedTesting ? '托管测试中...' : '使用托管凭证'}
            </button>
          )}
        </div>
        {testResult && (
          <p className={`text-sm ${testResult.ok ? 'text-positive' : 'text-negative'}`}>
            {testResult.ok
              ? `连接正常: ${testResult.environment}`
              : `连接失败: ${testResult.error}`}
          </p>
        )}
        {/* P1-2: connection error recovery guide */}
        {errorGuide && (
          <div
            style={{
              padding: '10px 12px',
              borderRadius: 6,
              background: 'var(--color-error-bg)',
              border: '1px solid var(--color-error-guide-border)',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <p className="text-sm text-negative font-medium">{errorGuide.message}</p>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={countdown > 0}
              onClick={handleGuidedRetry}
              style={{ alignSelf: 'flex-start' }}
            >
              {countdown > 0 ? `${errorGuide.actionLabel} (${countdown}s)` : errorGuide.actionLabel}
            </button>
          </div>
        )}
        {managedCredentialsAvailable && !testResult && (
          <p className="text-text-tertiary text-xs">检测到托管凭证，正在自动配置...</p>
        )}

        {/* P0-2: registration guidance for users without a BRAIN account */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '10px 12px',
            borderRadius: 6,
            background: 'var(--color-info-bg-soft)',
            border: '1px solid var(--color-info-border-soft)',
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--color-info-text)"
            strokeWidth="2"
            strokeLinecap="round"
            style={{ flexShrink: 0, marginTop: 1 }}
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <p className="text-xs" style={{ color: 'var(--color-info-text-soft)', lineHeight: 1.5 }}>
            还没有 BRAIN 账户？前往{' '}
            <a
              href="https://platform.worldquantbrain.com"
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontWeight: 600, textDecoration: 'underline', textUnderlineOffset: 2 }}
            >
              WorldQuant BRAIN 平台注册
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                style={{ display: 'inline', marginLeft: 2, verticalAlign: 'baseline' }}
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </p>
        </div>
      </div>
    </div>
  );
});
