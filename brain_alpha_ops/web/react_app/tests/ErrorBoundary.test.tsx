/** Unit tests for ErrorBoundary component */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ErrorBoundary from "../src/components/ErrorBoundary";

function ThrowError({ shouldThrow = false }: { shouldThrow?: boolean }) {
  if (shouldThrow) {
    throw new Error("Test error message");
  }
  return <div>Content rendered successfully</div>;
}

describe("ErrorBoundary", () => {
  const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

  beforeEach(() => {
    consoleErrorSpy.mockClear();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("renders children when no error occurs", () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">Child Content</div>
      </ErrorBoundary>
    );

    expect(screen.getByTestId("child")).toBeDefined();
    expect(screen.getByText("Child Content")).toBeDefined();
  });

  it("renders fallback when child component throws", () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Test error message/i)).toBeDefined();
  });

  it("renders retry button in fallback", () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("重试")).toBeDefined();
  });

  it("renders go home button in full-page fallback", () => {
    render(
      <ErrorBoundary level="full-page">
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("返回首页")).toBeDefined();
  });

  it("does not render go home button in section fallback by default", () => {
    render(
      <ErrorBoundary level="section">
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.queryByText("返回首页")).toBeNull();
  });

  it("renders with custom fallback component", () => {
    const CustomFallback = () => <div data-testid="custom-fallback">Custom Error Page</div>;

    render(
      <ErrorBoundary fallback={<CustomFallback />}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId("custom-fallback")).toBeDefined();
  });

  it("handles errors during render gracefully", () => {
    function BrokenComponent() {
      throw new Error("Render error");
    }

    render(
      <ErrorBoundary>
        <BrokenComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Render error/i)).toBeDefined();
  });

  describe("section level error boundary", () => {
    it("renders section level fallback UI", () => {
      render(
        <ErrorBoundary level="section">
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("加载失败")).toBeDefined();
    });

    it("renders custom title and description for section level", () => {
      render(
        <ErrorBoundary
          level="section"
          title="自定义标题"
          description="自定义错误描述"
        >
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText("自定义标题")).toBeDefined();
      expect(screen.getByText("自定义错误描述")).toBeDefined();
    });
  });

  describe("full-page level error boundary", () => {
    it("renders full-page level fallback UI", () => {
      render(
        <ErrorBoundary level="full-page">
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("出现了一些问题")).toBeDefined();
    });

    it("renders custom title and description for full-page level", () => {
      render(
        <ErrorBoundary
          level="full-page"
          title="自定义全屏标题"
          description="自定义全屏错误描述"
        >
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText("自定义全屏标题")).toBeDefined();
      expect(screen.getByText("自定义全屏错误描述")).toBeDefined();
    });

    it("defaults to full-page level when level not specified", () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText("出现了一些问题")).toBeDefined();
    });
  });

  describe("retry functionality", () => {
    it("calls onReset when retry button is clicked", () => {
      const onReset = vi.fn();

      render(
        <ErrorBoundary onReset={onReset}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const retryButton = screen.getByText("重试");
      fireEvent.click(retryButton);

      expect(onReset).toHaveBeenCalledTimes(1);
    });

    it("resets error state when retry button is clicked", () => {
      let shouldThrow = true;

      function ToggleableError() {
        if (shouldThrow) {
          throw new Error("Toggleable error");
        }
        return <div data-testid="recovered-content">Recovered content</div>;
      }

      const onReset = vi.fn(() => {
        shouldThrow = false;
      });

      const { rerender } = render(
        <ErrorBoundary onReset={onReset}>
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Toggleable error/i)).toBeDefined();

      const retryButton = screen.getByText("重试");
      fireEvent.click(retryButton);

      rerender(
        <ErrorBoundary onReset={onReset}>
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(onReset).toHaveBeenCalledTimes(1);
    });
  });

  describe("errorKey prop", () => {
    it("resets error state when errorKey changes", () => {
      let shouldThrow = true;

      function ToggleableError() {
        if (shouldThrow) {
          throw new Error("Key-based error");
        }
        return <div data-testid="recovered">Recovered via key</div>;
      }

      const { rerender } = render(
        <ErrorBoundary errorKey="key1">
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Key-based error/i)).toBeDefined();

      shouldThrow = false;
      rerender(
        <ErrorBoundary errorKey="key2">
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(screen.getByTestId("recovered")).toBeDefined();
      expect(screen.getByText("Recovered via key")).toBeDefined();
    });

    it("does not reset error state when errorKey stays the same", () => {
      let shouldThrow = true;

      function ToggleableError() {
        if (shouldThrow) {
          throw new Error("Same key error");
        }
        return <div data-testid="should-not-appear">Should not appear</div>;
      }

      const { rerender } = render(
        <ErrorBoundary errorKey="same-key">
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Same key error/i)).toBeDefined();

      shouldThrow = false;
      rerender(
        <ErrorBoundary errorKey="same-key">
          <ToggleableError />
        </ErrorBoundary>
      );

      expect(screen.queryByTestId("should-not-appear")).toBeNull();
    });
  });

  describe("showHomeButton prop", () => {
    it("shows home button in section level when showHomeButton is true", () => {
      render(
        <ErrorBoundary level="section" showHomeButton={true}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText("返回首页")).toBeDefined();
    });

    it("hides home button in full-page level when showHomeButton is false", () => {
      render(
        <ErrorBoundary level="full-page" showHomeButton={false}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.queryByText("返回首页")).toBeNull();
    });
  });

  describe("onError callback", () => {
    it("calls onError when an error is caught", () => {
      const onError = vi.fn();

      render(
        <ErrorBoundary onError={onError}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError).toHaveBeenCalledWith(expect.any(Error));
      expect(onError.mock.calls[0][0].message).toBe("Test error message");
    });
  });
});
