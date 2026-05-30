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

    const streamUrl = url;
    reconnectCountRef.current = 0;
    connect();

    function connect() {
      close();

      try {
        const es = new EventSource(withStreamToken(streamUrl), { withCredentials: true });
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

function withStreamToken(url: string) {
  const token = streamToken();
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}stream_token=${encodeURIComponent(token)}`;
}

function streamToken() {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-stream"]');
  const fromMeta = meta?.content || "";
  const fromWindow = String((window as unknown as { __BRAIN_ALPHA_OPS_STREAM_TOKEN__?: string }).__BRAIN_ALPHA_OPS_STREAM_TOKEN__ || "");
  const token = fromMeta || fromWindow;
  return token && !token.startsWith("__BRAIN_ALPHA_OPS") ? token : "";
}
