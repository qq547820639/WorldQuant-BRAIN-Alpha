/**
 * usePhaseState — manages phase navigation state (UI Design System v3.0)
 * Maps backend state (connection, sync, candidates, scoring) to phase progression.
 */
import { useMemo, useCallback } from "react";
import type { PhaseId, PhaseGroup, PhaseState, StepGuideItem, CardViewId } from "@/types";

export type PhaseApiStatus = "loading" | "error" | "ready";

interface PhaseInput {
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  activeView: CardViewId;
  phaseStatus?: PhaseApiStatus;
}

export function usePhaseState(input: PhaseInput) {
  const { connected, contextFresh, candidatesCount, scoredCount, readinessPassed, activeView, phaseStatus = "ready" } = input;

  const determinePhase = useCallback((): PhaseId => {
    if (phaseStatus !== "ready") return "connect";
    if (!contextFresh) return "connect";
    if (readinessPassed) return "ready";
    if (candidatesCount === 0) return "discover";
    if (!readinessPassed) return "evaluate";
    return "ready";
  }, [phaseStatus, contextFresh, candidatesCount, readinessPassed]);

  const currentPhase = determinePhase();
  const phasePending = phaseStatus === "loading";
  const phaseError = phaseStatus === "error";

  const phases = useMemo<Record<PhaseId, PhaseGroup>>(() => ({
    connect: {
      id: "connect",
      label: phasePending ? "读取本地状态" : phaseError ? "状态读取失败" : "准备与就绪",
      status: currentPhase === "connect" ? "active" : "complete",
      expanded: currentPhase === "connect",
      unlockCondition: phasePending
        ? "正在读取本地 session 与缓存状态；读取完成前不判定为未连接"
        : phaseError
          ? "暂时无法确认 BRAIN 账户连接和本地缓存状态；请刷新或稍后重试"
          : contextFresh
        ? connected
          ? "BRAIN 账户已连接，本地缓存可用；后续同步可手动触发"
          : "本地缓存可用；BRAIN 账户仅在同步、官方回测或提交前复核时需要"
        : connected
          ? "BRAIN 已连接；未检测到完整本地缓存，请执行首次同步"
          : "连接 BRAIN 账户或使用已有本地缓存后继续；后续同步可手动触发",
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
      unlockCondition: "主池保留至少 1 个可推进候选后解锁评估",
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
      unlockCondition: "自动模拟与质量门槛检查完成后进入人工复核",
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
  }), [connected, contextFresh, currentPhase, candidatesCount, scoredCount, readinessPassed, phasePending, phaseError]);

  const steps = useMemo<StepGuideItem[]>(() => {
    const allPhases: PhaseId[] = ["connect", "discover", "evaluate", "ready"];
    return allPhases.map((pid) => {
      const p = phases[pid];
      let status: StepGuideItem["status"] = "pending";
      if (p.status === "complete") status = "complete";
      else if (p.status === "active") status = "active";
      return {
        id: pid,
        label: pid === "connect"
          ? phasePending ? "读取" : phaseError ? "状态" : "准备"
          : pid === "discover" ? "搜索"
          : pid === "evaluate" ? "评分"
          : "提交",
        status,
        phase: pid,
      };
    });
  }, [phases, phasePending, phaseError]);

  const phaseState: PhaseState = { currentPhase, phases, overallProgress: steps.filter((s) => s.status === "complete").length };

  return { phaseState, steps, currentPhase };
}
