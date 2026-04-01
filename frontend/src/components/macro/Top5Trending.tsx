"use client";

import { useMemo } from "react";
import { useI18n } from "@/lib/i18n";
import type { MacroCategorySlug } from "@/lib/macroCategories";
import type { HeatmapCell } from "@/lib/macroMockData";

type Props = {
  categorySlug: MacroCategorySlug | null;
  selectedSubcategory: string | null;
  onSelectSubcategory: (name: string | null) => void;
  /** Optional: pass heatmap cells from parent to keep in sync */
  heatmapCells?: HeatmapCell[] | null;
};

export function Top5Trending({
  categorySlug,
  selectedSubcategory,
  onSelectSubcategory,
  heatmapCells,
}: Props) {
  const { t } = useI18n();
  const top5 = useMemo(() => {
    const cells = heatmapCells ?? [];
    return [...cells]
      .sort((a, b) => b.volume_24h - a.volume_24h)
      .slice(0, 5);
  }, [heatmapCells]);

  if (!categorySlug) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div className="text-sm font-semibold text-slate-300">{t("macro.top5Trending")}</div>
        <div className="mt-2 text-xs text-slate-500">{t("macro.selectCategory")}</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <div className="text-sm font-semibold text-slate-300">{t("macro.top5Trending")}</div>
      <div className="mt-2 flex flex-col gap-1">
        {top5.map((cell, i) => {
          const isSelected = selectedSubcategory === cell.name;
          return (
            <button
              key={cell.name}
              type="button"
              onClick={() => onSelectSubcategory(isSelected ? null : cell.name)}
              className={
                "flex items-center justify-between rounded border px-2 py-1.5 text-left text-sm transition-colors " +
                (isSelected
                  ? "border-indigo-500/70 bg-slate-700/60 text-slate-100"
                  : "border-slate-800 bg-slate-900/50 text-slate-300 hover:border-slate-600 hover:bg-slate-800/50 hover:text-slate-200")
              }
            >
              <span className="font-medium">{cell.name}</span>
              <span className="text-xs tabular-nums text-slate-400">
                #{i + 1} · {cell.volume_24h}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
