/**
 * Helpers extracted from renderView.tsx (Phase 15 — Workstream B1).
 * Hosts LocalCacheSessionCard and ScoringPlaceholder so renderView.tsx
 * stays under the 350-line budget.
 */
import { safeDisplayErrorMessage, apiErrorMessage } from '@/helpers/errorExperience';
import { useApi } from '@/hooks/useApi';

export function ScoringPlaceholder({ onPickCandidate }: { onPickCandidate: () => void }) {
  return (
    <div
      className="animate-fade-in"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        gap: 16,
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: '50%',
          background: 'var(--color-scoring-placeholder-bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-scoring-placeholder-stroke)"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
          <path d="M9 12h6" />
          <path d="M9 16h4" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-text-primary">尚未选择候选</h2>
      <p className="text-sm text-text-secondary max-w-xs text-center" style={{ lineHeight: 1.6 }}>
        科学评分需要先选择一个候选 Alpha。
        <br />
        请在候选管理中选择要评分的 Alpha。
      </p>
      <button type="button" className="btn btn-primary" onClick={onPickCandidate}>
        前往候选管理
      </button>
    </div>
  );
}

export function LocalCacheSessionCard({
  notify,
  onLoggedOut,
}: {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  onLoggedOut: () => void;
}) {
  const logoutApi = useApi<{ ok: boolean; error?: string; error_code?: string }>();
  const logoutErrorMessage = logoutApi.error ? safeDisplayErrorMessage(logoutApi.error) : null;

  const logout = async () => {
    const result = await logoutApi.call('/api/logout', { method: 'POST' });
    if (!result?.ok) {
      notify('error', safeDisplayErrorMessage(apiErrorMessage(result, '退出本地会话失败')));
      return;
    }
    onLoggedOut();
    notify('success', '已退出本地会话并清空页面凭证');
  };

  return (
    <div
      className="panel mb-4"
      style={{
        borderColor: 'var(--color-deferred-border)',
        background: 'var(--color-deferred-bg)',
      }}
    >
      <div className="panel-header">
        <span>本地缓存会话</span>
        <span className="badge badge-positive">缓存可用</span>
      </div>
      <div
        className="panel-body-padded"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ minWidth: 240, flex: '1 1 320px' }}>
          <p className="text-sm font-medium text-warning mb-1">当前使用本地缓存，不需要重新登录</p>
          <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
            页面会继续读取本地 Alpha
            快照和官方上下文缓存；退出只清空当前页面会话与临时凭证，不删除本地缓存。
          </p>
          {logoutErrorMessage && (
            <p className="text-xs text-negative mt-2" role="alert">
              退出失败: {logoutErrorMessage}
            </p>
          )}
        </div>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={logout}
          disabled={logoutApi.loading}
        >
          {logoutApi.loading ? '退出中...' : '退出本地会话'}
        </button>
      </div>
    </div>
  );
}
