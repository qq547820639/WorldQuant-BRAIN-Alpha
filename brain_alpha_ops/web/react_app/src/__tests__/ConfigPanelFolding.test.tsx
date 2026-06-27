/**
 * Workstream F2.1 — ConfigPanel credential folding regression tests.
 *
 * Spec ref: .trae/specs/overhaul-alpha-production-quality/spec.md
 *   "ConfigPanel 缓存模式回归保护（继承自已实现）"
 *
 * Behavior under test:
 *  - In cache-only mode, credential input fields MUST be hidden by default;
 *    only "退出本地会话" + "临时连接官方服务" buttons are visible.
 *  - Clicking "临时连接官方服务" expands the credential editor inline;
 *    clicking "收起凭据输入" collapses it again.
 *  - When NOT in cache-only mode, the credential editor is rendered directly
 *    inside a "BRAIN 连接" section.
 *  - Logout button calls onLogout; the parent collapses the temporary panel.
 *
 * These tests mount CredentialsSection / LocalCacheConnectionSection directly
 * with mocked props to avoid pulling useGlobalData/useApi providers.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CredentialsSection from '@/components/ConfigPanel/CredentialsSection';
import LocalCacheConnectionSection from '@/components/ConfigPanel/LocalCacheConnectionSection';
import type { BrainCredentials } from '@/types';

const EMPTY_CREDS: BrainCredentials = { username: '', password: '', token: '' };
const FILLED_CREDS: BrainCredentials = {
  username: 'someone@example.com',
  password: 'do-not-commit-real-password',
  token: 'do-not-commit-real-token',
};

const baseProps = (overrides: Record<string, unknown> = {}) => ({
  credentials: EMPTY_CREDS,
  cacheOnlyMode: false,
  temporaryConnectionOpen: false,
  showCredentialEditor: true,
  connectionApi: { loading: false, error: null as string | null, data: null },
  logoutApi: { loading: false, error: null as string | null },
  connectionStatusText: '请临时填写页面凭证',
  hasSessionCredentials: false,
  onUpdateCredential: vi.fn(),
  onTestConnection: vi.fn(),
  onLogout: vi.fn(),
  onOpenTemporaryConnection: vi.fn(),
  onCloseTemporaryConnection: vi.fn(),
  ...overrides,
});

const cacheProps = (overrides: Record<string, unknown> = {}) => ({
  ...baseProps(),
  cacheOnlyMode: true,
  temporaryConnectionOpen: true,
  showCredentialEditor: true,
  ...overrides,
});

const lcBase = (overrides: Record<string, unknown> = {}) => ({
  temporaryConnectionOpen: false,
  logoutLoading: false,
  logoutError: null,
  onOpenTemporaryConnection: vi.fn(),
  onCloseTemporaryConnection: vi.fn(),
  onLogout: vi.fn(),
  ...overrides,
});

// ── Cache-only mode (folding) ───────────────────────────────

describe('CredentialsSection — cache-only folding', () => {
  it('hides credential inputs by default in cache-only mode', () => {
    render(<CredentialsSection {...cacheProps({ temporaryConnectionOpen: false, showCredentialEditor: false })} />);
    expect(screen.queryByLabelText('账户邮箱')).toBeNull();
    expect(screen.queryByLabelText('密码')).toBeNull();
    expect(screen.queryByLabelText('Token')).toBeNull();
    expect(screen.getByText('退出本地会话')).toBeDefined();
    expect(screen.getByText('临时连接官方服务')).toBeDefined();
    expect(screen.getByText(/当前使用本地缓存运行/)).toBeDefined();
  });

  it('expands credential editor after "临时连接官方服务" is clicked', () => {
    const onOpen = vi.fn();
    render(
      <CredentialsSection
        {...cacheProps({ temporaryConnectionOpen: false, showCredentialEditor: false, onOpenTemporaryConnection: onOpen })}
      />
    );
    fireEvent.click(screen.getByText('临时连接官方服务'));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('renders credential inputs when temporaryConnectionOpen=true in cache-only mode', () => {
    render(<CredentialsSection {...cacheProps()} />);
    expect(screen.getByLabelText('账户邮箱')).toBeDefined();
    expect(screen.getByLabelText('密码')).toBeDefined();
    expect(screen.getByLabelText('Token')).toBeDefined();
    expect(screen.getByText('收起凭据输入')).toBeDefined();
  });

  it('calls onCloseTemporaryConnection when "收起凭据输入" is clicked', () => {
    const onClose = vi.fn();
    render(<CredentialsSection {...cacheProps({ onCloseTemporaryConnection: onClose })} />);
    fireEvent.click(screen.getByText('收起凭据输入'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not render the "BRAIN 连接" fieldset title in cache-only mode', () => {
    render(<CredentialsSection {...cacheProps()} />);
    // The cache-mode legend is "本地缓存会话", not "BRAIN 连接".
    expect(screen.getByText('本地缓存会话')).toBeDefined();
    expect(screen.queryByText('BRAIN 连接')).toBeNull();
  });

  it('renders logout error when provided; disables logout button while loading', () => {
    const { rerender } = render(
      <CredentialsSection {...cacheProps({ logoutApi: { loading: false, error: '退出失败：会话已过期' } })} />
    );
    expect(screen.getByText('退出失败：会话已过期')).toBeDefined();

    rerender(<CredentialsSection {...cacheProps({ logoutApi: { loading: true, error: null } })} />);
    const logoutBtn = screen.getByText('退出中...');
    expect(logoutBtn).toBeDefined();
    expect(logoutBtn.closest('button')?.disabled).toBe(true);
  });

  it('forwards credential updates via onUpdateCredential', () => {
    const onUpdate = vi.fn();
    render(<CredentialsSection {...cacheProps({ onUpdateCredential: onUpdate })} />);
    const emailInput = screen.getByLabelText('账户邮箱');
    fireEvent.change(emailInput, { target: { value: '  user@example.com  ' } });
    expect(onUpdate).toHaveBeenCalledWith('username', 'user@example.com');
  });

  it('invokes onTestConnection when "测试 BRAIN 连接" is clicked; disables while loading', () => {
    const onTest = vi.fn();
    const { rerender } = render(<CredentialsSection {...cacheProps({ onTestConnection: onTest })} />);
    fireEvent.click(screen.getByText('测试 BRAIN 连接'));
    expect(onTest).toHaveBeenCalledTimes(1);

    rerender(<CredentialsSection {...cacheProps({ connectionApi: { loading: true, error: null, data: null } })} />);
    const btn = screen.getByText('测试中...');
    expect(btn.closest('button')?.disabled).toBe(true);
  });
});

// ── Non-cache mode ──────────────────────────────────────────

describe('CredentialsSection — non-cache mode', () => {
  it('renders the "BRAIN 连接" section with credential inputs by default', () => {
    render(<CredentialsSection {...baseProps()} />);
    expect(screen.getByText('BRAIN 连接')).toBeDefined();
    expect(screen.getByLabelText('账户邮箱')).toBeDefined();
    expect(screen.getByLabelText('密码')).toBeDefined();
    expect(screen.getByLabelText('Token')).toBeDefined();
  });

  it('renders nothing when showCredentialEditor is false and not in cache-only mode', () => {
    const { container } = render(<CredentialsSection {...baseProps({ showCredentialEditor: false })} />);
    // Should render nothing — no fieldset, no buttons.
    expect(container.querySelector('fieldset')).toBeNull();
    expect(screen.queryByLabelText('账户邮箱')).toBeNull();
  });

  it('shows connection status text and filled-credential hint', () => {
    const { rerender } = render(
      <CredentialsSection {...baseProps({ connectionStatusText: '连接正常: production' })} />
    );
    expect(screen.getByText('连接正常: production')).toBeDefined();

    rerender(
      <CredentialsSection
        {...baseProps({
          credentials: FILLED_CREDS,
          hasSessionCredentials: true,
          connectionStatusText: '凭证已填写，尚未测试',
        })}
      />
    );
    expect(screen.getByText('凭证已填写，尚未测试')).toBeDefined();
  });

  it('keeps test button enabled regardless of form validation state', () => {
    render(<CredentialsSection {...baseProps()} />);
    const btn = screen.getByText('测试 BRAIN 连接');
    expect(btn.closest('button')?.disabled).toBe(false);
  });
});

// ── LocalCacheConnectionSection in isolation ────────────────

describe('LocalCacheConnectionSection — folding primitives', () => {
  it('renders "退出本地会话" and "临时连接官方服务" buttons when folded; shows children when expanded', () => {
    const { rerender } = render(
      <LocalCacheConnectionSection {...lcBase()}>
        <div data-testid="credential-fields">fields</div>
      </LocalCacheConnectionSection>
    );
    expect(screen.getByText('退出本地会话')).toBeDefined();
    expect(screen.getByText('临时连接官方服务')).toBeDefined();
    expect(screen.queryByTestId('credential-fields')).toBeNull();

    rerender(
      <LocalCacheConnectionSection {...lcBase({ temporaryConnectionOpen: true })}>
        <div data-testid="credential-fields">fields</div>
      </LocalCacheConnectionSection>
    );
    expect(screen.getByTestId('credential-fields')).toBeDefined();
    expect(screen.getByText('收起凭据输入')).toBeDefined();
    expect(screen.getByText(/当前使用本地缓存运行/)).toBeDefined();
  });

  it('switches the primary action button between expand/collapse labels', () => {
    const { rerender } = render(
      <LocalCacheConnectionSection {...lcBase()}>
        <div />
      </LocalCacheConnectionSection>
    );
    expect(screen.getByText('临时连接官方服务')).toBeDefined();
    expect(screen.queryByText('收起凭据输入')).toBeNull();

    rerender(
      <LocalCacheConnectionSection {...lcBase({ temporaryConnectionOpen: true })}>
        <div />
      </LocalCacheConnectionSection>
    );
    expect(screen.queryByText('临时连接官方服务')).toBeNull();
    expect(screen.getByText('收起凭据输入')).toBeDefined();
  });

  it('triggers onLogout when logout button is clicked', () => {
    const onLogout = vi.fn();
    render(
      <LocalCacheConnectionSection {...lcBase({ onLogout })}>
        <div />
      </LocalCacheConnectionSection>
    );
    fireEvent.click(screen.getByText('退出本地会话'));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it('shows logout error with role=alert when logoutError is provided', () => {
    render(
      <LocalCacheConnectionSection {...lcBase({ logoutError: '会话已过期，请重新登录' })}>
        <div />
      </LocalCacheConnectionSection>
    );
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('会话已过期，请重新登录');
  });

  it('shows the temporary-credential privacy note only when expanded', () => {
    const { rerender } = render(
      <LocalCacheConnectionSection {...lcBase()}>
        <div />
      </LocalCacheConnectionSection>
    );
    expect(screen.queryByText(/以下凭据仅用于本次临时连接/)).toBeNull();

    rerender(
      <LocalCacheConnectionSection {...lcBase({ temporaryConnectionOpen: true })}>
        <div />
      </LocalCacheConnectionSection>
    );
    expect(screen.getByText(/以下凭据仅用于本次临时连接/)).toBeDefined();
  });
});
