"use client";

import { useEffect, useMemo, useState } from "react";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { BlockStateMessage } from "@/components/BlockStateMessage";

type Series = {
  axis: string[];
  trading_activity: Array<number | null>;
  news_volume: Array<number | null>;
  search_volume: Array<number | null>;
};

function segmentsPath(points: Array<{ x: number; y: number } | null>): string {
  let d = "";
  let started = false;
  for (const p of points) {
    if (!p) {
      started = false;
      continue;
    }
    if (!started) {
      d += `M ${p.x} ${p.y} `;
      started = true;
    } else {
      d += `L ${p.x} ${p.y} `;
    }
  }
  return d.trim();
}

export function TripleSignalChartBlock({
  entityId,
  period = "3M",
  height = 220,
}: {
  entityId: string;
  period?: string;
  height?: number;
}) {
  const { t } = useI18n();
  const [data, setData] = useState<Series | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getEntityTripleSignalSeries(entityId, period)
      .then((res) => {
        if (cancelled) return;
        setData({
          axis: Array.isArray(res.axis) ? res.axis : [],
          trading_activity: Array.isArray(res.trading_activity) ? res.trading_activity : [],
          news_volume: Array.isArray(res.news_volume) ? res.news_volume : [],
          search_volume: Array.isArray(res.search_volume) ? res.search_volume : [],
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setError(parseApiError(e) || t("entity.chartLoadFailed"));
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, period, t]);

  const w = 600;
  const padding = { top: 12, right: 12, bottom: 26, left: 34 };
  const innerH = height - padding.top - padding.bottom;
  const innerW = w - padding.left - padding.right;

  const series = useMemo(() => {
    const axis = data?.axis ?? [];
    const n = axis.length;
    if (n === 0) return null;
    const x = (i: number) => (n <= 1 ? padding.left : padding.left + (i / (n - 1)) * innerW);
    const y = (v: number) => padding.top + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;

    const tradingVals = data?.trading_activity ?? [];
    const newsVals = data?.news_volume ?? [];
    const searchVals = data?.search_volume ?? [];

    const trading = axis.map((_, i) => {
      const v = tradingVals[i];
      return v == null ? null : { x: x(i), y: y(v) };
    });
    const news = axis.map((_, i) => {
      const v = newsVals[i];
      return v == null ? null : { x: x(i), y: y(v) };
    });
    const search = axis.map((_, i) => {
      const v = searchVals[i];
      return v == null ? null : { x: x(i), y: y(v) };
    });

    return {
      tradingD: segmentsPath(trading),
      newsD: segmentsPath(news),
      searchD: segmentsPath(search),
    };
  }, [data, innerW, innerH, padding.left, padding.top]);

  if (loading) {
    return <BlockStateMessage kind="loading" height={160} />;
  }
  if (error) {
    return <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>;
  }
  if (!data?.axis?.length || !series) {
    return <BlockStateMessage kind="no_data" height={160} reason="no metrics yet / not synced" />;
  }

  return (
    <div className="w-full overflow-x-auto">
      <svg width={w} height={height} className="min-w-[320px]" aria-label="Triple signal chart">
        <path d={series.tradingD} fill="none" stroke="#3b82f6" strokeWidth={2} strokeLinecap="round" />
        <path d={series.newsD} fill="none" stroke="#ef4444" strokeWidth={2} strokeLinecap="round" opacity={0.95} />
        <path d={series.searchD} fill="none" stroke="#22c55e" strokeWidth={2} strokeLinecap="round" opacity={0.95} />
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-blue-500" aria-hidden /> Trading activity
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-red-500" aria-hidden /> News volume
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-green-500" aria-hidden /> Keywords search (narrative)
        </span>
      </div>
    </div>
  );
}

