"use client";

import { useCallback, useEffect, useState } from "react";
import { CandleChart } from "@/components/CandleChart";
import { api } from "@/lib/api";
import type { CandleBar } from "@/lib/ohlcvBars";
import { useI18n } from "@/lib/i18n";
import { BlockStateMessage } from "@/components/BlockStateMessage";

export function EntityStackedCandleCharts({
  entityId,
  period = "1M",
  rowHeight = 200,
}: {
  entityId: string;
  period?: string;
  rowHeight?: number;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Array<{ symbol: string; bars: CandleBar[] }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const entity = await api.getEntity(entityId);
      const related = await api.getEntityRelatedInstruments(entityId).catch(() => []);
      const symbols: string[] = [];
      if (entity.instrument?.symbol) symbols.push(entity.instrument.symbol);
      related.forEach((r) => {
        if (r.symbol && !symbols.includes(r.symbol)) symbols.push(r.symbol);
      });
      if (symbols.length === 0) {
        setRows([]);
        return;
      }
      let batch: Record<string, CandleBar[]> = {};
      try {
        batch = await api.ohlcvBatch(symbols, period);
      } catch {
        batch = {};
      }
      setRows(
        symbols.map((symbol) => ({
          symbol,
          bars: batch[symbol.trim().toUpperCase()] ?? [],
        }))
      );
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? t("entity.chartLoadFailed"));
      setRows([]);
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
      <div className="flex min-h-[140px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-amber-200 text-balance break-words">
        {error}
      </div>
    );
  }
  if (!rows.length || rows.every((r) => !r.bars.length)) {
    return <BlockStateMessage kind="no_data" height={100} reason="no cached price history / worker not run" />;
  }

  return (
    <div className="flex max-h-full flex-col gap-3 overflow-y-auto">
      {rows.map((r) =>
        r.bars.length > 0 ? (
          <div key={r.symbol} className="flex min-h-0 flex-col overflow-hidden rounded border border-slate-700/60 bg-slate-900/30 p-2">
            <div className="mb-1 truncate text-xs font-medium text-slate-400" title={r.symbol}>
              {r.symbol}
            </div>
            <CandleChart bars={r.bars} height={rowHeight} />
          </div>
        ) : (
          <div
            key={r.symbol}
            className="flex min-h-[80px] items-center justify-center rounded border border-slate-700/40 bg-slate-900/20 px-2 text-center text-xs text-slate-500 text-balance break-words"
          >
            <span className="truncate font-medium" title={r.symbol}>
              {r.symbol}
            </span>
            {": "}
            {t("common.noData")}
          </div>
        )
      )}
    </div>
  );
}
