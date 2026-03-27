"use client";

import { useI18n } from "@/lib/i18n";

export type IndexCardProps = {
  name: string;
  /** Display price; use numeric string so we never show "--" when fallback/cache provides a value */
  price: string;
  changePercent: number | null;
  /** Optional absolute change for display (e.g. +1.2) */
  change?: number | null;
  /** If set, show a small subtle "cached", "fallback", stale, or placeholder label */
  dataSource?: "live" | "cached" | "fallback" | "stale" | "placeholder";
  /** Optional tooltip on the name row */
  title?: string;
};

export function IndexCard({ name, price, changePercent, change, dataSource, title }: IndexCardProps) {
  const { t } = useI18n();
  const hasChange = changePercent !== null && changePercent !== undefined;
  const isPositive = hasChange && changePercent > 0;
  const isNeutral = hasChange && changePercent === 0;
  const changeClass =
    !hasChange
      ? "text-slate-400"
      : isNeutral
        ? "text-slate-400"
        : isPositive
          ? "text-emerald-400/90"
          : "text-red-400/90";

  const changeLabel =
    hasChange
      ? (isPositive ? "+" : "") + changePercent.toFixed(2) + "%"
      : "--";
  const changeSubtext =
    change != null && !Number.isNaN(change)
      ? (change >= 0 ? "+" : "") + change.toFixed(2)
      : null;

  return (
    <div className="flex shrink-0 flex-col justify-center gap-1 rounded-lg border border-slate-800 bg-slate-900/40 p-2.5 transition-colors">
      <div className="flex items-center justify-between gap-1">
        <span className="text-xs font-medium text-slate-400" title={title}>
          {name}
        </span>
        {dataSource && dataSource !== "live" ? (
          <span
            className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-500 bg-slate-800/80"
            title={
              dataSource === "cached"
                ? t("macro.quoteCachedHint")
                : dataSource === "fallback"
                  ? t("macro.quoteSampleHint")
                  : dataSource === "stale"
                    ? "Older quote; refresh in progress"
                    : "Layout placeholder — quote warming up"
            }
          >
            {dataSource === "cached"
              ? t("macro.quoteCached")
              : dataSource === "fallback"
                ? t("macro.quoteSample")
                : dataSource === "stale"
                  ? "Stale"
                  : "Prep"}
          </span>
        ) : null}
      </div>
      <div className="text-base font-semibold tabular-nums text-slate-100">{price}</div>
      <div className={`text-sm font-medium tabular-nums ${changeClass}`}>
        {changeLabel}
        {changeSubtext != null ? (
          <span className="ml-1 text-slate-500 font-normal">({changeSubtext})</span>
        ) : null}
      </div>
    </div>
  );
}
