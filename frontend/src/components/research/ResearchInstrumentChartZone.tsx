"use client";

import { useEffect, useState } from "react";

import { CandleChart } from "@/components/CandleChart";
import { api } from "@/lib/api";
import type { CandleBar } from "@/lib/ohlcvBars";
import { useI18n } from "@/lib/i18n";

type Instrument = { id: string; symbol: string };

const PERIOD = "1M";
const MAX_SLOTS = 4;

export function ResearchInstrumentChartZone({
  instruments,
  height,
}: {
  instruments: Instrument[];
  height: number;
}) {
  const { t } = useI18n();
  const slots = instruments.slice(0, MAX_SLOTS);
  const symbolKey = slots.map((s) => s.symbol).join(",");
  const [barsBySymbol, setBarsBySymbol] = useState<Record<string, CandleBar[]>>({});
  const [fetchDone, setFetchDone] = useState(false);

  useEffect(() => {
    if (slots.length === 0) return;
    const abort = new AbortController();
    const load = async () => {
      setFetchDone(false);
      let next: Record<string, CandleBar[]> = {};
      try {
        const batch = await api.ohlcvBatch(
          slots.map((s) => s.symbol),
          PERIOD
        );
        next = {};
        for (const inst of slots) {
          const k = inst.symbol.trim().toUpperCase();
          next[inst.symbol] = batch[k] ?? [];
        }
      } catch {
        next = Object.fromEntries(slots.map((inst) => [inst.symbol, [] as CandleBar[]]));
      }
      if (!abort.signal.aborted) {
        setBarsBySymbol(next);
        setFetchDone(true);
      }
    };
    load();
    return () => abort.abort();
  }, [symbolKey, slots.length]);

  if (slots.length === 0) {
    return (
      <div className="flex h-full min-h-[120px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-900/20 px-4 text-center text-sm text-slate-500 text-balance break-words">
        {t("research.instrumentChartsHint")}
      </div>
    );
  }

  const chartHeight = Math.max(140, Math.floor(height / slots.length) - 12);
  const gridCols = slots.length === 1 ? 1 : slots.length <= 2 ? 2 : 2;
  const gridRows = slots.length <= 2 ? 1 : 2;

  return (
    <div
      className="grid w-full gap-2"
      style={{
        gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
        gridTemplateRows: `repeat(${gridRows}, minmax(0, 1fr))`,
      }}
    >
      {slots.map((inst) => (
        <div
          key={inst.id}
          className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900/50 p-2"
        >
          <div className="mb-1 truncate text-xs font-medium text-slate-400" title={inst.symbol}>
            {inst.symbol}
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            {!fetchDone ? (
              <div
                className="flex items-center justify-center px-2 text-center text-xs text-slate-500 text-balance"
                style={{ minHeight: chartHeight }}
              >
                {t("common.loading")}
              </div>
            ) : barsBySymbol[inst.symbol]?.length ? (
              <CandleChart bars={barsBySymbol[inst.symbol]} height={chartHeight} />
            ) : (
              <div
                className="flex items-center justify-center px-2 text-center text-xs text-slate-500 text-balance break-words"
                style={{ minHeight: chartHeight }}
              >
                {t("common.noData")}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
