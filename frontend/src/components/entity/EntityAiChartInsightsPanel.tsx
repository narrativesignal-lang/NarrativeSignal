"use client";

import { useCallback, useMemo, useState } from "react";

import { BlockStateMessage } from "@/components/BlockStateMessage";
import { api, parseApiError } from "@/lib/api";
import type { ChartVisibleTimeRange } from "@/lib/chartTimeUnix";
import type { CandleBar } from "@/lib/ohlcvBars";
import { useI18n } from "@/lib/i18n";

type PriceMoveRes = {
  summary: string;
  drivers: Array<{ label: string; confidence: number; evidence_type: string }>;
  time_window_start: string;
  time_window_end: string;
  cached?: boolean;
};

type RangeSummaryRes = {
  summary: string;
  narrative: string;
  highlights: string[];
  time_window_start: string;
  time_window_end: string;
  cached?: boolean;
};

function isAiDisabled(x: unknown): x is { disabled: true; reason?: string } {
  return Boolean(x && typeof x === "object" && (x as { disabled?: boolean }).disabled === true);
}

export function EntityAiChartInsightsPanel({
  entityId,
  symbol,
  period,
  visibleTimeRange,
  bars,
  isAdminUser,
  userLoading,
}: {
  entityId: string;
  symbol: string;
  period: string;
  visibleTimeRange: ChartVisibleTimeRange | null;
  bars: CandleBar[];
  isAdminUser: boolean;
  userLoading: boolean;
}) {
  const { t } = useI18n();
  const [priceBusy, setPriceBusy] = useState(false);
  const [rangeBusy, setRangeBusy] = useState(false);
  const [priceErr, setPriceErr] = useState<string | null>(null);
  const [rangeErr, setRangeErr] = useState<string | null>(null);
  const [priceOut, setPriceOut] = useState<PriceMoveRes | null>(null);
  const [rangeOut, setRangeOut] = useState<RangeSummaryRes | null>(null);

  const barExtent = useMemo(() => {
    if (!bars.length) return null;
    const times = bars.map((b) => b.time);
    return { from: Math.min(...times), to: Math.max(...times) };
  }, [bars]);

  const win = useMemo(() => {
    if (visibleTimeRange && visibleTimeRange.from < visibleTimeRange.to) return visibleTimeRange;
    return barExtent;
  }, [visibleTimeRange, barExtent]);

  const windowIso = useMemo(() => {
    if (!win) return null;
    return {
      window_start: new Date(win.from * 1000).toISOString(),
      window_end: new Date(win.to * 1000).toISOString(),
    };
  }, [win]);

  const runPrice = useCallback(async () => {
    if (!windowIso) return;
    setPriceBusy(true);
    setPriceErr(null);
    setPriceOut(null);
    try {
      const raw = await api.aiPriceMoveExplanation({
        entity_id: entityId,
        window_start: windowIso.window_start,
        window_end: windowIso.window_end,
        chart_period: period,
      });
      if (isAiDisabled(raw)) {
        setPriceErr(t("entity.aiChartDisabledFlag"));
        return;
      }
      setPriceOut(raw as PriceMoveRes);
    } catch (e) {
      setPriceErr(parseApiError(e));
    } finally {
      setPriceBusy(false);
    }
  }, [entityId, period, windowIso, t]);

  const runRange = useCallback(async () => {
    if (!windowIso) return;
    setRangeBusy(true);
    setRangeErr(null);
    setRangeOut(null);
    try {
      const raw = await api.aiRangeSummary({
        entity_id: entityId,
        window_start: windowIso.window_start,
        window_end: windowIso.window_end,
        chart_period: period,
      });
      if (isAiDisabled(raw)) {
        setRangeErr(t("entity.aiChartDisabledFlag"));
        return;
      }
      setRangeOut(raw as RangeSummaryRes);
    } catch (e) {
      setRangeErr(parseApiError(e));
    } finally {
      setRangeBusy(false);
    }
  }, [entityId, period, windowIso, t]);

  if (!symbol.trim()) return null;

  if (userLoading) {
    return (
      <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
        <BlockStateMessage kind="loading" />
      </div>
    );
  }

  if (!isAdminUser) {
    return (
      <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
        <div className="text-xs font-medium text-slate-400">{t("entity.aiChartInsightsTitle")}</div>
        <div className="mt-2">
          <BlockStateMessage kind="admin_only_ai" />
        </div>
      </div>
    );
  }

  if (!windowIso) {
    return (
      <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-500">
        {t("entity.aiChartNeedWindow")}
      </div>
    );
  }

  return (
    <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 px-3 py-3">
      <div className="text-xs font-medium text-slate-300">{t("entity.aiChartInsightsTitle")}</div>
      <p className="mt-1 text-[11px] text-slate-500">{t("entity.aiChartInsightsHint")}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={priceBusy}
          onClick={runPrice}
          className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600 disabled:opacity-50"
        >
          {priceBusy ? t("entity.generating") : t("entity.aiChartExplainMove")}
        </button>
        <button
          type="button"
          disabled={rangeBusy}
          onClick={runRange}
          className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600 disabled:opacity-50"
        >
          {rangeBusy ? t("entity.generating") : t("entity.aiChartRangeSummary")}
        </button>
      </div>
      {(priceBusy || rangeBusy) && !priceOut && !rangeOut ? (
        <div className="mt-2">
          <BlockStateMessage kind="ai_computing" />
        </div>
      ) : null}
      {priceErr ? <div className="mt-2 text-xs text-amber-200">{priceErr}</div> : null}
      {rangeErr ? <div className="mt-2 text-xs text-amber-200">{rangeErr}</div> : null}
      {priceOut ? (
        <div className="mt-3 border-t border-slate-800 pt-2 text-xs text-slate-300">
          <div className="font-medium text-slate-200">{t("entity.aiChartExplainMove")}</div>
          {priceOut.cached ? <div className="text-[10px] text-slate-500">{t("entity.aiChartCached")}</div> : null}
          <p className="mt-1 text-slate-300">{priceOut.summary}</p>
          {priceOut.drivers?.length ? (
            <ul className="mt-1 list-inside list-disc text-slate-400">
              {priceOut.drivers.map((d, i) => (
                <li key={i}>
                  <span className="text-slate-300">{d.label}</span>
                  <span className="ml-1 text-[10px] text-slate-500">
                    ({d.evidence_type} · {Math.round((d.confidence ?? 0) * 100)}%)
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {rangeOut ? (
        <div className="mt-3 border-t border-slate-800 pt-2 text-xs text-slate-300">
          <div className="font-medium text-slate-200">{t("entity.aiChartRangeSummary")}</div>
          {rangeOut.cached ? <div className="text-[10px] text-slate-500">{t("entity.aiChartCached")}</div> : null}
          <p className="mt-1 font-medium text-slate-200">{rangeOut.summary}</p>
          <p className="mt-1 text-slate-400">{rangeOut.narrative}</p>
          {rangeOut.highlights?.length ? (
            <ul className="mt-1 list-inside list-disc text-slate-400">
              {rangeOut.highlights.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
