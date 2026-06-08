import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import KpiCard from "@/components/KpiCard";
import Sidebar from "@/components/Sidebar";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="候选总数" value={1247} />);
    expect(screen.getByText("候选总数")).toBeInTheDocument();
    expect(screen.getByText("1247")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "候选总数: 1247");
  });

  it("renders subtitle with neutral trend", () => {
    render(<KpiCard label="Sharpe" value={1.68} subtitle="+0.12 vs 上次" trend="up" />);
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("1.68")).toBeInTheDocument();
    expect(screen.getByText("+0.12 vs 上次")).toBeInTheDocument();
    // trend up uses text-positive class
    expect(screen.getByText("+0.12 vs 上次")).toHaveClass("text-positive");
  });

  it("renders negative trend correctly", () => {
    render(<KpiCard label="回撤" value={-0.05} trend="down" />);
    expect(screen.getByText("-0.05")).toBeInTheDocument();
  });

  it("renders without subtitle", () => {
    render(<KpiCard label="槽位" value="4/8" />);
    expect(screen.getByText("4/8")).toBeInTheDocument();
    expect(screen.queryByText(/上次/)).not.toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  const onNavigate = () => {};

  it("renders all navigation sections", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    expect(screen.getByText("Alpha Ops")).toBeInTheDocument();
    expect(screen.getByText("工作流程")).toBeInTheDocument();
    expect(screen.getByText("工具")).toBeInTheDocument();
  });

  it("renders all 10 nav items", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    expect(screen.getByText("官方操作")).toBeInTheDocument();
    expect(screen.getByText("运行总览")).toBeInTheDocument();
    expect(screen.getByText("候选管理")).toBeInTheDocument();
    expect(screen.getByText("回测监控")).toBeInTheDocument();
    expect(screen.getByText("科学评分")).toBeInTheDocument();
    expect(screen.getByText("质量门禁")).toBeInTheDocument();
    expect(screen.getByText("阻断复核")).toBeInTheDocument();
    expect(screen.getByText("续跑记录")).toBeInTheDocument();
    expect(screen.getByText("云端快照")).toBeInTheDocument();
    expect(screen.getByText("系统配置")).toBeInTheDocument();
  });

  it("highlights the active view", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    const dashboardBtn = screen.getByText("运行总览").closest("button");
    expect(dashboardBtn).toHaveClass("is-active");
  });

  it("shows badge counts when provided", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate}
      badges={{ candidates: 1247, cloud: "25.5k", official_backtests: "4/8" }} />);
    expect(screen.getByText("1247")).toBeInTheDocument();
    expect(screen.getByText("25.5k")).toBeInTheDocument();
    expect(screen.getByText("4/8")).toBeInTheDocument();
  });

  it("calls onNavigate when a nav item is clicked", () => {
    const handleNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={handleNavigate} />);
    fireEvent.click(screen.getByText("候选管理"));
    expect(handleNavigate).toHaveBeenCalledWith("candidates");
  });

  it("shows user info section", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    expect(screen.getByText("operator")).toBeInTheDocument();
    expect(screen.getByText("本地非提交")).toBeInTheDocument();
  });
});
