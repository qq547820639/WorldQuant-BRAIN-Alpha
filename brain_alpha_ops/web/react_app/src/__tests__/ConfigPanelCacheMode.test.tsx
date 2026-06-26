/**
 * Regression tests for ConfigPanel cache-mode credential folding.
 *
 * Locks in behavior implemented in:
 * - ConfigPanel.tsx:76-80 (hasSessionCredentials, cacheOnlyMode, showCredentialEditor)
 * - CredentialsSection.tsx:94-107 (cacheOnlyMode → LocalCacheConnectionSection)
 * - LocalCacheConnectionSection.tsx:22-83 (children folded behind 临时连接官方服务)
 *
 * See .trae/specs/overhaul-alpha-production-quality/spec.md (Workstream E4).
 * Production components are NOT modified — these tests only lock in behavior.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LocalCacheConnectionSection from '@/components/ConfigPanel/LocalCacheConnectionSection';
import CredentialsSection from '@/components/ConfigPanel/CredentialsSection';
import type { BrainCredentials } from '@/types';

type CredentialsSectionProps = Parameters<typeof CredentialsSection>[0];

const emptyCredentials: BrainCredentials = { username: '', password: '', token: '' };

/** Stand-in for the credentialFields JSX CredentialsSection builds internally. */
function CredentialInputs() {
  return (
    <>
      <label>
        <span>账户邮箱</span>
        <input type="text" data-testid="username-input" />
      </label>
      <label>
        <span>密码</span>
        <input type="password" data-testid="password-input" />
      </label>
      <label>
        <span>Token</span>
        <input type="password" data-testid="token-input" />
      </label>
    </>
  );
}

const baseLocalCacheProps = {
  logoutLoading: false,
  logoutError: null,
  onOpenTemporaryConnection: vi.fn(),
  onCloseTemporaryConnection: vi.fn(),
  onLogout: vi.fn(),
};

function makeProps(
  overrides: Partial<CredentialsSectionProps> = {}
): CredentialsSectionProps {
  return {
    credentials: emptyCredentials,
    cacheOnlyMode: false,
    temporaryConnectionOpen: false,
    showCredentialEditor: true,
    connectionApi: { loading: false, error: null, data: null },
    logoutApi: { loading: false, error: null },
    validationError: null,
    connectionStatusText: '',
    hasSessionCredentials: false,
    onUpdateCredential: vi.fn(),
    onTestConnection: vi.fn(),
    onLogout: vi.fn(),
    onOpenTemporaryConnection: vi.fn(),
    onCloseTemporaryConnection: vi.fn(),
    ...overrides,
  };
}

// ── E4.1: cache-mode folding regression tests ──────────────

describe('E4.1 ConfigPanel cache-mode credential folding', () => {
  // Case 1: cache mode + collapsed → only cache UI shown, no credential inputs.
  it('cache mode + collapsed → shows cache UI, hides credential inputs', () => {
    const { container } = render(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        temporaryConnectionOpen={false}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    expect(screen.getByText(/本地缓存会话/)).toBeDefined();
    expect(screen.getByText(/当前使用本地缓存/)).toBeDefined();
    expect(screen.getByRole('button', { name: '退出本地会话' })).toBeDefined();
    expect(screen.getByRole('button', { name: '临时连接官方服务' })).toBeDefined();

    // Credential inputs NOT in document.
    expect(screen.queryByTestId('username-input')).toBeNull();
    expect(screen.queryByTestId('password-input')).toBeNull();
    expect(screen.queryByTestId('token-input')).toBeNull();
    expect(screen.queryByText('账户邮箱')).toBeNull();
    expect(screen.queryByText('密码')).toBeNull();
    expect(screen.queryByText('Token')).toBeNull();
    expect(container.querySelectorAll('input')).toHaveLength(0);
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });

  // Case 2: clicking 临时连接官方服务 → credential inputs appear.
  it('cache mode + expand click → onOpenTemporaryConnection fires; re-render reveals inputs', () => {
    const onOpen = vi.fn();
    const { rerender, container } = render(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        onOpenTemporaryConnection={onOpen}
        temporaryConnectionOpen={false}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    fireEvent.click(screen.getByRole('button', { name: '临时连接官方服务' }));
    expect(onOpen).toHaveBeenCalledTimes(1);

    // Parent re-renders with temporaryConnectionOpen=true.
    rerender(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        onOpenTemporaryConnection={onOpen}
        temporaryConnectionOpen={true}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    expect(screen.getByTestId('username-input')).toBeDefined();
    expect(screen.getByTestId('password-input')).toBeDefined();
    expect(screen.getByTestId('token-input')).toBeDefined();
    expect(screen.getByText('账户邮箱')).toBeDefined();
    expect(screen.getByText('密码')).toBeDefined();
    expect(screen.getByText('Token')).toBeDefined();
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
    expect(screen.getByRole('button', { name: '收起凭据输入' })).toBeDefined();
    expect(screen.queryByRole('button', { name: '临时连接官方服务' })).toBeNull();
  });

  // Case 3: expand → collapse → credential inputs disappear.
  it('cache mode + collapse click → onCloseTemporaryConnection fires; re-render hides inputs', () => {
    const onClose = vi.fn();
    const { rerender, container } = render(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        onCloseTemporaryConnection={onClose}
        temporaryConnectionOpen={true}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    expect(screen.getByTestId('username-input')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: '收起凭据输入' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        onCloseTemporaryConnection={onClose}
        temporaryConnectionOpen={false}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    expect(screen.queryByTestId('username-input')).toBeNull();
    expect(screen.queryByTestId('password-input')).toBeNull();
    expect(screen.queryByTestId('token-input')).toBeNull();
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);
    expect(screen.getByRole('button', { name: '临时连接官方服务' })).toBeDefined();
  });

  // Case 4: non-cache mode → credential inputs always shown (no expand action).
  it('non-cache mode → credential inputs always rendered without expand action', () => {
    const { container } = render(
      <CredentialsSection
        {...makeProps({ cacheOnlyMode: false, showCredentialEditor: true })}
      />
    );

    expect(screen.queryByText(/本地缓存会话/)).toBeNull();
    expect(screen.queryByRole('button', { name: '临时连接官方服务' })).toBeNull();
    expect(screen.queryByRole('button', { name: '退出本地会话' })).toBeNull();

    expect(screen.getByText('BRAIN 连接')).toBeDefined();
    expect(screen.getByText('账户邮箱')).toBeDefined();
    expect(screen.getByText('密码')).toBeDefined();
    expect(screen.getByText('Token')).toBeDefined();
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
    expect(container.querySelectorAll('input[type="text"]')).toHaveLength(1);
  });

  // Case 5: logout in cache mode → onLogout fires; parent re-render collapses.
  it('cache mode + logout click → onLogout fires; re-render with temporaryConnectionOpen=false hides inputs', () => {
    const onLogout = vi.fn();
    const { rerender, container } = render(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: true,
          showCredentialEditor: true,
          onLogout,
        })}
      />
    );

    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: '退出本地会话' }));
    expect(onLogout).toHaveBeenCalledTimes(1);

    // ConfigPanel.handleLogout (lines 92-95) sets temporaryConnectionOpen=false.
    rerender(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: false,
          showCredentialEditor: false,
          onLogout,
        })}
      />
    );
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);
    expect(screen.queryByText('账户邮箱')).toBeNull();
  });

  // Case 6: switching cache mode → connected → consistent state.
  it('switching cache mode → connected: cache UI gone, credential inputs visible', () => {
    const { rerender, container } = render(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: false,
          showCredentialEditor: false,
        })}
      />
    );

    expect(screen.getByText(/本地缓存会话/)).toBeDefined();
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);

    rerender(
      <CredentialsSection
        {...makeProps({ cacheOnlyMode: false, showCredentialEditor: true })}
      />
    );

    expect(screen.queryByText(/本地缓存会话/)).toBeNull();
    expect(screen.getByText('BRAIN 连接')).toBeDefined();
    expect(screen.getByText('账户邮箱')).toBeDefined();
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
  });

  // Case 7: no credentials exposed in DOM when cache mode + collapsed.
  it('cache mode + collapsed → no credential values leaked into DOM', () => {
    const { container } = render(
      <CredentialsSection
        {...makeProps({
          credentials: {
            username: 'someone@example.com',
            password: 'supersecret-value',
            token: 'tok-abc-123',
          },
          cacheOnlyMode: true,
          temporaryConnectionOpen: false,
          showCredentialEditor: false,
          hasSessionCredentials: true,
        })}
      />
    );

    expect(container.querySelectorAll('input')).toHaveLength(0);
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);
    expect(container.querySelectorAll('input[type="text"]')).toHaveLength(0);
    expect(container.textContent).not.toContain('someone@example.com');
    expect(container.textContent).not.toContain('supersecret-value');
    expect(container.textContent).not.toContain('tok-abc-123');
  });

  // Edge case: non-cache mode + showCredentialEditor=false → renders nothing.
  it('non-cache mode + showCredentialEditor=false → renders nothing', () => {
    const { container } = render(
      <CredentialsSection
        {...makeProps({ cacheOnlyMode: false, showCredentialEditor: false })}
      />
    );
    expect(container.firstChild).toBeNull();
    expect(container.querySelectorAll('input')).toHaveLength(0);
  });

  // Edge case: logoutLoading disables the 退出本地会话 button.
  it('cache mode + logoutLoading=true → 退出本地会话 disabled and relabeled', () => {
    render(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        logoutLoading={true}
        temporaryConnectionOpen={false}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    const logoutBtn = screen.getByRole('button', { name: '退出中...' });
    expect(logoutBtn.hasAttribute('disabled')).toBe(true);
  });

  // Edge case: logoutError renders as an alert.
  it('cache mode + logoutError → alert shown with error text', () => {
    render(
      <LocalCacheConnectionSection
        {...baseLocalCacheProps}
        logoutError="退出失败：网络异常"
        temporaryConnectionOpen={false}
      >
        <CredentialInputs />
      </LocalCacheConnectionSection>
    );

    expect(screen.getByRole('alert').textContent).toContain('退出失败：网络异常');
  });
});

// ── E4.2: state consistency after connection toggle ────────

describe('E4.2 state consistency after connection toggle', () => {
  it('expand → collapse → expand: handlers fire each cycle, no stale state', () => {
    const onOpen = vi.fn();
    const onClose = vi.fn();

    const { rerender, container } = render(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: false,
          showCredentialEditor: false,
          onOpenTemporaryConnection: onOpen,
          onCloseTemporaryConnection: onClose,
        })}
      />
    );

    // Expand (1st time).
    fireEvent.click(screen.getByRole('button', { name: '临时连接官方服务' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
    rerender(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: true,
          showCredentialEditor: true,
          onOpenTemporaryConnection: onOpen,
          onCloseTemporaryConnection: onClose,
        })}
      />
    );
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);

    // Collapse.
    fireEvent.click(screen.getByRole('button', { name: '收起凭据输入' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: false,
          showCredentialEditor: false,
          onOpenTemporaryConnection: onOpen,
          onCloseTemporaryConnection: onClose,
        })}
      />
    );
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);

    // Expand (2nd time) — second onOpen invocation, no stale closure.
    fireEvent.click(screen.getByRole('button', { name: '临时连接官方服务' }));
    expect(onOpen).toHaveBeenCalledTimes(2);
    rerender(
      <CredentialsSection
        {...makeProps({
          cacheOnlyMode: true,
          temporaryConnectionOpen: true,
          showCredentialEditor: true,
          onOpenTemporaryConnection: onOpen,
          onCloseTemporaryConnection: onClose,
        })}
      />
    );
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
  });

  // Connected → cache → connected transitions are covered by E4.1 Case 6
  // (cache → connected) and the symmetric collapse assertions above.
});
