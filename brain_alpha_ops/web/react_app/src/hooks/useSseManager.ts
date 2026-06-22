/**
 * Unified SSE connection manager.
 *
 * Wraps four independent useSSE calls (task, check, optimization, simulation)
 * behind a single connect/disconnect API with per-connection state tracking.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import { useSSE } from "@/hooks/useSSE";
import type { SSEEvent } from "@/types";

type ConnectionName = "task" | "check" | "optimization" | "simulation";

interface ConnectionHandlers {
  onEvent?: (event: SSEEvent) => void;
  onExhausted?: () => void;
  onError?: (error: Event) => void;
}

interface ConnectionState {
  connected: boolean;
  exhausted: boolean;
  reconnectAttempts: number;
  sseUrl: string | null;
}

export interface SseManagerState {
  task: ConnectionState;
  check: ConnectionState;
  optimization: ConnectionState;
  simulation: ConnectionState;
}

export interface SseManagerActions {
  connect: (name: ConnectionName, url: string, handlers: ConnectionHandlers) => void;
  disconnect: (name: ConnectionName) => void;
  isConnected: (name: ConnectionName) => boolean;
}

export function useSseManager(): SseManagerState & SseManagerActions {
  const taskHandlersRef = useRef<ConnectionHandlers>({});
  const checkHandlersRef = useRef<ConnectionHandlers>({});
  const optimizationHandlersRef = useRef<ConnectionHandlers>({});
  const simulationHandlersRef = useRef<ConnectionHandlers>({});

  const [taskUrl, setTaskUrl] = useState<string | null>(null);
  const [checkUrl, setCheckUrl] = useState<string | null>(null);
  const [optimizationUrl, setOptimizationUrl] = useState<string | null>(null);
  const [simulationUrl, setSimulationUrl] = useState<string | null>(null);

  const task = useSSE(taskUrl, {
    onEvent: useCallback((e: SSEEvent) => taskHandlersRef.current.onEvent?.(e), []),
    onExhausted: useCallback(() => taskHandlersRef.current.onExhausted?.(), []),
    onError: useCallback((e: Event) => taskHandlersRef.current.onError?.(e), []),
  });

  const check = useSSE(checkUrl, {
    onEvent: useCallback((e: SSEEvent) => checkHandlersRef.current.onEvent?.(e), []),
    onExhausted: useCallback(() => checkHandlersRef.current.onExhausted?.(), []),
    onError: useCallback((e: Event) => checkHandlersRef.current.onError?.(e), []),
  });

  const optimization = useSSE(optimizationUrl, {
    onEvent: useCallback((e: SSEEvent) => optimizationHandlersRef.current.onEvent?.(e), []),
    onExhausted: useCallback(() => optimizationHandlersRef.current.onExhausted?.(), []),
    onError: useCallback((e: Event) => optimizationHandlersRef.current.onError?.(e), []),
  });

  const simulation = useSSE(simulationUrl, {
    onEvent: useCallback((e: SSEEvent) => simulationHandlersRef.current.onEvent?.(e), []),
    onExhausted: useCallback(() => simulationHandlersRef.current.onExhausted?.(), []),
    onError: useCallback((e: Event) => simulationHandlersRef.current.onError?.(e), []),
  });

  const handlersMap: Record<ConnectionName, React.MutableRefObject<ConnectionHandlers>> = {
    task: taskHandlersRef,
    check: checkHandlersRef,
    optimization: optimizationHandlersRef,
    simulation: simulationHandlersRef,
  };

  const urlSettersMap: Record<ConnectionName, React.Dispatch<React.SetStateAction<string | null>>> = {
    task: setTaskUrl,
    check: setCheckUrl,
    optimization: setOptimizationUrl,
    simulation: setSimulationUrl,
  };

  const connect = useCallback((name: ConnectionName, url: string, handlers: ConnectionHandlers) => {
    handlersMap[name].current = handlers;
    urlSettersMap[name]((prev) => (prev === url ? prev : url));
  }, []);

  const disconnect = useCallback((name: ConnectionName) => {
    handlersMap[name].current = {};
    urlSettersMap[name](null);
  }, []);

  const isConnected = useCallback((name: ConnectionName) => {
    const states: Record<ConnectionName, boolean> = {
      task: task.connected,
      check: check.connected,
      optimization: optimization.connected,
      simulation: simulation.connected,
    };
    return states[name];
  }, [task.connected, check.connected, optimization.connected, simulation.connected]);

  useEffect(() => {
    return () => {
      setTaskUrl(null);
      setCheckUrl(null);
      setOptimizationUrl(null);
      setSimulationUrl(null);
    };
  }, []);

  return {
    task: {
      connected: task.connected,
      exhausted: task.exhausted,
      reconnectAttempts: task.reconnectAttempts,
      sseUrl: taskUrl,
    },
    check: {
      connected: check.connected,
      exhausted: check.exhausted,
      reconnectAttempts: check.reconnectAttempts,
      sseUrl: checkUrl,
    },
    optimization: {
      connected: optimization.connected,
      exhausted: optimization.exhausted,
      reconnectAttempts: optimization.reconnectAttempts,
      sseUrl: optimizationUrl,
    },
    simulation: {
      connected: simulation.connected,
      exhausted: simulation.exhausted,
      reconnectAttempts: simulation.reconnectAttempts,
      sseUrl: simulationUrl,
    },
    connect,
    disconnect,
    isConnected,
  };
}
