/** Server-Sent Events hook with automatic reconnection. */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { SSEEvent } from '@/types';
import { streamToken } from '@/utils/csrf';
import { reportIgnoredError } from '@/utils/reportIgnoredError';

type NamedSSEEvent = NonNullable<SSEEvent['type']>;

interface UseSSEOptions {
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Event) => void;
  onExhausted?: () => void;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

export function useSSE(url: string | null, options: UseSSEOptions = {}) {
  const {
    onEvent,
    onError,
    onExhausted,
    // BRAIN simulations can take 2+ minutes.  Use a longer reconnect
    // window (30 attempts × 5s = 150s) so the hook survives transient
    // disconnects without prematurely marking the stream as exhausted.
    reconnectIntervalMs = 5000,
    maxReconnectAttempts = 30,
  } = options;

  const [connected, setConnected] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const terminalClosedRef = useRef(false);
  const intentionalCloseRef = useRef(false);

  // Use refs so callback identity changes don't trigger SSE reconnect cycles
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onExhaustedRef = useRef(onExhausted);
  onExhaustedRef.current = onExhausted;

  const close = useCallback(() => {
    intentionalCloseRef.current = true;
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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- url 置空时关闭旧连接并更新连接状态（清理副作用）
      close();
      return;
    }

    const streamUrl = url;
    reconnectCountRef.current = 0;
    terminalClosedRef.current = false;
    intentionalCloseRef.current = false;
    setExhausted(false);
    setReconnectAttempts(0);
    connect();

    function connect() {
      close();
      // Reset intentionalClose after internal cleanup close so the new
      // connection can still attempt reconnection on unexpected errors.
      intentionalCloseRef.current = false;

      try {
        const es = new EventSource(withStreamToken(streamUrl), { withCredentials: true });
        eventSourceRef.current = es;

        es.onopen = () => {
          setConnected(true);
          setExhausted(false);
          reconnectCountRef.current = 0;
          setReconnectAttempts(0);
        };

        const handleMessage = (msg: MessageEvent, fallbackType?: NamedSSEEvent) => {
          try {
            const parsed = JSON.parse(msg.data) as SSEEvent;
            const event: SSEEvent =
              fallbackType && !parsed.type ? { ...parsed, type: fallbackType } : parsed;
            setLastEvent(event);
            if (event.type === 'stream_timeout') {
              setExhausted(true);
              closeTerminalStream();
              onExhaustedRef.current?.();
              return;
            }
            onEventRef.current?.(event);
            if (event.type === 'complete' || event.type === 'error') {
              closeTerminalStream();
            }
          } catch (err) {
            // Non-JSON SSE data — log and ignore for debugging
            reportIgnoredError('SSE non-JSON message ignored', err);
            if (process.env.NODE_ENV === 'development') {
              console.debug('SSE: received non-JSON data:', msg.data.slice(0, 120));
            }
          }
        };

        // P2-8 [C7]: onmessage fires only for unnamed events. addEventListener
        // below handles named events.  Do NOT add "message" to namedEvents
        // — that would double-fire every unnamed message.
        es.onmessage = (msg: MessageEvent) => handleMessage(msg);
        const namedEvents: NamedSSEEvent[] = [
          'progress',
          'complete',
          'error',
          'heartbeat',
          'stream_timeout',
        ];
        for (const eventName of namedEvents) {
          es.addEventListener(eventName, (msg) => handleMessage(msg, eventName));
        }

        es.onerror = (err: Event) => {
          // C25 P2: EventSource.onerror fires on normal close too.
          // Do NOT reconnect if the stream was closed by the server.
          if (terminalClosedRef.current) return;
          if (intentionalCloseRef.current) return;
          if (es.readyState === EventSource.CLOSED) {
            // Unexpected close — reconnect rather than marking exhausted
            setConnected(false);
            onErrorRef.current?.(err);
            if (reconnectCountRef.current < maxReconnectAttempts) {
              reconnectCountRef.current += 1;
              setReconnectAttempts(reconnectCountRef.current);
              scheduleReconnect(connect, reconnectIntervalMs);
            } else {
              clearReconnectTimer();
              setExhausted(true);
              onExhaustedRef.current?.();
            }
            return;
          }
          setConnected(false);
          onErrorRef.current?.(err);

          if (reconnectCountRef.current < maxReconnectAttempts) {
            reconnectCountRef.current += 1;
            setReconnectAttempts(reconnectCountRef.current);
            scheduleReconnect(connect, reconnectIntervalMs);
          } else {
            clearReconnectTimer();
            setExhausted(true);
            onExhaustedRef.current?.();
          }
        };
      } catch (err) {
        // EventSource constructor failed — retry
        reportIgnoredError('SSE EventSource connection failed', err);
        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          setReconnectAttempts(reconnectCountRef.current);
          scheduleReconnect(connect, reconnectIntervalMs);
        } else {
          clearReconnectTimer();
          setExhausted(true);
          onExhaustedRef.current?.();
        }
      }
    }

    return close;
    // P2-20 fix: close is a stable useCallback identity — including it
    // in the deps array risks unnecessary re-connection cycles if close
    // is ever modified to have dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, reconnectIntervalMs, maxReconnectAttempts]);

  return { connected, exhausted, reconnectAttempts, lastEvent, close };

  function clearReconnectTimer() {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }

  function scheduleReconnect(connectFn: () => void, delayMs: number) {
    clearReconnectTimer();
    reconnectTimerRef.current = setTimeout(connectFn, delayMs);
  }

  function closeTerminalStream() {
    intentionalCloseRef.current = true;
    terminalClosedRef.current = true;
    setConnected(false);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    clearReconnectTimer();
  }
}

function withStreamToken(url: string) {
  const token = streamToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}stream_token=${encodeURIComponent(token)}`;
}
