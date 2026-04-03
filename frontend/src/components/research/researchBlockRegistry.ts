import type { ChartType } from "./ResearchChart";

/**
 * Single source for Research Add Block modal: which chart types appear under Overlay / Split / Analysis.
 * Overlay = same entity-period timeline (mapped to entity overlay series when an entity target exists).
 */
export const RESEARCH_OVERLAY_CHART_TYPES: ChartType[] = [
  "asset_price",
  "sentiment",
  "momentum",
  "coverage",
  "custom_index",
];

export const RESEARCH_SPLIT_CHART_TYPES: ChartType[] = [
  "asset_price",
  "sentiment",
  "momentum",
  "coverage",
  "custom_index",
];

export const RESEARCH_ANALYSIS_CHART_TYPES: ChartType[] = [
  "three_d",
  "three_d_narrative",
  "three_d_derivative",
  "institution_bias",
  "rating_distribution",
];

/**
 * Map research chart types to entity workspace overlay series keys (EntityMathOverlayChart).
 * UI labels: `momentum` → Target Search Volume, `sentiment` → Keyword Search Volume, `coverage` → Coverage Volume.
 * Split-chart blocks use the same entity APIs: `coverage` → `getEntityCoverageVolumeSeries`, etc.
 */
export const RESEARCH_OVERLAY_TYPE_TO_ENTITY_KEY: Partial<Record<ChartType, string>> = {
  asset_price: "price_close",
  sentiment: "keywords_search_volume",
  momentum: "target_search_volume",
  coverage: "coverage_volume",
  custom_index: "keywords_search_volume",
};
