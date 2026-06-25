import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RetryButton from "@/components/ErrorState/RetryButton";

describe("RetryButton", () => {
  it("renders with default label", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} />);
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("calls onRetry when clicked", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows loading state", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} loading={true} />);
    const button = screen.getByRole("button", { name: "重试中..." });
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("shows custom loading label", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} loading={true} loadingLabel="处理中..." />);
    expect(screen.getByRole("button", { name: "处理中..." })).toBeInTheDocument();
  });

  it("is disabled when loading", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} loading={true} />);
    const button = screen.getByRole("button", { name: "重试中..." });
    fireEvent.click(button);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("is disabled when disabled prop is true", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} disabled={true} />);
    const button = screen.getByRole("button", { name: "重试" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("supports custom label", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} label="重新加载" />);
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
  });

  it("supports different sizes", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<RetryButton onRetry={onRetry} size="sm" label="重试" />);
    let button = screen.getByRole("button", { name: "重试" });
    expect(button.style.fontSize).toBe("13px");

    rerender(<RetryButton onRetry={onRetry} size="md" label="重试" />);
    button = screen.getByRole("button", { name: "重试" });
    expect(button.style.fontSize).toBe("14px");

    rerender(<RetryButton onRetry={onRetry} size="lg" label="重试" />);
    button = screen.getByRole("button", { name: "重试" });
    expect(button.style.fontSize).toBe("15px");
  });

  it("supports different variants", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<RetryButton onRetry={onRetry} variant="primary" label="重试" />);
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();

    rerender(<RetryButton onRetry={onRetry} variant="secondary" label="重试" />);
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();

    rerender(<RetryButton onRetry={onRetry} variant="ghost" label="重试" />);
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} className="custom-retry" />);
    expect(screen.getByRole("button", { name: "重试" }).className).toContain("custom-retry");
  });
});
