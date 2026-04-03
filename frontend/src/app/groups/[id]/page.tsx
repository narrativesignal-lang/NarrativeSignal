"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { CandleChart } from "@/components/CandleChart";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";

const PERIODS = ["1D", "5D", "1M", "6M", "1Y", "MAX"] as const;

export default function GroupPage() {
  const params = useParams<{ id: string }>();
  const groupId = params.id;

  const [group, setGroup] = useState<any | null>(null);
  const [asset, setAsset] = useState<any | null>(null);
  const [symbolInput, setSymbolInput] = useState("");
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("1M");
  const [ohlcv, setOhlcv] = useState<any | null>(null);
  const [articles, setArticles] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshingArticles, setRefreshingArticles] = useState(false);
  const [savingSymbol, setSavingSymbol] = useState(false);

  useEffect(() => {
    (async () => {
      setInitialLoading(true);
      try {
        const g = await api.getGroup(groupId);
        setGroup(g);
        const a = await api.getGroupAsset(groupId);
        setAsset(a);
        setSymbolInput(a?.symbol || "");
      } catch (e: any) {
        setError(e?.message || "Failed to load group");
      } finally {
        setInitialLoading(false);
      }
    })();
  }, [groupId]);

  useEffect(() => {
    (async () => {
      setRefreshingArticles(true);
      try {
        const arts = await api.groupArticles(groupId, 30);
        setArticles(arts);
      } catch {
        setArticles(null);
      } finally {
        setRefreshingArticles(false);
      }
    })();
  }, [groupId]);

  useEffect(() => {
    (async () => {
      if (!asset?.symbol) {
        setOhlcv(null);
        return;
      }
      try {
        const res = await api.ohlcv(asset.symbol, period);
        setOhlcv(res);
      } catch (e: any) {
        setError(e?.message || "Failed to load OHLCV");
      }
    })();
  }, [asset?.symbol, period]);

  const bars = useMemo(() => (ohlcv?.bars || []) as any[], [ohlcv]);

  async function saveSymbol() {
    setError(null);
    setSavingSymbol(true);
    try {
      const next = await api.setGroupAsset(groupId, { symbol: symbolInput.trim().toUpperCase(), provider: "stooq" });
      setAsset(next);
    } catch (e: any) {
      setError(e?.message || "Failed to save symbol");
    } finally {
      setSavingSymbol(false);
    }
  }

  return (
    <Shell>
      <div className="space-y-6">
        {error ? (
          <div className="rounded border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">{error}</div>
        ) : null}

        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs text-slate-400">Keyword group</div>
              <h1 className="text-lg font-semibold">{group?.name || (initialLoading ? "Loading…" : "—")}</h1>
              <div className="mt-1 text-sm text-slate-300">
                {group?.terms?.length ? group.terms.map((t: any) => t.term).join(", ") : "—"}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Newly added targets/groups may take up to a few hours before trend/history data is fully populated.
              </p>
            </div>
            <Link href="/dashboard" className="text-sm text-indigo-300 hover:text-indigo-200">
              ← Back
            </Link>
          </div>
        </section>

        <section className="grid min-w-0 gap-6 md:grid-cols-[1fr_340px]">
          <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">Price chart</div>
              <div className="flex items-center gap-2">
                <select
                  className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value as any)}
                >
                  {PERIODS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mt-3">
              {asset?.symbol ? (
                bars.length ? (
                  <CandleChart bars={bars} />
                ) : (
                  <div className="text-sm text-slate-400">Loading OHLCV…</div>
                )
              ) : (
                <div className="text-sm text-slate-400">Link a symbol to enable candlesticks.</div>
              )}
            </div>
          </div>

          <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="text-sm font-semibold">Linked asset</div>
            <div className="mt-3 space-y-2">
              <label className="block">
                <div className="text-xs text-slate-400">Symbol</div>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  value={symbolInput}
                  onChange={(e) => setSymbolInput(e.target.value)}
                  placeholder="NVDA"
                />
              </label>
              <button className="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60" onClick={saveSymbol} disabled={savingSymbol}>
                {savingSymbol ? "Saving…" : "Save symbol"}
              </button>
              <div className="text-xs text-slate-400">Provider: Stooq (daily OHLCV, no API key).</div>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">Latest articles</div>
            <button
              className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
              disabled={refreshingArticles}
              onClick={async () => {
                setRefreshingArticles(true);
                try {
                  setArticles(await api.groupArticles(groupId, 30));
                } finally {
                  setRefreshingArticles(false);
                }
              }}
            >
              {refreshingArticles ? "Refreshing…" : "Refresh"}
            </button>
          </div>
          <div className="mt-3 space-y-3">
            {articles?.items?.length ? (
              articles.items.map((it: any) => (
                <div key={it.document_id} className="rounded border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">
                        {it.url ? (
                          <a className="text-indigo-200 hover:text-indigo-100" href={it.url} target="_blank" rel="noreferrer">
                            {it.title || "(untitled)"}
                          </a>
                        ) : (
                          it.title || "(untitled)"
                        )}
                      </div>
                      <div className="mt-1 text-xs text-slate-400">
                        {it.source} • {it.published_at ? new Date(it.published_at).toLocaleString() : "—"}
                      </div>
                    </div>
                    <div className="text-xs text-slate-300">
                      {it.sentiment_label ? (
                        <span
                          className={
                            "rounded px-2 py-1 " +
                            (it.sentiment_label === "bullish"
                              ? "bg-emerald-950/60 text-emerald-200 border border-emerald-900"
                              : it.sentiment_label === "bearish"
                              ? "bg-red-950/60 text-red-200 border border-red-900"
                              : "bg-slate-900 text-slate-200 border border-slate-800")
                          }
                        >
                          {it.sentiment_label} {typeof it.sentiment_score === "number" ? `(${it.sentiment_score.toFixed(2)})` : ""}
                        </span>
                      ) : (
                        <span className="text-slate-500">pending</span>
                      )}
                    </div>
                  </div>
                  {it.narrative_summary ? (
                    <div className="mt-2 text-sm text-slate-200">{it.narrative_summary}</div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-400">No linked articles yet. Create a schedule and trigger a run.</div>
            )}
          </div>
        </section>
      </div>
    </Shell>
  );
}

