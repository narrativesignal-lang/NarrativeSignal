"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MacroCategorySlug } from "@/lib/macroCategories";
import { getSubcategories } from "@/lib/macroCategories";
import type { NewsItem } from "@/lib/macroMockData";
import { mockNewsForCategory } from "@/lib/macroMockData";

const NEWS_LIMIT = 40;

type Props = {
  categorySlug: MacroCategorySlug | null;
  subcategoryFilter: string | null;
};

function sentimentClass(sentiment: string | null): string {
  if (!sentiment) return "bg-slate-800 text-slate-400 border-slate-700";
  const s = sentiment.toLowerCase();
  if (s === "bullish" || s === "positive")
    return "bg-emerald-950/40 text-emerald-300 border-emerald-800/60";
  if (s === "bearish" || s === "negative")
    return "bg-red-950/40 text-red-300 border-red-800/60";
  return "bg-slate-800 text-slate-400 border-slate-700";
}

function NewsListItem({
  item,
  expanded,
  onToggle,
}: {
  item: NewsItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const ts = item.timestamp ? new Date(item.timestamp).toLocaleString() : "—";
  return (
    <div className="border-b border-slate-800/80 py-2.5 last:border-b-0">
      <div className="flex items-start justify-between gap-2">
        <div>
          <button
            type="button"
            onClick={onToggle}
            className="cursor-pointer font-medium leading-snug text-slate-100 hover:text-indigo-300"
          >
            {item.title}
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-400">
            <span>{item.source}</span>
            <span>·</span>
            <span>{ts}</span>
            <span>·</span>
            <span className="text-slate-400">{item.subcategory}</span>
          </div>
        </div>
        {/* Right side reserved for future icons/buttons if needed */}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <span
          className={
            "inline-block rounded border px-2 py-0.5 text-xs " + sentimentClass(item.sentiment)
          }
        >
          {item.sentiment ?? "—"}
        </span>
        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          Impact {item.impact}/10
        </span>
      </div>
      {expanded ? (
        <div className="mt-2 rounded bg-slate-900/60 p-2 text-xs text-slate-200">
          {item.summary ? (
            <p className="leading-relaxed">{item.summary}</p>
          ) : (
            <p className="text-slate-400">
              No summary available. Use the original source link for full details.
            </p>
          )}
          <div className="mt-2 flex items-center gap-2">
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center rounded bg-indigo-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500"
              >
                Open Original Source
              </a>
            ) : (
              <span className="text-[11px] text-slate-500">
                Original source URL not available.
              </span>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function NewsList({ categorySlug, subcategoryFilter }: Props) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [useMock, setUseMock] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (!categorySlug) {
      setItems([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    setUseMock(false);

    (async () => {
      try {
        const data = await api.macroNews(categorySlug, subcategoryFilter, NEWS_LIMIT);
        const mapped: NewsItem[] = (data || []).map((e) => ({
          id: e.id,
          title: e.title,
          source: e.source ?? "—",
          timestamp: e.timestamp ?? new Date().toISOString(),
          category: e.category ?? categorySlug,
          subcategory: e.subcategory ?? "General",
          url: e.url,
          summary: e.summary,
          sentiment: e.sentiment ?? null,
          impact: e.impact ?? 5,
        }));

        // Extra safety: if backend didn't filter by subcategory, enforce it here.
        const filtered =
          subcategoryFilter != null
            ? mapped.filter((x) => x.subcategory === subcategoryFilter)
            : mapped;
        setItems(filtered);
      } catch (e: unknown) {
        setError((e as { message?: string })?.message ?? "Failed to load news");
        const mock = mockNewsForCategory(categorySlug, subcategoryFilter, NEWS_LIMIT);
        setItems(mock);
        setUseMock(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [categorySlug, subcategoryFilter]);

  if (!categorySlug) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-1 items-center justify-center p-4 text-sm text-slate-500">
          Select a category to see news
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-2 flex shrink-0 items-center justify-between">
        <div className="text-sm font-semibold text-slate-300">News list</div>
        {subcategoryFilter ? (
          <span className="rounded bg-slate-700/80 px-2 py-0.5 text-xs text-slate-200">
            Filter: {subcategoryFilter}
          </span>
        ) : null}
      </div>
      {error && !useMock ? (
        <div className="mb-2 rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
          {error} (showing mock data)
        </div>
      ) : null}
      {loading ? (
        <div className="py-4 text-sm text-slate-500">Loading…</div>
      ) : (
        <div className="min-h-0 flex-1 space-y-0 overflow-y-auto pr-2">
          {items.length === 0 ? (
            <div className="py-4 text-sm text-slate-500">No news in this filter.</div>
          ) : (
            items.map((item) => (
              <NewsListItem
                key={item.id}
                item={item}
                expanded={expandedId === item.id}
                onToggle={() =>
                  setExpandedId((prev) => (prev === item.id ? null : item.id))
                }
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
