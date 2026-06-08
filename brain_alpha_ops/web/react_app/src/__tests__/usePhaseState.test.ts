/** Unit tests for usePhaseState hook */
import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
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

describe("usePhaseState", () => {
  it("returns connect phase when not connected", () => {
    const { result } = renderHook(() => usePhaseState(DEFAULT_INPUT));
    expect(result.current.currentPhase).toBe("connect");
  });

  it("returns discover phase when connected but no candidates", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      connected: true,
      contextFresh: true,
    }));
    expect(result.current.currentPhase).toBe("discover");
  });

  it("returns evaluate phase when candidates exist but readiness not passed", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      connected: true,
      contextFresh: true,
      candidatesCount: 5,
      scoredCount: 3,
    }));
    expect(result.current.currentPhase).toBe("evaluate");
  });

  it("returns ready phase when readiness passed", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      connected: true,
      contextFresh: true,
      candidatesCount: 5,
      scoredCount: 5,
      readinessPassed: true,
    }));
    expect(result.current.currentPhase).toBe("ready");
  });

  it("returns 5 step items", () => {
    const { result } = renderHook(() => usePhaseState(DEFAULT_INPUT));
    expect(result.current.steps.length).toBe(4);
    expect(result.current.steps[0].id).toBe("connect");
    expect(result.current.steps[3].id).toBe("ready");
  });

  it("marks first step as active when in connect phase", () => {
    const { result } = renderHook(() => usePhaseState(DEFAULT_INPUT));
    expect(result.current.steps[0].status).toBe("active");
  });

  it("marks earlier steps as complete and current as active", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      connected: true,
      contextFresh: true,
      candidatesCount: 5,
    }));
    expect(result.current.steps[0].status).toBe("complete");
    expect(result.current.steps[1].status).toBe("complete");
    expect(result.current.steps[2].status).toBe("active");
    expect(result.current.steps[3].status).toBe("pending");
  });

  it("computes overallProgress correctly", () => {
    const { result } = renderHook(() => usePhaseState({
      ...DEFAULT_INPUT,
      connected: true,
      contextFresh: true,
      candidatesCount: 5,
      scoredCount: 3,
    }));
    expect(result.current.phaseState.overallProgress).toBe(2); // connect + discover
  });

  it("returns phase labels in Chinese", () => {
    const { result } = renderHook(() => usePhaseState(DEFAULT_INPUT));
    expect(result.current.phaseState.phases.connect.label).toBe("连接与就绪");
    expect(result.current.phaseState.phases.discover.label).toBe("候选发现");
    expect(result.current.phaseState.phases.evaluate.label).toBe("评估与验证");
    expect(result.current.phaseState.phases.ready.label).toBe("提交就绪");
  });
});
