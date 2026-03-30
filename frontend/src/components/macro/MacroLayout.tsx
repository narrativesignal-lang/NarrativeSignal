"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import type { MacroCategorySlug } from "@/lib/macroCategories";
import { MACRO_CATEGORY_SLUGS } from "@/lib/macroCategories";
import { api } from "@/lib/api";
import { mockHeatmapForCategory } from "@/lib/macroMockData";
import { STALE_MACRO_NEWS_MS, STALE_MARKET_MS } from "@/lib/queryClient";
import { IndexWatchlist } from "./IndexWatchlist";
import { MacroSidebar } from "./MacroSidebar";
import { NewsHeatmap } from "./NewsHeatmap";
import { NewsList } from "./NewsList";
import { Top5Trending } from "./Top5Trending";

const NEWS_PRELOAD_LIMIT = 40;

type MacroLayoutProps = {
  isActive?: boolean;
};

export function MacroLayout({ isActive = true }: MacroLayoutProps) {
  const queryClient = useQueryClient();
  const [selectedCategory, setSelectedCategory] = useState<MacroCategorySlug | null>("general");
  const [heatmapFilter, setHeatmapFilter] = useState<string | null>(null);

  useEffect(() => {
    setHeatmapFilter(null);
  }, [selectedCategory]);

  useEffect(() => {
    if (!isActive) return;
    for (const slug of MACRO_CATEGORY_SLUGS) {
      void queryClient.prefetchQuery({
        queryKey: ["macro", "news", slug, NEWS_PRELOAD_LIMIT],
        queryFn: () => api.macroNews(slug, null, NEWS_PRELOAD_LIMIT),
        staleTime: STALE_MACRO_NEWS_MS
      });
      void queryClient.prefetchQuery({
        queryKey: ["market", "indices", slug],
        queryFn: () => api.marketIndices(slug),
        staleTime: STALE_MARKET_MS
      });
    }
    for (const sym of ["SPX", "^GSPC", "BTC-USD"]) {
      void queryClient.prefetchQuery({
        queryKey: ["market", "quote", sym],
        queryFn: () => api.quote(sym),
        staleTime: STALE_MARKET_MS
      });
    }
  }, [queryClient, isActive]);

  const heatmapCells = useMemo(() => {
    if (!selectedCategory) return null;
    return mockHeatmapForCategory(selectedCategory);
  }, [selectedCategory]);

  return (
    <div className="flex flex-col gap-4 md:grid md:min-h-[70vh] md:grid-cols-[200px_1fr_280px] md:items-stretch">
      {/* LEFT: Category selector */}
      <aside className="shrink-0 rounded-lg border border-slate-800 bg-slate-900/40 p-4 md:min-h-0">
        <MacroSidebar
          selectedCategory={selectedCategory}
          onSelectCategory={setSelectedCategory}
        />
      </aside>

      {/* CENTER: News list + Heatmap — flexible on mobile, fixed height on desktop */}
      <section className="flex min-h-0 flex-1 flex-col gap-4 md:min-h-0">
        <div
          className="flex min-h-[280px] flex-col overflow-hidden rounded-lg border border-slate-800 bg-slate-900/40 p-4 md:h-[46vh] md:min-h-[200px] md:max-h-[46vh]"
        >
          <NewsList
            categorySlug={selectedCategory}
            subcategoryFilter={heatmapFilter}
          />
        </div>
        <div className="flex min-h-[200px] shrink-0 flex-col overflow-hidden rounded-lg border border-slate-800 bg-slate-900/40 p-4 md:min-h-[220px]">
          <NewsHeatmap
            categorySlug={selectedCategory}
            selectedSubcategory={heatmapFilter}
            onSelectSubcategory={setHeatmapFilter}
            cells={heatmapCells}
          />
        </div>
      </section>

      {/* RIGHT: Index watchlist + Top 5 trending */}
      <aside className="flex min-h-0 flex-col gap-4 md:min-h-0">
        <div className="flex min-h-[200px] flex-col overflow-hidden rounded-lg border border-slate-800 bg-slate-900/40 p-4 md:min-h-0 md:flex-1">
          <IndexWatchlist category={selectedCategory ?? "general"} />
        </div>
        <div className="shrink-0">
          <Top5Trending
            categorySlug={selectedCategory}
            selectedSubcategory={heatmapFilter}
            onSelectSubcategory={setHeatmapFilter}
            heatmapCells={heatmapCells}
          />
        </div>
      </aside>
    </div>
  );
}
