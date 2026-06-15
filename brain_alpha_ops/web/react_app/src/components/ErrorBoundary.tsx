/** P1-10 fix: Generic React Error Boundary for component-level crash
 * isolation.  Catches rendering errors and displays a fallback UI instead
 * of a white screen.  Designed for data-heavy panels like CandidateTable. */

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error) => void;
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
    console.error("ErrorBoundary caught:", error.message, info.componentStack);
    this.props.onError?.(error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div style={{
          padding: "2rem 1.5rem",
          border: "1px solid oklch(0.48 0.08 22 / 0.30)",
          borderRadius: 8,
          background: "oklch(0.48 0.06 22 / 0.06)",
          textAlign: "center",
        }}>
          <p style={{ color: "oklch(0.48 0.10 22)", fontWeight: 500, fontSize: 14, marginBottom: 8 }}>
            面板加载异常
          </p>
          <p style={{ color: "oklch(0.50 0.006 45)", fontSize: 12, lineHeight: 1.5, maxWidth: 320, margin: "0 auto 12px" }}>
            候选管理面板在渲染过程中遇到未预期的错误。请尝试刷新页面或返回上一步操作。
          </p>
          <details style={{ fontSize: 11, color: "oklch(0.44 0.006 45)", textAlign: "left", maxWidth: 400, margin: "0 auto" }}>
            <summary>错误详情</summary>
            <pre style={{ marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {this.state.error?.message}
            </pre>
          </details>
        </div>
      );
    }
    return this.props.children;
  }
}
