"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";

type Kind = "search" | "coverage";

export function EntitySeriesVolumeBlock({
  entityId,
  period = "1M",
  kind,
}: {
  entityId: string;
  period?: string;
  kind: Kind;
}) {
  const [points, setPoints] = useState<Array<{ t: string; value: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res =
        kind === "search"
          ? await api.getEntitySearchVolumeSeries(entityId, period)
          : await api.getEntityCoverageVolumeSeries(entityId, period);
      setPoints(res.points.map((p) => ({ t: p.t, value: p.value })));
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to load series");
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, period, kind]);

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
