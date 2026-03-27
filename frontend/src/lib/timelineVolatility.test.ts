import { describe, expect, it } from "vitest";

import type { CandleBar } from "./ohlcvBars";
import { buildSyncedTimelinePoints, computeVolatilityTopDayStarts, dayStartUtcUnix } from "./timelineVolatility";

function bar(t: number, o: number, h: number, l: number, c: number): CandleBar {
  return { time: t, open: o, high: h, low: l, close: c, volume: 1 };
}

describe("timelineVolatility", () => {
  it("dayStartUtcUnix normalizes to UTC midnight", () => {
    const noon = Math.floor(Date.UTC(2024, 5, 15, 12, 0, 0) / 1000);
    expect(dayStartUtcUnix(noon)).toBe(Math.floor(Date.UTC(2024, 5, 15, 0, 0, 0) / 1000));
  });

  it("returns no volatility days when fewer than 3 distinct days", () => {
    const d0 = Math.floor(Date.UTC(2024, 0, 1) / 1000);
    const d1 = Math.floor(Date.UTC(2024, 0, 2) / 1000);
    const bars = [bar(d0, 10, 11, 9, 10), bar(d1, 10, 20, 8, 12)];
    expect(computeVolatilityTopDayStarts(bars)).toEqual([]);
  });

  it("buildSyncedTimelinePoints keeps points inside visible window", () => {
    const days = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((d) => Math.floor(Date.UTC(2024, 0, d) / 1000));
    const bars = days.map((t, i) => bar(t, 100, 100 + i * 5, 100 - i, 100 + i));
    const official = [
      {
        id: "off:TEST:0",
        point_type: "official" as const,
        time: days[5],
        score: null,
        label_hint: "demo",
      },
    ];
    const from = days[3];
    const to = days[7];
    const pts = buildSyncedTimelinePoints("TEST", bars, official, from, to);
    expect(pts.length).toBeGreaterThan(0);
    for (const p of pts) {
      expect(p.time).toBeGreaterThanOrEqual(from);
      expect(p.time).toBeLessThanOrEqual(to);
    }
  });
});
