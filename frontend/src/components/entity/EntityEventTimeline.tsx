"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { SectionHelp } from "@/components/SectionHelp";
import { api, parseApiError } from "@/lib/api";
import type { ChartVisibleTimeRange } from "@/lib/chartTimeUnix";
import { useI18n } from "@/lib/i18n";
import type { CandleBar } from "@/lib/ohlcvBars";
import { buildSyncedTimelinePoints, type TimelinePointBuilt } from "@/lib/timelineVolatility";

type TimelineAccess = {
  can_interact: boolean;
  is_admin: boolean;
  paid_access: boolean;
  credits_balance: number;
  reason: string | null;
};

export type EntityEventTimelineProps = {
  entityId: string;
  symbol: string;
  period: string;
  chartScope: string;
  /** OHLCV bars for the same chart; used to recompute volatility for the visible window. */
  bars?: CandleBar[];
  /** From CandleChart zoom/pan; when null, timeline uses full bar extent. */
  visibleTimeRange?: ChartVisibleTimeRange | null;
};

type SummaryWindowKey = "point" | "24h" | "72h" | "7d" | "custom";

const PROVIDERS = [
  { id: "gemini" as const, labelKey: "timeline.providerGemini" as const },
  { id: "openai" as const, labelKey: "timeline.providerGpt" as const },
  { id: "anthropic" as const, labelKey: "timeline.providerClaude" as const },
  { id: "qwen" as const, labelKey: "timeline.providerQwen" as const },
];

function localDatetimeInputToIsoUtc(value: string): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

export function EntityEventTimeline({
  entityId,
  symbol,
  period,
  chartScope,
  bars = [],
  visibleTimeRange = null,
}: EntityEventTimelineProps) {
  const { t } = useI18n();
  const panelId = useId();
  const [officialPoints, setOfficialPoints] = useState<TimelinePointBuilt[]>([]);
  const [access, setAccess] = useState<TimelineAccess | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [windowLoading, setWindowLoading] = useState(false);
  const [windowErr, setWindowErr] = useState<string | null>(null);
  const [windowData, setWindowData] = useState<Awaited<ReturnType<typeof api.getEntityPriceTimelineWindow>> | null>(
    null
  );

  const [provider, setProvider] = useState<(typeof PROVIDERS)[number]["id"]>("gemini");
  const [summaryWindow, setSummaryWindow] = useState<SummaryWindowKey>("point");
  const [customStartLocal, setCustomStartLocal] = useState("");
  const [customEndLocal, setCustomEndLocal] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiBlock, setAiBlock] = useState<Awaited<ReturnType<typeof api.postEntityPriceTimelineAiSummary>> | null>(null);

  const fetchPoints = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoading(true);
    setLoadErr(null);
    try {
      const res = await api.getEntityPriceTimelinePoints(entityId, {
        symbol: symbol.trim(),
        period,
        chart_scope: chartScope,
      });
      setOfficialPoints(res.points.filter((p) => p.point_type === "official"));
      setAccess(res.access);
    } catch (e) {
      setLoadErr(parseApiError(e));
      setOfficialPoints([]);
      setAccess(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, period, chartScope, entityId]);

  useEffect(() => {
    fetchPoints();
  }, [fetchPoints]);

  const barExtent = useMemo(() => {
    if (!bars.length) return null;
    const times = bars.map((b) => b.time);
    return { from: Math.min(...times), to: Math.max(...times) };
  }, [bars]);

  /** Timeline track [start,end] in unix: visible chart range clamped to loaded bars. */
  const trackRange = useMemo(() => {
    if (!barExtent) return null;
    if (visibleTimeRange && visibleTimeRange.from < visibleTimeRange.to) {
      return {
        start: Math.max(barExtent.from, visibleTimeRange.from),
        end: Math.min(barExtent.to, visibleTimeRange.to),
      };
    }
    return { start: barExtent.from, end: barExtent.to };
  }, [barExtent, visibleTimeRange]);

  const displayPoints = useMemo(() => {
    if (!bars.length || !trackRange || trackRange.end <= trackRange.start) {
      return [] as TimelinePointBuilt[];
    }
    const sym = symbol.trim().toUpperCase();
    return buildSyncedTimelinePoints(sym, bars, officialPoints, trackRange.start, trackRange.end);
  }, [bars, officialPoints, symbol, trackRange]);

  const openPoint = useCallback(
    async (pointId: string) => {
      setSelectedId(pointId);
      setPanelOpen(true);
      setWindowErr(null);
      setWindowData(null);
      setAiBlock(null);
      setSummaryWindow("point");
      setWindowLoading(true);
      try {
        const w = await api.getEntityPriceTimelineWindow(entityId, pointId);
        setWindowData(w);
      } catch (e: unknown) {
        const msg = parseApiError(e);
        setWindowErr(msg);
      } finally {
        setWindowLoading(false);
      }
    },
    [entityId]
  );

  const closePanel = useCallback(() => {
    setPanelOpen(false);
    setSelectedId(null);
    setWindowData(null);
    setWindowErr(null);
    setAiBlock(null);
  }, []);

  const runAi = useCallback(async () => {
    if (!selectedId || !access?.can_interact || !access?.is_admin) return;
    let custom_start_iso: string | null = null;
    let custom_end_iso: string | null = null;
    if (summaryWindow === "custom") {
      custom_start_iso = localDatetimeInputToIsoUtc(customStartLocal);
      custom_end_iso = localDatetimeInputToIsoUtc(customEndLocal);
      if (!custom_start_iso || !custom_end_iso) {
        setAiBlock({
          status: "error",
          provider,
          interpretation: null,
          summary: t("timeline.customRangeInvalid"),
          citations: [],
          model_label: null,
          detail: null,
        });
        return;
      }
    }
    setAiLoading(true);
    setAiBlock(null);
    try {
      const res = await api.postEntityPriceTimelineAiSummary(entityId, {
        point_id: selectedId,
        provider,
        summary_window: summaryWindow,
        custom_start_iso,
        custom_end_iso,
      });
      setAiBlock(res);
    } catch (e) {
      setAiBlock({
        status: "error",
        provider,
        interpretation: null,
        summary: parseApiError(e),
        citations: [],
        model_label: null,
        detail: null,
      });
    } finally {
      setAiLoading(false);
    }
  }, [
    selectedId,
    access?.can_interact,
    access?.is_admin,
    entityId,
    provider,
    summaryWindow,
    customStartLocal,
    customEndLocal,
    t,
  ]);

  if (!symbol.trim()) return null;

  const span = trackRange ? trackRange.end - trackRange.start : 0;
  const posFor = (unix: number) => {
    if (!trackRange || span <= 0) return 50;
    return Math.min(100, Math.max(0, ((unix - trackRange.start) / span) * 100));
  };

  const panel =
    panelOpen && typeof document !== "undefined"
      ? createPortal(
          <div className="fixed inset-0 z-[80] flex justify-end bg-black/50" role="presentation">
            <button type="button" className="absolute inset-0 cursor-default" aria-label={t("timeline.closePanel")} onClick={closePanel} />
            <div
              role="dialog"
              aria-labelledby={`${panelId}-title`}
              className="relative z-[81] flex h-full w-full max-w-md flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
                <h3 id={`${panelId}-title`} className="text-sm font-semibold text-slate-100">
                  {t("timeline.windowTitle")}
                </h3>
                <button
                  type="button"
                  onClick={closePanel}
                  className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                >
                  {t("timeline.closePanel")}
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-sm">
                {windowLoading ? (
                  <p className="text-slate-400">{t("common.loading")}</p>
                ) : windowErr ? (
                  <p className="text-red-300">{windowErr}</p>
                ) : windowData ? (
                  <div className="space-y-4">
                    <div className="text-xs text-slate-400">
                      <div>
                        <span className="text-slate-500">{t("timeline.windowFocus")}: </span>
                        {new Date(windowData.focus_time * 1000).toISOString().slice(0, 10)}
                      </div>
                      <div className="mt-1">
                        <span className="text-slate-500">{t("timeline.windowRange")}: </span>
                        {windowData.window_start_iso} — {windowData.window_end_iso}
                      </div>
                      <div className="mt-1">
                        <span className="text-slate-500">{t("entity.instrument")}: </span>
                        {windowData.symbol}
                      </div>
                      <div className="mt-1">
                        <span className="text-slate-500">{t("timeline.pointType")}: </span>
                        {windowData.point_type === "volatility" ? t("timeline.pointVolatility") : t("timeline.pointOfficial")}
                      </div>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      {windowData.point_type === "volatility" ? t("timeline.newsContextVolatility") : t("timeline.newsContextOfficial")}
                    </p>
                    {!windowData.items.length ? (
                      <p className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2.5 text-sm text-slate-400">
                        {(windowData.status_message && windowData.status_message.trim()) ||
                          (windowData.news_status === "fetch_failed"
                            ? t("timeline.newsFetchFailed")
                            : t("timeline.noRelevantNews"))}
                      </p>
                    ) : (
                    <ul className="space-y-3">
                      {windowData.items.map((item) => (
                        <li key={item.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                          <div className="font-medium text-slate-100">{item.title}</div>
                          <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-400">
                            <span>
                              {t("timeline.source")}: {item.source_name}
                            </span>
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{item.category}</span>
                            <span
                              className={
                                item.sentiment === "bullish"
                                  ? "text-emerald-400"
                                  : item.sentiment === "bearish"
                                    ? "text-red-400"
                                    : "text-slate-400"
                              }
                            >
                              {item.sentiment === "bullish"
                                ? t("timeline.sentiment.bullish")
                                : item.sentiment === "bearish"
                                  ? t("timeline.sentiment.bearish")
                                  : t("timeline.sentiment.neutral")}
                            </span>
                          </div>
                          {item.source_url ? (
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 inline-block text-[11px] text-indigo-400 hover:text-indigo-300"
                            >
                              {t("timeline.link")}
                            </a>
                          ) : null}
                          <p className="mt-2 text-xs leading-relaxed text-slate-300">{item.summary}</p>
                        </li>
                      ))}
                    </ul>
                    )}
                    <div className="border-t border-slate-800 pt-3">
                      {access?.is_admin ? (
                        <>
                      <div className="text-xs font-semibold text-slate-300">{t("timeline.aiSummary")}</div>
                      <div className="mt-2 space-y-2">
                        <label className="block text-[11px] text-slate-500">
                          {t("timeline.summaryWindowLabel")}
                          <select
                            className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                            value={summaryWindow}
                            onChange={(e) => setSummaryWindow(e.target.value as SummaryWindowKey)}
                          >
                            <option value="point">{t("timeline.summaryWindowPoint")}</option>
                            <option value="24h">{t("timeline.summaryWindow24h")}</option>
                            <option value="72h">{t("timeline.summaryWindow72h")}</option>
                            <option value="7d">{t("timeline.summaryWindow7d")}</option>
                            <option value="custom">{t("timeline.summaryWindowCustom")}</option>
                          </select>
                        </label>
                        {summaryWindow === "custom" ? (
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <label className="text-[11px] text-slate-500">
                              {t("timeline.customStart")}
                              <input
                                type="datetime-local"
                                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                                value={customStartLocal}
                                onChange={(e) => setCustomStartLocal(e.target.value)}
                              />
                            </label>
                            <label className="text-[11px] text-slate-500">
                              {t("timeline.customEnd")}
                              <input
                                type="datetime-local"
                                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                                value={customEndLocal}
                                onChange={(e) => setCustomEndLocal(e.target.value)}
                              />
                            </label>
                          </div>
                        ) : null}
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                          <label className="text-[11px] text-slate-500">
                            {t("timeline.aiChooseProvider")}
                            <select
                              className="ml-2 rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                              value={provider}
                              onChange={(e) => setProvider(e.target.value as (typeof PROVIDERS)[number]["id"])}
                            >
                              {PROVIDERS.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {t(p.labelKey)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            onClick={runAi}
                            disabled={aiLoading}
                            className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                          >
                            {aiLoading ? t("timeline.aiLoading") : t("timeline.aiRun")}
                          </button>
                        </div>
                      </div>
                      {aiBlock ? (
                        <div className="mt-3 rounded-md border border-slate-700 bg-slate-950/80 p-2.5 text-xs text-slate-300">
                          {aiBlock.model_label ? (
                            <div className="mb-1 text-[11px] text-slate-500">{aiBlock.model_label}</div>
                          ) : null}
                          {aiBlock.interpretation ? (
                            <div className="mb-2 text-[11px] text-slate-400">
                              {t("timeline.aiInterpretation")}: {aiBlock.interpretation}
                            </div>
                          ) : null}
                          <p className="whitespace-pre-wrap leading-relaxed">{aiBlock.summary}</p>
                          {aiBlock.citations?.length ? (
                            <div className="mt-2 border-t border-slate-800 pt-2">
                              <div className="text-[11px] text-slate-500">{t("timeline.aiCitations")}</div>
                              <ul className="mt-1 space-y-1">
                                {aiBlock.citations.map((c, i) => (
                                  <li key={`${c.title}-${i}`}>
                                    {c.url ? (
                                      <a href={c.url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:text-indigo-300">
                                        {c.title}
                                      </a>
                                    ) : (
                                      c.title
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {aiBlock.status === "placeholder" ? (
                            <p className="mt-2 text-[11px] text-amber-200/80">{t("timeline.aiPlaceholderNote")}</p>
                          ) : null}
                        </div>
                      ) : null}
                        </>
                      ) : (
                        <p className="text-[11px] text-slate-500">{t("timeline.aiAdminOnlyNote")}</p>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-500">—</p>
                )}
              </div>
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div className="mt-2 border-t border-slate-800/80 pt-2">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{t("timeline.title")}</span>
        <SectionHelp titleKey="help.entityEventTimelineTitle" bodyKey="help.entityEventTimelineBody" className="scale-90" />
        <span className="ml-auto flex items-center gap-3 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-400" aria-hidden />
            {t("timeline.legendVolatility")}
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-sky-500" aria-hidden />
            {t("timeline.legendOfficial")}
          </span>
        </span>
      </div>
      {loading ? (
        <p className="text-[11px] text-slate-500">{t("timeline.loading")}</p>
      ) : loadErr ? (
        <p className="text-[11px] text-red-400">{t("timeline.loadError")}</p>
      ) : !access ? null : !bars.length ? (
        <p className="text-[11px] text-slate-500">{t("timeline.empty")}</p>
      ) : !displayPoints.length || span <= 0 ? (
        <p className="text-[11px] text-slate-500">{t("timeline.empty")}</p>
      ) : (
        <div
          className="relative h-7 rounded bg-slate-950/80 ring-1 ring-slate-800"
          role="list"
          aria-label={t("timeline.title")}
        >
          <div className="absolute inset-x-2 top-1/2 h-px -translate-y-1/2 bg-slate-700/90" aria-hidden />
          {displayPoints.map((p) => {
            const left = posFor(p.time);
            const color = p.point_type === "volatility" ? "bg-amber-400" : "bg-sky-500";
            return (
              <button
                key={p.id}
                type="button"
                role="listitem"
                title={p.point_type === "volatility" ? t("timeline.pointVolatility") : t("timeline.pointOfficial")}
                className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ${color} ring-2 ring-slate-900 hover:scale-110 focus:outline-none focus:ring-2 focus:ring-indigo-500`}
                style={{ left: `${left}%` }}
                onClick={() => openPoint(p.id)}
              />
            );
          })}
        </div>
      )}
      {panel}
    </div>
  );
}
