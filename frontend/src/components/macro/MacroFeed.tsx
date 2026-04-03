"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { BlockStateMessage } from "@/components/BlockStateMessage";

type MacroEventItem = Awaited<ReturnType<typeof api.macroEvents>>[number];

function sentimentClass(sentiment: string | null): string {
  if (!sentiment) return "bg-slate-800 text-slate-400 border-slate-700";
  const s = sentiment.toLowerCase();
  if (s === "bullish" || s === "positive") return "bg-emerald-950/40 text-emerald-300 border-emerald-800/60";
  if (s === "bearish" || s === "negative") return "bg-red-950/40 text-red-300 border-red-800/60";
  return "bg-slate-800 text-slate-400 border-slate-700";
}

function FeedItem({ event, onPreview }: { event: MacroEventItem; onPreview: () => void }) {
  const ts = event.timestamp ? new Date(event.timestamp).toLocaleString() : "—";
  return (
    <div className="border-b border-slate-800/80 py-2.5 last:border-b-0">
      <div className="flex items-start justify-between gap-2">
        <div>
          <button
            type="button"
            onClick={onPreview}
            className="cursor-pointer font-medium leading-snug text-slate-100 hover:text-indigo-300"
          >
            {event.title}
          </button>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            <span>{event.source}</span>
            <span>·</span>
            <span>{ts}</span>
          </div>
        </div>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span
          className={
            "inline-block rounded border px-2 py-0.5 text-xs " + sentimentClass(event.sentiment)
          }
        >
          {event.sentiment ?? "—"}
        </span>
        <button
          type="button"
          onClick={onPreview}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] font-medium text-slate-300 hover:bg-slate-800"
        >
          Preview
        </button>
      </div>
    </div>
  );
}

function FeedItemPlaceholder({ index }: { index: number }) {
  return (
    <div className="border-b border-slate-800/80 py-2.5 last:border-b-0">
      <div className="font-medium leading-snug text-slate-300">Headline placeholder {index + 1}</div>
      <div className="mt-1 text-xs text-slate-500">Source · {new Date(Date.now() - index * 3600000).toLocaleString()}</div>
      <div className="mt-1.5">
        <span className="inline-block rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          —
        </span>
      </div>
    </div>
  );
}

export function MacroFeed({ category }: { category: string | null }) {
  const [events, setEvents] = useState<MacroEventItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<MacroEventItem | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.macroEvents(50, category ?? undefined);
        setEvents(data);
      } catch (e: any) {
        setError(e?.message ?? "Failed to load macro events");
        setEvents([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [category]);

  const showPlaceholder = loading === false && (!events || events.length === 0);
  const placeholderCount = 8;

  return (
    <div className="flex flex-col">
      <div className="text-sm font-semibold text-slate-300">News & narrative feed</div>
      {error ? (
        <div className="mt-2 rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
          {error}
        </div>
      ) : null}
      {loading ? (
        <div className="mt-3">
          <BlockStateMessage kind="loading" />
        </div>
      ) : (
        <div className="mt-3 flex-1 space-y-0 overflow-y-auto pr-2">
          {showPlaceholder
            ? Array.from({ length: placeholderCount }, (_, i) => (
                <FeedItemPlaceholder key={i} index={i} />
              ))
            : (events ?? []).map((event) => (
                <FeedItem key={event.id} event={event} onPreview={() => setPreview(event)} />
              ))}
        </div>
      )}
      {preview ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-100">Article preview</h3>
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              >
                Close
              </button>
            </div>
            <div className="mt-2 space-y-2">
              <div>
                <div className="text-sm font-medium leading-snug text-slate-50">
                  {preview.title}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{preview.source}</span>
                  {preview.timestamp ? (
                    <>
                      <span>·</span>
                      <span>{new Date(preview.timestamp).toLocaleString()}</span>
                    </>
                  ) : null}
                  {preview.category ? (
                    <>
                      <span>·</span>
                      <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
                        {preview.category}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {preview.sentiment && (
                  <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200">
                    Sentiment: {preview.sentiment}
                  </span>
                )}
                {typeof preview.importance_score === "number" && (
                  <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200">
                    Impact: {preview.importance_score}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-400">
                No full article text available. Use the original publisher directly for full details.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
