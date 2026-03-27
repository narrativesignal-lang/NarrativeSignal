/**
 * Shared time-range model for analysis blocks. Aligned with entity/instrument context.
 * Use for Narrative Flow, Search Volume, Coverage Volume, Sentiment, and future blocks.
 */
export const ANALYSIS_PERIODS = ["7D", "1M", "3M", "6M", "1Y", "MAX"] as const;
export type AnalysisPeriod = (typeof ANALYSIS_PERIODS)[number];

export const DEFAULT_ANALYSIS_PERIOD: AnalysisPeriod = "1M";

/** Periods supported by Narrative Flow (path/trail) — can extend to full set later. */
export const NARRATIVE_FLOW_PERIODS: AnalysisPeriod[] = ["7D", "1M", "3M", "6M", "1Y", "MAX"];

/** Periods supported by time-series blocks (Search/Coverage/Sentiment) — backend may support subset. */
export const TIME_SERIES_PERIODS: AnalysisPeriod[] = ["7D", "1M", "3M", "6M", "1Y", "MAX"];

export function isValidAnalysisPeriod(p: string): p is AnalysisPeriod {
  return ANALYSIS_PERIODS.includes(p as AnalysisPeriod);
}
