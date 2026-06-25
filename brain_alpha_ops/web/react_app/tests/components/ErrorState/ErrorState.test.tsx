import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorState from "@/components/ErrorState/ErrorState";

describe("ErrorState", () => {
  describe("severity levels", () => {
    it("renders with error severity (default)", () => {
      render(<ErrorState title="发生错误" />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("发生错误")).toBeInTheDocument();
    });

    it("renders with warning severity", () => {
      render(<ErrorState title="警告信息" severity="warning" />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("警告信息")).toBeInTheDocument();
    });

    it("renders with info severity", () => {
      render(<ErrorState title="提示信息" severity="info" />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("提示信息")).toBeInTheDocument();
    });
  });

  describe("display levels", () => {
    it("renders with card display level (default)", () => {
      const { container } = render(<ErrorState title="错误标题" />);
      expect(container.querySelector(".error-card")).toBeInTheDocument();
    });

    it("renders with inline display level", () => {
      render(<ErrorState title="内联错误" displayLevel="inline" />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      const element = screen.getByRole("alert");
      expect(element.className).toContain("inline-flex");
    });

    it("renders with page display level", () => {
      render(<ErrorState title="页面错误" displayLevel="page" />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 3, name: "页面错误" })).toBeInTheDocument();
    });
  });

  describe("retry button", () => {
    it("renders retry button when onRetry is provided", () => {
      const onRetry = vi.fn();
      render(<ErrorState title="错误" onRetry={onRetry} />);
      expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    });

    it("does not render retry button when onRetry is not provided", () => {
      render(<ErrorState title="错误" />);
      expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    });

    it("calls onRetry when retry button is clicked", () => {
      const onRetry = vi.fn();
      render(<ErrorState title="错误" onRetry={onRetry} />);
      fireEvent.click(screen.getByRole("button", { name: "重试" }));
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("shows loading state on retry button", () => {
      const onRetry = vi.fn();
      render(<ErrorState title="错误" onRetry={onRetry} retryLoading={true} />);
      const button = screen.getByRole("button", { name: "重试中..." });
      expect(button).toBeInTheDocument();
      expect(button).toBeDisabled();
    });

    it("supports custom retry label", () => {
      const onRetry = vi.fn();
      render(<ErrorState title="错误" onRetry={onRetry} retryLabel="重新加载" />);
      expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
    });
  });

  describe("error details", () => {
    it("renders description when provided", () => {
      render(<ErrorState title="错误" description="详细描述信息" />);
      expect(screen.getByText("详细描述信息")).toBeInTheDocument();
    });

    it("renders details when provided", () => {
      render(<ErrorState title="错误" details="错误详情信息" displayLevel="page" />);
      expect(screen.getByText("错误详情信息")).toBeInTheDocument();
    });
  });

  it("renders custom icon", () => {
    const CustomIcon = () => <svg data-testid="custom-icon" />;
    render(<ErrorState title="错误" icon={<CustomIcon />} />);
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
  });

  it("renders children", () => {
    render(
      <ErrorState title="错误">
        <button type="button">自定义操作</button>
      </ErrorState>
    );
    expect(screen.getByRole("button", { name: "自定义操作" })).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(<ErrorState title="错误" className="custom-error" />);
    expect(container.querySelector(".custom-error")).toBeInTheDocument();
  });
});
