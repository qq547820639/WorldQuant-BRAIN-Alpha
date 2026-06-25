import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Spinner from "@/components/LoadingState/Spinner";

describe("Spinner", () => {
  it("renders with default md size", () => {
    render(<Spinner />);
    const spinner = screen.getByRole("status");
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveAttribute("aria-label", "加载中");
  });

  it("renders with sm size", () => {
    const { container } = render(<Spinner size="sm" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "16");
    expect(svg).toHaveAttribute("height", "16");
  });

  it("renders with md size", () => {
    const { container } = render(<Spinner size="md" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "24");
    expect(svg).toHaveAttribute("height", "24");
  });

  it("renders with lg size", () => {
    const { container } = render(<Spinner size="lg" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "32");
    expect(svg).toHaveAttribute("height", "32");
  });

  it("renders with xl size", () => {
    const { container } = render(<Spinner size="xl" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
    expect(svg).toHaveAttribute("height", "48");
  });

  it("renders with xs size", () => {
    const { container } = render(<Spinner size="xs" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "12");
    expect(svg).toHaveAttribute("height", "12");
  });

  it("applies custom className", () => {
    render(<Spinner className="custom-spinner" />);
    const spinner = screen.getByRole("status");
    expect(spinner.className).toContain("custom-spinner");
  });

  it("supports custom label", () => {
    render(<Spinner label="处理中" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "处理中");
  });

  it("supports custom color", () => {
    const { container } = render(<Spinner color="#ff0000" />);
    const svg = container.querySelector("svg");
    const paths = svg?.querySelectorAll("circle, path");
    expect(paths?.length).toBeGreaterThan(0);
  });

  it("has svg with aria-hidden", () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});
