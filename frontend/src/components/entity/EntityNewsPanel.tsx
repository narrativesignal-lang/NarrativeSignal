"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type NewsMode = "target" | "keywords";

type InstrumentLite = { symbol: string; display_name: string | null } | null;

const ENTITY_NEWS_STALE_MS = 5 * 60 * 1000;

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Date.now() - t;
  const sec = Math.floor(diff / 1000);
  if (sec < 45) return "now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 36) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-slate-400" aria-hidden>
      <path
        d="M4 12a8 8 0 0114.583-4.001M20 12a8 8 0 01-14.583 4.001"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path d="M19 5v4h-4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 19v-4h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function EntityNewsPanel(props: {
  entityId: string;
  heightPx: number;
  instrument: InstrumentLite;
  entityName: string;
  terms: string[];
  onPendingChange?: (pending: boolean) => void;
}) {
  const { entityId, heightPx, instrument, entityName, terms, onPendingChange } = props;
  const { t } = useI18n();
  const [tab, setTab] = useState<NewsMode>("target");

  const targetQ = useQuery({
    queryKey: ["entity", "news", entityId, "target"],
    queryFn: () => api.getEntityNews(entityId, "target"),
    enabled: Boolean(entityId),
    staleTime: ENTITY_NEWS_STALE_MS,
    gcTime: 45 * 60 * 1000,
  });

  const keywordsQ = useQuery({
    queryKey: ["entity", "news", entityId, "keywords"],
    queryFn: () => api.getEntityNews(entityId, "keywords"),
    enabled: tab === "keywords" && terms.length > 0 && Boolean(entityId),
    staleTime: ENTITY_NEWS_STALE_MS,
    gcTime: 45 * 60 * 1000,
  });

  const activeQ = tab === "target" ? targetQ : keywordsQ;
  const active = activeQ.data;
  const items = active?.items ?? [];
  const backendErr = active?.error;

  const listLoading = activeQ.isPending && !activeQ.data;

  useEffect(() => {
    onPendingChange?.(listLoading);
  }, [listLoading, onPendingChange]);

  const showKeywordEmpty = tab === "keywords" && terms.length === 0;
  const showTargetHint = tab === "target" && !instrument && !entityName.trim();
  const showEmptyList =
    !listLoading &&
    active &&
    items.length === 0 &&
    !showKeywordEmpty &&
    !showTargetHint &&
    backendErr !== "fetch_failed";

  const countLabel =
    listLoading && !active
      ? "—"
      : showKeywordEmpty || showTargetHint
        ? "—"
        : t("entity.newsCount", { count: items.length });

  const clientError =
    activeQ.isError && !active
      ? parseApiError(activeQ.error)
      : active && backendErr === "fetch_failed"
        ? t("entity.newsError")
        : null;

  return (
    <section
      data-testid="entity-news-panel"
      className="flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900/30"
      style={{ height: Math.max(220, Math.round(heightPx)) }}
    >
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <div className="flex min-w-0 flex-1 items-baseline gap-2">
          <h2 className="shrink-0 text-sm font-semibold text-slate-200">{t("entity.newsTitle")}</h2>
          <span className="truncate text-[11px] font-medium tabular-nums text-slate-500" title={String(countLabel)}>
            {countLabel}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void activeQ.refetch()}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-slate-700 bg-slate-950/40 text-slate-300 hover:border-slate-500 hover:bg-slate-800 disabled:opacity-45"
          disabled={listLoading || showKeywordEmpty || showTargetHint}
          aria-label={t("entity.newsRefresh")}
          title={t("entity.newsRefresh")}
        >
          <RefreshIcon />
        </button>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 px-2 pt-1">
        <div className="flex gap-1">
          {(["target", "keywords"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setTab(m)}
              className={
                "rounded-t px-2.5 py-1.5 text-xs font-medium " +
                (tab === m ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200")
              }
            >
              {m === "target" ? t("entity.newsTargetTab") : t("entity.newsKeywordTab")}
            </button>
          ))}
        </div>
        {active?.cached && !listLoading ? (
          <span className="pr-1 text-[10px] text-slate-600">{t("entity.newsCached")}</span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {clientError && !active ? (
          <div className="mb-2 text-center text-sm text-amber-200/90">{clientError}</div>
        ) : null}
        {backendErr === "fetch_failed" && active && !activeQ.isFetching ? (
          <div className="mb-2 text-center text-sm text-amber-200/90">{t("entity.newsError")}</div>
        ) : null}
        {listLoading && !active ? (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse rounded border border-slate-800 bg-slate-950/50 p-2">
                <div className="h-3 w-4/5 rounded bg-slate-800" />
                <div className="mt-2 h-2 w-1/3 rounded bg-slate-800/70" />
                <div className="mt-2 h-2 w-full rounded bg-slate-800/40" />
              </div>
            ))}
          </div>
        ) : null}
        {listLoading && active ? (
          <div className="mb-2 text-[11px] text-slate-500">{t("entity.newsLoading")}</div>
        ) : null}
        {showKeywordEmpty ? (
          <div className="py-6 text-center text-sm text-slate-500">{t("entity.newsEmptyKeywords")}</div>
        ) : null}
        {showTargetHint ? (
          <div className="py-6 text-center text-sm text-slate-500">{t("entity.newsEmptyTarget")}</div>
        ) : null}
        {showEmptyList ? (
          <div className="py-6 text-center text-sm text-slate-500">{t("entity.newsNoHeadlines")}</div>
        ) : null}
        <ul className="space-y-3">
          {items.map((item, idx) => (
            <li key={`${item.url ?? item.title}-${idx}`} className="border-b border-slate-800/60 pb-3 last:border-0">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="line-clamp-2 text-sm font-medium text-indigo-200 hover:text-indigo-100"
                >
                  {item.title}
                </a>
              ) : (
                <span className="line-clamp-2 text-sm font-medium text-slate-200">{item.title}</span>
              )}
              <div className="mt-0.5 text-[11px] text-slate-500">
                <span className="text-slate-400">{item.source}</span>
                <span className="mx-1">·</span>
                <span>{formatRelative(item.published_at)}</span>
              </div>
              {item.snippet ? (
                <p className="mt-1 line-clamp-2 text-xs text-slate-400">{item.snippet}</p>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
