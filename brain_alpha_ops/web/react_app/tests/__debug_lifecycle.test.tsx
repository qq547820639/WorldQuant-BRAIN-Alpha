import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { GlobalDataProvider } from "@/hooks/useGlobalData";
import { ThemeProvider } from "@/components/ThemeProvider";
import CandidateTable from "@/components/CandidateTable";
import type { Candidate } from "@/types";

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <ThemeProvider>
      <GlobalDataProvider>{ui}</GlobalDataProvider>
    </ThemeProvider>
  );
}
function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}
function createMockCandidate(index: number): Candidate {
  return { alpha_id: `alpha_${index}`, expression: `ts_delay(close, ${index})`, family: index % 3 === 0 ? "momentum" : index % 3 === 1 ? "value" : "quality", score: 60 + index, status: "new", created: Date.now() - index * 3600000, updated: Date.now() - index * 1800000, is_starred: false, tags: [] } as Candidate;
}

describe("debug", () => {
  it("dumps candidate-flow DOM", async () => {
    const candidates = Array.from({ length: 15 }, (_, i) => createMockCandidate(i));
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      if (path === "/api/candidates" || path.startsWith("/api/candidates?")) {
        return jsonResponse({ ok: true, candidates, display_queue_candidates: candidates.slice(0, 10), display_count: 10, promotable_count: 25, history_count: 25, returned_count: 25, returned_total: 25, refine_capacity: 5, max_main_pool: 10, output_mode: "alpha101" });
      }
      if (path === "/api/check_results") return jsonResponse({ ok: true, check_results: {} });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path === "/api/snapshot/cloud") return jsonResponse({ ok: true, count: 100, total: 200, summary: {} });
      if (path === "/api/config") return jsonResponse({ ok: true, config: { environment: "production", credentials: { managed_credentials_available: false } } });
      if (path.startsWith("/api/alpha_lifecycle")) return jsonResponse({ ok: true, official_api_called: false, submit_allowed: false, summary: { record_count: 0, alpha_count: 0, passed_count: 0, blocked_count: 0, failed_count: 0, submitted_count: 0, replay_ready: false }, alpha_traces: [] });
      return jsonResponse({ ok: false, error: `Not mocked: ${path}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<CandidateTable notify={vi.fn()} />);
    await screen.findByText("候选管理");
    await new Promise((r) => setTimeout(r, 500));
    // eslint-disable-next-line no-console
    console.log("--- TEXTBOXES ---");
    screen.getAllByRole("textbox").forEach((el) => console.log("TEXTBOX label=", (el as HTMLInputElement).getAttribute("aria-label"), "type=", (el as HTMLInputElement).type, "value=", (el as HTMLInputElement).value));
    // eslint-disable-next-line no-console
    console.log("--- SEARCHBOXES ---");
    screen.queryAllByRole("searchbox").forEach((el) => console.log("SEARCHBOX label=", (el as HTMLInputElement).getAttribute("aria-label")));
    // eslint-disable-next-line no-console
    console.log("--- STATUS ---");
    screen.getAllByRole("status").forEach((el) => console.log("STATUS >>>", el.textContent));
    // eslint-disable-next-line no-console
    console.log("--- BUTTONS ---");
    screen.getAllByRole("button").forEach((el) => console.log("BUTTON >>>", el.textContent && el.textContent.replace(/\s+/g, " ").trim()));
    // eslint-disable-next-line no-console
    console.log("--- BODY TEXT ---");
    // eslint-disable-next-line no-console
    console.log(document.body.textContent?.replace(/\s+/g, " ").slice(0, 3000));
    expect(true).toBe(true);
  });
});