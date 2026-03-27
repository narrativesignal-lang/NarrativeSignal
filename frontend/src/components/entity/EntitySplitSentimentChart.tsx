"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ComparisonChart } from "@/components/ComparisonChart";

export function EntitySplitSentimentChart({
  entityId,
  period = "1M",
  height = 140,
}: {
  entityId: string;
  period?: string;
  height?: number;
}) {
  const [series, setSeries] = useState<Array<{ symbol: string; points: Array<{ t: string; value: number }> }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getEntitySentimentSeries(entityId, period);
      setSeries([
        {
          symbol: "Sentiment",
          points: res.points.map((p) => ({ t: p.t, value: p.value })),
        },
      ]);
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to load sentiment");
      setSeries([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, period]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[140px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
        Loading…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex min-h-[140px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-amber-200">
        {error}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="rounded border border-slate-700/60 bg-slate-900/30 p-2">
        <div className="mb-1 text-xs font-medium text-slate-400">Sentiment</div>
        <ComparisonChart series={series} height={height} />
      </div>
    </div>
  );
}
