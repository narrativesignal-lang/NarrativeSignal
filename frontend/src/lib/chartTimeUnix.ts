import type { Time } from "lightweight-charts";

/** Convert lightweight-charts Time to UTC unix seconds (for candle data). */
export function chartTimeToUnix(t: Time): number {
  if (typeof t === "number") return t;
  const b = t as { year: number; month: number; day: number };
  if (b && typeof b.year === "number") {
    return Math.floor(Date.UTC(b.year, b.month - 1, b.day) / 1000);
  }
  return 0;
}

export type ChartVisibleTimeRange = { from: number; to: number };

export function chartVisibleRangeToUnix(range: { from: Time; to: Time } | null): ChartVisibleTimeRange | null {
  if (!range) return null;
  return { from: chartTimeToUnix(range.from), to: chartTimeToUnix(range.to) };
}
