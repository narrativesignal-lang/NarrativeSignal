/**
 * Mock data for Narrative Radar (Macro Data tab).
 * Used when API is unavailable or for MVP demonstration.
 */

import type { MacroCategorySlug } from "./macroCategories";
import { getSubcategories } from "./macroCategories";

export type NewsItem = {
  id: string;
  title: string;
  source: string;
  timestamp: string;
  category: string;
  subcategory: string;
  url?: string | null;
  summary?: string | null;
  sentiment: string | null;
  /** Kept for UI; macro RSS items often omit scores — use `null` to sort by tier. */
  impact: number | null;
  publisher_tier: 1 | 2 | 3;
  publisher_normalized?: string | null;
  duplicate_count: number;
  related_publishers: string[];
};

/** Mock tier hints (subset of backend publisher_tier map). */
const MOCK_SOURCE_TIER: Record<string, 1 | 2 | 3> = {
  Reuters: 1,
  Bloomberg: 1,
  CNBC: 1,
  FT: 1,
  WSJ: 1,
  MarketWatch: 1,
  CoinDesk: 2,
};

function mockTierForSource(source: string): 1 | 2 | 3 {
  return MOCK_SOURCE_TIER[source] ?? 3;
}

export type HeatmapCell = {
  name: string;
  volume_24h: number;
  volume_prev_24h: number;
  delta: number; // (current - prev) / prev
};

const SOURCES = ["Reuters", "Bloomberg", "CNBC", "FT", "WSJ", "MarketWatch", "CoinDesk"];
const SENTIMENTS = ["Neutral", "Bullish", "Bearish", "Positive", "Negative", null];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!;
}

export function mockNewsForCategory(
  categorySlug: MacroCategorySlug,
  subcategoryFilter: string | null,
  limit: number
): NewsItem[] {
  const subcategories = getSubcategories(categorySlug);
  const subs = subcategoryFilter
    ? subcategories.filter((s) => s === subcategoryFilter)
    : subcategories;
  if (subs.length === 0) return [];

  const out: NewsItem[] = [];
  const now = Date.now();
  for (let i = 0; i < limit; i++) {
    const sub = pick(subs);
    const source = pick(SOURCES);
    out.push({
      id: `mock-${categorySlug}-${i}-${now}`,
      title: `Headline: ${sub} and macro developments ${i + 1}`,
      source,
      timestamp: new Date(now - i * 3600000 * (0.5 + Math.random())).toISOString(),
      category: categorySlug,
      subcategory: sub,
      summary: `Short mock preview for ${sub}: markets and policy watch (${i + 1}).`,
      url: `https://example.com/news/mock-${categorySlug}-${i}`,
      sentiment: pick(SENTIMENTS),
      impact: null,
      publisher_tier: mockTierForSource(source),
      publisher_normalized: source,
      duplicate_count: 1,
      related_publishers: [],
    });
  }
  return out.sort((a, b) => {
    if (a.publisher_tier !== b.publisher_tier) return a.publisher_tier - b.publisher_tier;
    return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
  });
}

/**
 * Deterministic hash from string for hydration-safe mock data.
 * Same inputs always produce the same output (no Math.random / Date.now).
 */
function hashSeed(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h >>> 0;
}

/**
 * Deterministic heatmap data from category + subcategory names.
 * Safe for SSR/hydration: same categorySlug always yields same cells.
 */
export function mockHeatmapForCategory(categorySlug: MacroCategorySlug): HeatmapCell[] {
  const subcategories = getSubcategories(categorySlug);
  return subcategories.map((name) => {
    const seed = hashSeed(`${categorySlug}\0${name}`);
    const volume_prev_24h = 20 + (seed % 381);
    const change = (seed >> 4) % 601 / 1000 - 0.3;
    const volume_24h = Math.max(5, Math.round(volume_prev_24h * (1 + change)));
    const delta = volume_prev_24h === 0 ? 0 : (volume_24h - volume_prev_24h) / volume_prev_24h;
    return { name, volume_24h, volume_prev_24h, delta };
  });
}

export type IndexWatchlistItem = {
  id: string;
  name: string;
  symbol: string;
  price: number | null;
  change_percent: number | null;
  /** Absolute change (e.g. +7.2) for display; derived from price and change_percent if not set */
  change?: number | null;
  /** How this value was obtained: live API, cached from last success, or deterministic fallback */
  dataSource?: "live" | "cached" | "fallback";
};

/** Deterministic fallback watchlist. Symbols must match backend DEFAULT_INDICES_BY_CATEGORY for merge. */
export const DEFAULT_INDEX_WATCHLIST: IndexWatchlistItem[] = [
  { id: "sp500", name: "S&P 500", symbol: "^GSPC", price: 5820.5, change_percent: 0.12, change: 6.98, dataSource: "fallback" },
  { id: "nasdaq", name: "NASDAQ", symbol: "^IXIC", price: 20450.2, change_percent: 0.35, change: 71.58, dataSource: "fallback" },
  { id: "dxy", name: "DXY", symbol: "DX-Y.NYB", price: 104.8, change_percent: 0.05, change: 0.05, dataSource: "fallback" },
  { id: "oil", name: "Oil", symbol: "CL=F", price: 78.4, change_percent: -0.4, change: -0.31, dataSource: "fallback" },
  { id: "gold", name: "Gold", symbol: "GC=F", price: 2654.3, change_percent: 0.8, change: 21.07, dataSource: "fallback" },
  { id: "vix", name: "VIX", symbol: "^VIX", price: 13.2, change_percent: -2.1, change: -0.28, dataSource: "fallback" },
  { id: "russell", name: "Russell 2000", symbol: "^RUT", price: 2080.0, change_percent: 0.18, change: 3.74, dataSource: "fallback" },
  { id: "soxx", name: "SOXX", symbol: "SOXX", price: 620.5, change_percent: 0.5, change: 3.1, dataSource: "fallback" },
  { id: "btc", name: "BTC", symbol: "BTC-USD", price: 67200.0, change_percent: 1.2, change: 798.0, dataSource: "fallback" },
  { id: "eth", name: "ETH", symbol: "ETH-USD", price: 3450.0, change_percent: 0.8, change: 27.6, dataSource: "fallback" },
];

/** Build a display-safe item: ensure price and change_percent are numbers when possible; compute change if missing. */
export function normalizeWatchlistItem(
  item: IndexWatchlistItem,
  dataSource?: "live" | "cached" | "fallback"
): IndexWatchlistItem {
  const price = item.price ?? null;
  const changePercent = item.change_percent ?? null;
  const change =
    item.change ??
    (price != null && changePercent != null ? (price * changePercent) / 100 : null);
  return {
    ...item,
    price,
    change_percent: changePercent,
    change: change ?? undefined,
    dataSource: dataSource ?? item.dataSource,
  };
}
