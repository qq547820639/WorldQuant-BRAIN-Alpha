/**
 * NotFound — 404 页面未找到
 * 当访问未匹配的路由时显示，提供返回首页的链接。
 */
import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center min-h-[60vh]"
      role="alert"
      aria-live="polite"
    >
      <div className="mb-6" style={{ color: 'var(--color-text-dim)' }} aria-hidden="true">
        <svg
          width="72"
          height="72"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          focusable="false"
        >
          <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z" />
          <line x1="3" y1="7" x2="21" y2="7" />
          <line x1="7" y1="3" x2="7" y2="5" />
          <line x1="17" y1="3" x2="17" y2="5" />
          <line x1="9" y1="14" x2="15" y2="14" />
        </svg>
      </div>
      <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--color-text-bright)' }}>
        404
      </h1>
      <h2 className="text-lg font-semibold mb-2" style={{ color: 'var(--color-text-bright)' }}>
        页面未找到
      </h2>
      <p className="text-sm mb-6 max-w-sm text-text-tertiary">
        您访问的页面不存在或已被移除，请检查地址或返回首页继续操作。
      </p>
      <Link
        to="/"
        className="btn btn-primary"
        style={{ padding: '8px 20px', fontSize: 13, fontWeight: 600 }}
      >
        返回首页
      </Link>
    </div>
  );
}
