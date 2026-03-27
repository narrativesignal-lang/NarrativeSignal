"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";

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
  metric: "momentum" | "acceleration";
}) {
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
      setError((e as { message?: string })?.message ?? "Failed to load metric");
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, metric, range]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[160px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
        Loading…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>
    );
  }

  return <TimeSeriesChart points={points} height={220} />;
}
