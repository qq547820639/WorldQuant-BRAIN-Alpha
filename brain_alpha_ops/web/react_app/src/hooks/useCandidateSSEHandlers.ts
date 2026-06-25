import type { SSEEvent } from '@/types';

export interface CandidateSSEHandlers {
  handleTaskEvent: (event: SSEEvent) => void;
  handleTaskStreamExhausted: () => void;
  handleSimEvent: (event: SSEEvent) => void;
  handleSimStreamExhausted: () => void;
  handleOptimizationEvent: (event: SSEEvent) => void;
  handleOptimizationStreamExhausted: () => void;
  handleCheckEvent: (event: SSEEvent) => void;
  handleCheckStreamExhausted: () => void;
}

export interface CandidateSSEHandlersDeps {
  generationHandlers: {
    handleTaskEvent: (event: SSEEvent) => void;
    handleTaskStreamExhausted: () => void;
  };
  simulationHandlers: {
    handleSimEvent: (event: SSEEvent) => void;
    handleSimStreamExhausted: () => void;
  };
  optimizationHandlers: {
    handleOptimizationEvent: (event: SSEEvent) => void;
    handleOptimizationStreamExhausted: () => void;
  };
  checkHandlers: {
    handleCheckEvent: (event: SSEEvent) => void;
    handleCheckStreamExhausted: () => void;
  };
}

export function useCandidateSSEHandlers(deps: CandidateSSEHandlersDeps): CandidateSSEHandlers {
  const { generationHandlers, simulationHandlers, optimizationHandlers, checkHandlers } = deps;

  return {
    handleTaskEvent: generationHandlers.handleTaskEvent,
    handleTaskStreamExhausted: generationHandlers.handleTaskStreamExhausted,
    handleSimEvent: simulationHandlers.handleSimEvent,
    handleSimStreamExhausted: simulationHandlers.handleSimStreamExhausted,
    handleOptimizationEvent: optimizationHandlers.handleOptimizationEvent,
    handleOptimizationStreamExhausted: optimizationHandlers.handleOptimizationStreamExhausted,
    handleCheckEvent: checkHandlers.handleCheckEvent,
    handleCheckStreamExhausted: checkHandlers.handleCheckStreamExhausted,
  };
}
