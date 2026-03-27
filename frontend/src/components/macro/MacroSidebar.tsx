"use client";

import type { MacroCategorySlug } from "@/lib/macroCategories";
import { MACRO_CATEGORIES } from "@/lib/macroCategories";
import { useI18n } from "@/lib/i18n";

const CATEGORY_KEYS: Record<MacroCategorySlug, string> = {
  general: "macro.general",
  stock: "macro.stock",
  futures: "macro.futures",
  crypto: "macro.crypto",
};

export function MacroSidebar({
  selectedCategory,
  onSelectCategory,
}: {
  selectedCategory: MacroCategorySlug | null;
  onSelectCategory: (category: MacroCategorySlug | null) => void;
}) {
  const { t } = useI18n();
  const isSelected = (slug: string) =>
    selectedCategory === slug || selectedCategory === slug.toLowerCase();

  return (
    <div className="space-y-3">
      <div className="text-sm font-semibold text-slate-300">{t("macro.categorySelector")}</div>
      <nav className="space-y-0.5">
        {MACRO_CATEGORIES.map(({ slug }) => {
          const selected = isSelected(slug);
          return (
            <button
              key={slug}
              type="button"
              onClick={() => onSelectCategory(selected ? null : slug)}
              className={
                "flex w-full items-center rounded-r border-l-2 py-2 pl-3 pr-2 text-left text-sm transition-colors " +
                (selected
                  ? "border-indigo-500/70 bg-slate-700/60 text-slate-100"
                  : "border-transparent bg-slate-900/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800/50 hover:text-slate-200")
              }
            >
              {t(CATEGORY_KEYS[slug])}
            </button>
          );
        })}
        <button
          type="button"
          disabled
          className="flex w-full cursor-default items-center rounded-r border-l-2 border-transparent py-2 pl-3 pr-2 text-left text-sm text-slate-500"
          title="Coming soon"
        >
          {t("macro.customPlaceholder")}
        </button>
      </nav>
    </div>
  );
}
