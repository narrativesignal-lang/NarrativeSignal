import { CHART_TYPES as RESEARCH_CHART_TYPES, type ChartType } from "./ResearchChart";

/** Research Universe / Scope for one tab: multiple instruments, terms, entity. */
export type TabSetup = {
  tab_title?: string;
  /** Multiple instruments in this tab's scope. */
  instruments?: Array<{ id: string; symbol: string }>;
  /** Legacy: single primary instrument (migrated into instruments). */
  primary_instrument_id?: string | null;
  primary_instrument_symbol?: string;
  entity_id?: string | null;
  entity_name?: string;
  keyword_group_id?: string | null;
  keyword_group_name?: string;
  related_instrument_ids?: string[];
  related_instrument_labels?: string[];
  terms?: string[];
  default_time_range?: string;
  notes?: string;
};

/** One block in the tab canvas. */
export type PanelConfig = {
  type: ChartType;
  /** overlay = overlay chart (multi-series); single = standalone; analysis = 2D/3D/relationship. */
  kind?: "overlay" | "single" | "analysis";
  /** When kind is overlay: multiple compatible series in one panel (persisted). */
  overlayTypes?: ChartType[];
};

/** One research tab: title, scope, blocks. */
export type ResearchTab = {
  id: string;
  title: string;
  setup: TabSetup;
  panels: PanelConfig[];
  /** Resizable height of the built-in instrument K-line zone (px). */
  chart_zone_height?: number;
};

export type LayoutConfig = {
  tabs?: ResearchTab[];
  active_tab_id?: string;
  /** Legacy: migrated into first tab. */
  panels?: PanelConfig[];
  setup?: TabSetup;
};

function isChartType(s: string): s is ChartType {
  return (RESEARCH_CHART_TYPES as readonly string[]).includes(s);
}

function isPanelConfig(x: unknown): x is PanelConfig {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  const type = o.type;
  if (typeof type !== "string" || !isChartType(type)) return false;
  if (o.kind !== undefined && !["overlay", "single", "analysis"].includes(String(o.kind))) return false;
  if (o.overlayTypes !== undefined) {
    if (!Array.isArray(o.overlayTypes)) return false;
    for (const t of o.overlayTypes) {
      if (typeof t !== "string" || !isChartType(t)) return false;
    }
  }
  return true;
}

const MAX_PANELS_PER_TAB = 5;

export function parseTabSetup(raw: unknown): TabSetup {
  if (!raw || typeof raw !== "object") return {};
  const o = raw as Record<string, unknown>;
  const instruments: Array<{ id: string; symbol: string }> = [];
  if (Array.isArray(o.instruments)) {
    for (const item of o.instruments) {
      if (item && typeof item === "object" && typeof (item as any).id === "string" && typeof (item as any).symbol === "string") {
        instruments.push({ id: (item as any).id, symbol: (item as any).symbol });
      }
    }
  }
  return {
    tab_title: typeof o.tab_title === "string" ? o.tab_title : undefined,
    instruments: instruments.length ? instruments : undefined,
    primary_instrument_id: o.primary_instrument_id != null ? String(o.primary_instrument_id) : undefined,
    primary_instrument_symbol: typeof o.primary_instrument_symbol === "string" ? o.primary_instrument_symbol : undefined,
    entity_id: o.entity_id != null ? String(o.entity_id) : undefined,
    entity_name: typeof o.entity_name === "string" ? o.entity_name : undefined,
    keyword_group_id: o.keyword_group_id != null ? String(o.keyword_group_id) : undefined,
    keyword_group_name: typeof o.keyword_group_name === "string" ? o.keyword_group_name : undefined,
    related_instrument_ids: Array.isArray(o.related_instrument_ids) ? o.related_instrument_ids.map(String) : undefined,
    related_instrument_labels: Array.isArray(o.related_instrument_labels) ? o.related_instrument_labels.map(String) : undefined,
    terms: Array.isArray(o.terms) ? o.terms.filter((t): t is string => typeof t === "string") : undefined,
    default_time_range: typeof o.default_time_range === "string" ? o.default_time_range : undefined,
    notes: typeof o.notes === "string" ? o.notes : undefined,
  };
}

export function parsePanels(raw: unknown): PanelConfig[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(isPanelConfig).slice(0, MAX_PANELS_PER_TAB);
}

export function getTabsFromLayoutConfig(config: Record<string, unknown>): { tabs: ResearchTab[]; active_tab_id: string } {
  const tabs = config?.tabs;
  if (Array.isArray(tabs) && tabs.length > 0) {
    const list: ResearchTab[] = [];
    for (const t of tabs) {
      if (!t || typeof t !== "object") continue;
      const o = t as Record<string, unknown>;
      const id = typeof o.id === "string" ? o.id : crypto.randomUUID();
      const title = typeof o.title === "string" ? o.title : "Untitled";
      const setup = parseTabSetup(o.setup);
      const panels = parsePanels(o.panels);
      const chart_zone_height = typeof o.chart_zone_height === "number" && o.chart_zone_height > 0 ? o.chart_zone_height : undefined;
      list.push({ id, title, setup, panels, chart_zone_height });
    }
    if (list.length === 0) {
      return migrateLegacyToTabs(config);
    }
    const active = typeof config.active_tab_id === "string" && list.some((tab) => tab.id === config.active_tab_id)
      ? config.active_tab_id
      : list[0].id;
    return { tabs: list, active_tab_id: active };
  }
  return migrateLegacyToTabs(config);
}

function migrateLegacyToTabs(config: Record<string, unknown>): { tabs: ResearchTab[]; active_tab_id: string } {
  const legacyPanels = parsePanels(config?.panels);
  const legacySetup = parseTabSetup(config?.setup);
  const instruments = legacySetup.instruments?.length
    ? legacySetup.instruments
    : legacySetup.primary_instrument_id && legacySetup.primary_instrument_symbol
      ? [{ id: legacySetup.primary_instrument_id, symbol: legacySetup.primary_instrument_symbol }]
      : undefined;
  const setup: TabSetup = {
    ...legacySetup,
    instruments,
  };
  const tab: ResearchTab = {
    id: crypto.randomUUID(),
    title: legacySetup.tab_title ?? "Research",
    setup,
    panels: legacyPanels.map((p) => ({ ...p, kind: p.kind ?? (p.type === "three_d" ? "analysis" : "single") })),
    chart_zone_height: undefined,
  };
  return { tabs: [tab], active_tab_id: tab.id };
}

/** Instruments list for display: from setup.instruments or legacy primary. */
export function getInstrumentsList(setup: TabSetup | null | undefined): Array<{ id: string; symbol: string }> {
  if (!setup) return [];
  if (Array.isArray(setup.instruments) && setup.instruments.length > 0) return setup.instruments;
  if (setup.primary_instrument_id && setup.primary_instrument_symbol)
    return [{ id: setup.primary_instrument_id, symbol: setup.primary_instrument_symbol }];
  return [];
}

export function hasResearchTarget(setup: TabSetup | null | undefined): boolean {
  if (!setup) return false;
  const hasInstruments = Array.isArray(setup.instruments) && setup.instruments.length > 0;
  const hasPrimary = !!(setup.primary_instrument_id ?? setup.primary_instrument_symbol);
  const hasEntity = !!(setup.entity_id ?? setup.entity_name);
  const hasTerms = Array.isArray(setup.terms) && setup.terms.length > 0;
  return hasInstruments || hasPrimary || hasEntity || hasTerms;
}
