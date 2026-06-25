import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { SSEEvent, Candidate } from "@/types";
import { useCandidateActions } from "@/hooks/useCandidateActions";
import type { CandidatePipeline } from "@/hooks/useCandidatePipeline";
import { useCandidateSSEHandlers } from "@/hooks/useCandidateSSEHandlers";

const mockGenerateCandidates = vi.fn();
const mockHandleTaskEvent = vi.fn();
const mockHandleTaskStreamExhausted = vi.fn();

const mockStartSimulation = vi.fn();
const mockStartOfficialValidationQueue = vi.fn();
const mockHandleSimEvent = vi.fn();
const mockHandleSimStreamExhausted = vi.fn();
const mockNextBatchCheckCandidatesRef = { current: null as Candidate[] | null };

const mockStartOptimization = vi.fn();
const mockHandleOptimizationEvent = vi.fn();
const mockHandleOptimizationStreamExhausted = vi.fn();
const mockMAX_AUTO_OPTIMIZATION_CYCLES = 3;
const mockAUTO_SIMULATION_BATCH_SIZE = 5;
const mockOptimizationCandidatesForPool = vi.fn();

const mockStartSingleCheck = vi.fn();
const mockStartBatchCheck = vi.fn();
const mockHandleCheckEvent = vi.fn();
const mockHandleCheckStreamExhausted = vi.fn();
const mockLastBatchCheckCandidatesRef = { current: null as Candidate[] | null };

const mockSSEHandleTaskEvent = vi.fn();
const mockSSEHandleTaskStreamExhausted = vi.fn();
const mockSSEHandleSimEvent = vi.fn();
const mockSSEHandleSimStreamExhausted = vi.fn();
const mockSSEHandleOptimizationEvent = vi.fn();
const mockSSEHandleOptimizationStreamExhausted = vi.fn();
const mockSSEHandleCheckEvent = vi.fn();
const mockSSEHandleCheckStreamExhausted = vi.fn();

vi.mock("@/hooks/useCandidateGeneration", () => ({
  useCandidateGeneration: vi.fn(() => ({
    generateCandidates: mockGenerateCandidates,
    handleTaskEvent: mockHandleTaskEvent,
    handleTaskStreamExhausted: mockHandleTaskStreamExhausted,
  })),
}));

vi.mock("@/hooks/useCandidateSimulation", () => ({
  useCandidateSimulation: vi.fn(() => ({
    startSimulation: mockStartSimulation,
    startOfficialValidationQueue: mockStartOfficialValidationQueue,
    handleSimEvent: mockHandleSimEvent,
    handleSimStreamExhausted: mockHandleSimStreamExhausted,
    nextBatchCheckCandidatesRef: mockNextBatchCheckCandidatesRef,
  })),
}));

vi.mock("@/hooks/useCandidateOptimization", () => ({
  useCandidateOptimization: vi.fn(() => ({
    startOptimization: mockStartOptimization,
    handleOptimizationEvent: mockHandleOptimizationEvent,
    handleOptimizationStreamExhausted: mockHandleOptimizationStreamExhausted,
    MAX_AUTO_OPTIMIZATION_CYCLES: mockMAX_AUTO_OPTIMIZATION_CYCLES,
    AUTO_SIMULATION_BATCH_SIZE: mockAUTO_SIMULATION_BATCH_SIZE,
    optimizationCandidatesForPool: mockOptimizationCandidatesForPool,
  })),
  optimizationCandidatesForPool: vi.fn(),
}));

vi.mock("@/hooks/useCandidateCheck", () => ({
  useCandidateCheck: vi.fn(() => ({
    startSingleCheck: mockStartSingleCheck,
    startBatchCheck: mockStartBatchCheck,
    handleCheckEvent: mockHandleCheckEvent,
    handleCheckStreamExhausted: mockHandleCheckStreamExhausted,
    lastBatchCheckCandidatesRef: mockLastBatchCheckCandidatesRef,
  })),
}));

vi.mock("@/hooks/useCandidateSSEHandlers", () => ({
  useCandidateSSEHandlers: vi.fn(() => ({
    handleTaskEvent: mockSSEHandleTaskEvent,
    handleTaskStreamExhausted: mockSSEHandleTaskStreamExhausted,
    handleSimEvent: mockSSEHandleSimEvent,
    handleSimStreamExhausted: mockSSEHandleSimStreamExhausted,
    handleOptimizationEvent: mockSSEHandleOptimizationEvent,
    handleOptimizationStreamExhausted: mockSSEHandleOptimizationStreamExhausted,
    handleCheckEvent: mockSSEHandleCheckEvent,
    handleCheckStreamExhausted: mockSSEHandleCheckStreamExhausted,
  })),
}));

function createMockPipeline(): CandidatePipeline {
  return {
    task: {
      state: "idle",
      progress: null,
      error: null,
      jobId: null,
      setState: vi.fn(),
      setProgress: vi.fn(),
      setError: vi.fn(),
      setJobId: vi.fn(),
    },
    simulation: {
      state: "idle",
      progress: null,
      error: null,
      jobId: null,
      setState: vi.fn(),
      setProgress: vi.fn(),
      setError: vi.fn(),
      setJobId: vi.fn(),
    },
    optimization: {
      state: "idle",
      progress: null,
      error: null,
      jobId: null,
      setState: vi.fn(),
      setProgress: vi.fn(),
      setError: vi.fn(),
      setJobId: vi.fn(),
    },
    check: {
      state: "idle",
      progress: null,
      error: null,
      jobId: null,
      setState: vi.fn(),
      setProgress: vi.fn(),
      setError: vi.fn(),
      setJobId: vi.fn(),
    },
    checkingAlphaId: null,
    setCheckingAlphaId: vi.fn(),
    taskSuccessBanner: null,
    setTaskSuccessBanner: vi.fn(),
    autoPipelineStage: "idle",
    autoPipelineStageRef: { current: "idle" as const },
    updateAutoPipelineStage: vi.fn(),
    resetAutoPipelineStageIfCurrent: vi.fn(),
    autoOptimizationCycles: 0,
    setAutoOptimizationCycles: vi.fn(),
  };
}

function createDefaultDeps() {
  return {
    pipeline: createMockPipeline(),
    callApi: vi.fn(),
    callSingleCheckApi: vi.fn(),
    callBatchCheckApi: vi.fn(),
    loadCandidates: vi.fn(),
    refreshCheckResults: vi.fn(),
    onCandidatePoolUpdated: vi.fn(),
    notify: vi.fn(),
    credentials: { username: "testuser", password: "testpass", token: "testtoken" },
    candidates: [] as Candidate[],
    retainedPoolCandidates: [] as Candidate[],
    poolEligibleCandidates: [] as Candidate[],
    serverWorkflowPlan: null,
    targetPoolSize: 10,
  };
}

describe("useCandidateActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNextBatchCheckCandidatesRef.current = null;
    mockLastBatchCheckCandidatesRef.current = null;
  });

  describe("buildCredentialOverrides", () => {
    it("returns correct overrides with complete credentials", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({
        username: "testuser",
        password: "testpass",
        token: "testtoken",
      });
    });

    it("returns empty object with empty credentials", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "", password: "", token: "" },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({});
    });

    it("returns empty object when credentials is undefined", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: undefined,
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({});
    });

    it("handles partial credentials - only username", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "testuser", password: "", token: "" },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({ username: "testuser" });
    });

    it("handles partial credentials - only password", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "", password: "testpass", token: "" },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({ password: "testpass" });
    });

    it("handles partial credentials - only token", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "", password: "", token: "testtoken" },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({ token: "testtoken" });
    });

    it("trims whitespace from username and token", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "  testuser  ", password: "testpass", token: "  testtoken  " },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({
        username: "testuser",
        password: "testpass",
        token: "testtoken",
      });
    });

    it("does not include username if only whitespace", () => {
      const deps = {
        ...createDefaultDeps(),
        credentials: { username: "   ", password: "testpass", token: "testtoken" },
      };
      const { result } = renderHook(() => useCandidateActions(deps));

      const overrides = result.current.buildCredentialOverrides();

      expect(overrides).toEqual({
        password: "testpass",
        token: "testtoken",
      });
    });
  });

  describe("hook initialization", () => {
    it("returns all expected methods", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      expect(typeof result.current.generateCandidates).toBe("function");
      expect(typeof result.current.startSimulation).toBe("function");
      expect(typeof result.current.startOfficialValidationQueue).toBe("function");
      expect(typeof result.current.startOptimization).toBe("function");
      expect(typeof result.current.startSingleCheck).toBe("function");
      expect(typeof result.current.startBatchCheck).toBe("function");
      expect(typeof result.current.handleTaskEvent).toBe("function");
      expect(typeof result.current.handleTaskStreamExhausted).toBe("function");
      expect(typeof result.current.handleSimEvent).toBe("function");
      expect(typeof result.current.handleSimStreamExhausted).toBe("function");
      expect(typeof result.current.handleOptimizationEvent).toBe("function");
      expect(typeof result.current.handleOptimizationStreamExhausted).toBe("function");
      expect(typeof result.current.handleCheckEvent).toBe("function");
      expect(typeof result.current.handleCheckStreamExhausted).toBe("function");
      expect(typeof result.current.buildCredentialOverrides).toBe("function");
      expect(result.current.nextBatchCheckCandidatesRef).toBeDefined();
      expect(result.current.lastBatchCheckCandidatesRef).toBeDefined();
    });

    it("maintains stable method references across re-renders", () => {
      const deps = createDefaultDeps();
      const { result, rerender } = renderHook(() => useCandidateActions(deps));

      const firstGenerateCandidates = result.current.generateCandidates;
      const firstStartSimulation = result.current.startSimulation;
      const firstStartOptimization = result.current.startOptimization;
      const firstStartSingleCheck = result.current.startSingleCheck;
      const firstStartBatchCheck = result.current.startBatchCheck;
      const firstBuildCredentialOverrides = result.current.buildCredentialOverrides;
      const firstHandleTaskEvent = result.current.handleTaskEvent;
      const firstHandleSimEvent = result.current.handleSimEvent;
      const firstHandleOptimizationEvent = result.current.handleOptimizationEvent;
      const firstHandleCheckEvent = result.current.handleCheckEvent;

      rerender();

      expect(result.current.generateCandidates).toBe(firstGenerateCandidates);
      expect(result.current.startSimulation).toBe(firstStartSimulation);
      expect(result.current.startOptimization).toBe(firstStartOptimization);
      expect(result.current.startSingleCheck).toBe(firstStartSingleCheck);
      expect(result.current.startBatchCheck).toBe(firstStartBatchCheck);
      expect(result.current.buildCredentialOverrides).toBe(firstBuildCredentialOverrides);
      expect(result.current.handleTaskEvent).toBe(firstHandleTaskEvent);
      expect(result.current.handleSimEvent).toBe(firstHandleSimEvent);
      expect(result.current.handleOptimizationEvent).toBe(firstHandleOptimizationEvent);
      expect(result.current.handleCheckEvent).toBe(firstHandleCheckEvent);
    });
  });

  describe("method delegation", () => {
    it("delegates generateCandidates to useCandidateGeneration", async () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockPoolSnapshot = { eligibleCount: 5, retainedCount: 3, deficit: 5, retainedCandidates: [] as Candidate[] };
      await act(async () => {
        await result.current.generateCandidates(mockPoolSnapshot as any);
      });

      expect(mockGenerateCandidates).toHaveBeenCalledWith(mockPoolSnapshot);
    });

    it("delegates startSimulation to useCandidateSimulation", async () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockCandidate = { alpha_id: "alpha_1" } as Candidate;
      const mockOverride = [{ alpha_id: "alpha_2" }] as Candidate[];
      await act(async () => {
        await result.current.startSimulation(mockCandidate, mockOverride);
      });

      expect(mockStartSimulation).toHaveBeenCalledWith(mockCandidate, mockOverride);
    });

    it("delegates startOptimization to useCandidateOptimization", async () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockPoolSnapshot = { eligibleCount: 5, retainedCount: 3, deficit: 5, retainedCandidates: [] as Candidate[] };
      const mockOverride = [{ alpha_id: "alpha_1" }] as Candidate[];
      await act(async () => {
        await result.current.startOptimization(mockPoolSnapshot as any, mockOverride);
      });

      expect(mockStartOptimization).toHaveBeenCalledWith(mockPoolSnapshot, mockOverride);
    });

    it("delegates startSingleCheck to useCandidateCheck", async () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockCandidate = { alpha_id: "alpha_1" } as Candidate;
      await act(async () => {
        await result.current.startSingleCheck(mockCandidate);
      });

      expect(mockStartSingleCheck).toHaveBeenCalledWith(mockCandidate);
    });

    it("delegates startBatchCheck to useCandidateCheck", async () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockOverride = [{ alpha_id: "alpha_1" }] as Candidate[];
      await act(async () => {
        await result.current.startBatchCheck(mockOverride);
      });

      expect(mockStartBatchCheck).toHaveBeenCalledWith(mockOverride);
    });

    it("passes nextBatchCheckCandidatesRef from simulation", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      expect(result.current.nextBatchCheckCandidatesRef).toBe(mockNextBatchCheckCandidatesRef);
    });

    it("passes lastBatchCheckCandidatesRef from check", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      expect(result.current.lastBatchCheckCandidatesRef).toBe(mockLastBatchCheckCandidatesRef);
    });

    it("delegates startOfficialValidationQueue to simulation", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      act(() => {
        result.current.startOfficialValidationQueue();
      });

      expect(mockStartOfficialValidationQueue).toHaveBeenCalled();
    });
  });

  describe("SSE event handling", () => {
    it("delegates handleTaskEvent to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockEvent = { type: "progress", data: { phase: "test" } } as SSEEvent;
      act(() => {
        result.current.handleTaskEvent(mockEvent);
      });

      expect(mockSSEHandleTaskEvent).toHaveBeenCalledWith(mockEvent);
    });

    it("delegates handleTaskStreamExhausted to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      act(() => {
        result.current.handleTaskStreamExhausted();
      });

      expect(mockSSEHandleTaskStreamExhausted).toHaveBeenCalled();
    });

    it("delegates handleSimEvent to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockEvent = { type: "progress", data: { phase: "simulation" } } as SSEEvent;
      act(() => {
        result.current.handleSimEvent(mockEvent);
      });

      expect(mockSSEHandleSimEvent).toHaveBeenCalledWith(mockEvent);
    });

    it("delegates handleSimStreamExhausted to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      act(() => {
        result.current.handleSimStreamExhausted();
      });

      expect(mockSSEHandleSimStreamExhausted).toHaveBeenCalled();
    });

    it("delegates handleOptimizationEvent to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockEvent = { type: "progress", data: { phase: "optimization" } } as SSEEvent;
      act(() => {
        result.current.handleOptimizationEvent(mockEvent);
      });

      expect(mockSSEHandleOptimizationEvent).toHaveBeenCalledWith(mockEvent);
    });

    it("delegates handleOptimizationStreamExhausted to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      act(() => {
        result.current.handleOptimizationStreamExhausted();
      });

      expect(mockSSEHandleOptimizationStreamExhausted).toHaveBeenCalled();
    });

    it("delegates handleCheckEvent to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      const mockEvent = { type: "progress", data: { phase: "check" } } as SSEEvent;
      act(() => {
        result.current.handleCheckEvent(mockEvent);
      });

      expect(mockSSEHandleCheckEvent).toHaveBeenCalledWith(mockEvent);
    });

    it("delegates handleCheckStreamExhausted to sseHandlers", () => {
      const deps = createDefaultDeps();
      const { result } = renderHook(() => useCandidateActions(deps));

      act(() => {
        result.current.handleCheckStreamExhausted();
      });

      expect(mockSSEHandleCheckStreamExhausted).toHaveBeenCalled();
    });

    it("passes generation handlers to useCandidateSSEHandlers", () => {
      const deps = createDefaultDeps();
      renderHook(() => useCandidateActions(deps));

      const useCandidateSSEHandlersMock = vi.mocked(useCandidateSSEHandlers);

      const callArgs = useCandidateSSEHandlersMock.mock.calls[0][0];
      expect(callArgs.generationHandlers.handleTaskEvent).toBe(mockHandleTaskEvent);
      expect(callArgs.generationHandlers.handleTaskStreamExhausted).toBe(mockHandleTaskStreamExhausted);
    });

    it("passes simulation handlers to useCandidateSSEHandlers", () => {
      const deps = createDefaultDeps();
      renderHook(() => useCandidateActions(deps));

      const useCandidateSSEHandlersMock = vi.mocked(useCandidateSSEHandlers);

      const callArgs = useCandidateSSEHandlersMock.mock.calls[0][0];
      expect(typeof callArgs.simulationHandlers.handleSimEvent).toBe("function");
      expect(callArgs.simulationHandlers.handleSimStreamExhausted).toBe(mockHandleSimStreamExhausted);
    });

    it("passes optimization handlers to useCandidateSSEHandlers", () => {
      const deps = createDefaultDeps();
      renderHook(() => useCandidateActions(deps));

      const useCandidateSSEHandlersMock = vi.mocked(useCandidateSSEHandlers);

      const callArgs = useCandidateSSEHandlersMock.mock.calls[0][0];
      expect(callArgs.optimizationHandlers.handleOptimizationEvent).toBe(mockHandleOptimizationEvent);
      expect(callArgs.optimizationHandlers.handleOptimizationStreamExhausted).toBe(mockHandleOptimizationStreamExhausted);
    });

    it("passes check handlers to useCandidateSSEHandlers", () => {
      const deps = createDefaultDeps();
      renderHook(() => useCandidateActions(deps));

      const useCandidateSSEHandlersMock = vi.mocked(useCandidateSSEHandlers);

      const callArgs = useCandidateSSEHandlersMock.mock.calls[0][0];
      expect(callArgs.checkHandlers.handleCheckEvent).toBe(mockHandleCheckEvent);
      expect(callArgs.checkHandlers.handleCheckStreamExhausted).toBe(mockHandleCheckStreamExhausted);
    });
  });
});
