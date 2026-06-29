/**
 * Unit tests for <ErrorBoundary> — L3 audit item.
 *
 * Covers:
 *   - normal rendering (children pass-through)
 *   - error capture and fallback UI (full-page + section levels)
 *   - ActionableError is rendered inside the fallback
 *   - error message propagation
 *   - retry / reset behaviour
 *   - errorKey-driven automatic recovery
 *   - custom fallback prop
 *   - onError / onReset callbacks
 *   - showHomeButton flag
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorBoundary from '@/components/ErrorBoundary';

// ── helpers ────────────────────────────────────────────────────────────────

/** Component that throws during render. */
function ThrowingChild({ message = 'boom' }: { message?: string }) {
  throw new Error(message);
}

/** Well-behaved child. */
function GoodChild() {
  return <div data-testid="good-child">all good</div>;
}

// Suppress the expected console.error noise from ErrorBoundary.
let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleErrorSpy.mockRestore();
});

// ── normal rendering ───────────────────────────────────────────────────────

describe('ErrorBoundary — normal rendering', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <GoodChild />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId('good-child')).toBeDefined();
    expect(screen.getByText('all good')).toBeDefined();
  });

  it('renders multiple children', () => {
    render(
      <ErrorBoundary>
        <div data-testid="a">A</div>
        <div data-testid="b">B</div>
      </ErrorBoundary>,
    );
    expect(screen.getByTestId('a')).toBeDefined();
    expect(screen.getByTestId('b')).toBeDefined();
  });
});

// ── error capture & fallback UI ────────────────────────────────────────────

describe('ErrorBoundary — error capture (full-page)', () => {
  it('catches child errors and renders full-page fallback by default', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );

    // role="alert" is present on the full-page fallback wrapper.
    expect(screen.getByRole('alert')).toBeDefined();
    // Default title for full-page level.
    expect(screen.getByText('出现了一些问题')).toBeDefined();
  });

  it('renders the default description text', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(
      screen.getByText('页面渲染时发生了意外错误，请尝试刷新或返回首页'),
    ).toBeDefined();
  });

  it('shows the error message from the thrown Error', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild message="something broke badly" />
      </ErrorBoundary>,
    );
    // The error message is forwarded to <ActionableError> which renders
    // the cause text.  At minimum the raw message should appear somewhere
    // in the document (either via ActionableError or the raw error display).
    expect(screen.getByText(/something broke badly/)).toBeDefined();
  });

  it('renders retry ("重试") button', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('重试')).toBeDefined();
  });

  it('renders "返回首页" button when showHomeButton is true (default)', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('返回首页')).toBeDefined();
  });

  it('hides "返回首页" button when showHomeButton is false', () => {
    render(
      <ErrorBoundary showHomeButton={false}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.queryByText('返回首页')).toBeNull();
  });

  it('calls onError callback when an error is caught', () => {
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <ThrowingChild message="callback-test" />
      </ErrorBoundary>,
    );
    expect(onError).toHaveBeenCalled();
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onError.mock.calls[0][0].message).toBe('callback-test');
  });
});

// ── section level ──────────────────────────────────────────────────────────

describe('ErrorBoundary — section level', () => {
  it('renders section fallback with "加载失败" title', () => {
    render(
      <ErrorBoundary level="section">
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.getByText('加载失败')).toBeDefined();
  });

  it('uses custom title and description for section fallback', () => {
    render(
      <ErrorBoundary level="section" title="模块出错" description="请重试该模块">
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('模块出错')).toBeDefined();
    expect(screen.getByText('请重试该模块')).toBeDefined();
  });

  it('does not show "返回首页" by default for section level', () => {
    render(
      <ErrorBoundary level="section">
        <ThrowingChild />
      </ErrorBoundary>,
    );
    // showHomeButton defaults to false for section-level (see renderSectionFallback).
    expect(screen.queryByText('返回首页')).toBeNull();
  });
});

// ── custom fallback ────────────────────────────────────────────────────────

describe('ErrorBoundary — custom fallback', () => {
  it('renders the custom fallback ReactNode instead of the built-in UI', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom-fb">custom error UI</div>}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId('custom-fb')).toBeDefined();
    expect(screen.getByText('custom error UI')).toBeDefined();
    // Built-in title should NOT appear.
    expect(screen.queryByText('出现了一些问题')).toBeNull();
  });
});

// ── retry / reset ──────────────────────────────────────────────────────────

describe('ErrorBoundary — retry / reset', () => {
  it('resets error state when "重试" button is clicked and children re-render', () => {
    let shouldThrow = true;

    function ConditionalChild() {
      if (shouldThrow) {
        throw new Error('transient');
      }
      return <div data-testid="recovered">recovered!</div>;
    }

    render(
      <ErrorBoundary>
        <ConditionalChild />
      </ErrorBoundary>,
    );

    // Initially the error is caught — fallback visible.
    expect(screen.getByText('出现了一些问题')).toBeDefined();

    // Fix the child before clicking retry so the re-render succeeds.
    shouldThrow = false;
    fireEvent.click(screen.getByText('重试'));

    // After reset the child should render normally again.
    expect(screen.getByTestId('recovered')).toBeDefined();
    expect(screen.queryByText('出现了一些问题')).toBeNull();
  });

  it('calls onReset callback when retry button is clicked', () => {
    const onReset = vi.fn();
    render(
      <ErrorBoundary onReset={onReset}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    fireEvent.click(screen.getByText('重试'));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it('"返回首页" button also resets error state', () => {
    let shouldThrow = true;

    function ConditionalChild() {
      if (shouldThrow) {
        throw new Error('nav-test');
      }
      return <div data-testid="after-home">home</div>;
    }

    render(
      <ErrorBoundary>
        <ConditionalChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('出现了一些问题')).toBeDefined();

    shouldThrow = false;
    fireEvent.click(screen.getByText('返回首页'));
    expect(screen.getByTestId('after-home')).toBeDefined();
  });
});

// ── errorKey-driven recovery ───────────────────────────────────────────────

describe('ErrorBoundary — errorKey recovery', () => {
  it('auto-resets when errorKey prop changes', () => {
    let shouldThrow = true;

    function ConditionalChild() {
      if (shouldThrow) {
        throw new Error('keyed-error');
      }
      return <div data-testid="keyed-recovered">ok</div>;
    }

    const { rerender } = render(
      <ErrorBoundary errorKey="v1">
        <ConditionalChild />
      </ErrorBoundary>,
    );

    // Error state.
    expect(screen.getByText('出现了一些问题')).toBeDefined();

    // Fix the child and change the errorKey → should auto-recover.
    shouldThrow = false;
    rerender(
      <ErrorBoundary errorKey="v2">
        <ConditionalChild />
      </ErrorBoundary>,
    );

    expect(screen.getByTestId('keyed-recovered')).toBeDefined();
    expect(screen.queryByText('出现了一些问题')).toBeNull();
  });

  it('does NOT auto-reset when errorKey stays the same', () => {
    render(
      <ErrorBoundary errorKey="stable">
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('出现了一些问题')).toBeDefined();
  });
});

// ── ActionableError integration ────────────────────────────────────────────

describe('ErrorBoundary — ActionableError integration', () => {
  it('renders ActionableError card inside the full-page fallback', () => {
    const { container } = render(
      <ErrorBoundary>
        <ThrowingChild message="actionable-test" />
      </ErrorBoundary>,
    );
    // ActionableError renders a div with class "actionable-error-card".
    const card = container.querySelector('.actionable-error-card');
    expect(card).not.toBeNull();
  });

  it('renders ActionableError card inside the section fallback', () => {
    const { container } = render(
      <ErrorBoundary level="section">
        <ThrowingChild message="section-actionable" />
      </ErrorBoundary>,
    );
    const card = container.querySelector('.actionable-error-card');
    expect(card).not.toBeNull();
  });
});

// ── custom title / description for full-page ───────────────────────────────

describe('ErrorBoundary — custom title & description (full-page)', () => {
  it('uses custom title and description', () => {
    render(
      <ErrorBoundary title="自定义标题" description="自定义描述">
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('自定义标题')).toBeDefined();
    expect(screen.getByText('自定义描述')).toBeDefined();
  });
});
