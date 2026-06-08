/**
 * usePhaseState — manages phase navigation state (UI Design System v3.0)
 * Maps backend state (connection, sync, candidates, scoring) to phase progression.
 */
import { useMemo, useCallback } from "react";
import type { PhaseId, PhaseGroup, PhaseState, StepGuideItem, CardViewId } from "@/types";

interface PhaseInput {
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  activeView: CardViewId;
}

export function usePhaseState(input: PhaseInput) {
  const { connected, contextFresh, candidatesCount, scoredCount, readinessPassed, activeView } = input;

  const determinePhase = useCallback((): PhaseId => {
    if (!connected || !contextFresh) return "connect";
    if (candidatesCount === 0) return "discover";
    if (!readinessPassed) return "evaluate";
    return "ready";
  }, [connected, contextFresh, candidatesCount, readinessPassed]);

  const currentPhase = determinePhase();

  const phases = useMemo<Record<PhaseId, PhaseGroup>>(() => ({
    connect: {
      id: "connect",
      label: "连接与就绪",
      status: currentPhase === "connect" ? "active" : "complete",
      expanded: currentPhase === "connect",
      unlockCondition: "连接 BRAIN 账户并完成云端同步后解锁下一步",
      items: [
        { id: "official_operations" as CardViewId, label: "云端同步", icon: "00" },
        { id: "config" as CardViewId, label: "系统配置", icon: "10" },
      ],
    },
    discover: {
      id: "discover",
      label: "候选发现",
      status: currentPhase === "discover" ? "active"
        : currentPhase === "connect" ? "pending"
        : "complete",
      expanded: currentPhase === "discover",
      unlockCondition: "至少生成 1 个候选后解锁评分",
      items: [
        { id: "candidates" as CardViewId, label: "候选管理", icon: "02", badge: candidatesCount || undefined },
        { id: "dashboard" as CardViewId, label: "运行总览", icon: "01" },
      ],
    },
    evaluate: {
      id: "evaluate",
      label: "评估与验证",
      status: currentPhase === "evaluate" ? "active"
        : currentPhase === "connect" || currentPhase === "discover" ? "pending"
        : "complete",
      expanded: currentPhase === "evaluate",
      unlockCondition: "完成至少 1 个候选评分",
      items: [
        { id: "scoring" as CardViewId, label: "科学评分", icon: "04", badge: scoredCount || undefined },
        { id: "official_backtests" as CardViewId, label: "回测监控", icon: "03" },
        { id: "quality_check" as CardViewId, label: "质量门禁", icon: "05" },
      ],
    },
    ready: {
      id: "ready",
      label: "提交就绪",
      status: currentPhase === "ready" ? (readinessPassed ? "complete" : "active")
        : "pending",
      expanded: currentPhase === "ready",
      unlockCondition: "通过质量门禁后进入人工审核",
      items: [
        { id: "submission_confirm" as CardViewId, label: "阻断复核", icon: "06" },
      ],
    },
  }), [currentPhase, candidatesCount, scoredCount, readinessPassed]);

  const steps = useMemo<StepGuideItem[]>(() => {
    const allPhases: PhaseId[] = ["connect", "discover", "evaluate", "ready"];
    return allPhases.map((pid) => {
      const p = phases[pid];
      let status: StepGuideItem["status"] = "pending";
      if (p.status === "complete") status = "complete";
      else if (p.status === "active") status = "active";
      return { id: pid, label: pid === "connect" ? "连接" : pid === "discover" ? "搜索" : pid === "evaluate" ? "评分" : "提交", status, phase: pid };
    });
  }, [phases]);

  const phaseState: PhaseState = { currentPhase, phases, overallProgress: steps.filter((s) => s.status === "complete").length };

  return { phaseState, steps, currentPhase };
}
