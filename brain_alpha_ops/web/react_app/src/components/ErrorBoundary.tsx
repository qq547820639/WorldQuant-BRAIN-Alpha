import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error) => void;
  onReset?: () => void;
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

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
    window.location.hash = "";
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

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
              出现了一些问题
            </h1>

            <p
              className="text-sm mb-8 leading-relaxed"
              style={{ color: "var(--color-text-muted)" }}
            >
              页面渲染时发生了意外错误，请尝试刷新或返回首页
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
              <button
                type="button"
                className="btn btn-secondary"
                onClick={this.handleGoHome}
              >
                返回首页
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
