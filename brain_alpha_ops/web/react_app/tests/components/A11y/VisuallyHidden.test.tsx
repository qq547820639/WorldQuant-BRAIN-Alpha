import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VisuallyHidden from "@/components/A11y/VisuallyHidden";

describe("VisuallyHidden", () => {
  it("renders with default span tag", () => {
    render(<VisuallyHidden>Hidden text</VisuallyHidden>);
    const element = screen.getByText("Hidden text");
    expect(element.tagName.toLowerCase()).toBe("span");
  });

  it("renders with different tags (div, p, h1-h6, label)", () => {
    const { rerender } = render(<VisuallyHidden as="div">Content</VisuallyHidden>);
    expect(screen.getByText("Content").tagName.toLowerCase()).toBe("div");

    rerender(<VisuallyHidden as="p">Content</VisuallyHidden>);
    expect(screen.getByText("Content").tagName.toLowerCase()).toBe("p");

    rerender(<VisuallyHidden as="h1">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 1, name: "Content" })).toBeInTheDocument();

    rerender(<VisuallyHidden as="h2">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 2, name: "Content" })).toBeInTheDocument();

    rerender(<VisuallyHidden as="h3">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 3, name: "Content" })).toBeInTheDocument();

    rerender(<VisuallyHidden as="h4">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 4, name: "Content" })).toBeInTheDocument();

    rerender(<VisuallyHidden as="h5">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 5, name: "Content" })).toBeInTheDocument();

    rerender(<VisuallyHidden as="h6">Content</VisuallyHidden>);
    expect(screen.getByRole("heading", { level: 6, name: "Content" })).toBeInTheDocument();
  });

  it("applies visually hidden styles", () => {
    render(<VisuallyHidden>Hidden</VisuallyHidden>);
    const element = screen.getByText("Hidden");
    const style = element.style;

    expect(style.position).toBe("absolute");
    expect(style.width).toBe("1px");
    expect(style.height).toBe("1px");
    expect(style.padding).toBe("0px");
    expect(style.overflow).toBe("hidden");
    expect(style.clip).toBe("rect(0px, 0px, 0px, 0px)");
    expect(style.whiteSpace).toBe("nowrap");
    expect(style.border).toBe("0px");
  });

  it("renders children content", () => {
    render(
      <VisuallyHidden>
        <span data-testid="child">Child element</span>
      </VisuallyHidden>
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByText("Child element")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    render(<VisuallyHidden className="custom-class">Content</VisuallyHidden>);
    const element = screen.getByText("Content");
    expect(element.className).toContain("custom-class");
  });

  it("passes through additional props like id and htmlFor", () => {
    render(
      <VisuallyHidden as="label" htmlFor="input-id" id="label-id">
        Label text
      </VisuallyHidden>
    );
    const element = screen.getByText("Label text");
    expect(element.id).toBe("label-id");
    expect(element).toHaveAttribute("for", "input-id");
  });
});
