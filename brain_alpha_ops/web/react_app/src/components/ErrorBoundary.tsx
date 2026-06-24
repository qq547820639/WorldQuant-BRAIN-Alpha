import { Component, type ReactNode } from "react";

type ErrorBoundaryLevel = "full-page" | "section";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error) => void;
  onReset?: () => void;
  level?: ErrorBoundaryLevel;
  title?: string;
  description?: string;
  showHomeButton?: boolean;
  errorKey?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("ErrorBoundary caught an error:", error);
    console.error("Component stack:", info.componentStack);
    this.props.onError?.(error);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && this.props.errorKey && prevProps.errorKey !== this.props.errorKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
    window.location.hash = "";
  };

  renderFullPageFallback() {
    const { title, description, showHomeButton = true } = this.props;
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-root p-4" role="alert">
        <div className="max-w-md w-full text-center">
          <div className="mb-6 flex justify-center">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center"
              style={{
                backgroundColor: "var(--color-error-bg-faint)",
                border: "1px solid var(--color-error-border-subtle)",
              }}
              aria-hidden="true"
            >
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ color: "var(--color-error-text)" }}
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
          </div>

          <h1
            className="text-xl font-semibold mb-3"
            style={{ color: "var(--color-text-bright)" }}
          >
            {title || "出现了一些问题"}
          </h1>

          <p
            className="text-sm mb-8 leading-relaxed"
            style={{ color: "var(--color-text-muted)" }}
          >
            {description || "页面渲染时发生了意外错误，请尝试刷新或返回首页"}
          </p>

          {this.state.error && (
            <details
              className="text-left mb-6 text-xs rounded-md p-3"
              style={{
                backgroundColor: "var(--color-surface-deep)",
                border: "1px solid var(--color-border-default)",
                color: "var(--color-text-dim)",
              }}
            >
              <summary
                className="cursor-pointer font-medium"
                style={{ color: "var(--color-text-muted)" }}
              >
                错误详情
              </summary>
              <pre
                className="mt-2 whitespace-pre-wrap break-all font-mono text-xs"
                style={{ color: "var(--color-text-dim)" }}
              >
                {this.state.error.message}
              </pre>
            </details>
          )}

          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              className="btn btn-primary"
              onClick={this.handleReset}
            >
              重试
            </button>
            {showHomeButton && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={this.handleGoHome}
              >
                返回首页
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  renderSectionFallback() {
    const { title, description, showHomeButton = false } = this.props;
    return (
      <div className="panel" role="alert">
        <div className="panel-body-padded" style={{ textAlign: "center", padding: "2rem" }}>
          <div className="mb-4 flex justify-center">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{
                backgroundColor: "var(--color-error-bg-faint)",
                border: "1px solid var(--color-error-border-subtle)",
              }}
              aria-hidden="true"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ color: "var(--color-error-text)" }}
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
          </div>

          <h3
            className="text-base font-semibold mb-2"
            style={{ color: "var(--color-text-bright)" }}
          >
            {title || "加载失败"}
          </h3>

          <p
            className="text-sm mb-4 leading-relaxed"
            style={{ color: "var(--color-text-muted)" }}
          >
            {description || "模块加载时发生错误，请重试"}
          </p>

          {this.state.error && (
            <details
              className="text-left mb-4 text-xs rounded-md p-2"
              style={{
                backgroundColor: "var(--color-surface-deep)",
                border: "1px solid var(--color-border-default)",
                color: "var(--color-text-dim)",
                display: "inline-block",
                textAlign: "left",
              }}
            >
              <summary
                className="cursor-pointer font-medium"
                style={{ color: "var(--color-text-muted)" }}
              >
                错误详情
              </summary>
              <pre
                className="mt-2 whitespace-pre-wrap break-all font-mono text-xs"
                style={{ color: "var(--color-text-dim)" }}
              >
                {this.state.error.message}
              </pre>
            </details>
          )}

          <div className="flex items-center justify-center gap-2">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={this.handleReset}
            >
              重试
            </button>
            {showHomeButton && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={this.handleGoHome}
              >
                返回首页
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const level = this.props.level || "full-page";
      if (level === "section") {
        return this.renderSectionFallback();
      }
      return this.renderFullPageFallback();
    }

    return this.props.children;
  }
}
