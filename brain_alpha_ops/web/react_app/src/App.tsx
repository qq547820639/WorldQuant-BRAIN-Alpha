/**
 * BRAIN Alpha Ops — UI Design System v3.0
 * 应用外壳：侧边栏(阶段组) + 顶栏(连接+阶段) + PhaseShell + 移动端Tab
 * 渐进式 4 阶段导航，基于新架构重新实现
 */

import { Suspense } from 'react';
import { useAppStateContext, AppStateProvider } from '@/hooks/useAppState/useAppState';
import ToastContainer from '@/components/ToastContainer';
import Sidebar from '@/components/Sidebar';
import ErrorBoundary from '@/components/ErrorBoundary';
import { FlowGuide } from './components/FlowGuide';
import PhaseShell from '@/components/PhaseShell';
import MobileTabBar from '@/components/MobileTabBar';
import KeyboardShortcutsHelp from '@/components/KeyboardShortcutsHelp';
import { ActiveViewRenderer } from '@/components/views/renderViewFromContext';
import { PageLoader } from '@/components/views/renderView';
import { topbarConnectionStatus, fmtEta } from '@/components/views/helpers';
import { ThemeProvider, useThemeContext } from '@/components/ThemeProvider';
import Tooltip from '@/components/Tooltip';
import { safeDisplayErrorMessage } from '@/helpers/errorExperience';

const VIEW_LABELS: Record<string, string> = {
  dashboard: '运行总览',
  official_operations: '官方操作',
  candidates: '候选管理',
  official_backtests: '回测监控',
  scoring: '科学评分',
  quality_check: '质量门禁',
  submission_confirm: '阻断复核',
  checkpoint_status: '续跑记录',
  robustness: '稳健性证据',
  config: '系统配置',
  cloud: '云端快照',
};

export default function App() {
  return (
    <ThemeProvider>
      <AppStateProvider>
        <AppContent />
      </AppStateProvider>
    </ThemeProvider>
  );
}

function AppContent() {
  const { theme, toggleTheme } = useThemeContext();
  const {
    activeView,
    sidebarOpen,
    shortcutsHelpOpen,
    toasts,
    dismissToast,
    jobState,
    connected,
    contextFresh,
    phaseApiStatus,
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    sidebarBadges,
    setActiveView,
    setSidebarOpen,
    setShortcutsHelpOpen,
    handleTogglePhase,
    handleNavigate,
    handleMobileNavigate,
  } = useAppStateContext();

  const viewLabel = VIEW_LABELS[activeView] || activeView;
  const currentPhaseObj = phaseState.phases[currentPhase];
  const topbarStatus = topbarConnectionStatus({
    connected,
    contextFresh,
    phaseStatus: phaseApiStatus,
  });
  const phaseShellStatusLabel =
    phaseApiStatus === 'loading'
      ? '读取中'
      : phaseApiStatus === 'error'
        ? '读取失败'
        : currentPhaseObj?.status === 'complete'
          ? '已完成'
          : currentPhaseObj?.status === 'active'
            ? '进行中'
            : currentPhaseObj?.status === 'blocked'
              ? '已阻断'
              : '待解锁';
  const phaseShellStatusTone =
    phaseApiStatus === 'loading' || phaseApiStatus === 'error'
      ? 'active'
      : currentPhaseObj?.status === 'complete'
        ? 'complete'
        : currentPhaseObj?.status === 'blocked'
          ? 'blocked'
          : currentPhaseObj?.status === 'active'
            ? 'active'
            : 'pending';

  return (
    <ErrorBoundary>
      <div className="app-shell">
          <header className="app-topbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm lg:hidden"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                aria-label="切换导航菜单"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  aria-hidden="true"
                  focusable="false"
                >
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <line x1="3" y1="12" x2="21" y2="12" />
                  <line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              </button>
              <span className={`topbar-connection ${topbarStatus.tone}`} title={topbarStatus.title}>
                <span className={`status-dot ${topbarStatus.dotClass}`} />
                {topbarStatus.label}
              </span>
              <span style={{ color: 'var(--color-text-dim)', fontSize: 12 }}>·</span>
              <span className="topbar-phase">
                Phase {steps.findIndex((s) => s.status === 'active') + 1 || '?'} ·{' '}
                <strong>{currentPhaseObj?.label || viewLabel}</strong>
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {jobState.running && (
                <button
                  type="button"
                  className="badge badge-warning"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    cursor: 'pointer',
                    border: 'none',
                  }}
                  title={`${safeDisplayErrorMessage(jobState.progress?.status_message, '任务状态待确认')} · ${jobState.progress?.percent_complete != null ? Math.round(jobState.progress.percent_complete) + '%' : ''}`}
                  onClick={() => setActiveView('dashboard')}
                  aria-label={`任务运行中，${jobState.progress?.percent_complete != null ? Math.round(jobState.progress.percent_complete) + '%' : ''}，点击跳转到运行总览`}
                >
                  {jobState.progress?.percent_complete != null
                    ? `${Math.round(jobState.progress.percent_complete)}%`
                    : '...'}{' '}
                  {(jobState.progress?.eta_seconds ?? 0) > 0
                    ? fmtEta(jobState.progress?.eta_seconds ?? 0)
                    : ''}
                </button>
              )}
              <Tooltip
                content={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
                placement="bottom"
              >
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={toggleTheme}
                  aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
                >
                  {theme === 'dark' ? (
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                      focusable="false"
                    >
                      <circle cx="12" cy="12" r="5" />
                      <line x1="12" y1="1" x2="12" y2="3" />
                      <line x1="12" y1="21" x2="12" y2="23" />
                      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                      <line x1="1" y1="12" x2="3" y2="12" />
                      <line x1="21" y1="12" x2="23" y2="12" />
                      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                    </svg>
                  ) : (
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                      focusable="false"
                    >
                      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                    </svg>
                  )}
                </button>
              </Tooltip>
              <Tooltip content="键盘快捷键帮助 (按 ? 打开)" placement="bottom">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setShortcutsHelpOpen(true)}
                  aria-label="键盘快捷键帮助"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                </button>
              </Tooltip>
              <span
                className="badge badge-positive"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}
              >
                PRODUCTION
              </span>
            </div>
          </header>

          <Sidebar
            className={sidebarOpen ? 'is-open' : ''}
            activeView={activeView}
            badges={sidebarBadges}
            onNavigate={handleNavigate}
            onClose={() => setSidebarOpen(false)}
            onTogglePhase={handleTogglePhase}
            phases={sidebarPhases}
          />
          {sidebarOpen && (
            <div
              role="presentation"
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 150,
                backgroundColor: 'rgba(0,0,0,0.4)',
              }}
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden"
              aria-hidden="true"
            />
          )}

          <main className="app-main" id="main-content" tabIndex={-1}>
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[999] focus:px-4 focus:py-2 focus:bg-accent focus:text-text-inverse focus:rounded-md focus:font-medium focus:text-sm"
            >
              跳到主内容
            </a>

            {currentPhaseObj && (
              <PhaseShell
                phaseId={currentPhase}
                phaseLabel={currentPhaseObj.label}
                statusLabel={phaseShellStatusLabel}
                statusTone={phaseShellStatusTone}
                unlockCondition={currentPhaseObj.unlockCondition}
                steps={steps}
              >
                <FlowGuide currentPhase={currentPhase} />
                <div className="animate-fade-in">
                  <Suspense fallback={<PageLoader />}><ActiveViewRenderer /></Suspense>
                </div>
              </PhaseShell>
            )}

            {!currentPhaseObj && (
              <div className="animate-fade-in">
                <Suspense fallback={<PageLoader />}><ActiveViewRenderer /></Suspense>
              </div>
            )}
          </main>

          <footer className="app-statusbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <span className={`status-dot ${topbarStatus.dotClass}`} />
              <span>BRAIN API</span>
              <span>{connected ? '已连接' : '未连接'}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <span>v3.0 · Phase Navigation</span>
              <span>本地非提交页面</span>
            </div>
          </footer>

          <MobileTabBar activePhase={currentPhase} onNavigate={handleMobileNavigate} />

          <ToastContainer toasts={toasts} onDismiss={dismissToast} />

          <KeyboardShortcutsHelp
            open={shortcutsHelpOpen}
            onClose={() => setShortcutsHelpOpen(false)}
          />
        </div>
    </ErrorBoundary>
  );
}
