"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ComparisonChart } from "@/components/ComparisonChart";
import { BlockStateMessage } from "@/components/BlockStateMessage";

export function EntityOverlaySentimentChart({
  entityId,
  period = "1M",
  height = 220,
}: {
  entityId: string;
  period?: string;
  height?: number;
}) {
  const { t } = useI18n();
  const [series, setSeries] = useState<Array<{ symbol: string; points: Array<{ t: string; value: number }> }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyHint, setEmptyHint] = useState<string | null>(null);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [aiStatus, setAiStatus] = useState<"none" | "computing" | "partial" | "disabled" | "admin_only">("none");
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setEmptyHint(null);
    setStatusHint(null);
    setAiStatus("none");
    setEtaSeconds(null);
    try {
      const res = await api.getEntitySentimentSeries(entityId, period);
      const pts = res.points.map((p) => ({ t: p.t, value: p.sentiment_score }));
      const label =
        t("workspace.narrativeSentimentScore") !== "workspace.narrativeSentimentScore"
          ? t("workspace.narrativeSentimentScore")
          : "Narrative sentiment score";
      setSeries([{ symbol: label, points: pts }]);
      const anyRes = res as any;
      const eta = typeof anyRes?.eta_hint === "string" ? anyRes.eta_hint : null;
      if (eta && typeof eta === "string") {
        const m = eta.match(/(\d+)\s*[–-]\s*(\d+)s/i) || eta.match(/(\d+)\s*s/i);
        if (m) setEtaSeconds(parseInt(m[m.length - 1], 10));
      }
      if (anyRes?.loading_state === "disabled" && anyRes?.data_source === "disabled_by_runtime_flag") {
        setAiStatus("disabled");
      } else if (anyRes?.loading_state === "disabled") {
        setAiStatus("admin_only");
      } else if (anyRes?.loading_state === "computing") {
        setAiStatus("computing");
        setStatusHint("Computing (AI)...");
      } else if (anyRes?.loading_state === "partial") {
        setAiStatus("partial");
        setStatusHint("Updating... (AI)");
      }
      if (!pts.length) {
        const msg = typeof anyRes?.message === "string" ? anyRes.message : null;
        if (msg) setEmptyHint(msg);
        else setEmptyHint("No sentiment series yet.");
      }
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
    return <BlockStateMessage kind="loading" height={height} />;
  }
  if (error) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-amber-200"
        style={{ height }}
      >
        {error}
      </div>
    );
  }
  if (!series.length || !series[0]?.points?.length) {
    if (aiStatus === "disabled") return <BlockStateMessage kind="disabled" height={height} />;
    if (aiStatus === "admin_only") return <BlockStateMessage kind="admin_only_ai" height={height} />;
    return <BlockStateMessage kind="no_data" height={height} reason={emptyHint || "no news / not computed"} />;
  }
  return (
    <div className="h-full min-h-[120px]">
      {aiStatus === "computing" ? <BlockStateMessage kind="ai_computing" etaSeconds={etaSeconds} /> : null}
      {aiStatus === "partial" ? <BlockStateMessage kind="partial_ai" /> : null}
      <ComparisonChart series={series} height={height} />
    </div>
  );
}
