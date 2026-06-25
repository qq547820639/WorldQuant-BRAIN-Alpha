import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ButtonLoader from "@/components/LoadingState/ButtonLoader";

describe("ButtonLoader", () => {
  it("renders children when not loading", () => {
    render(<ButtonLoader loading={false}>提交</ButtonLoader>);
    expect(screen.getByText("提交")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders spinner when loading", () => {
    render(<ButtonLoader loading={true}>提交</ButtonLoader>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("提交")).toBeInTheDocument();
  });

  it("has spinner with xs size by default", () => {
    const { container } = render(<ButtonLoader loading={true}>提交</ButtonLoader>);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "12");
  });

  it("supports different spinner sizes", () => {
    const { rerender, container } = render(
      <ButtonLoader loading={true} size="xs">
        提交
      </ButtonLoader>
    );
    let svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "12");

    rerender(
      <ButtonLoader loading={true} size="sm">
        提交
      </ButtonLoader>
    );
    svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "16");

    rerender(
      <ButtonLoader loading={true} size="md">
        提交
      </ButtonLoader>
    );
    svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "24");
  });

  it("children have opacity 0 when loading", () => {
    render(<ButtonLoader loading={true}>提交</ButtonLoader>);
    const textSpan = screen.getByText("提交");
    expect(textSpan.style.opacity).toBe("0");
  });

  it("children have opacity 1 when not loading", () => {
    render(<ButtonLoader loading={false}>提交</ButtonLoader>);
    const textSpan = screen.getByText("提交");
    expect(textSpan.style.opacity).toBe("1");
  });

  it("applies custom className", () => {
    const { container } = render(
      <ButtonLoader className="custom-btn-loader">提交</ButtonLoader>
    );
    expect(container.firstChild).toHaveClass("custom-btn-loader");
  });
});
