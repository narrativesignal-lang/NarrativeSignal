"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { BlockStateMessage } from "@/components/BlockStateMessage";
import { api, parseApiError } from "@/lib/api";
import type { CandleBar } from "@/lib/ohlcvBars";
import { ENTITY_OVERLAY_SERIES_META, isEntityOverlaySeriesKey } from "@/lib/entityWorkspaceCharts";
import {
  OVERLAY_LOCAL_RANGES,
  type OverlayLocalRange,
  filterSortedAxisByOverlayRange,
} from "@/lib/overlayDateRange";
import { useI18n } from "@/lib/i18n";

type RawLine = {
  id: string;
  label: string;
  color: string;
  /** Raw values aligned to `fullAxis` (null = no sample that day). */
  raw: (number | null)[];
};

const COLORS = ["#818cf8", "#22c55e", "#ef4444", "#eab308", "#38bdf8", "#a78bfa", "#f472b6"];

function utcDayKeyFromBarTime(time: number): string {
  const sec = time > 1e12 ? Math.floor(time / 1000) : time;
  const d = new Date(sec * 1000);
  return d.toISOString().slice(0, 10);
}

/** Per-window min–max normalize (honest gaps preserved as null). */
function normalizeMinMax(values: (number | null)[]): (number | null)[] {
  const fin = values.filter((v): v is number => v != null && Number.isFinite(v));
  if (fin.length === 0) return values.map(() => null);
  const lo = Math.min(...fin);
  const hi = Math.max(...fin);
  const span = hi - lo || 1;
  return values.map((v) =>
    v == null || !Number.isFinite(v) ? null : (v - lo) / span
  );
}

function mergeSortedUniqueDates(arrays: string[][]): string[] {
  const s = new Set<string>();
  for (const a of arrays) for (const t of a) s.add(t);
  return [...s].sort();
}

function mapFromPoints(pts: Array<{ t: string; value: number }>): Map<string, number> {
  const m = new Map<string, number>();
  for (const p of pts) {
    if (p.t && Number.isFinite(p.value)) m.set(p.t, p.value);
  }
  return m;
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

/** Map normalized 0–1 value through vertical band [yMin,yMax] subset of 0–1. */
function applyYBand(v: number | null, yMin: number, yMax: number): number | null {
  if (v == null) return null;
  const band = yMax - yMin || 1e-9;
  return clamp01((v - yMin) / band);
}

function computeVisibleSlice(
  sortedAxis: string[],
  range: OverlayLocalRange
): { visibleAxis: string[]; startIdx: number } {
  if (sortedAxis.length === 0) return { visibleAxis: [], startIdx: 0 };
  const visibleAxis = filterSortedAxisByOverlayRange(sortedAxis, range);
  if (visibleAxis.length === 0) return { visibleAxis: [], startIdx: sortedAxis.length };
  const firstK = visibleAxis[0]!.trim().slice(0, 10);
  const startIdx = sortedAxis.findIndex((k) => k.trim().slice(0, 10) === firstK);
  return { visibleAxis, startIdx: startIdx === -1 ? 0 : startIdx };
}

export function EntityMathOverlayChart({
  entityId,
  period = "1M",
  height = 280,
  seriesKeys,
}: {
  entityId: string;
  period?: string;
  height?: number;
  seriesKeys: readonly string[];
}) {
  const { t } = useI18n();
  const keys = useMemo(
    () => [...new Set(seriesKeys.filter(isEntityOverlaySeriesKey))],
    [seriesKeys]
  );

  const [fullAxis, setFullAxis] = useState<string[]>([]);
  const [rawLines, setRawLines] = useState<RawLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [footnote, setFootnote] = useState<string | null>(null);

  const [localRange, setLocalRange] = useState<OverlayLocalRange>("ALL");
  const [yBandMin, setYBandMin] = useState(0);
  const [yBandMax, setYBandMax] = useState(1);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    if (!entityId || keys.length === 0) {
      setFullAxis([]);
      setRawLines([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setFootnote(null);
    try {
      const entity = await api.getEntity(entityId);
      const symbol = entity.instrument?.symbol?.trim().toUpperCase() ?? "";

      const dateArrays: string[][] = [];
      const lines: RawLine[] = [];
      let colorIdx = 0;

      let priceMap = new Map<string, number>();
      if (keys.includes("price_close")) {
        if (!symbol) {
          setFootnote(t("workspace.overlayPriceNeedsInstrument"));
        } else {
          const batch = await api.ohlcvBatch([symbol], period).catch(() => ({} as Record<string, CandleBar[]>));
          const bars = batch[symbol] ?? [];
          for (const b of bars) {
            priceMap.set(utcDayKeyFromBarTime(b.time), b.close);
          }
          dateArrays.push([...priceMap.keys()].sort());
        }
      }

      let targetMap = new Map<string, number>();
      if (keys.includes("target_search_volume")) {
        const res = await api.getEntityTargetSearchVolumeSeries(entityId, period);
        targetMap = mapFromPoints(res.points ?? []);
        dateArrays.push([...targetMap.keys()].sort());
      }

      let keywordsMap = new Map<string, number>();
      if (keys.includes("keywords_search_volume")) {
        const res = await api.getEntityKeywordsSearchVolumeSeries(entityId, period);
        keywordsMap = mapFromPoints(res.points ?? []);
        dateArrays.push([...keywordsMap.keys()].sort());
      }

      let coverageMap = new Map<string, number>();
      if (keys.includes("coverage_volume")) {
        const res = await api.getEntityCoverageVolumeSeries(entityId, period);
        coverageMap = mapFromPoints(res.points ?? []);
        dateArrays.push([...coverageMap.keys()].sort());
      }

      let triple: {
        axis: string[];
        trading_activity: Array<number | null>;
        news_volume: Array<number | null>;
        search_volume: Array<number | null>;
      } | null = null;

      if (keys.includes("triple_signal")) {
        const res = await api.getEntityTripleSignalSeries(entityId, period);
        triple = {
          axis: Array.isArray(res.axis) ? res.axis : [],
          trading_activity: Array.isArray(res.trading_activity) ? res.trading_activity : [],
          news_volume: Array.isArray(res.news_volume) ? res.news_volume : [],
          search_volume: Array.isArray(res.search_volume) ? res.search_volume : [],
        };
        dateArrays.push([...triple.axis]);
      }

      const dates = mergeSortedUniqueDates(dateArrays);
      if (dates.length === 0) {
        setFullAxis([]);
        setRawLines([]);
        setLoading(false);
        return;
      }

      const pull = (m: Map<string, number>, d: string) => {
        const v = m.get(d);
        return v === undefined ? null : v;
      };

      if (keys.includes("price_close") && symbol) {
        const raw = dates.map((d) => pull(priceMap, d));
        lines.push({
          id: "price_close",
          label: ENTITY_OVERLAY_SERIES_META.price_close.label,
          color: COLORS[colorIdx % COLORS.length]!,
          raw,
        });
        colorIdx += 1;
      }
      if (keys.includes("target_search_volume")) {
        const raw = dates.map((d) => pull(targetMap, d));
        lines.push({
          id: "target_search_volume",
          label: ENTITY_OVERLAY_SERIES_META.target_search_volume.label,
          color: COLORS[colorIdx % COLORS.length]!,
          raw,
        });
        colorIdx += 1;
      }
      if (keys.includes("keywords_search_volume")) {
        const raw = dates.map((d) => pull(keywordsMap, d));
        lines.push({
          id: "keywords_search_volume",
          label: ENTITY_OVERLAY_SERIES_META.keywords_search_volume.label,
          color: COLORS[colorIdx % COLORS.length]!,
          raw,
        });
        colorIdx += 1;
      }
      if (keys.includes("coverage_volume")) {
        const raw = dates.map((d) => pull(coverageMap, d));
        lines.push({
          id: "coverage_volume",
          label: ENTITY_OVERLAY_SERIES_META.coverage_volume.label,
          color: COLORS[colorIdx % COLORS.length]!,
          raw,
        });
        colorIdx += 1;
      }

      if (keys.includes("triple_signal") && triple && triple.axis.length > 0) {
        const ax = triple.axis;
        const idxForDate = (d: string) => ax.indexOf(d);
        const pullTr = (arr: Array<number | null>, d: string) => {
          const i = idxForDate(d);
          if (i < 0) return null;
          const v = arr[i];
          return v == null || !Number.isFinite(v) ? null : v;
        };
        const rt = dates.map((d) => pullTr(triple.trading_activity, d));
        const rn = dates.map((d) => pullTr(triple.news_volume, d));
        const rs = dates.map((d) => pullTr(triple.search_volume, d));
        lines.push({
          id: "triple_trading",
          label: "Trading activity",
          color: COLORS[colorIdx % COLORS.length]!,
          raw: rt,
        });
        colorIdx += 1;
        lines.push({
          id: "triple_news",
          label: "News volume",
          color: COLORS[colorIdx % COLORS.length]!,
          raw: rn,
        });
        colorIdx += 1;
        lines.push({
          id: "triple_search",
          label: "Keywords search",
          color: COLORS[colorIdx % COLORS.length]!,
          raw: rs,
        });
      }

      setFullAxis(dates);
      setRawLines(lines);
    } catch (e: unknown) {
      setError(parseApiError(e) || t("entity.chartLoadFailed"));
      setFullAxis([]);
      setRawLines([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, period, keys, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const { visibleAxis, startIdx } = useMemo(
    () => computeVisibleSlice(fullAxis, localRange),
    [fullAxis, localRange]
  );

  const plotData = useMemo(() => {
    if (!fullAxis.length || !visibleAxis.length || !rawLines.length) {
      return { lines: [] as Array<{ id: string; label: string; color: string; y: (number | null)[]; sparse: boolean }> };
    }
    const linesOut: Array<{
      id: string;
      label: string;
      color: string;
      y: (number | null)[];
      sparse: boolean;
    }> = [];

    for (const ln of rawLines) {
      const sliceRaw = ln.raw.slice(startIdx);
      const norm = normalizeMinMax(sliceRaw);
      const y = norm.map((v) => applyYBand(v, yBandMin, yBandMax));
      const nonNull = sliceRaw.filter((v) => v != null && Number.isFinite(v as number)).length;
      const sparse = sliceRaw.length > 0 && nonNull / sliceRaw.length < 0.12;
      linesOut.push({
        id: ln.id,
        label: ln.label,
        color: ln.color,
        y,
        sparse,
      });
    }
    return { lines: linesOut };
  }, [fullAxis.length, visibleAxis, rawLines, startIdx, yBandMin, yBandMax]);

  const padding = { top: 12, right: 12, bottom: 30, left: 44 };
  const plotW = 640;
  const innerW = plotW - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const paths = useMemo(() => {
    const axis = visibleAxis;
    const n = axis.length;
    const lines = plotData.lines.filter((l) => !hiddenIds.has(l.id));
    if (n < 1) return [];
    const xAt = (i: number) =>
      n <= 1 ? padding.left + innerW / 2 : padding.left + (i / Math.max(1, n - 1)) * innerW;
    return lines.map((ln) => {
      const pts: Array<{ x: number; y: number }> = [];
      for (let i = 0; i < n; i++) {
        const yy = ln.y[i];
        if (yy == null) continue;
        pts.push({ x: xAt(i), y: padding.top + innerH - yy * innerH });
      }
      if (pts.length === 1) {
        return {
          id: ln.id,
          d: "",
          dot: pts[0]!,
          color: ln.color,
          label: ln.label,
        };
      }
      if (pts.length < 2)
        return {
          id: ln.id,
          d: "",
          dot: null as { x: number; y: number } | null,
          color: ln.color,
          label: ln.label,
        };
      const d = pts
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
        .join(" ");
      return { id: ln.id, d, dot: null as { x: number; y: number } | null, color: ln.color, label: ln.label };
    });
  }, [visibleAxis, plotData.lines, hiddenIds, innerH, innerW, padding.left, padding.top]);

  const resetView = useCallback(() => {
    setLocalRange("ALL");
    setYBandMin(0);
    setYBandMax(1);
  }, []);

  const toggleHidden = useCallback((id: string) => {
    setHiddenIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);

  if (keys.length === 0) {
    return <BlockStateMessage kind="no_data" height={height} reason={t("workspace.overlayPickSeries")} />;
  }

  if (loading) {
    return <BlockStateMessage kind="loading" height={height} />;
  }
  if (error) {
    return (
      <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>
    );
  }
  if (!fullAxis.length || !rawLines.length) {
    return <BlockStateMessage kind="no_data" height={height} reason={t("workspace.overlayNoAlignedData")} />;
  }

  if (!loading && fullAxis.length > 0 && visibleAxis.length === 0) {
    return (
      <div className="w-full min-w-0">
        {footnote ? <p className="mb-1 text-[11px] text-amber-200/90">{footnote}</p> : null}
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-slate-500">{t("workspace.overlayLocalRangeLabel")}</span>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1">
              {OVERLAY_LOCAL_RANGES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setLocalRange(p)}
                  className={`rounded px-2 py-1 text-xs ${
                    localRange === p ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
                  }`}
                >
                  {p === "ALL" ? t("workspace.overlayRangeAll") : p}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={resetView}
              className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800"
            >
              {t("workspace.overlayResetView")}
            </button>
          </div>
        </div>
        <BlockStateMessage kind="no_data" height={height} reason={t("workspace.overlayRangeEmpty")} />
      </div>
    );
  }

  return (
    <div className="w-full min-w-0">
      {footnote ? <p className="mb-1 text-[11px] text-amber-200/90">{footnote}</p> : null}

      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
        <span className="text-xs text-slate-500">{t("workspace.overlayLocalRangeLabel")}</span>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {OVERLAY_LOCAL_RANGES.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setLocalRange(p)}
                className={`rounded px-2 py-1 text-xs ${
                  localRange === p ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
                }`}
              >
                {p === "ALL" ? t("workspace.overlayRangeAll") : p}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={resetView}
            className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800"
          >
            {t("workspace.overlayResetView")}
          </button>
        </div>
      </div>

      <p className="mb-1 text-[10px] text-slate-500">{t("workspace.overlayNormalizedNote")}</p>

      <div className="mb-2 flex flex-wrap items-center gap-3 rounded border border-slate-800/80 bg-slate-950/40 px-2 py-1.5 text-[11px] text-slate-400">
        <span className="text-slate-500">{t("workspace.overlayVerticalBand")}:</span>
        <label className="flex min-w-[140px] flex-1 items-center gap-2">
          <span className="shrink-0 text-[10px]">{t("workspace.overlayYMin")}</span>
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(yBandMin * 100)}
            onChange={(e) => {
              const v = Number(e.target.value) / 100;
              setYBandMin(Math.min(v, yBandMax - 0.05));
            }}
            className="min-w-0 flex-1 accent-indigo-500"
          />
        </label>
        <label className="flex min-w-[140px] flex-1 items-center gap-2">
          <span className="shrink-0 text-[10px]">{t("workspace.overlayYMax")}</span>
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(yBandMax * 100)}
            onChange={(e) => {
              const v = Number(e.target.value) / 100;
              setYBandMax(Math.max(yBandMin + 0.05, v));
            }}
            className="min-w-0 flex-1 accent-indigo-500"
          />
        </label>
        <span className="text-[10px] text-slate-500">
          {Math.round(yBandMin * 100)}–{Math.round(yBandMax * 100)}% {t("workspace.overlayYBandHint")}
        </span>
      </div>
      {yBandMin > 0.02 || yBandMax < 0.98 ? (
        <p className="mb-2 text-[10px] text-amber-200/85">{t("workspace.overlayYBandCroppedHint")}</p>
      ) : null}

      <div className="max-h-[min(70vh,520px)] overflow-y-auto overflow-x-auto">
        <svg width={plotW} height={height} className="min-w-[280px]" aria-label="Multi-series overlay chart">
          {paths.map((p) => (
            <g key={p.id}>
              {p.d ? (
                <path
                  d={p.d}
                  fill="none"
                  stroke={p.color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ) : null}
              {p.dot ? (
                <circle cx={p.dot.x} cy={p.dot.y} r={4} fill={p.color} stroke="#e2e8f0" strokeWidth={1} />
              ) : null}
            </g>
          ))}
          <text
            x={padding.left + innerW / 2}
            y={height - 22}
            textAnchor="middle"
            className="fill-slate-500"
            style={{ fontSize: 10 }}
          >
            {t("workspace.overlayTimeAxis")}
          </text>
          {visibleAxis.length > 0 ? (
            <>
              <text
                x={padding.left}
                y={height - 6}
                textAnchor="start"
                className="fill-slate-400"
                style={{ fontSize: 9 }}
              >
                {visibleAxis[0]!.trim().slice(0, 10)}
              </text>
              <text
                x={padding.left + innerW}
                y={height - 6}
                textAnchor="end"
                className="fill-slate-400"
                style={{ fontSize: 9 }}
              >
                {visibleAxis[visibleAxis.length - 1]!.trim().slice(0, 10)}
              </text>
            </>
          ) : null}
        </svg>
      </div>

      <div className="mt-2 space-y-1">
        {plotData.lines.map((ln) => (
          <label
            key={ln.id}
            className="flex cursor-pointer flex-wrap items-center gap-2 text-[11px] text-slate-400"
          >
            <input
              type="checkbox"
              className="rounded border-slate-600"
              checked={!hiddenIds.has(ln.id)}
              onChange={() => toggleHidden(ln.id)}
            />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ln.color }} aria-hidden />
              {ln.label}
            </span>
            {ln.sparse ? (
              <span className="text-[10px] text-amber-200/80">· {t("workspace.overlaySparseSeries")}</span>
            ) : null}
          </label>
        ))}
      </div>
    </div>
  );
}
