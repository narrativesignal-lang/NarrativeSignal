"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { IndexCard } from "./IndexCard";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  DEFAULT_INDEX_WATCHLIST,
  normalizeWatchlistItem,
  type IndexWatchlistItem,
} from "@/lib/macroMockData";

type ApiIndexRow = {
  name: string;
  symbol: string;
  price: number | null;
  change_percent: number | null;
};

type Props = {
  category: string;
};

const COOLDOWN_MS = 60_000;
const REFRESH_INTERVAL_MS = 30_000;

type CategoryCache = {
  items: IndexWatchlistItem[];
  timestamp: number;
};

const FALLBACK_BY_SYMBOL = new Map(
  DEFAULT_INDEX_WATCHLIST.map((i) => [i.symbol, i])
);

function mergeWithCache(
  apiRows: ApiIndexRow[],
  cached: IndexWatchlistItem[] | null,
  _category: string
): IndexWatchlistItem[] {
  const bySymbol = new Map<string, IndexWatchlistItem>();
  if (cached) {
    for (const item of cached) {
      bySymbol.set(item.symbol, item);
    }
  }
  const result: IndexWatchlistItem[] = [];
  apiRows.forEach((row, i) => {
    const cachedItem = bySymbol.get(row.symbol);
    const fallbackItem = FALLBACK_BY_SYMBOL.get(row.symbol);
    const price = row.price ?? cachedItem?.price ?? fallbackItem?.price ?? null;
    const changePercent =
      row.change_percent ?? cachedItem?.change_percent ?? fallbackItem?.change_percent ?? null;
    const change =
      row.price != null && row.change_percent != null
        ? (row.price * row.change_percent) / 100
        : cachedItem?.change ?? fallbackItem?.change ?? (price != null && changePercent != null ? (price * changePercent) / 100 : null);
    const usedCache =
      (row.price == null && cachedItem?.price != null) ||
      (row.change_percent == null && cachedItem?.change_percent != null);
    const usedFallback =
      (row.price == null && fallbackItem?.price != null) ||
      (row.change_percent == null && fallbackItem?.change_percent != null);
    const dataSource: "live" | "cached" | "fallback" =
      row.price != null && row.change_percent != null
        ? "live"
        : usedCache
          ? "cached"
          : usedFallback
            ? "fallback"
            : "cached";
    result.push(
      normalizeWatchlistItem(
        {
          id: `api-${row.symbol}-${i}`,
          name: row.name,
          symbol: row.symbol,
          price,
          change_percent: changePercent,
          change: change ?? undefined,
          dataSource,
        },
        dataSource
      )
    );
  });
  return result;
}

function toDisplayItems(items: IndexWatchlistItem[]): IndexWatchlistItem[] {
  return items.map((item) => {
    const price = item.price ?? null;
    const changePercent = item.change_percent ?? null;
    const change =
      item.change ??
      (price != null && changePercent != null ? (price * changePercent) / 100 : null);
    return normalizeWatchlistItem({
      ...item,
      price,
      change_percent: changePercent,
      change: change ?? undefined,
    });
  });
}

export function IndexWatchlist({ category }: Props) {
  const { t } = useI18n();
  const [items, setItems] = useState<IndexWatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");

  const cacheRef = useRef<Map<string, CategoryCache>>(new Map());
  const lastFailureRef = useRef<Map<string, number>>(new Map());

  const fetchIndices = useCallback(async () => {
    const now = Date.now();
    const lastFail = lastFailureRef.current.get(category) ?? 0;
    const inCooldown = lastFail > 0 && now - lastFail < COOLDOWN_MS;
    const cached = cacheRef.current.get(category);

    if (inCooldown) {
      setLoading(false);
      if (cached?.items.length) {
        setItems(toDisplayItems(cached.items));
        setError(null);
      } else {
        const fallback = DEFAULT_INDEX_WATCHLIST.map((i) =>
          normalizeWatchlistItem({ ...i }, "fallback")
        );
        setItems(fallback);
      }
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const json = await api.marketIndices(category);
      const data = json?.data ?? [];
      if (!Array.isArray(data) || data.length === 0) {
        throw new Error(t("macro.indicesEmpty"));
      }
      const merged = mergeWithCache(
        data,
        cached?.items ?? null,
        category
      );
      const display = toDisplayItems(merged);
      setItems(display);
      cacheRef.current.set(category, { items: merged, timestamp: now });
      lastFailureRef.current.set(category, 0);
    } catch (e: unknown) {
      lastFailureRef.current.set(category, now);
      const hint = parseApiError(e);
      if (cached?.items.length) {
        const display = toDisplayItems(
          cached.items.map((i) => ({ ...i, dataSource: "cached" as const }))
        );
        setItems(display);
        setError(hint);
      } else {
        const fallback = DEFAULT_INDEX_WATCHLIST.map((i) =>
          normalizeWatchlistItem({ ...i }, "fallback")
        );
        setItems(fallback);
        setError(hint);
      }
    } finally {
      setLoading(false);
    }
  }, [category, t]);

  useEffect(() => {
    fetchIndices();
    const id = setInterval(fetchIndices, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchIndices]);

  const handleAdd = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim() || !symbol.trim()) return;
      setError(null);
      try {
        await api.addMarketIndex({
          category,
          name: name.trim(),
          symbol: symbol.trim(),
          asset_type: "index",
        });
        setName("");
        setSymbol("");
        setModalOpen(false);
        fetchIndices();
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    },
    [category, name, symbol, fetchIndices]
  );

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-slate-300">{t("macro.indexWatchlist")}</div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="rounded bg-slate-800 px-2 py-1 text-xs font-medium text-slate-100 hover:bg-slate-700"
        >
          {t("macro.addIndex")}
        </button>
      </div>
      {error ? (
        <div className="mt-2 rounded border border-amber-900/60 bg-amber-950/40 px-2 py-1 text-xs text-amber-200">
          {error}
        </div>
      ) : null}
      <div className="mt-2 flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-auto">
        {loading && items.length === 0 ? (
          <div className="text-xs text-slate-400">{t("common.loading")}</div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="group relative shrink-0">
              <IndexCard
                name={item.name}
                price={
                  item.price != null && !Number.isNaN(item.price)
                    ? item.price.toFixed(2)
                    : "--"
                }
                changePercent={
                  item.change_percent != null && !Number.isNaN(item.change_percent)
                    ? item.change_percent
                    : 0
                }
                change={item.change}
                dataSource={item.dataSource}
              />
              <button
                type="button"
                onClick={() => removeItem(item.id)}
                className="absolute right-2 top-2 rounded p-1 text-slate-500 opacity-0 hover:bg-slate-800 hover:text-red-300 group-hover:opacity-100"
                title={t("common.remove")}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      {modalOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-100">{t("macro.addIndexModalTitle")}</h3>
            <form className="mt-3 space-y-3" onSubmit={handleAdd}>
              <div>
                <label className="block text-xs font-medium text-slate-400">{t("macro.indexName")}</label>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="S&P 500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400">{t("macro.indexSymbol")}</label>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="SPX"
                />
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="rounded px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={!name.trim() || !symbol.trim()}
                  className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {t("common.add")}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
