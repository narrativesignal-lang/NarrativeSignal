/**
 * Narrative Radar category and subcategory definitions.
 * Used by heatmap, news filter, and trending list.
 */

export type MacroCategorySlug = "general" | "stock" | "futures" | "crypto";

export type CategoryDef = {
  slug: MacroCategorySlug;
  label: string;
  subcategories: string[];
};

export const MACRO_CATEGORIES: CategoryDef[] = [
  {
    slug: "general",
    label: "General",
    subcategories: [
      "AI",
      "Rates",
      "Inflation",
      "Energy",
      "China",
      "Geopolitics",
      "Regulation",
      "Consumer",
      "Labor",
      "Banking",
    ],
  },
  {
    slug: "stock",
    label: "Stock",
    subcategories: [
      "Semiconductors",
      "Software",
      "Internet",
      "Consumer Electronics",
      "Auto Manufacturers",
      "Aerospace & Defense",
      "Utilities",
      "Banks",
      "Biotech",
      "Oil & Gas",
      "Retail",
      "Industrials",
    ],
  },
  {
    slug: "futures",
    label: "Futures",
    subcategories: [
      "Precious Metals",
      "Energy",
      "Industrial Metals",
      "Agriculture",
      "Softs",
      "Livestock",
      "Rates",
      "FX",
    ],
  },
  {
    slug: "crypto",
    label: "Crypto",
    subcategories: ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA"],
  },
];

export const MACRO_CATEGORY_SLUGS = MACRO_CATEGORIES.map((c) => c.slug);

export function getSubcategories(slug: MacroCategorySlug | null): string[] {
  if (!slug) return [];
  const cat = MACRO_CATEGORIES.find((c) => c.slug === slug);
  return cat?.subcategories ?? [];
}

export function getCategoryLabel(slug: MacroCategorySlug): string {
  return MACRO_CATEGORIES.find((c) => c.slug === slug)?.label ?? slug;
}
