import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders with title only", () => {
    render(<EmptyState title="暂无数据" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "暂无数据" })).toBeInTheDocument();
  });

  it("renders with title and description", () => {
    render(
      <EmptyState
        title="暂无候选"
        description="点击开始按钮生成第一批候选"
      />,
    );
    expect(screen.getByRole("heading", { name: "暂无候选" })).toBeInTheDocument();
    expect(screen.getByText("点击开始按钮生成第一批候选")).toBeInTheDocument();
  });

  it("renders with children (CTA button)", () => {
    render(
      <EmptyState title="空状态">
        <button type="button">开始操作</button>
      </EmptyState>,
    );
    expect(screen.getByRole("button", { name: "开始操作" })).toBeInTheDocument();
  });

  it("renders with custom icon", () => {
    const CustomIcon = () => <svg data-testid="custom-icon" />;
    render(<EmptyState title="测试" icon={<CustomIcon />} />);
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
  });

  it("renders default icon when no icon provided", () => {
    const { container } = render(<EmptyState title="测试" />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(<EmptyState title="测试" className="custom-empty" />);
    expect(container.firstChild).toHaveClass("custom-empty");
  });

  it("matches snapshot with all props", () => {
    const { container } = render(
      <EmptyState
        title="快照测试标题"
        description="快照测试描述"
        className="snapshot-empty"
      >
        <button type="button">操作按钮</button>
      </EmptyState>,
    );
    expect(container).toMatchSnapshot();
  });
});
