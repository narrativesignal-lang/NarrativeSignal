"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, parseApiError } from "@/lib/api";
import type { MacroCategorySlug } from "@/lib/macroCategories";
import { STALE_MACRO_NEWS_MS } from "@/lib/queryClient";
import { mockNewsForCategory, type NewsItem } from "@/lib/macroMockData";
import { writeMacroNewsArticleToSession } from "@/lib/macroNewsDetailCache";
import { cleanMacroNewsTitle, htmlToPlainText } from "@/lib/plainText";

const NEWS_LIMIT = 40;

const MACRO_NEWS_LS_KEY = "narrative_macro_news_list_v1";

function readRawFromStorage(category: string): NewsItem[] | null {
  try {
    const raw = localStorage.getItem(MACRO_NEWS_LS_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as Record<string, { items: NewsItem[] }>;
    const row = o[category];
    if (!row?.items?.length) return null;
    return row.items;
  } catch {
    return null;
  }
}

function writeRawToStorage(category: string, items: NewsItem[]) {
  try {
    const raw = localStorage.getItem(MACRO_NEWS_LS_KEY);
    const o = raw ? (JSON.parse(raw) as Record<string, { items: NewsItem[] }>) : {};
    o[category] = { items };
    localStorage.setItem(MACRO_NEWS_LS_KEY, JSON.stringify(o));
  } catch {
    /* quota */
  }
}

function mapApiToNewsItems(
  data: Awaited<ReturnType<typeof api.macroNews>>["data"] | undefined,
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

function compareNewsItems(a: NewsItem, b: NewsItem): number {
  const ia = a.impact;
  const ib = b.impact;
  const tierA = a.publisher_tier;
  const tierB = b.publisher_tier;
  const tsA = new Date(a.timestamp).getTime();
  const tsB = new Date(b.timestamp).getTime();
  if (ia != null && ib != null) {
    if (ib !== ia) return ib - ia;
    if (tierA !== tierB) return tierA - tierB;
    return tsB - tsA;
  }
  if (ia != null && ib == null) return -1;
  if (ia == null && ib != null) return 1;
  if (tierA !== tierB) return tierA - tierB;
  return tsB - tsA;
}

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

function NewsListItem({ item, categorySlug }: { item: NewsItem; categorySlug: MacroCategorySlug }) {
  const [open, setOpen] = useState(false);
  const ts = item.timestamp ? new Date(item.timestamp).toLocaleString() : "—";
  const dupCount = item.duplicate_count ?? 1;
  const others = item.related_publishers ?? [];
  const clusterTitle =
    others.length > 0
      ? `Also: ${others.join(", ")}`
      : dupCount > 1
        ? `${dupCount} outlets merged for this story`
        : "";
  const titleDisplay = cleanMacroNewsTitle(item.title);
  const summaryPlain = item.summary ? htmlToPlainText(item.summary, 12000) : "";
  const detailHref = `/news/${encodeURIComponent(item.id)}?source=macro_news&category=${encodeURIComponent(
    categorySlug
  )}${item.subcategory ? `&subcategory=${encodeURIComponent(item.subcategory)}` : ""}`;

  const persistArticle = () =>
    writeMacroNewsArticleToSession({
      id: item.id,
      title: item.title,
      source: item.source,
      timestamp: item.timestamp ?? null,
      category: categorySlug,
      subcategory: item.subcategory,
      sentiment: item.sentiment,
      impact: item.impact ?? null,
      summary: item.summary ?? null,
      url: item.url ?? null,
      duplicate_count: item.duplicate_count,
      related_publishers: item.related_publishers,
    });

  return (
    <div className="border-b border-slate-800/80 py-2.5 last:border-b-0">
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        className="w-full cursor-pointer rounded-md text-left outline-none ring-slate-600 focus-visible:ring-2"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-2">
              <span className="block min-w-0 flex-1 font-medium leading-snug text-slate-100">{titleDisplay}</span>
              <span className="shrink-0 tabular-nums text-xs text-slate-500" aria-hidden>
                {open ? "−" : "+"}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1">
                {item.source}
                {item.publisher_tier === 1 || item.publisher_tier === 2 ? (
                  <span
                    className="rounded border border-slate-700/60 px-1 py-px text-[9px] font-medium uppercase tracking-wide text-slate-500"
                    title={`Publisher tier ${item.publisher_tier}`}
                  >
                    T{item.publisher_tier}
                  </span>
                ) : null}
              </span>
              <span>·</span>
              <span>{ts}</span>
              <span>·</span>
              <span>{item.subcategory}</span>
            </div>
            {dupCount > 1 ? (
              <p
                className="mt-0.5 text-[10px] leading-snug text-slate-500"
                title={clusterTitle || undefined}
              >
                <span className="text-slate-500">{dupCount}-source coverage</span>
                <span className="text-slate-600">
                  {" "}
                  · +{dupCount - 1} related
                  {others.length ? ` · ${others.join(", ")}` : ""}
                </span>
              </p>
            ) : null}
            {open ? (
              <div className="mt-2 space-y-2 border-l-2 border-slate-700/80 pl-3">
                {summaryPlain ? (
                  <p className="text-sm leading-relaxed text-slate-300">{summaryPlain}</p>
                ) : (
                  <p className="text-sm text-slate-500">No summary for this item yet.</p>
                )}
                <Link
                  href={detailHref}
                  className="inline-block text-xs font-medium text-indigo-400 hover:text-indigo-300"
                  onClick={(e) => {
                    e.stopPropagation();
                    persistArticle();
                  }}
                >
                  Open article page in app →
                </Link>
              </div>
            ) : null}
          </div>
        </div>
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
          Impact {item.impact != null ? `${item.impact}/10` : "—"}
        </span>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded bg-indigo-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500"
            title="Opens the publisher site in a new tab"
          >
            Open Original Source
          </a>
        ) : (
          <span className="text-[11px] text-slate-500">Original URL unavailable.</span>
        )}
      </div>
    </div>
  );
}

export function NewsList({ categorySlug, subcategoryFilter }: Props) {
  const q = useQuery({
    queryKey: ["macro", "news", categorySlug ?? "", NEWS_LIMIT],
    queryFn: () => api.macroNews(categorySlug!, null, NEWS_LIMIT),
    enabled: Boolean(categorySlug),
    staleTime: STALE_MACRO_NEWS_MS,
    gcTime: 60 * 60 * 1000
  });

  useEffect(() => {
    if (q.isSuccess && q.data?.data?.length && categorySlug) {
      const mapped = mapApiToNewsItems(q.data.data, categorySlug);
      writeRawToStorage(categorySlug, mapped);
    }
  }, [q.isSuccess, q.data, categorySlug]);

  const rawItems = useMemo(() => {
    if (!categorySlug) return [];
    if (q.isSuccess && q.data?.data) {
      return mapApiToNewsItems(q.data.data, categorySlug);
    }
    const cached = readRawFromStorage(categorySlug);
    if (cached?.length) return cached;
    if (q.isError) {
      return mockNewsForCategory(categorySlug, subcategoryFilter, NEWS_LIMIT);
    }
    return [];
  }, [categorySlug, q.isSuccess, q.data, q.isError, subcategoryFilter]);

  const displayedItems = useMemo(() => {
    let list = rawItems;
    if (subcategoryFilter != null) {
      list = list.filter((x) => x.subcategory === subcategoryFilter);
    }
    return [...list].sort(compareNewsItems);
  }, [rawItems, subcategoryFilter]);

  const loading = Boolean(categorySlug) && q.isPending && rawItems.length === 0;
  const error = q.isError ? parseApiError(q.error) : null;

  if (!categorySlug) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-1 items-center justify-center p-4 text-sm text-slate-500">
          Select a category to see news
        </div>
      </div>
    );
  }

  const env = q.data;
  const showPrep =
    env?.loading_state === "warming" ||
    env?.loading_state === "placeholder" ||
    env?.data_source === "placeholder";
  const showStale =
    env?.data_source === "stale_fallback" ||
    env?.loading_state === "stale" ||
    Boolean(env?.stale && env?.data_updated_at);

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
      {env?.message && showPrep ? (
        <div className="mb-2 rounded border border-sky-900/50 bg-sky-950/25 px-3 py-2 text-[11px] leading-snug text-sky-100/90">
          {env.message}
          <span className="mt-1 block text-sky-200/60">Retrying in the background…</span>
        </div>
      ) : null}
      {showStale && env?.data_updated_at && !showPrep ? (
        <div className="mb-2 text-[10px] text-slate-500">
          Snapshot from {new Date(env.data_updated_at).toLocaleString()} ·{" "}
          <span className="text-amber-200/80">stale</span>
        </div>
      ) : null}
      {q.isError && error ? (
        <div className="mb-2 rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
          {error} Sample articles are shown below.
        </div>
      ) : null}
      {loading && displayedItems.length > 0 ? (
        <div className="mb-2 text-[11px] text-slate-500">Refreshing latest…</div>
      ) : null}
      {loading && displayedItems.length === 0 ? (
        <div className="min-h-0 flex-1 space-y-3 overflow-hidden py-2 pr-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="animate-pulse border-b border-slate-800/60 pb-3">
              <div className="h-4 rounded bg-slate-800/90" style={{ maxWidth: `${88 - i * 8}%` }} />
              <div className="mt-2 h-3 w-1/2 rounded bg-slate-800/60" />
            </div>
          ))}
        </div>
      ) : null}
      {(!loading || displayedItems.length > 0) && (
        <div className="min-h-0 flex-1 space-y-0 overflow-y-auto pr-2">
          {!loading && displayedItems.length === 0 ? (
            <div className="py-4 text-sm text-slate-500">No news in this filter.</div>
          ) : displayedItems.length > 0 ? (
            displayedItems.map((item) => (
              <NewsListItem key={item.id} item={item} categorySlug={categorySlug} />
            ))
          ) : null}
        </div>
      )}
    </div>
  );
}
