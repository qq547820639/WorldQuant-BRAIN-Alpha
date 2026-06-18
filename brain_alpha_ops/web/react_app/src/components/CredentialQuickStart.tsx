/**
 * CredentialQuickStart — credential entry and connection testing panel.
 * Shown when the App is not connected and no context cache is available.
 */

import { useState, useCallback } from "react";
import type { BrainCredentials } from "@/types";

interface Props {
  credentials: BrainCredentials | null;
  managedCredentialsAvailable: boolean;
  onCredentialsChange: (creds: BrainCredentials) => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onConnectionTested: (ok: boolean, err: string | null) => void;
}

export default function CredentialQuickStart({
  credentials,
  managedCredentialsAvailable,
  onCredentialsChange,
  notify,
  onConnectionTested,
}: Props) {
  const [username, setUsername] = useState(credentials?.username || "");
  const [password, setPassword] = useState(credentials?.password || "");
  const [token, setToken] = useState(credentials?.token || "");
  const [testResult, setTestResult] = useState<{ ok: boolean; environment?: string; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const handleTestConnection = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      onCredentialsChange({ username: username.trim(), password: password.trim(), token: token.trim() });
      const res = await fetch("/api/test_connection", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password: password.trim(), token: token.trim() }),
      });
      const json = await res.json();
      if (json.ok) {
        setTestResult({ ok: true, environment: json.environment || "unknown" });
        onConnectionTested(true, null);
        notify("success", `连接正常: ${json.environment || "unknown"}`);
      } else {
        setTestResult({ ok: false, error: json.error || "连接失败" });
        onConnectionTested(false, json.error || "连接失败");
      }
    } catch (err) {
      setTestResult({ ok: false, error: String(err) });
      onConnectionTested(false, String(err));
    } finally {
      setTesting(false);
    }
  }, [username, password, token, onCredentialsChange, onConnectionTested, notify]);

  return (
    <div className="panel" style={{ padding: "1.5rem" }}>
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
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={testing || !username.trim() || !password.trim()}
          onClick={handleTestConnection}
        >
          {testing ? "测试中..." : "测试连接"}
        </button>
        {testResult && (
          <p className={`text-sm ${testResult.ok ? "text-positive" : "text-negative"}`}>
            {testResult.ok ? `连接正常: ${testResult.environment}` : `连接失败: ${testResult.error}`}
          </p>
        )}
        {managedCredentialsAvailable && !testResult && (
          <p className="text-text-tertiary text-xs">检测到托管凭证，正在自动配置...</p>
        )}
      </div>
    </div>
  );
}
