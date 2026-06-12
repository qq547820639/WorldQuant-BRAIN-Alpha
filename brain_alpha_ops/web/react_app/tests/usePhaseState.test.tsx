import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePhaseState } from "@/hooks/usePhaseState";
import type { CardViewId } from "@/types";

const DEFAULT_INPUT = {
  connected: false,
  contextFresh: false,
  candidatesCount: 0,
  scoredCount: 0,
  readinessPassed: false,
  activeView: "dashboard" as CardViewId,
};

describe("usePhaseState phase API status", () => {
  it("keeps loading state neutral before backend phase state is known", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      phaseStatus: "loading",
    }));

    expect(result.current.currentPhase).toBe("connect");
    expect(result.current.phaseState.phases.connect.label).toBe("读取本地状态");
    expect(result.current.phaseState.phases.connect.unlockCondition).toContain("读取完成前不判定为未连接");
    expect(result.current.steps[0].label).toBe("读取");
  });

  it("keeps read errors separate from disconnected setup", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      phaseStatus: "error",
    }));

    expect(result.current.currentPhase).toBe("connect");
    expect(result.current.phaseState.phases.connect.label).toBe("状态读取失败");
    expect(result.current.phaseState.phases.connect.unlockCondition).not.toContain("连接 BRAIN 账户");
    expect(result.current.steps[0].label).toBe("状态");
  });

  it("does not lock evaluation behind stale zero candidate counts after readiness passes", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      contextFresh: true,
      candidatesCount: 0,
      readinessPassed: true,
    }));

    expect(result.current.currentPhase).toBe("ready");
    expect(result.current.phaseState.phases.evaluate.status).toBe("complete");
  });
});
