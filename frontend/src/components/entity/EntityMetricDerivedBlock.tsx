"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";
import { useI18n } from "@/lib/i18n";

/** Map entity page period buttons to backend metric-series range. */
export function entityPeriodToMetricRange(period: string): "1m" | "3m" | "6m" {
  const u = period.trim().toUpperCase();
  if (u === "1Y" || u === "MAX") return "6m";
  if (u === "6M") return "3m";
  return "1m";
}

export function EntityMetricDerivedBlock({
  entityId,
  period = "1M",
  metric,
}: {
  entityId: string;
  period?: string;
  metric:
    | "momentum_target"
    | "acceleration_target"
    | "momentum_keywords"
    | "acceleration_keywords";
}) {
  const { t } = useI18n();
  const [points, setPoints] = useState<Array<{ t: string; value: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const range = entityPeriodToMetricRange(period);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getEntityMetricSeries(entityId, metric, range);
      setPoints(res.points.map((p) => ({ t: p.date, value: p.value })));
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? t("entity.chartLoadFailed"));
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, metric, range, t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[160px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
        {t("entity.loadingSeries")}
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>
    );
  }
  if (!points.length) {
    return (
      <div className="flex min-h-[160px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-slate-500">
        {t("entity.noMetricRows")}
      </div>
    );
  }

  return <TimeSeriesChart points={points} height={220} />;
}
