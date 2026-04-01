/**
 * Derive macro UI state from API-backed news (no mock headlines).
 */

import type { MacroCategorySlug } from "./macroCategories";
import { getSubcategories } from "./macroCategories";
import type { NewsItem, HeatmapCell } from "./macroMockData";
export function mapMacroNewsApiToItems(
  data:
    | Array<{
        id: string;
        title: string;
        source?: string | null;
        timestamp?: string | null;
        category?: string | null;
        subcategory?: string | null;
        url?: string | null;
        summary?: string | null;
        sentiment?: string | null;
        impact?: number | null;
        publisher_tier?: number | null;
        publisher_normalized?: string | null;
        duplicate_count?: number | null;
        related_publishers?: string[] | null;
      }>
    | undefined,
  categorySlug: MacroCategorySlug
): NewsItem[] {
  return (data || []).map((e) => {
    const tierRaw = e.publisher_tier;
    const publisher_tier: 1 | 2 | 3 = tierRaw === 1 || tierRaw === 2 ? tierRaw : 3;
    return {
      id: e.id,
      title: e.title,
      source: e.source ?? "—",
      timestamp: e.timestamp ?? new Date().toISOString(),
      category: e.category ?? categorySlug,
      subcategory: e.subcategory ?? "General",
      url: e.url,
      summary: e.summary,
      sentiment: e.sentiment ?? null,
      impact: e.impact ?? null,
      publisher_tier,
      publisher_normalized: e.publisher_normalized ?? null,
      duplicate_count:
        typeof e.duplicate_count === "number" && e.duplicate_count >= 1 ? e.duplicate_count : 1,
      related_publishers: Array.isArray(e.related_publishers) ? e.related_publishers.slice(0, 5) : [],
    };
  });
}

/** Count API news rows per subcategory for heatmap / top-5 (not volume deltas from market data). */
export function heatmapCellsFromNewsItems(categorySlug: MacroCategorySlug, items: NewsItem[]): HeatmapCell[] {
  const subs = getSubcategories(categorySlug);
  const counts = new Map<string, number>();
  for (const s of subs) counts.set(s, 0);
  for (const it of items) {
    const k = it.subcategory || "General";
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const maxV = Math.max(1, ...subs.map((s) => counts.get(s) ?? 0));
  return subs.map((name) => {
    const v = counts.get(name) ?? 0;
    const median = maxV * 0.5;
    const delta =
      maxV > 0 ? Math.max(-1, Math.min(1, (v - median) / (median + 1e-6))) : 0;
    return {
      name,
      volume_24h: v,
      volume_prev_24h: 0,
      delta,
      footerLabel: v === 0 ? "0 articles" : `${v} article${v === 1 ? "" : "s"}`,
    };
  });
}
