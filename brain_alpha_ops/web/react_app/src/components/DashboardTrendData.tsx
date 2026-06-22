import type { TrendData } from "@/components/TrendPanel";

const TREND_KEY_CANDIDATES = "trend_candidates";
const TREND_KEY_SUBMISSIONS = "trend_submissions";
const TREND_MAX_POINTS = 7;

export function loadTrendData(key: string): TrendData[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (d): d is TrendData =>
        typeof d === "object" &&
        d !== null &&
        typeof (d as TrendData).date === "string" &&
        typeof (d as TrendData).value === "number" &&
        Number.isFinite((d as TrendData).value),
    ).slice(-TREND_MAX_POINTS);
  } catch {
    return [];
  }
}

function saveTrendData(key: string, data: TrendData[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(data.slice(-TREND_MAX_POINTS)));
  } catch { console.warn("Dashboard: localStorage full or unavailable"); }
}

export function appendTrendPoint(key: string, value: number): TrendData[] {
  const existing = loadTrendData(key);
  const today = new Date().toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
  const newPoint: TrendData = { date: today, value };
  const updated = [...existing, newPoint].slice(-TREND_MAX_POINTS);
  saveTrendData(key, updated);
  return updated;
}

export function computeTrendChange(data: TrendData[]): number | undefined {
  if (data.length < 2) return undefined;
  const first = data[0].value;
  const last = data[data.length - 1].value;
  if (first === 0) return last > 0 ? 100 : 0;
  return ((last - first) / Math.abs(first)) * 100;
}

export function syncTrendToBackend(candidates: number, submissions: number, cycles: number = 0): void {
  fetch("/api/trends", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidates, submissions, cycles }),
  }).catch(() => {
    console.warn("Dashboard trend sync unavailable — data preserved in localStorage");
  });
}

export const TREND_KEY = { CANDIDATES: TREND_KEY_CANDIDATES, SUBMISSIONS: TREND_KEY_SUBMISSIONS } as const;

export const TREND_LIMITS = { MAX_POINTS: TREND_MAX_POINTS } as const;
