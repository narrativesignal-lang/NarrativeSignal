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
  "series_target_search_volume",
  "series_keywords_search_volume",
  "series_coverage_volume",
  "series_triple_signal",
  "metric_momentum_target",
  "metric_acceleration_target",
  "metric_momentum_keywords",
  "metric_acceleration_keywords",
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
  /** For `overlay_technical`: which math series share the entity period timeline (normalized overlay). */
  overlaySeries?: readonly string[];
};

/** Ordered keys for deterministic UI and merge behavior. */
export const ENTITY_OVERLAY_SERIES_ORDER = [
  "price_close",
  "target_search_volume",
  "keywords_search_volume",
  "coverage_volume",
  "triple_signal",
] as const;

export type EntityOverlaySeriesKey = (typeof ENTITY_OVERLAY_SERIES_ORDER)[number];

export const ENTITY_OVERLAY_TIMELINE_HINT =
  "These series use the same entity period (daily-aligned where available). Values are min–max normalized per series for comparison (math only, not price levels).";

export const ENTITY_OVERLAY_SERIES_META: Record<
  EntityOverlaySeriesKey,
  { label: string; description: string }
> = {
  price_close: {
    label: "Price (close)",
    description: "Instrument close from cached OHLCV, normalized for shape — not dollar scale.",
  },
  target_search_volume: {
    label: "Target Search Volume",
    description: "Ticker-intent search index for the entity period (raw series).",
  },
  keywords_search_volume: {
    label: "Keyword Search Volume",
    description: "Narrative keyword search aggregate for the entity period (raw series).",
  },
  coverage_volume: {
    label: "Coverage Volume",
    description: "News coverage volume for the entity period (raw series).",
  },
  triple_signal: {
    label: "Triple signal (3 lines)",
    description: "Trading activity, coverage volume, and keyword search index (each normalized 0–100 in source API).",
  },
};

export function isEntityOverlaySeriesKey(s: string): s is EntityOverlaySeriesKey {
  return (ENTITY_OVERLAY_SERIES_ORDER as readonly string[]).includes(s);
}

const ENTITY_OVERLAY_LABEL_I18N: Record<EntityOverlaySeriesKey, string> = {
  price_close: "workspace.overlayPriceClose",
  target_search_volume: "workspace.targetSearchVolume",
  keywords_search_volume: "workspace.keywordSearchVolume",
  coverage_volume: "workspace.coverageVolume",
  triple_signal: "workspace.overlayTripleSignalTitle",
};

/** User-facing overlay picker / legend label (i18n with English fallback from `ENTITY_OVERLAY_SERIES_META`). */
export function entityOverlaySeriesLabel(
  t: (key: string) => string,
  key: EntityOverlaySeriesKey
): string {
  const i18nKey = ENTITY_OVERLAY_LABEL_I18N[key];
  const v = t(i18nKey);
  return v !== i18nKey ? v : ENTITY_OVERLAY_SERIES_META[key].label;
}

function sortOverlayKeys(keys: Iterable<string>): string[] {
  const order = new Map(ENTITY_OVERLAY_SERIES_ORDER.map((k, i) => [k, i]));
  return [...new Set(keys)].filter(isEntityOverlaySeriesKey).sort((a, b) => (order.get(a)! - order.get(b)!));
}

/** Data tab (single charts): one block per add — parallel time-series / stacked layouts. */
export const ENTITY_SPLIT_TAB_TYPES: readonly WorkspaceChartType[] = [
  "split_technical",
  "split_sentiment",
  "series_target_search_volume",
  "series_keywords_search_volume",
  "series_coverage_volume",
  "series_triple_signal",
] as const;

/** Analysis tab: derived / spatial charts (DB metrics; no LLM in request path for 3D). */
export const ENTITY_CLASSIC_ANALYSIS_TAB_TYPES: readonly WorkspaceChartType[] = [
  "quadrant",
  "analysis_3d",
  "metric_momentum_target",
  "metric_acceleration_target",
  "metric_momentum_keywords",
  "metric_acceleration_keywords",
  "analysis_institution_bias",
  "analysis_rating_distribution",
] as const;

/**
 * Target Data → AI Analysis tab only: blocks that call LLM / AI pipelines on the backend
 * (same tier as `FeatureKey.ENTITY_SENTIMENT_AI` — LIGHT_AI).
 */
export const ENTITY_AI_ANALYSIS_TAB_TYPES: readonly WorkspaceChartType[] = ["overlay_sentiment"] as const;

/** UI + gating: which workspace block types consume AI (matches backend feature tiers). */
export type WorkspaceAiCost = "none" | "light" | "heavy";

export const WORKSPACE_BLOCK_AI_COST: Partial<Record<WorkspaceChartType, WorkspaceAiCost>> = {
  overlay_sentiment: "light",
};

/** All analysis-category picks (classic + AI). */
export const ENTITY_ANALYSIS_TAB_TYPES: readonly WorkspaceChartType[] = [
  ...ENTITY_CLASSIC_ANALYSIS_TAB_TYPES,
  ...ENTITY_AI_ANALYSIS_TAB_TYPES,
] as const;

export type ChartAspectMode = "rectangular" | "square";

export function workspaceBlockAspectMode(type: WorkspaceChartType | string): ChartAspectMode {
  if (type === "quadrant" || type === "3d" || type === "analysis_3d") return "square";
  return "rectangular";
}

/** Component category for Entity add modal. Data = raw time-series; Analysis = derived/composite. */
export const COMPONENT_CATEGORY: Record<WorkspaceChartType, ComponentCategory> = {
  technical: "data",
  sentiment: "data",
  overlay_technical: "data",
  overlay_sentiment: "data",
  split_technical: "data",
  split_sentiment: "data",
  series_target_search_volume: "data",
  series_keywords_search_volume: "data",
  series_coverage_volume: "data",
  series_triple_signal: "data",
  quadrant: "analysis",
  "3d": "analysis",
  analysis_3d: "analysis",
  metric_momentum_target: "analysis",
  metric_acceleration_target: "analysis",
  metric_momentum_keywords: "analysis",
  metric_acceleration_keywords: "analysis",
  analysis_institution_bias: "analysis",
  analysis_rating_distribution: "analysis",
};

/**
 * Workspace types wired for Entity page: real chart renderers or intentional “coming soon” panels.
 * Derived from backend /api/entities/* routes + frontend Entity* components.
 */
export const ENTITY_WORKSPACE_IMPLEMENTED_TYPES: readonly WorkspaceChartType[] = [
  // Data (Entity workspace surface — these MUST stay aligned with Add Component modal tabs)
  "overlay_technical",
  "overlay_sentiment",
  "series_target_search_volume",
  "series_keywords_search_volume",
  "series_coverage_volume",
  "series_triple_signal",
  // Analysis
  "quadrant",
  "analysis_3d",
  "metric_momentum_target",
  "metric_acceleration_target",
  "metric_momentum_keywords",
  "metric_acceleration_keywords",
  "analysis_institution_bias",
  "analysis_rating_distribution",
] as const;

/** Premium / admin-only types for Entity workspace add modal (empty = all available). */
export const ENTITY_PREMIUM_WORKSPACE_TYPES: readonly WorkspaceChartType[] = [] as const;

/** @deprecated Modal uses ENTITY_SPLIT_TAB_TYPES / ENTITY_ANALYSIS_TAB_TYPES + overlay series keys. */
export const ENTITY_ADD_MODAL_DATA_TYPES: WorkspaceChartType[] = ENTITY_WORKSPACE_IMPLEMENTED_TYPES.filter(
  (t) => COMPONENT_CATEGORY[t] === "data"
);

/** @deprecated Modal uses ENTITY_ANALYSIS_TAB_TYPES. */
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
  sentiment: "Narrative sentiment score",
  quadrant: "Narrative quadrant",
  "3d": "3D",
  overlay_technical: "Price & indicators",
  overlay_sentiment: "AI sentiment overlay",
  split_technical: "Technical (stacked)",
  split_sentiment: "Sentiment score (stacked)",
  series_target_search_volume: "Target Search Volume",
  series_keywords_search_volume: "Keyword Search Volume",
  series_coverage_volume: "Coverage Volume",
  series_triple_signal: "Triple signal",
  metric_momentum_target: "Target Search Momentum",
  metric_acceleration_target: "Target Search Acceleration",
  metric_momentum_keywords: "Keyword Search Momentum",
  metric_acceleration_keywords: "Keyword Search Acceleration",
  analysis_3d: "3D narrative space",
  analysis_institution_bias: "Institution bias",
  analysis_rating_distribution: "Rating distribution",
};

export const WORKSPACE_CHART_DESCRIPTIONS: Record<string, string> = {
  technical: "Price, volume, and technical indicators.",
  sentiment: "Narrative sentiment score time series (not keyword search volume).",
  quadrant: "Keyword search volume vs coverage volume quadrant.",
  "3d": "Search trend vs coverage over time (3D path).",
  overlay_technical: "Multiple compatible series on the same plot.",
  overlay_sentiment: "AI-derived sentiment from news (server pipeline).",
  split_technical: "Stacked vertically with shared time axis.",
  split_sentiment: "Stacked sentiment score charts, shared timeline.",
  series_target_search_volume: "Google Trends index for the primary instrument symbol (ticker intent), one keyword.",
  series_keywords_search_volume: "Sum of independent narrative keyword Trends series (not mixed with ticker).",
  series_coverage_volume: "Daily coverage volume time series from entity metrics.",
  series_triple_signal: "Three normalized lines: trading activity, coverage volume, keyword search index.",
  metric_momentum_target: "Day-over-day change in target (ticker) search volume (derived).",
  metric_acceleration_target: "Second difference of target search volume (derived).",
  metric_momentum_keywords: "Day-over-day change in keyword search aggregate (derived).",
  metric_acceleration_keywords: "Second difference of keyword search aggregate (derived).",
  analysis_3d: "3D narrative space — keywords search vs coverage.",
  analysis_institution_bias: "Institutional stance category shares (bullish / neutral / bearish).",
  analysis_rating_distribution: "Analyst rating category percentages (distribution).",
};

export const WORKSPACE_CHART_DEFAULT_TITLES: Record<string, string> = {
  technical: "Technical",
  sentiment: "Narrative sentiment score",
  quadrant: "Quadrant",
  "3d": "Narrative 3D",
  overlay_technical: "Overlay — Technical",
  overlay_sentiment: "Overlay — AI sentiment",
  split_technical: "Split — Technical",
  split_sentiment: "Split — Sentiment score",
  series_target_search_volume: "Target Search Volume",
  series_keywords_search_volume: "Keyword Search Volume",
  series_coverage_volume: "Coverage Volume",
  series_triple_signal: "Triple signal",
  metric_momentum_target: "Target Search Momentum",
  metric_acceleration_target: "Target Search Acceleration",
  metric_momentum_keywords: "Keyword Search Momentum",
  metric_acceleration_keywords: "Keyword Search Acceleration",
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
  if (type === "series_search_volume") return "series_keywords_search_volume";
  if (type === "metric_momentum") return "metric_momentum_keywords";
  if (type === "metric_acceleration") return "metric_acceleration_keywords";
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

const OVERLAY_TECH_BLOCK: WorkspaceChartType = "overlay_technical";

/**
 * Merge overlay series into the single `overlay_technical` block (deduped). Returns null if nothing to do or at block cap.
 */
export function mergeOverlaySeriesIntoWorkspace(
  blocks: WorkspaceChartBlock[],
  keysToAdd: string[]
): WorkspaceChartBlock[] | null {
  const sorted = sortOverlayKeys(keysToAdd);
  if (sorted.length === 0) return null;
  const idx = blocks.findIndex((b) => b.type === OVERLAY_TECH_BLOCK);
  if (idx >= 0) {
    const b = blocks[idx];
    const prev = new Set<string>(
      b.overlaySeries?.length ? [...b.overlaySeries] : ["price_close"]
    );
    for (const k of sorted) prev.add(k);
    const next = [...blocks];
    next[idx] = { ...b, overlaySeries: sortOverlayKeys(prev) };
    return next;
  }
  if (blocks.length >= MAX_WORKSPACE_CHARTS) return null;
  const id = newBlockId();
  return [
    ...blocks,
    {
      id,
      type: OVERLAY_TECH_BLOCK,
      title: WORKSPACE_CHART_DEFAULT_TITLES[OVERLAY_TECH_BLOCK],
      overlaySeries: sorted,
    },
  ];
}

/** Series already present on the overlay_technical block (for disabling checkboxes). */
export function getExistingOverlaySeriesKeys(blocks: WorkspaceChartBlock[]): Set<string> {
  const b = blocks.find((x) => x.type === OVERLAY_TECH_BLOCK);
  if (!b) return new Set();
  if (b.overlaySeries?.length) return new Set(b.overlaySeries);
  return new Set(["price_close"]);
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
      const migrated =
        rawType === "series_search_volume"
          ? "series_keywords_search_volume"
          : rawType === "metric_momentum"
            ? "metric_momentum_keywords"
            : rawType === "metric_acceleration"
              ? "metric_acceleration_keywords"
              : rawType;
      const type: WorkspaceChartType = isWorkspaceType(migrated)
        ? migrated
        : ("split_technical" as WorkspaceChartType);
      const id = typeof b.id === "string" && b.id.trim() ? b.id : newBlockId();
      const title = typeof b.title === "string" && b.title.trim() ? b.title.trim() : undefined;
      const overlayRaw = b.overlaySeries;
      const overlaySeries =
        Array.isArray(overlayRaw) && overlayRaw.length > 0
          ? sortOverlayKeys(overlayRaw.filter((x): x is string => typeof x === "string"))
          : undefined;
      blocks.push({
        id,
        type,
        title,
        ...(overlaySeries?.length ? { overlaySeries } : {}),
      });
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
      ...(b.overlaySeries?.length ? { overlaySeries: [...b.overlaySeries] } : {}),
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
