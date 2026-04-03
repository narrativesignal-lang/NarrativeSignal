/**
 * Chart-local overlay display ranges (independent of entity page period).
 * Filtering uses calendar date keys (YYYY-MM-DD), not point counts.
 */

export const OVERLAY_LOCAL_RANGES = ["5D", "1M", "6M", "1Y", "ALL"] as const;

export type OverlayLocalRange = (typeof OVERLAY_LOCAL_RANGES)[number];

function dayKey(s: string): string {
  return s.trim().slice(0, 10);
}

/** Parse ISO day at UTC noon for stable calendar math. */
function utcNoon(dayKeyStr: string): Date {
  return new Date(dayKeyStr + "T12:00:00.000Z");
}

/**
 * Minimum inclusive date key (YYYY-MM-DD) for the visible window ending at maxKey.
 * Returns null when range is ALL (no lower bound).
 */
export function minDayKeyForOverlayRange(maxKey: string, range: OverlayLocalRange): string | null {
  if (range === "ALL") return null;
  const d = utcNoon(dayKey(maxKey));
  if (range === "5D") {
    d.setUTCDate(d.getUTCDate() - 5);
  } else if (range === "1M") {
    d.setUTCMonth(d.getUTCMonth() - 1);
  } else if (range === "6M") {
    d.setUTCMonth(d.getUTCMonth() - 6);
  } else if (range === "1Y") {
    d.setUTCFullYear(d.getUTCFullYear() - 1);
  }
  return d.toISOString().slice(0, 10);
}

/**
 * Filter sorted ascending date keys to [minDay, maxDay] where max is the series end
 * and min is derived from `range` relative to that end date.
 */
export function filterSortedAxisByOverlayRange(sortedDayKeys: string[], range: OverlayLocalRange): string[] {
  if (sortedDayKeys.length === 0) return [];
  if (range === "ALL") return sortedDayKeys;
  const maxKey = dayKey(sortedDayKeys[sortedDayKeys.length - 1]!);
  const minKey = minDayKeyForOverlayRange(maxKey, range);
  if (!minKey) return sortedDayKeys;
  return sortedDayKeys.filter((k) => dayKey(k) >= minKey);
}
