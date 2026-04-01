"use client";

import { useEffect, useState } from "react";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function EntityInstitutionBiasBlock({ entityId }: { entityId: string }) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.getEntityInstitutionBias>> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api
      .getEntityInstitutionBias(entityId)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setErr(parseApiError(e));
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  if (loading) {
    return (
      <div className="flex min-h-[140px] items-center justify-center bg-slate-950 text-xs text-slate-500">
        {t("entity.loadingSeries")}
      </div>
    );
  }
  if (err) {
    return <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">{err}</div>;
  }
  if (!data) {
    return (
      <div className="flex min-h-[140px] items-center justify-center bg-slate-950 text-xs text-slate-500">
        {t("entity.noMetricRows")}
      </div>
    );
  }

  const rows = [
    { label: "Bullish", v: data.bullish_pct, color: "bg-emerald-500/70" },
    { label: "Neutral", v: data.neutral_pct, color: "bg-slate-500/60" },
    { label: "Bearish", v: data.bearish_pct, color: "bg-rose-500/70" },
  ];

  return (
    <div className="p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-100">{data.bias_label}</div>
        <div className="text-xs text-slate-400">Score {Math.round(data.score)}</div>
      </div>
      <div className="mt-3 space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2">
            <div className="w-16 text-[11px] text-slate-400">{r.label}</div>
            <div className="h-2 flex-1 rounded bg-slate-800/60">
              <div className={`h-2 rounded ${r.color}`} style={{ width: `${Math.max(0, Math.min(100, r.v))}%` }} />
            </div>
            <div className="w-10 text-right text-[11px] text-slate-400">{Math.round(r.v)}%</div>
          </div>
        ))}
      </div>
      {data.last_updated_at ? (
        <div className="mt-3 text-[11px] text-slate-500">Last updated: {new Date(data.last_updated_at).toLocaleString()}</div>
      ) : null}
    </div>
  );
}

