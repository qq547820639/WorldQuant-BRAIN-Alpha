import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PageLoader from "@/components/LoadingState/PageLoader";

describe("PageLoader", () => {
  it("renders with spinner and default size", () => {
    render(<PageLoader />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders with custom message", () => {
    render(<PageLoader message="正在加载数据..." />);
    expect(screen.getByText("正在加载数据...")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders without message", () => {
    render(<PageLoader />);
    expect(screen.queryByText("正在加载")).not.toBeInTheDocument();
  });

  it("supports different sizes", () => {
    const { rerender, container } = render(<PageLoader size="sm" />);
    let svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "16");

    rerender(<PageLoader size="md" />);
    svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "24");

    rerender(<PageLoader size="lg" />);
    svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "32");

    rerender(<PageLoader size="xl" />);
    svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
  });

  it("applies custom className", () => {
    const { container } = render(<PageLoader className="custom-loader" />);
    expect(container.firstChild).toHaveClass("custom-loader");
  });

  it("has aria-live polite attribute", () => {
    render(<PageLoader message="加载中" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("has default minHeight of 200px", () => {
    const { container } = render(<PageLoader />);
    const element = container.firstChild as HTMLElement;
    expect(element.style.minHeight).toBe("200px");
  });

  it("supports custom minHeight as number", () => {
    const { container } = render(<PageLoader minHeight={400} />);
    const element = container.firstChild as HTMLElement;
    expect(element.style.minHeight).toBe("400px");
  });

  it("supports custom minHeight as string", () => {
    const { container } = render(<PageLoader minHeight="50vh" />);
    const element = container.firstChild as HTMLElement;
    expect(element.style.minHeight).toBe("50vh");
  });
});
