"use client";

import { useMemo } from "react";
import { useI18n } from "@/lib/i18n";
import type { MacroCategorySlug } from "@/lib/macroCategories";
import type { HeatmapCell } from "@/lib/macroMockData";
import { mockHeatmapForCategory } from "@/lib/macroMockData";

type Props = {
  categorySlug: MacroCategorySlug | null;
  selectedSubcategory: string | null;
  onSelectSubcategory: (name: string | null) => void;
  /** Optional: override mock with real data when API exists */
  cells?: HeatmapCell[] | null;
};

function cellColor(delta: number): string {
  /** Higher volume vs prior period: neutral-positive (emerald); drop: red */
  if (delta > 0.05) return "bg-emerald-600/55 hover:bg-emerald-600/75 border-emerald-500/50";
  if (delta < -0.05) return "bg-red-500/65 hover:bg-red-500/85 border-red-400/50";
  return "bg-slate-600/60 hover:bg-slate-500/70 border-slate-500/50";
}

function changeTextColor(delta: number): string {
  if (delta > 0.05) return "text-emerald-100";
  if (delta < -0.05) return "text-red-100";
  return "text-slate-100";
}

export function NewsHeatmap({
  categorySlug,
  selectedSubcategory,
  onSelectSubcategory,
  cells: cellsProp,
}: Props) {
  const { t } = useI18n();
  const cells = useMemo(() => {
    if (cellsProp != null) return cellsProp;
    if (!categorySlug) return [];
    return mockHeatmapForCategory(categorySlug);
  }, [categorySlug, cellsProp]);

  const maxVolume = useMemo(() => Math.max(1, ...cells.map((c) => c.volume_24h)), [cells]);

  if (!categorySlug) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-500">
        {t("macro.selectCategoryHeatmap")}
      </div>
    );
  }

  if (cells.length === 0) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-500">
        {t("macro.noSubcategories")}
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="mb-2 text-sm font-semibold text-slate-300">
        {t("macro.newsHeatmapTitle")}
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {cells.map((cell) => {
            const isSelected = selectedSubcategory === cell.name;
            const sizeRatio = maxVolume > 0 ? cell.volume_24h / maxVolume : 0.5;
            const minH = 56;
            const h = Math.max(minH, 80 + sizeRatio * 80);
            return (
              <button
                key={cell.name}
                type="button"
                onClick={() => onSelectSubcategory(isSelected ? null : cell.name)}
                className={
                  "flex flex-col justify-between rounded-lg border p-3 sm:p-4 text-left transition-all " +
                  cellColor(cell.delta) +
                  (isSelected ? " ring-2 ring-indigo-400 ring-offset-2 ring-offset-slate-900" : "")
                }
                style={{ minHeight: `${h}px` }}
                title={`${cell.name}: ${cell.volume_24h} (prev: ${cell.volume_prev_24h}), ${(cell.delta * 100).toFixed(1)}%`}
              >
                <div className="text-sm sm:text-base font-medium text-slate-50 drop-shadow-sm line-clamp-2">
                  {cell.name}
                </div>
                <div className="mt-1 flex flex-1 items-center">
                  <span className="text-2xl sm:text-3xl font-semibold tabular-nums text-slate-50 drop-shadow">
                    {cell.volume_24h}
                  </span>
                </div>
                <div className="mt-1 text-sm sm:text-base font-medium tabular-nums">
                  <span className={changeTextColor(cell.delta)}>
                    {(() => {
                      const pct = cell.delta * 100;
                      const magnitude = Math.abs(pct).toFixed(0);
                      const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
                      return `${sign}${magnitude}%`;
                    })()}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
