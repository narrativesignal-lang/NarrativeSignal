/**
 * Normalize API OHLCV bars for CandleChart (lightweight-charts).
 * Ensures volume is always a number so the volume histogram always renders.
 */

export type CandleBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export function normalizeOhlcvBars(raw: unknown): CandleBar[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((b: Record<string, unknown>) => {
    const time = typeof b.time === "number" ? b.time : Number(b.time);
    const open = Number(b.open ?? b.o ?? 0);
    const high = Number(b.high ?? b.h ?? open);
    const low = Number(b.low ?? b.l ?? open);
    const close = Number(b.close ?? b.c ?? open);
    const volRaw = b.volume ?? b.vol ?? b.v ?? 0;
    const volume = typeof volRaw === "number" ? volRaw : Number(volRaw);
    return {
      time: Number.isFinite(time) ? time : 0,
      open: Number.isFinite(open) ? open : 0,
      high: Number.isFinite(high) ? high : open,
      low: Number.isFinite(low) ? low : open,
      close: Number.isFinite(close) ? close : open,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
    };
  });
}
