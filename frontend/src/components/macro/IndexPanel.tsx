"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { IndexCard } from "./IndexCard";
import { api, parseApiError } from "@/lib/api";
import { STALE_MARKET_MS } from "@/lib/queryClient";

/** Response shape from GET /api/market/indices?category=... */
type IndexRow = {
  name: string;
  symbol: string;
  price: number | null;
  change_percent: number | null;
  /** From market_quote_snapshots: last fetch failed but previous value kept */
  stale?: boolean;
  last_updated_at?: string | null;
  data_source?: string;
};

const MAX_ITEMS_PER_CATEGORY = 10;

export function IndexPanel({ category }: { category: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [assetType, setAssetType] = useState("index");

  const q = useQuery({
    queryKey: ["market", "indices", category],
    queryFn: () => api.marketIndices(category),
    staleTime: STALE_MARKET_MS,
    gcTime: 45 * 60 * 1000
  });

  const indices: IndexRow[] = Array.isArray(q.data?.data) ? q.data!.data : [];
  const top = q.data;
  const loading = q.isLoading && indices.length === 0;
  const showPrep =
    top?.loading_state === "warming" ||
    top?.loading_state === "placeholder" ||
    top?.data_source === "placeholder";

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
          asset_type: assetType
        });
        setName("");
        setSymbol("");
        setAssetType("index");
        setModalOpen(false);
        await queryClient.invalidateQueries({ queryKey: ["market", "indices", category] });
      } catch (e2: unknown) {
        setError(parseApiError(e2));
      }
    },
    [category, name, symbol, assetType, queryClient]
  );

  const atLimit = indices.length >= MAX_ITEMS_PER_CATEGORY;
  const msg = error || (q.isError ? parseApiError(q.error) : null);

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-slate-300">Market indexes</div>
        <button
          type="button"
          onClick={() => !atLimit && setModalOpen(true)}
          disabled={atLimit}
          title={atLimit ? `Maximum ${MAX_ITEMS_PER_CATEGORY} items per category` : undefined}
          className="rounded bg-slate-800 px-2 py-1 text-xs font-medium text-slate-100 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          + Add Data
        </button>
      </div>
      {msg ? (
        <div className="mt-2 rounded border border-amber-900/60 bg-amber-950/40 px-2 py-1 text-xs text-amber-200">
          {msg}
        </div>
      ) : null}
      {top?.message && showPrep ? (
        <div className="mt-2 rounded border border-sky-900/50 bg-sky-950/30 px-2 py-1.5 text-[11px] leading-snug text-sky-100/90">
          {top.message}
        </div>
      ) : null}
      {top?.data_source === "stale_fallback" &&
      !showPrep &&
      top?.data_updated_at ? (
        <div className="mt-1 text-[10px] text-slate-500">
          <span className="text-amber-200/80">Stale</span> · updated{" "}
          {new Date(top.data_updated_at).toLocaleString()}
        </div>
      ) : null}
      <div className="mt-2 flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-auto">
        {loading ? (
          <div className="animate-pulse space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-14 rounded-lg bg-slate-800/60" />
            ))}
          </div>
        ) : (
          indices.map((item) => {
            const priceStr = item.price != null ? item.price.toFixed(2) : "--";
            const rowDs = item.data_source;
            let dataSource: "live" | "cached" | "fallback" | "stale" | "placeholder" | undefined;
            if (rowDs === "placeholder" || (!item.last_updated_at && item.price == null)) dataSource = "placeholder";
            else if (rowDs === "stale_fallback") dataSource = "stale";
            else if (item.stale) dataSource = "stale";
            else dataSource = undefined;
            return (
              <IndexCard
                key={`${item.name}-${item.symbol}`}
                name={item.name}
                price={priceStr}
                changePercent={item.change_percent}
                dataSource={dataSource}
                title={
                  item.last_updated_at
                    ? `Updated ${item.last_updated_at}${item.stale ? " (stale)" : ""}`
                    : item.stale
                      ? "Stale — last fetch failed; showing last known quote"
                      : rowDs === "placeholder"
                        ? "Quote not yet available for this symbol"
                        : undefined
                }
              />
            );
          })
        )}
      </div>

      {modalOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-100">Add Market Data</h3>
            <form className="mt-3 space-y-3" onSubmit={handleAdd}>
              <div>
                <label className="block text-xs font-medium text-slate-400">Name</label>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Gold"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400">Symbol</label>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="GC=F"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400">Asset type</label>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  value={assetType}
                  onChange={(e) => setAssetType(e.target.value)}
                >
                  <option value="equity">equity</option>
                  <option value="crypto">crypto</option>
                  <option value="forex">forex</option>
                  <option value="index">index</option>
                  <option value="futures">futures</option>
                  <option value="commodity">commodity</option>
                </select>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="rounded px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!name.trim() || !symbol.trim()}
                  className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
