"use client";

import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";

type MacroNewsItem = Awaited<ReturnType<typeof api.macroNews>>[number];
type MacroEventItem = Awaited<ReturnType<typeof api.macroEvents>>[number];

type Article = {
  id: string;
  title: string;
  source: string;
  timestamp: string | null;
  category?: string | null;
  subcategory?: string | null;
  sentiment?: string | null;
  impact?: number | null;
  summary?: string | null;
  url?: string | null;
};

export default function NewsDetailPage() {
  const params = useParams();
  const search = useSearchParams();
  const router = useRouter();
  const id = typeof params?.id === "string" ? params.id : null;

  const sourceType = search.get("source") || "macro_news"; // "macro_news" | "macro_event"
  const category = search.get("category") || undefined;
  const subcategory = search.get("subcategory") || undefined;

  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setArticle(null);
      setLoading(false);
      setError("Missing article id");
      return;
    }
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (sourceType === "macro_event") {
          const events: MacroEventItem[] = await api.macroEvents(100, category);
          const e = events.find((x) => x.id === id);
          if (!e) {
            setArticle(null);
            setError("Article not found");
          } else {
            setArticle({
              id: e.id,
              title: e.title,
              source: e.source,
              timestamp: e.timestamp ?? null,
              category: e.category,
              sentiment: e.sentiment ?? null,
              impact: e.importance_score ?? null,
              summary: null,
              url: null,
            });
          }
        } else {
          const news: MacroNewsItem[] = await api.macroNews(category || "general", subcategory, 100);
          const n = news.find((x) => x.id === id);
          if (!n) {
            setArticle(null);
            setError("Article not found");
          } else {
            setArticle({
              id: n.id,
              title: n.title,
              source: n.source ?? "—",
              timestamp: n.timestamp ?? null,
              category: n.category ?? category,
              subcategory: n.subcategory ?? subcategory,
              sentiment: n.sentiment ?? null,
              impact: n.impact ?? null,
              summary: n.summary ?? null,
              url: n.url ?? null,
            });
          }
        }
      } catch (e: any) {
        setError(e?.message ?? "Failed to load article");
        setArticle(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [id, sourceType, category, subcategory]);

  const ts = useMemo(() => {
    if (!article?.timestamp) return null;
    try {
      return new Date(article.timestamp).toLocaleString();
    } catch {
      return article.timestamp;
    }
  }, [article?.timestamp]);

  return (
    <Shell>
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => router.back()}
          className="text-xs text-slate-400 hover:text-slate-200"
        >
          ← Back
        </button>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          {loading ? (
            <div className="text-sm text-slate-400">Loading article…</div>
          ) : error ? (
            <div className="text-sm text-slate-400">{error}</div>
          ) : !article ? (
            <div className="text-sm text-slate-400">Article not found.</div>
          ) : (
            <div className="space-y-3">
              <div>
                <h1 className="text-lg font-semibold text-slate-50 leading-snug">
                  {article.title}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{article.source}</span>
                  {ts ? (
                    <>
                      <span>·</span>
                      <span>{ts}</span>
                    </>
                  ) : null}
                  {article.category ? (
                    <>
                      <span>·</span>
                      <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
                        {article.category}
                      </span>
                    </>
                  ) : null}
                  {article.subcategory ? (
                    <>
                      <span>·</span>
                      <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
                        {article.subcategory}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-xs">
                {article.sentiment && (
                  <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200">
                    Sentiment: {article.sentiment}
                  </span>
                )}
                {typeof article.impact === "number" && (
                  <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200">
                    Impact: {article.impact}
                  </span>
                )}
              </div>

              {article.summary ? (
                <div className="mt-2 rounded bg-slate-900/60 p-3 text-sm leading-relaxed text-slate-200">
                  {article.summary}
                </div>
              ) : (
                <div className="mt-2 rounded bg-slate-900/60 p-3 text-sm text-slate-400">
                  No full article text available. Use the original source link below for more details.
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-3">
                {article.url ? (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
                  >
                    Open Original Source
                  </a>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}

