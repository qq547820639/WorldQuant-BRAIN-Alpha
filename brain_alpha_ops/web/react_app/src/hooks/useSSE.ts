/** Server-Sent Events hook with automatic reconnection. */

import { useEffect, useRef, useState, useCallback } from "react";
import type { SSEEvent } from "@/types";

interface UseSSEOptions {
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Event) => void;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

export function useSSE(
  url: string | null,
  options: UseSSEOptions = {},
) {
  const {
    onEvent,
    onError,
    reconnectIntervalMs = 3000,
    maxReconnectAttempts = 10,
  } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const close = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    setConnected(false);
  }, []);

  useEffect(() => {
    if (!url) {
      close();
      return;
    }

    reconnectCountRef.current = 0;
    connect();

    function connect() {
      close();

      try {
        const es = new EventSource(url);
        eventSourceRef.current = es;

        es.onopen = () => {
          setConnected(true);
          reconnectCountRef.current = 0;
        };

        es.onmessage = (msg: MessageEvent) => {
          try {
            const event: SSEEvent = JSON.parse(msg.data);
            setLastEvent(event);
            onEvent?.(event);
          } catch {
            // Non-JSON SSE data — ignore
          }
        };

        es.onerror = (err: Event) => {
          setConnected(false);
          onError?.(err);

          if (reconnectCountRef.current < maxReconnectAttempts) {
            reconnectCountRef.current += 1;
            reconnectTimerRef.current = setTimeout(connect, reconnectIntervalMs);
          }
        };
      } catch {
        // EventSource constructor failed — retry
        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          reconnectTimerRef.current = setTimeout(connect, reconnectIntervalMs);
        }
      }
    }

    return close;
  }, [url, close, onEvent, onError, reconnectIntervalMs, maxReconnectAttempts]);

  return { connected, lastEvent, close };
}
