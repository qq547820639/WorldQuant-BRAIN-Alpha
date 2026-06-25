import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import KpiCard from "@/components/KpiCard";
import Sidebar from "@/components/Sidebar";
import type { PhaseGroup } from "@/types";

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
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} phases={phaseGroups()} />);
    expect(screen.getByText("BRAIN Alpha Ops")).toBeInTheDocument();
    expect(screen.getByText("准备与就绪")).toBeInTheDocument();
    expect(screen.getByText("候选发现")).toBeInTheDocument();
    expect(screen.getByText("评估与验证")).toBeInTheDocument();
    expect(screen.getByText("提交就绪")).toBeInTheDocument();
    expect(screen.getByText("工具")).toBeInTheDocument();
  });

  it("renders all 10 nav items", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} phases={phaseGroups()} />);
    for (const label of ["云端同步", "运行总览", "候选管理", "回测监控", "科学评分", "质量门禁", "阻断复核", "续跑记录", "云端快照", "系统配置"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("highlights the active view", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    const dashboardBtn = screen.getByText("运行总览").closest("button");
    expect(dashboardBtn).toHaveClass("is-active");
  });

  it("shows badge counts when provided", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate}
      phases={phaseGroups({ candidates: 1247, official_backtests: "4/8" })}
      badges={{ candidates: 1247, cloud: "25.5k", official_backtests: "4/8" }} />);
    expect(screen.getByText("1247")).toBeInTheDocument();
    expect(screen.getByText("25.5k")).toBeInTheDocument();
    expect(screen.getByText("4/8")).toBeInTheDocument();
  });

  it("calls onNavigate when a nav item is clicked", () => {
    const handleNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={handleNavigate} phases={phaseGroups()} />);
    fireEvent.click(screen.getByText("候选管理"));
    expect(handleNavigate).toHaveBeenCalledWith("candidates");
  });

  it("shows user info section", () => {
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    expect(screen.getByText("operator")).toBeInTheDocument();
    expect(screen.getByText("本地非提交")).toBeInTheDocument();
  });
});

function phaseGroups(badges: { candidates?: number; official_backtests?: string } = {}): PhaseGroup[] {
  return [
    {
      id: "connect",
      label: "准备与就绪",
      status: "complete",
      expanded: true,
      unlockCondition: "连接 BRAIN 账户并具备本地缓存后解锁；后续同步可手动触发",
      items: [
        { id: "official_operations", label: "云端同步", icon: "00" },
        { id: "config", label: "系统配置", icon: "10" },
      ],
    },
    {
      id: "discover",
      label: "候选发现",
      status: "active",
      expanded: true,
      unlockCondition: "至少生成 1 个候选后解锁评分",
      items: [
        { id: "candidates", label: "候选管理", icon: "02", badge: badges.candidates },
        { id: "dashboard", label: "运行总览", icon: "01" },
      ],
    },
    {
      id: "evaluate",
      label: "评估与验证",
      status: "pending",
      expanded: true,
      unlockCondition: "完成至少 1 个候选评分",
      items: [
        { id: "scoring", label: "科学评分", icon: "04" },
        { id: "official_backtests", label: "回测监控", icon: "03", badge: badges.official_backtests },
        { id: "quality_check", label: "质量门禁", icon: "05" },
      ],
    },
    {
      id: "ready",
      label: "提交就绪",
      status: "pending",
      expanded: true,
      unlockCondition: "通过质量门禁后进入人工审核",
      items: [
        { id: "submission_confirm", label: "阻断复核", icon: "06" },
      ],
    },
  ];
}
