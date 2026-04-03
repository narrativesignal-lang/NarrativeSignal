"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ComparisonChart } from "@/components/ComparisonChart";
import { BlockStateMessage } from "@/components/BlockStateMessage";

export function EntitySplitSentimentChart({
  entityId,
  period = "1M",
  height = 140,
}: {
  entityId: string;
  period?: string;
  height?: number;
}) {
  const { t } = useI18n();
  const scoreLabel =
    t("workspace.narrativeSentimentScore") !== "workspace.narrativeSentimentScore"
      ? t("workspace.narrativeSentimentScore")
      : "Narrative sentiment score";
  const [series, setSeries] = useState<Array<{ symbol: string; points: Array<{ t: string; value: number }> }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getEntitySentimentSeries(entityId, period);
      const label =
        t("workspace.narrativeSentimentScore") !== "workspace.narrativeSentimentScore"
          ? t("workspace.narrativeSentimentScore")
          : "Narrative sentiment score";
      setSeries([
        {
          symbol: label,
          points: res.points.map((p) => ({ t: p.t, value: p.sentiment_score })),
        },
      ]);
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to load sentiment");
      setSeries([]);
    } finally {
      setLoading(false);
    }
  }, [entityId, period, t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <BlockStateMessage kind="loading" height={140} />;
  }
  if (error) {
    return (
      <div className="flex min-h-[140px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-amber-200">
        {error}
      </div>
    );
  }
  if (!series.length || series.every((s) => !s.points.length)) {
    return <BlockStateMessage kind="no_data" height={140} reason="no news / not computed" />;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="rounded border border-slate-700/60 bg-slate-900/30 p-2">
        <div className="mb-1 text-xs font-medium text-slate-400">{scoreLabel}</div>
        <ComparisonChart series={series} height={height} />
      </div>
    </div>
  );
}
