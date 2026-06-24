import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ErrorCard from "@/components/ErrorCard";

describe("ErrorCard", () => {
  it("renders with default error severity", () => {
    render(<ErrorCard title="测试错误标题" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("测试错误标题")).toBeInTheDocument();
  });

  it("renders with details and reason", () => {
    render(
      <ErrorCard
        title="加载失败"
        details="无法连接到服务器"
        reason="网络超时"
      />,
    );
    expect(screen.getByText("加载失败")).toBeInTheDocument();
    expect(screen.getByText("无法连接到服务器")).toBeInTheDocument();
    expect(screen.getByText(/原因：网络超时/)).toBeInTheDocument();
  });

  it("renders retry button when onRetry provided", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorCard title="错误" onRetry={onRetry} />);

    const retryButton = screen.getByRole("button", { name: "重试" });
    expect(retryButton).toBeInTheDocument();

    await user.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not render retry button when onRetry not provided", () => {
    render(<ErrorCard title="错误" />);
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  });

  it("renders with warning severity", () => {
    render(<ErrorCard title="警告信息" severity="warning" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("警告信息")).toBeInTheDocument();
  });

  it("renders with info severity", () => {
    render(<ErrorCard title="提示信息" severity="info" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("提示信息")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(<ErrorCard title="测试" className="custom-class" />);
    expect(container.firstChild).toHaveClass("custom-class");
  });

  it("matches snapshot with all props", () => {
    const { container } = render(
      <ErrorCard
        title="快照测试标题"
        details="快照测试详情"
        reason="快照测试原因"
        severity="error"
        onRetry={() => {}}
        className="snapshot-test-class"
      />,
    );
    expect(container).toMatchSnapshot();
  });
});
