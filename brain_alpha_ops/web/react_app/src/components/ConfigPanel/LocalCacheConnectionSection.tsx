import type { ReactNode } from "react";

interface LocalCacheConnectionSectionProps {
  temporaryConnectionOpen: boolean;
  logoutLoading: boolean;
  logoutError: string | null;
  onOpenTemporaryConnection: () => void;
  onCloseTemporaryConnection: () => void;
  onLogout: () => void;
  children?: ReactNode;
}

export default function LocalCacheConnectionSection({
  temporaryConnectionOpen,
  logoutLoading,
  logoutError,
  onOpenTemporaryConnection,
  onCloseTemporaryConnection,
  onLogout,
  children,
}: LocalCacheConnectionSectionProps) {
  return (
    <fieldset className="panel min-w-0 border-info/30 bg-info/5">
      <legend className="px-1 text-base font-semibold text-text-primary">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-info" aria-hidden="true" />
          本地缓存会话
        </span>
      </legend>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
        当前使用本地缓存运行。无需登录即可浏览历史候选、查看评分结果和调整配置。
        需要官方同步、官方回测或提交前复核时，再临时连接官方服务。
      </p>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onLogout}
          className="btn btn-secondary btn-sm"
          disabled={logoutLoading}
          aria-describedby="cache-logout-desc"
        >
          {logoutLoading ? "退出中..." : "退出本地会话"}
        </button>
        {!temporaryConnectionOpen ? (
          <button
            type="button"
            onClick={onOpenTemporaryConnection}
            className="btn btn-primary btn-sm"
            aria-describedby="temp-connect-desc"
          >
            临时连接官方服务
          </button>
        ) : (
          <button
            type="button"
            onClick={onCloseTemporaryConnection}
            className="btn btn-secondary btn-sm"
          >
            收起凭据输入
          </button>
        )}
      </div>

      <p id="cache-logout-desc" className="mt-2 text-xs text-text-tertiary">
        退出本地会话会清空当前页面的所有缓存状态和历史记录。
      </p>

      {logoutError && (
        <p role="alert" className="mt-3 text-xs text-negative">
          {logoutError}
        </p>
      )}

      {temporaryConnectionOpen && (
        <div className="mt-5 pt-4 border-t border-border-subtle">
          <p id="temp-connect-desc" className="mb-3 text-sm text-text-secondary">
            以下凭据仅用于本次临时连接，不会保存到配置文件或本地存储。
            关闭页面或退出会话后立即失效。
          </p>
          {children}
        </div>
      )}
    </fieldset>
  );
}
