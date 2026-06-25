import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import LiveRegion from "@/components/A11y/LiveRegion";

describe("LiveRegion", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("renders with default polite aria-live", () => {
    render(<LiveRegion message="Hello" />);
    const region = screen.getByText("Hello");
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("supports assertive politeness", () => {
    render(<LiveRegion message="Alert!" politeness="assertive" />);
    const region = screen.getByText("Alert!");
    expect(region).toHaveAttribute("aria-live", "assertive");
  });

  it("supports off politeness", () => {
    render(<LiveRegion message="Off" politeness="off" />);
    const region = screen.getByText("Off");
    expect(region).toHaveAttribute("aria-live", "off");
  });

  it("has aria-atomic=true by default", () => {
    render(<LiveRegion message="Test" />);
    const region = screen.getByText("Test");
    expect(region).toHaveAttribute("aria-atomic", "true");
  });

  it("supports aria-atomic=false", () => {
    render(<LiveRegion message="Test" atomic={false} />);
    const region = screen.getByText("Test");
    expect(region).toHaveAttribute("aria-atomic", "false");
  });

  it("has default aria-relevant", () => {
    render(<LiveRegion message="Test" />);
    const region = screen.getByText("Test");
    expect(region).toHaveAttribute("aria-relevant", "additions text");
  });

  it("updates message after delay", () => {
    const { rerender } = render(<LiveRegion message="Initial" />);
    expect(screen.getByText("Initial")).toBeInTheDocument();

    rerender(<LiveRegion message="Updated" />);

    expect(screen.queryByText("Updated")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(50);
    });

    expect(screen.getByText("Updated")).toBeInTheDocument();
  });

  it("renders children instead of message when provided", () => {
    render(
      <LiveRegion>
        <span data-testid="child">Child content</span>
      </LiveRegion>
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByText("Child content")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    render(<LiveRegion message="Test" className="custom-live" />);
    const region = screen.getByText("Test");
    expect(region.className).toContain("custom-live");
  });

  it("supports role prop", () => {
    render(<LiveRegion message="Status update" role="status" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("is visually hidden", () => {
    render(<LiveRegion message="Hidden" />);
    const region = screen.getByText("Hidden");
    expect(region.style.position).toBe("absolute");
    expect(region.style.width).toBe("1px");
    expect(region.style.height).toBe("1px");
    expect(region.style.overflow).toBe("hidden");
  });
});
