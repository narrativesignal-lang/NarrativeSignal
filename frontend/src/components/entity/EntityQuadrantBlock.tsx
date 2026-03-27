"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { QuadrantChart } from "@/components/QuadrantChart";
import { api } from "@/lib/api";
import { STALE_TRENDS_MS } from "@/lib/queryClient";

export function EntityQuadrantBlock({
  entityId,
  period = "1M"
}: {
  entityId: string;
  period?: string;
}) {
  const histQuery = useQuery({
    queryKey: ["entity", "quadrantHistory", entityId, period],
    queryFn: () => api.getEntityQuadrantHistory(entityId, period),
    staleTime: 10 * 60 * 1000,
    gcTime: 45 * 60 * 1000,
    enabled: Boolean(entityId)
  });

  const trendQuery = useQuery({
    queryKey: ["entity", "trending", entityId],
    queryFn: () => api.getEntityTrending(entityId),
    staleTime: STALE_TRENDS_MS,
    gcTime: 24 * 60 * 60 * 1000,
    enabled: Boolean(entityId)
  });

  const points = useMemo(() => {
    const p = histQuery.data?.points;
    if (!p?.length) return null;
    return p.map((x) => ({
      t: x.t,
      coverage_momentum: x.coverage_momentum,
      search_momentum: x.search_momentum
    }));
  }, [histQuery.data]);

  const trending = trendQuery.data
    ? { search_momentum: trendQuery.data.search_momentum, coverage_momentum: trendQuery.data.coverage_momentum }
    : null;

  const env = trendQuery.data;
  const showPrep =
    env?.loading_state === "warming" ||
    env?.loading_state === "placeholder" ||
    env?.data_source === "placeholder";
  const showStale =
    (env?.data_source === "stale_fallback" || env?.loading_state === "stale") && !showPrep;

  const loading = histQuery.isLoading && !points?.length;
  const error = histQuery.isError ? (histQuery.error as { message?: string })?.message ?? "Failed to load quadrant" : null;

  if (loading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
        Loading…
      </div>
    );
  }
  if (error) {
    return <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>;
  }

  const historyPoints = points && points.length > 0 ? points : null;
  const searchMom = historyPoints?.length
    ? historyPoints[historyPoints.length - 1].search_momentum
    : trending?.search_momentum;
  const coverageMom = historyPoints?.length
    ? historyPoints[historyPoints.length - 1].coverage_momentum
    : trending?.coverage_momentum;

  return (
    <div className="flex min-h-0 flex-col gap-2">
      {env?.message && showPrep ? (
        <div className="rounded border border-sky-900/50 bg-sky-950/30 px-2 py-1.5 text-[11px] text-sky-100/90">
          {env.message}
        </div>
      ) : null}
      {showStale && env?.data_updated_at ? (
        <div className="text-[10px] text-slate-500">
          <span className="text-amber-200/80">Stale</span> ·{" "}
          {new Date(env.data_updated_at).toLocaleString()}
        </div>
      ) : null}
      <QuadrantChart
        searchMomentum={searchMom}
        coverageMomentum={coverageMom}
        points={historyPoints ?? undefined}
        height={260}
        periodLabel={period}
      />
    </div>
  );
}
