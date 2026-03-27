/**
 * Client-side volatility day selection for the event timeline, aligned with the chart's visible range.
 * Mirrors backend compute_volatility_top_days (replace together if the rule changes).
 */

import type { CandleBar } from "@/lib/ohlcvBars";

export function dayStartUtcUnix(ts: number): number {
  const d = new Date(ts * 1000);
  return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000);
}

export type TimelinePointBuilt = {
  id: string;
  point_type: "volatility" | "official";
  time: number;
  score: number | null;
  label_hint: string | null;
};

export function computeVolatilityTopDayStarts(bars: CandleBar[]): { dayStart: number; score: number }[] {
  if (!bars.length) return [];
  const byDay = new Map<number, CandleBar[]>();
  for (const b of bars) {
    const t = b.time;
    if (!Number.isFinite(t)) continue;
    const d0 = dayStartUtcUnix(t);
    const arr = byDay.get(d0) ?? [];
    arr.push(b);
    byDay.set(d0, arr);
  }
  const days: { dayStart: number; score: number }[] = [];
  for (const d0 of Array.from(byDay.keys()).sort((a, b) => a - b)) {
    const daybars = byDay.get(d0)!;
    const o = daybars[0].open;
    const h = Math.max(...daybars.map((x) => x.high));
    const low = Math.min(...daybars.map((x) => x.low));
    const denom = Math.max(Math.abs(o), 1e-9);
    const rangePct = (h - low) / denom;
    days.push({ dayStart: d0, score: rangePct });
  }
  const n = days.length;
  if (n < 3) return [];
  const k = Math.min(Math.max(1, Math.ceil(n * 0.1)), n);
  const ranked = [...days].sort((a, b) => b.score - a.score).slice(0, k);
  return ranked.sort((a, b) => a.dayStart - b.dayStart);
}

/** Bars whose bar time lies in [visibleFrom, visibleTo] (UTC unix), inclusive. */
export function barsInVisibleRange(bars: CandleBar[], visibleFrom: number, visibleTo: number): CandleBar[] {
  return bars.filter((b) => b.time >= visibleFrom && b.time <= visibleTo);
}

export function buildSyncedTimelinePoints(
  symbolUpper: string,
  bars: CandleBar[],
  officialFromApi: TimelinePointBuilt[],
  visibleFrom: number,
  visibleTo: number
): TimelinePointBuilt[] {
  const sym = symbolUpper.trim().toUpperCase();
  const slice = barsInVisibleRange(bars, visibleFrom, visibleTo);
  const volRows = computeVolatilityTopDayStarts(slice);
  const volPoints: TimelinePointBuilt[] = volRows.map((row) => ({
    id: `vol:${sym}:${row.dayStart}`,
    point_type: "volatility",
    time: row.dayStart,
    score: row.score,
    label_hint: "high_range_day",
  }));
  const volDays = new Set(volPoints.map((p) => p.time));
  const officialPoints: TimelinePointBuilt[] = officialFromApi
    .filter((p) => p.point_type === "official" && p.time >= visibleFrom && p.time <= visibleTo && !volDays.has(p.time))
    .map((p) => ({ ...p }));
  const merged = [...volPoints, ...officialPoints];
  merged.sort((a, b) => {
    if (a.time !== b.time) return a.time - b.time;
    return a.point_type === "volatility" ? -1 : 1;
  });
  return merged;
}
