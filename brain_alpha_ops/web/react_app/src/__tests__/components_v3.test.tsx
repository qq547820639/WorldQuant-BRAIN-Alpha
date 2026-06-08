/** Unit tests for new v3.0 components — PhaseShell, StepGuide, MobileTabBar, EmptyState, usePhaseState */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PhaseShell from "@/components/PhaseShell";
import StepGuide from "@/components/StepGuide";
import MobileTabBar from "@/components/MobileTabBar";
import EmptyState from "@/components/EmptyState";

// ── StepGuide ────────────────────────────────────────────────

describe("StepGuide", () => {
  const steps = [
    { id: "connect", label: "连接", status: "complete" as const, phase: "connect" as const },
    { id: "discover", label: "搜索", status: "active" as const, phase: "discover" as const },
    { id: "evaluate", label: "评分", status: "pending" as const, phase: "evaluate" as const },
    { id: "ready", label: "提交", status: "pending" as const, phase: "ready" as const },
  ];

  it("renders all steps", () => {
    render(<StepGuide steps={steps} />);
    expect(screen.getByText("连接")).toBeDefined();
    expect(screen.getByText("搜索")).toBeDefined();
    expect(screen.getByText("评分")).toBeDefined();
    expect(screen.getByText("提交")).toBeDefined();
  });

  it("renders nothing when steps array is empty", () => {
    const { container } = render(<StepGuide steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("applies complete class to completed steps", () => {
    render(<StepGuide steps={steps} />);
    const completeStep = screen.getByText("连接").closest(".step");
    expect(completeStep?.className).toContain("complete");
  });

  it("applies active class to current step", () => {
    render(<StepGuide steps={steps} />);
    const activeStep = screen.getByText("搜索").closest(".step");
    expect(activeStep?.className).toContain("active");
  });

  it("has accessible list role", () => {
    render(<StepGuide steps={steps} />);
    expect(screen.getByRole("list")).toBeDefined();
  });
});

// ── PhaseShell ───────────────────────────────────────────────

describe("PhaseShell", () => {
  const steps = [
    { id: "connect", label: "连接", status: "complete" as const, phase: "connect" as const },
    { id: "discover", label: "搜索", status: "active" as const, phase: "discover" as const },
  ];

  it("renders phase label and unlock condition", () => {
    render(
      <PhaseShell
        phaseId="discover"
        phaseLabel="候选发现"
        statusLabel="进行中"
        statusTone="active"
        unlockCondition="至少生成 1 个候选"
        steps={steps}
      >
        <div data-testid="child">content</div>
      </PhaseShell>,
    );
    expect(screen.getByText("候选发现")).toBeDefined();
    expect(screen.getByText("至少生成 1 个候选")).toBeDefined();
    expect(screen.getByTestId("child")).toBeDefined();
  });

  it("renders correct status badge for different tones", () => {
    const { rerender } = render(
      <PhaseShell phaseId="connect" phaseLabel="连接" statusLabel="已完成" statusTone="complete" unlockCondition="done" steps={steps}>
        <div />
      </PhaseShell>,
    );
    expect(screen.getByText("已完成").className).toContain("badge-positive");

    rerender(
      <PhaseShell phaseId="connect" phaseLabel="连接" statusLabel="已阻断" statusTone="blocked" unlockCondition="done" steps={steps}>
        <div />
      </PhaseShell>,
    );
    expect(screen.getByText("已阻断").className).toContain("badge-negative");
  });
});

// ── MobileTabBar ─────────────────────────────────────────────

describe("MobileTabBar", () => {
  it("renders 4 tabs", () => {
    render(<MobileTabBar activePhase="connect" onNavigate={vi.fn()} />);
    const tabs = screen.getAllByRole("button");
    expect(tabs.length).toBe(4);
  });

  it("marks active tab with aria-current", () => {
    render(<MobileTabBar activePhase="discover" onNavigate={vi.fn()} />);
    const tabs = screen.getAllByRole("button");
    const activeTab = tabs.find((t) => t.getAttribute("aria-current") === "true");
    expect(activeTab).toBeDefined();
    expect(activeTab?.textContent).toContain("候选");
  });

  it("calls onNavigate when tab is clicked", () => {
    const onNavigate = vi.fn();
    render(<MobileTabBar activePhase="connect" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("评估"));
    expect(onNavigate).toHaveBeenCalledWith("evaluate");
  });

  it("has navigation role", () => {
    const { container } = render(<MobileTabBar activePhase="connect" onNavigate={vi.fn()} />);
    expect(container.querySelector('[role="navigation"]')).toBeDefined();
  });
});

// ── EmptyState ───────────────────────────────────────────────

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(<EmptyState title="暂无候选" description="开始生产搜索" />);
    expect(screen.getByText("暂无候选")).toBeDefined();
    expect(screen.getByText("开始生产搜索")).toBeDefined();
  });

  it("renders action button when provided", () => {
    const onClick = vi.fn();
    render(<EmptyState title="空" action={{ label: "开始", onClick }} />);
    fireEvent.click(screen.getByText("开始"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders hint when provided", () => {
    render(<EmptyState title="空" hint="请先连接账户" />);
    expect(screen.getByText("请先连接账户")).toBeDefined();
  });

  it("has status role for accessibility", () => {
    render(<EmptyState title="空" />);
    expect(screen.getByRole("status")).toBeDefined();
  });
});
