"use client";

import { useEffect, useState } from "react";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function EntityRatingDistributionBlock({ entityId }: { entityId: string }) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.getEntityRatingDistribution>> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api
      .getEntityRatingDistribution(entityId)
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

  const buy = Math.max(0, Math.min(100, data.buy_pct));
  const hold = Math.max(0, Math.min(100, data.hold_pct));
  const sell = Math.max(0, Math.min(100, data.sell_pct));
  const conf = Math.max(0, Math.min(100, data.confidence));

  return (
    <div className="p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-100">Heuristic mix</div>
        <div className="text-xs text-slate-400">Confidence {Math.round(conf)}%</div>
      </div>

      <div className="mt-3 h-3 w-full overflow-hidden rounded bg-slate-800/60">
        <div className="flex h-3 w-full">
          <div className="h-3 bg-emerald-500/70" style={{ width: `${buy}%` }} />
          <div className="h-3 bg-slate-500/60" style={{ width: `${hold}%` }} />
          <div className="h-3 bg-rose-500/70" style={{ width: `${sell}%` }} />
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-400">
        <span>Buy {Math.round(buy)}%</span>
        <span>Hold {Math.round(hold)}%</span>
        <span>Sell {Math.round(sell)}%</span>
      </div>

      {data.last_updated_at ? (
        <div className="mt-3 text-[11px] text-slate-500">Last updated: {new Date(data.last_updated_at).toLocaleString()}</div>
      ) : null}
    </div>
  );
}

