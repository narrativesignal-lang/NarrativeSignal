"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";
import { useI18n } from "@/lib/i18n";
import { BlockStateMessage } from "@/components/BlockStateMessage";

type Kind = "target_search" | "keywords_search" | "coverage";

export function EntitySeriesVolumeBlock({
  entityId,
  period = "1M",
  kind,
}: {
  entityId: string;
  period?: string;
  kind: Kind;
}) {
  const { t } = useI18n();
  const [points, setPoints] = useState<Array<{ t: string; value: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyHint, setEmptyHint] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setEmptyHint(null);
    try {
      if (kind === "keywords_search") {
        const res = await api.getEntityKeywordsSearchVolumeSeries(entityId, period);
        setPoints(res.points.map((p) => ({ t: p.t, value: p.value })));
        if (!res.points?.length) {
          const msg = typeof res.message === "string" ? res.message : null;
          if (msg) setEmptyHint(msg);
          else if (res.loading_state === "warming" || res.loading_state === "placeholder") {
            setEmptyHint("Metrics are still loading. Try again shortly.");
          } else {
            setEmptyHint("No keywords search volume for this period.");
          }
        }
      } else if (kind === "target_search") {
        const res = await api.getEntityTargetSearchVolumeSeries(entityId, period);
        setPoints(res.points.map((p) => ({ t: p.t, value: p.value })));
        if (!res.points?.length) {
          const msg = typeof res.message === "string" ? res.message : null;
          if (msg) setEmptyHint(msg);
          else if (res.loading_state === "warming" || res.loading_state === "placeholder") {
            setEmptyHint("Metrics are still loading. Try again shortly.");
          } else {
            setEmptyHint("No target (ticker) search volume for this period.");
          }
        }
      } else {
        const res = await api.getEntityCoverageVolumeSeries(entityId, period);
        setPoints(res.points.map((p) => ({ t: p.t, value: p.value })));
        if (!res.points?.length) {
          const msg = typeof res.message === "string" ? res.message : null;
          if (msg) setEmptyHint(msg);
          else if (res.loading_state === "warming" || res.loading_state === "placeholder") {
            setEmptyHint("Metrics are still loading. Try again shortly.");
          } else {
            setEmptyHint("No coverage data for this period.");
          }
        }
      }
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? t("entity.chartLoadFailed"));
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, period, kind, t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <BlockStateMessage kind="loading" height={160} />;
  }
  if (error) {
    return (
      <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{error}</div>
    );
  }
  if (!points.length) {
    const reason =
      emptyHint ||
      (kind === "coverage"
        ? "No coverage data for this period."
        : kind === "target_search"
          ? "No target search volume for this period."
          : "No keywords search volume for this period.");
    return <BlockStateMessage kind="no_data" height={160} reason={reason} />;
  }

  return <TimeSeriesChart points={points} height={220} />;
}
