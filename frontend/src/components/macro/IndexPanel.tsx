"use client";

import { useCallback, useEffect, useState } from "react";
import { IndexCard } from "./IndexCard";

/** Response shape from GET /api/market/indices?category=... */
type IndexRow = {
  name: string;
  symbol: string;
  price: number | null;
  change_percent: number | null;
  /** From market_quote_snapshots: last fetch failed but previous value kept */
  stale?: boolean;
  last_updated_at?: string | null;
};

const MAX_ITEMS_PER_CATEGORY = 10;

export function IndexPanel({ category }: { category: string }) {
  const [indices, setIndices] = useState<IndexRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [assetType, setAssetType] = useState("index");

  const fetchIndices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/market/indices?category=${encodeURIComponent(category)}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(await res.text());
      const json = (await res.json()) as IndexRow[] | { data?: IndexRow[] };
      const data = Array.isArray(json) ? json : Array.isArray(json.data) ? json.data : [];
      setIndices(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load indices");
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    fetchIndices();
    const id = setInterval(fetchIndices, 30_000);
    return () => clearInterval(id);
  }, [fetchIndices]);

  const handleAdd = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim() || !symbol.trim()) return;
      setError(null);
      try {
        const res = await fetch("/api/market/indices", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category,
            name: name.trim(),
            symbol: symbol.trim(),
            asset_type: assetType,
          }),
        });
        if (!res.ok) throw new Error(await res.text());
        setName("");
        setSymbol("");
        setAssetType("index");
        setModalOpen(false);
        fetchIndices();
      } catch (e: any) {
        setError(e?.message || "Failed to add index");
      }
    },
    [category, name, symbol, assetType, fetchIndices]
  );

  const atLimit = indices.length >= MAX_ITEMS_PER_CATEGORY;

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
      {error ? (
        <div className="mt-2 rounded border border-amber-900/60 bg-amber-950/40 px-2 py-1 text-xs text-amber-200">
          {error}
        </div>
      ) : null}
      <div className="mt-2 flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-auto">
        {loading && indices.length === 0 ? (
          <div className="text-xs text-slate-400">Loading…</div>
        ) : (
          indices.map((item) => {
            const priceStr = item.price != null ? item.price.toFixed(2) : "--";
            const dataSource =
              item.stale ? "cached" : item.last_updated_at ? "live" : undefined;
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
