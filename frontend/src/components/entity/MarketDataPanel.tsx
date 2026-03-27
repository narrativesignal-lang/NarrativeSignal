"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

const MAX_ITEMS = 5;

type CardData = { symbol: string; name?: string; price: string | null; changePct: number | null };

export function MarketDataPanel({
  symbols,
  onAdd,
  onRemove,
}: {
  symbols: string[];
  onAdd: (symbol: string) => void;
  onRemove: (symbol: string) => void;
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ symbol: string; name?: string }>>([]);
  const [cards, setCards] = useState<CardData[]>([]);

  const canAdd = symbols.length < MAX_ITEMS;

  const fetchResults = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    try {
      const data = await api.assetsSearch(q);
      setResults(data);
    } catch {
      setResults([]);
    }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(fetchResults, 200);
    return () => clearTimeout(t);
  }, [fetchResults]);

  useEffect(() => {
    if (symbols.length === 0) {
      setCards([]);
      return;
    }
    let cancelled = false;
    (async () => {
      const next: CardData[] = [];
      for (const symbol of symbols) {
        try {
          const res = await api.ohlcv(symbol, "1D");
          const bars = (res?.bars || []) as Array<{ close: number }>;
          if (bars.length >= 2) {
            const close = bars[bars.length - 1].close;
            const prev = bars[bars.length - 2].close;
            const changePct = prev ? ((close - prev) / prev) * 100 : null;
            next.push({ symbol, name: undefined, price: close.toFixed(2), changePct });
          } else if (bars.length === 1) {
            next.push({ symbol, name: undefined, price: bars[0].close.toFixed(2), changePct: null });
          } else {
            next.push({ symbol, name: undefined, price: null, changePct: null });
          }
        } catch {
          next.push({ symbol, name: undefined, price: null, changePct: null });
        }
      }
      if (!cancelled) setCards(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [symbols.join(",")]);

  const selectResult = (symbol: string) => {
    if (!symbols.includes(symbol)) onAdd(symbol);
    setSearchOpen(false);
    setQuery("");
    setResults([]);
  };

  return (
    <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-900/30 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Market Data</h2>
        {canAdd && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setSearchOpen(!searchOpen)}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
            >
              + Add Data
            </button>
            {searchOpen && (
              <div className="absolute right-0 top-full z-10 mt-1 w-56 rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-lg">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search asset symbol"
                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-600"
                  autoFocus
                />
                <ul className="mt-2 max-h-40 overflow-y-auto">
                  {results.slice(0, 10).map((r) => (
                    <li key={r.symbol}>
                      <button
                        type="button"
                        onClick={() => selectResult(r.symbol)}
                        className="w-full rounded px-2 py-1 text-left text-xs text-slate-300 hover:bg-slate-800"
                      >
                        {r.symbol} {r.name ? `· ${r.name}` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">Max {MAX_ITEMS} symbols</p>
      <div className="mt-3 space-y-2">
        {cards.map((c) => (
          <div
            key={c.symbol}
            className="flex items-center justify-between rounded border border-slate-700 bg-slate-800/40 px-3 py-2"
          >
            <div>
              <div className="text-sm font-medium text-slate-200">{c.symbol}</div>
              <div className="flex items-baseline gap-2 text-xs">
                <span className="text-slate-400">{c.price ?? "—"}</span>
                {c.changePct != null && (
                  <span
                    className={
                      c.changePct >= 0 ? "text-emerald-400" : "text-red-400"
                    }
                  >
                    {c.changePct >= 0 ? "+" : ""}
                    {c.changePct.toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemove(c.symbol)}
              className="rounded p-1 text-slate-500 hover:bg-slate-700 hover:text-red-300"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
