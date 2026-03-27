/**
 * Target Data workspace charts (Add Block system).
 * Persisted in portfolio_entity.chart_layout as workspace_charts + blockHeights.
 */

export type BlockKind = "overlay" | "split" | "analysis";

/** Component category for Entity add flow: data = raw/direct, analysis = derived/composite. */
export type ComponentCategory = "data" | "analysis";

/** Supported block types. Legacy: technical, sentiment, quadrant, 3d. New: overlay_*, split_*, analysis_*. */
export const WORKSPACE_CHART_TYPES = [
  "technical",
  "sentiment",
  "quadrant",
  "3d",
  "overlay_technical",
  "overlay_sentiment",
  "split_technical",
  "split_sentiment",
  "series_search_volume",
  "series_coverage_volume",
  "metric_momentum",
  "metric_acceleration",
  "analysis_3d",
  "analysis_institution_bias",
  "analysis_rating_distribution",
] as const;

export type WorkspaceChartType = (typeof WORKSPACE_CHART_TYPES)[number];

export const MAX_WORKSPACE_CHARTS = 5;

export type WorkspaceChartBlock = {
  id: string;
  type: WorkspaceChartType;
  title?: string;
};

/** Component category for Entity add modal. Data = raw time-series; Analysis = derived/composite. */
export const COMPONENT_CATEGORY: Record<WorkspaceChartType, ComponentCategory> = {
  technical: "data",
  sentiment: "data",
  overlay_technical: "data",
  overlay_sentiment: "data",
  split_technical: "data",
  split_sentiment: "data",
  series_search_volume: "data",
  series_coverage_volume: "data",
  quadrant: "analysis",
  "3d": "analysis",
  analysis_3d: "analysis",
  metric_momentum: "analysis",
  metric_acceleration: "analysis",
  analysis_institution_bias: "analysis",
  analysis_rating_distribution: "analysis",
};

/**
 * Workspace types wired for Entity page: real chart renderers or intentional “coming soon” panels.
 * Derived from backend /api/entities/* routes + frontend Entity* components. Excludes overlay_* (layout only).
 */
export const ENTITY_WORKSPACE_IMPLEMENTED_TYPES: readonly WorkspaceChartType[] = [
  "split_technical",
  "split_sentiment",
  "series_search_volume",
  "series_coverage_volume",
  "quadrant",
  "analysis_3d",
  "metric_momentum",
  "metric_acceleration",
  "analysis_institution_bias",
  "analysis_rating_distribution",
] as const;

/** Premium / admin-only preview in Entity workspace until backends ship. */
export const ENTITY_PREMIUM_WORKSPACE_TYPES: readonly WorkspaceChartType[] = [
  "analysis_institution_bias",
  "analysis_rating_distribution",
] as const;

/** Sentiment Data section in Add Component modal. */
export const ENTITY_ADD_MODAL_DATA_TYPES: WorkspaceChartType[] = ENTITY_WORKSPACE_IMPLEMENTED_TYPES.filter(
  (t) => COMPONENT_CATEGORY[t] === "data"
);

/** Sentiment Analysis section in Add Component modal. */
export const ENTITY_ADD_MODAL_ANALYSIS_TYPES: WorkspaceChartType[] = ENTITY_WORKSPACE_IMPLEMENTED_TYPES.filter(
  (t) => COMPONENT_CATEGORY[t] === "analysis"
);

/** @deprecated Use ENTITY_ADD_MODAL_DATA_TYPES */
export const SENTIMENT_DATA_TYPES = ENTITY_ADD_MODAL_DATA_TYPES;
/** @deprecated Use ENTITY_ADD_MODAL_ANALYSIS_TYPES */
export const SENTIMENT_ANALYSIS_TYPES = ENTITY_ADD_MODAL_ANALYSIS_TYPES;

/** Block types by kind. Kept for Research page and backward compatibility. */
export const OVERLAY_TYPES: WorkspaceChartType[] = ["overlay_technical", "overlay_sentiment"];
export const SPLIT_TYPES: WorkspaceChartType[] = ["split_technical", "split_sentiment"];
export const ANALYSIS_TYPES: WorkspaceChartType[] = [
  "analysis_3d",
  "analysis_institution_bias",
  "analysis_rating_distribution",
];

export const WORKSPACE_CHART_LABELS: Record<string, string> = {
  technical: "Technical",
  sentiment: "Sentiment",
  quadrant: "Quadrant",
  "3d": "3D",
  overlay_technical: "Price & indicators",
  overlay_sentiment: "Sentiment series",
  split_technical: "Technical (stacked)",
  split_sentiment: "Sentiment (stacked)",
  series_search_volume: "Search trend",
  series_coverage_volume: "Coverage volume",
  metric_momentum: "Search momentum (Δ trend)",
  metric_acceleration: "Search acceleration (Δ² trend)",
  analysis_3d: "3D Narrative Space",
  analysis_institution_bias: "Institution bias",
  analysis_rating_distribution: "Rating distribution",
};

export const WORKSPACE_CHART_DESCRIPTIONS: Record<string, string> = {
  technical: "Price, volume, and technical indicators.",
  sentiment: "Narrative and sentiment time series.",
  quadrant: "Search vs coverage momentum quadrant.",
  "3d": "Search trend vs coverage over time (3D path).",
  overlay_technical: "Multiple compatible series on the same plot.",
  overlay_sentiment: "Multiple sentiment series overlaid.",
  split_technical: "Stacked vertically with shared time axis.",
  split_sentiment: "Stacked sentiment charts, shared timeline.",
  series_search_volume: "Daily search-trend time series from entity metrics (DB snapshots).",
  series_coverage_volume: "Daily coverage-volume time series from entity metrics.",
  metric_momentum: "First difference of search trend (day-over-day change).",
  metric_acceleration: "Second difference of search trend (momentum of momentum).",
  analysis_3d: "3D narrative space — search vs coverage.",
  analysis_institution_bias: "Bullish vs bearish institution stance.",
  analysis_rating_distribution: "Buy / hold / sell distribution.",
};

export const WORKSPACE_CHART_DEFAULT_TITLES: Record<string, string> = {
  technical: "Technical",
  sentiment: "Sentiment",
  quadrant: "Quadrant",
  "3d": "Narrative 3D",
  overlay_technical: "Overlay — Technical",
  overlay_sentiment: "Overlay — Sentiment",
  split_technical: "Split — Technical",
  split_sentiment: "Split — Sentiment",
  series_search_volume: "Search trend",
  series_coverage_volume: "Coverage volume",
  metric_momentum: "Search momentum",
  metric_acceleration: "Search acceleration",
  analysis_3d: "3D Narrative Space",
  analysis_institution_bias: "Institution Bias",
  analysis_rating_distribution: "Rating Distribution",
};

export const KIND_LABELS: Record<BlockKind, string> = {
  overlay: "Overlay Chart",
  split: "Split Chart",
  analysis: "Analysis",
};

function isWorkspaceType(s: string): s is WorkspaceChartType {
  return (WORKSPACE_CHART_TYPES as readonly string[]).includes(s);
}

/** Legacy types map to new for display/lookup. */
function normalizeType(type: string): string {
  if (type === "3d") return "analysis_3d";
  return type;
}

/** User-facing chart title for the card (never exposes internal `id`). */
export function getWorkspaceChartDisplayTitle(block: WorkspaceChartBlock): string {
  const t = block.title?.trim();
  if (t) {
    const norm = normalizeType(block.type);
    if (
      (block.type === "3d" || norm === "analysis_3d") &&
      (t === "3D" || t === "3D Surface" || t === "Search vs Coverage 3D" || t === "Narrative 3D")
    ) {
      return WORKSPACE_CHART_DEFAULT_TITLES["analysis_3d"];
    }
    return t;
  }
  const norm = normalizeType(block.type);
  return WORKSPACE_CHART_DEFAULT_TITLES[norm] ?? WORKSPACE_CHART_LABELS[block.type] ?? block.type;
}

/** Resolve block kind from type. */
export function getBlockKind(type: WorkspaceChartType | string): BlockKind {
  if (type.startsWith("overlay_")) return "overlay";
  if (type.startsWith("split_")) return "split";
  if (type.startsWith("series_")) return "split";
  if (type.startsWith("metric_")) return "analysis";
  if (type.startsWith("analysis_") || type === "3d" || type === "quadrant") return "analysis";
  if (["technical", "sentiment"].includes(type)) return "split";
  return "analysis";
}

function newBlockId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `blk-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Parse and migrate chart_layout from API into workspace blocks + heights. */
export function parseWorkspaceChartLayout(raw: unknown): {
  blocks: WorkspaceChartBlock[];
  heights: Record<string, number>;
  narrativeFlowPeriod: string | undefined;
} {
  if (!raw || typeof raw !== "object") {
    return { blocks: [], heights: {}, narrativeFlowPeriod: undefined };
  }
  const o = raw as Record<string, unknown>;

  const narrativeFlowPeriod =
    typeof o.narrativeFlowPeriod === "string"
      ? o.narrativeFlowPeriod
      : typeof o.quadrantPeriod === "string"
        ? o.quadrantPeriod
        : undefined;

  // New format
  const ws = o.workspace_charts;
  if (Array.isArray(ws) && ws.length > 0) {
    const blocks: WorkspaceChartBlock[] = [];
    for (const item of ws) {
      if (blocks.length >= MAX_WORKSPACE_CHARTS) break;
      if (!item || typeof item !== "object") continue;
      const b = item as Record<string, unknown>;
      const rawType = typeof b.type === "string" ? b.type : null;
      if (!rawType) continue;
      const type: WorkspaceChartType = isWorkspaceType(rawType) ? rawType : ("split_technical" as WorkspaceChartType);
      const id = typeof b.id === "string" && b.id.trim() ? b.id : newBlockId();
      const title = typeof b.title === "string" && b.title.trim() ? b.title.trim() : undefined;
      blocks.push({ id, type, title });
    }
    const heights = parseHeights(o.blockHeights, blocks.map((x) => x.id));
    return { blocks, heights, narrativeFlowPeriod };
  }

  // Legacy: charts[] strings → up to one block per category
  const legacyCharts = Array.isArray(o.charts) ? o.charts.filter((c): c is string => typeof c === "string") : [];
  const blocks: WorkspaceChartBlock[] = [];
  let hasTechnical = false;
  let hasSentiment = false;
  let hasQuadrant = false;

  for (const c of legacyCharts) {
    if (blocks.length >= MAX_WORKSPACE_CHARTS) break;
    if (c === "Sentiment" && !hasSentiment) {
      blocks.push({ id: newBlockId(), type: "sentiment", title: WORKSPACE_CHART_LABELS.sentiment });
      hasSentiment = true;
    } else if ((c === "Narrative Flow" || c === "Quadrant") && !hasQuadrant) {
      blocks.push({ id: newBlockId(), type: "quadrant", title: WORKSPACE_CHART_LABELS.quadrant });
      hasQuadrant = true;
    } else if (
      (c === "Price" ||
        c === "Search Volume" ||
        c === "Coverage Volume" ||
        c === "Order Flow" ||
        c === "Search Momentum" ||
        c === "Coverage Momentum" ||
        c === "Sentiment Change" ||
        c === "Attention Ratio" ||
        c === "Narrative Summary") &&
      !hasTechnical
    ) {
      blocks.push({ id: newBlockId(), type: "technical", title: WORKSPACE_CHART_LABELS.technical });
      hasTechnical = true;
    }
  }

  const heights = parseHeights(o.blockHeights, blocks.map((x) => x.id));
  return { blocks, heights, narrativeFlowPeriod };
}

function parseHeights(raw: unknown, validIds: string[]): Record<string, number> {
  const out: Record<string, number> = {};
  if (!raw || typeof raw !== "object") return out;
  const idSet = new Set(validIds);
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!idSet.has(k) && !k.startsWith("blk-")) continue;
    if (typeof v === "number" && Number.isFinite(v)) out[k] = v;
  }
  return out;
}

export function buildChartLayoutPayload(
  blocks: WorkspaceChartBlock[],
  heights: Record<string, number>,
  narrativeFlowPeriod?: string
): Record<string, unknown> {
  return {
    version: 2,
    workspace_charts: blocks.map((b) => ({
      id: b.id,
      type: b.type,
      ...(b.title ? { title: b.title } : {}),
    })),
    blockHeights: heights,
    ...(narrativeFlowPeriod ? { narrativeFlowPeriod } : {}),
  };
}

export function addWorkspaceChart(blocks: WorkspaceChartBlock[], type: WorkspaceChartType): WorkspaceChartBlock[] {
  if (blocks.length >= MAX_WORKSPACE_CHARTS) return blocks;
  return [
    ...blocks,
    {
      id: newBlockId(),
      type,
      title: WORKSPACE_CHART_DEFAULT_TITLES[type] ?? WORKSPACE_CHART_LABELS[type],
    },
  ];
}

export function removeWorkspaceChart(blocks: WorkspaceChartBlock[], id: string): WorkspaceChartBlock[] {
  return blocks.filter((b) => b.id !== id);
}
