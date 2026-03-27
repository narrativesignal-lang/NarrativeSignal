"use client";

import { useCallback, useEffect, useState } from "react";
import { QuadrantChart } from "@/components/QuadrantChart";
import { api } from "@/lib/api";

export function EntityQuadrantBlock({
  entityId,
  period = "1M",
}: {
  entityId: string;
  period?: string;
}) {
  const [points, setPoints] = useState<
    Array<{ t: string; coverage_momentum: number; search_momentum: number }> | null
  >(null);
  const [trending, setTrending] = useState<{
    search_momentum: number;
    coverage_momentum: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [hist, trend] = await Promise.all([
        api.getEntityQuadrantHistory(entityId, period),
        api.getEntityTrending(entityId).catch(() => null),
      ]);
      setPoints(hist.points.map((p) => ({ t: p.t, coverage_momentum: p.coverage_momentum, search_momentum: p.search_momentum })));
      if (trend) {
        setTrending({ search_momentum: trend.search_momentum, coverage_momentum: trend.coverage_momentum });
      } else {
        setTrending(null);
      }
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to load quadrant");
      setPoints(null);
      setTrending(null);
    } finally {
      setLoading(false);
    }
  }, [entityId, period]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
        Loading…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>
    );
  }

  const historyPoints = points && points.length > 0 ? points : null;
  const searchMom = historyPoints?.length
    ? historyPoints[historyPoints.length - 1].search_momentum
    : trending?.search_momentum;
  const coverageMom = historyPoints?.length
    ? historyPoints[historyPoints.length - 1].coverage_momentum
    : trending?.coverage_momentum;

  return (
    <QuadrantChart
      searchMomentum={searchMom}
      coverageMomentum={coverageMom}
      points={historyPoints ?? undefined}
      height={260}
      periodLabel={period}
    />
  );
}
