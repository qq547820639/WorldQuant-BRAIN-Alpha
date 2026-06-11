import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

if (!HTMLElement.prototype.scrollTo) {
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value() {},
  });
}

class MockEventSource {
  static instances: MockEventSource[] = [];

  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;
  readonly listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  readonly url: string;
  readonly withCredentials: boolean;
  readyState = 0;

  constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(eventSourceInitDict?.withCredentials);
    MockEventSource.instances.push(this);
    queueMicrotask(() => {
      if (this.readyState === 2) return;
      this.readyState = 1;
      this.onopen?.(new Event("open"));
    });
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type) || [];
    this.listeners.set(type, listeners.filter((item) => item !== listener));
  }

  emit(type: string, data: unknown) {
    if (this.readyState === 2) return;
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    const event = new MessageEvent(type, { data: payload });
    if (type === "message") this.onmessage?.(event);
    for (const listener of this.listeners.get(type) || []) {
      listener(event);
    }
  }

  emitError() {
    if (this.readyState === 2) return;
    this.onerror?.(new Event("error"));
  }

  close() {
    this.readyState = 2;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
