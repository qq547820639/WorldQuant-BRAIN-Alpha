/** Unit tests for ErrorBoundary component */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "../src/components/ErrorBoundary";

// Helper component that throws an error
function ThrowError({ shouldThrow = false }: { shouldThrow?: boolean }) {
  if (shouldThrow) {
    throw new Error("Test error message");
  }
  return <div>Content rendered successfully</div>;
}

// ── ErrorBoundary Tests ─────────────────────────────────────────

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

    // The actual error message from the component
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

  it("renders go home button in fallback", () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("返回首页")).toBeDefined();
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
});
