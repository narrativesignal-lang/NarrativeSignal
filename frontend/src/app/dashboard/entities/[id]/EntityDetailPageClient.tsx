"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { SlowLoadBanner, useSlowLoadVisible } from "@/components/SlowLoadBanner";
import { api, instrumentSearchNeedsResolve, parseApiError, toInstrumentBindResolve } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
import { STALE_MARKET_MS } from "@/lib/queryClient";
import { CandleChart } from "@/components/CandleChart";
import { normalizeOhlcvBars, type CandleBar } from "@/lib/ohlcvBars";
import {
  ResizableChartSection,
  RESIZE_DEFAULT_HEIGHT,
  RESIZE_MIN_HEIGHT,
  RESIZE_MAX_HEIGHT,
  RESIZE_HANDLE_HEIGHT,
} from "@/components/ResizableChartSection";
import { FREE_PLAN_LIMITS } from "@/lib/limits";
import {
  addWorkspaceChart,
  buildChartLayoutPayload,
  MAX_WORKSPACE_CHARTS,
  parseWorkspaceChartLayout,
  removeWorkspaceChart,
  type WorkspaceChartBlock,
  type WorkspaceChartType,
} from "@/lib/entityWorkspaceCharts";
import { EntityAddBlockModal } from "@/components/entity/EntityAddBlockModal";
import {
  EntityWorkspaceChartCard,
  EntityWorkspaceChartPlaceholder,
  EntityAnalysisComingUpPlaceholder,
} from "@/components/entity/EntityWorkspaceChartCard";
import { EntityQuadrantBlock } from "@/components/entity/EntityQuadrantBlock";
import { EntitySeriesVolumeBlock } from "@/components/entity/EntitySeriesVolumeBlock";
import { EntityMetricDerivedBlock } from "@/components/entity/EntityMetricDerivedBlock";
import { TripleSignalChartBlock } from "@/components/entity/TripleSignalChartBlock";
import { EntityInstitutionBiasBlock } from "@/components/entity/EntityInstitutionBiasBlock";
import { EntityRatingDistributionBlock } from "@/components/entity/EntityRatingDistributionBlock";
import { WorkspaceChartErrorBoundary } from "@/components/entity/WorkspaceChartErrorBoundary";
import { SectionHelp } from "@/components/SectionHelp";
import { EntityEventTimeline } from "@/components/entity/EntityEventTimeline";
import { EntityNewsPanel } from "@/components/entity/EntityNewsPanel";
import { DEFAULT_ANALYSIS_PERIOD, isValidAnalysisPeriod } from "@/lib/analysisPeriods";
import type { ChartVisibleTimeRange } from "@/lib/chartTimeUnix";
import { INSTRUMENT_CATEGORIES } from "@/lib/instrumentCategories";

type PortfolioInstrumentSearchHit = Awaited<ReturnType<typeof api.searchInstruments>>[number];

function Loading3DPlaceholder() {
  const { t } = useI18n();
  return (
    <div className="flex h-full min-h-[140px] items-center justify-center bg-slate-950 text-xs text-slate-500">
      {t("entity.loading3D")}
    </div>
  );
}

const EntityWorkspace3DChart = dynamic(
  () => import("@/components/entity/EntityWorkspace3DChart").then((m) => m.EntityWorkspace3DChart),
  {
    ssr: false,
    loading: () => <Loading3DPlaceholder />,
  }
);

const EntityOverlayChart = dynamic(
  () => import("@/components/entity/EntityOverlayChart").then((m) => m.EntityOverlayChart),
  { ssr: false }
);
const EntityOverlaySentimentChart = dynamic(
  () => import("@/components/entity/EntityOverlaySentimentChart").then((m) => m.EntityOverlaySentimentChart),
  { ssr: false }
);
const EntitySplitChart = dynamic(
  () => import("@/components/entity/EntitySplitChart").then((m) => m.EntitySplitChart),
  { ssr: false }
);
const EntitySplitSentimentChart = dynamic(
  () => import("@/components/entity/EntitySplitSentimentChart").then((m) => m.EntitySplitSentimentChart),
  { ssr: false }
);

type EntityDetail = Awaited<ReturnType<typeof api.getEntity>>;
type RelatedInstrument = Awaited<ReturnType<typeof api.getEntityRelatedInstruments>>[number];

const PERIODS = ["1D", "5D", "1M", "6M", "1Y", "MAX"] as const;

const MAX_ITEMS_PER_ENTITY = FREE_PLAN_LIMITS.MAX_ITEMS_PER_ENTITY;
const MAX_COMPARISON = 4;
/** Compare stack: up to this many rows high before only scrolling (not growing the section). */
const MAX_COMPARE_VISIBLE_ROWS = 3;
const COMPARE_ROW_CANDLE_HEIGHT = 220;
/** Per-row chrome: card padding, symbol label, Events & news header + strip */
const COMPARE_ROW_BLOCK_CHROME = 104;
const COMPARE_ROW_GAP_PX = 12;
const COMPARE_ROW_BLOCK_HEIGHT = COMPARE_ROW_CANDLE_HEIGHT + COMPARE_ROW_BLOCK_CHROME;
const COMPARE_SECTION_MAX_HEIGHT = 1100;

export default function EntityDetailPageClient({ entityId }: { entityId: string }) {
  const { t } = useI18n();
  const { user: authUser, loading: userLoading } = useUser();
  const isAdminUser = Boolean(authUser?.is_admin);
  const id = entityId;
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [terms, setTerms] = useState<string[]>([]);
  const [termInput, setTermInput] = useState("");
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("1M");
  const [newsPending, setNewsPending] = useState(false);
  const [workspaceCharts, setWorkspaceCharts] = useState<WorkspaceChartBlock[]>([]);
  const [workspaceBlockHeights, setWorkspaceBlockHeights] = useState<Record<string, number>>({});
  const [addChartModalOpen, setAddChartModalOpen] = useState(false);
  const [chartPersistError, setChartPersistError] = useState<string | null>(null);
  const [chartSavePending, setChartSavePending] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiIdea, setAiIdea] = useState("");
  const [aiKeywords, setAiKeywords] = useState<string[]>([]);
  const [aiKeywordError, setAiKeywordError] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [saveTermsBusy, setSaveTermsBusy] = useState(false);
  const [addRelatedBusy, setAddRelatedBusy] = useState(false);

  const [relatedInstruments, setRelatedInstruments] = useState<RelatedInstrument[]>([]);
  const [relatedQuotes, setRelatedQuotes] = useState<Record<string, { price: number | null; change_percent: number | null }>>({});
  const [addRelatedOpen, setAddRelatedOpen] = useState(false);
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [instrumentCategory, setInstrumentCategory] = useState("");
  const [instrumentResults, setInstrumentResults] = useState<PortfolioInstrumentSearchHit[]>([]);
  const [comparisonPeriod, setComparisonPeriod] = useState<(typeof PERIODS)[number]>("1M");
  const [comparisonInstrumentIds, setComparisonInstrumentIds] = useState<string[]>([]);
  const [comparisonCandles, setComparisonCandles] = useState<Array<{ symbol: string; bars: CandleBar[] }>>([]);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [compareAllowFetch, setCompareAllowFetch] = useState(false);
  const [removeItemConfirm, setRemoveItemConfirm] = useState<{
    relatedId: string;
    instrumentId: string;
    symbol: string;
  } | null>(null);
  const [removeItemLoading, setRemoveItemLoading] = useState(false);
  const [bindInstrumentOpen, setBindInstrumentOpen] = useState(false);
  const [bindInstrumentQuery, setBindInstrumentQuery] = useState("");
  const [bindInstrumentType, setBindInstrumentType] = useState<"all" | "equity" | "etf" | "futures" | "crypto" | "index" | "hk">("all");
  const [bindInstrumentResults, setBindInstrumentResults] = useState<PortfolioInstrumentSearchHit[]>([]);
  const [bindInstrumentLoading, setBindInstrumentLoading] = useState(false);

  const [priceSectionHeight, setPriceSectionHeight] = useState(RESIZE_DEFAULT_HEIGHT);
  const [compareSectionHeight, setCompareSectionHeight] = useState(RESIZE_DEFAULT_HEIGHT);
  const [mainChartVisibleRange, setMainChartVisibleRange] = useState<ChartVisibleTimeRange | null>(null);
  const [compareChartVisibleRange, setCompareChartVisibleRange] = useState<
    Record<string, ChartVisibleTimeRange | null>
  >({});
  const [removeWorkspaceChartId, setRemoveWorkspaceChartId] = useState<string | null>(null);
  const layoutRestoredRef = useRef(false);
  const skipNextChartPersistRef = useRef(false);
  const leftColRef = useRef<HTMLDivElement>(null);
  const priceSectionRef = useRef<HTMLElement>(null);
  const [newsPanelHeight, setNewsPanelHeight] = useState(360);

  const [narrativeFlowPeriod, setNarrativeFlowPeriod] = useState<string>(DEFAULT_ANALYSIS_PERIOD);
  const [trendingData, setTrendingData] = useState<{
    search_momentum: number;
    coverage_momentum: number;
    sentiment_change: number;
    trend_label: string;
  } | null>(null);

  const ENTITY_LOAD_TIMEOUT_MS = 15000;

  const ohlcvQuery = useQuery({
    queryKey: ["market", "timeseries", entity?.instrument?.symbol ?? "", period],
    queryFn: async () => {
      const sym = entity!.instrument!.symbol;
      const res = await api.marketTimeSeries(sym, period);
      return {
        symbol: res.symbol,
        period: res.period,
        bars: normalizeOhlcvBars(res.bars || []),
      };
    },
    enabled: Boolean(entity?.instrument?.symbol),
    staleTime: STALE_MARKET_MS,
    placeholderData: (previousData) => previousData,
  });
  const ohlcv = ohlcvQuery.data ?? null;
  const ohlcvLoading = ohlcvQuery.isPending && !ohlcvQuery.data;
  const ohlcvLoaded = !entity?.instrument?.symbol || ohlcvQuery.isFetched;

  const entityShellLoading = !entity && !error;
  const pageSlowPending =
    entityShellLoading ||
    (!!entity &&
      (newsPending ||
        (!!entity.instrument?.symbol && ohlcvQuery.isPending && !ohlcvQuery.data) ||
        (compareAllowFetch && comparisonLoading)));
  const showPageSlowBanner = useSlowLoadVisible(pageSlowPending);

  const recalcNewsHeight = useCallback(() => {
    const col = leftColRef.current;
    const price = priceSectionRef.current;
    if (!col || !price) return;
    const top = col.getBoundingClientRect().top;
    const bottom = price.getBoundingClientRect().bottom;
    const h = bottom - top;
    if (h > 120) setNewsPanelHeight(Math.round(h));
  }, []);

  useEffect(() => {
    recalcNewsHeight();
    const ro = new ResizeObserver(() => recalcNewsHeight());
    if (leftColRef.current) ro.observe(leftColRef.current);
    if (priceSectionRef.current) ro.observe(priceSectionRef.current);
    window.addEventListener("resize", recalcNewsHeight);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", recalcNewsHeight);
    };
  }, [recalcNewsHeight, entity?.id, priceSectionHeight, ohlcvLoaded, ohlcv?.bars?.length]);

  const applyLoadedEntity = useCallback((e: EntityDetail) => {
    skipNextChartPersistRef.current = true;
    setEntity(e);
    setTerms((e.terms ?? []).map((t) => t.term));
    const parsed = parseWorkspaceChartLayout(e.chart_layout);
    setWorkspaceCharts(parsed.blocks);
    setWorkspaceBlockHeights(parsed.heights);
    const period = parsed.narrativeFlowPeriod ?? "";
    setNarrativeFlowPeriod(typeof period === "string" && isValidAnalysisPeriod(period) ? period : DEFAULT_ANALYSIS_PERIOD);
    setChartPersistError(null);
    layoutRestoredRef.current = true;
  }, []);

  /** Refetch without clearing the page (retry / after save). */
  const loadEntity = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error(t("entity.requestTimeout"))), ENTITY_LOAD_TIMEOUT_MS)
      );
      const e = await Promise.race([api.getEntity(id), timeoutPromise]);
      applyLoadedEntity(e);
      api.getEntityTrending(id).then(setTrendingData).catch(() => setTrendingData(null));
    } catch (e: unknown) {
      setError(parseApiError(e));
      layoutRestoredRef.current = false;
    }
  }, [id, applyLoadedEntity, t]);

  /** Route change or hard refresh: reset so we never show the wrong entity or PATCH wrong charts. */
  useEffect(() => {
    if (!id) return;
    setEntity(null);
    setError(null);
    setTerms([]);
    setWorkspaceCharts([]);
    setWorkspaceBlockHeights({});
    setChartPersistError(null);
    layoutRestoredRef.current = false;
    skipNextChartPersistRef.current = true;
    setTrendingData(null);
    setComparisonCandles([]);
    setComparisonLoading(false);

    let cancelled = false;
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(t("entity.requestTimeout"))), ENTITY_LOAD_TIMEOUT_MS)
    );

    void (async () => {
      try {
        const e = await Promise.race([api.getEntity(id), timeoutPromise]);
        if (cancelled) return;
        applyLoadedEntity(e);
        api
          .getEntityTrending(id)
          .then((t) => {
            if (!cancelled) setTrendingData(t);
          })
          .catch(() => {
            if (!cancelled) setTrendingData(null);
          });
      } catch (e: unknown) {
        if (cancelled) return;
        setError(parseApiError(e));
        layoutRestoredRef.current = false;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, applyLoadedEntity, t]);

  useEffect(() => {
    if (!id || !entity || !layoutRestoredRef.current) return;
    if (skipNextChartPersistRef.current) {
      skipNextChartPersistRef.current = false;
      return;
    }
    const t = setTimeout(() => {
      setChartSavePending(true);
      setChartPersistError(null);
      api
        .updateEntity(id, {
          chart_layout: buildChartLayoutPayload(workspaceCharts, workspaceBlockHeights, narrativeFlowPeriod),
        })
        .then((updated) => {
          setEntity((prev) => (prev && prev.id === updated.id ? { ...prev, chart_layout: updated.chart_layout } : prev));
        })
        .catch((err: unknown) => {
          setChartPersistError((err as { message?: string })?.message ?? "Failed to save charts");
        })
        .finally(() => setChartSavePending(false));
    }, 500);
    return () => clearTimeout(t);
  }, [id, entity?.id, workspaceCharts, workspaceBlockHeights, narrativeFlowPeriod]);

  useEffect(() => {
    setMainChartVisibleRange(null);
  }, [period, entity?.instrument?.symbol]);

  useEffect(() => {
    setCompareChartVisibleRange({});
  }, [comparisonPeriod, comparisonInstrumentIds.join(",")]);

  const loadRelatedInstruments = useCallback(async () => {
    if (!id) return;
    try {
      const list = await api.getEntityRelatedInstruments(id);
      setRelatedInstruments(list);
    } catch {
      setRelatedInstruments([]);
    }
  }, [id]);

  useEffect(() => {
    loadRelatedInstruments();
  }, [loadRelatedInstruments]);

  useEffect(() => {
    if (!entity?.id) {
      setCompareAllowFetch(false);
      return;
    }
    setCompareAllowFetch(false);
    let cancelled = false;
    const handle = () => {
      if (!cancelled) setCompareAllowFetch(true);
    };
    let idleId = 0;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    if (typeof window !== "undefined" && "requestIdleCallback" in window) {
      idleId = window.requestIdleCallback(handle, { timeout: 2000 });
    } else {
      timeoutId = setTimeout(handle, 600);
    }
    return () => {
      cancelled = true;
      if (typeof window !== "undefined" && "cancelIdleCallback" in window && idleId) {
        window.cancelIdleCallback(idleId);
      }
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [entity?.id]);

  useEffect(() => {
    if (entity?.instrument?.id && comparisonInstrumentIds.length === 0) {
      setComparisonInstrumentIds([entity.instrument.id]);
    }
  }, [entity?.instrument?.id]);

  useEffect(() => {
    if (!relatedInstruments.length) {
      setRelatedQuotes({});
      return;
    }
    const syms = relatedInstruments.map((r) => r.symbol);
    Promise.all(syms.map((sym) => api.quote(sym).catch(() => ({ symbol: sym, price: null, change_percent: null }))))
      .then((results) => {
        const next: Record<string, { price: number | null; change_percent: number | null }> = {};
        results.forEach((r, i) => {
          const sym = syms[i];
          if (sym) next[sym] = { price: r.price ?? null, change_percent: r.change_percent ?? null };
        });
        setRelatedQuotes(next);
      });
  }, [relatedInstruments]);

  useEffect(() => {
    if (!instrumentQuery.trim()) {
      setInstrumentResults([]);
      return;
    }
    const t = setTimeout(() => {
      const category = instrumentCategory || undefined;
      api
        .searchInstruments(instrumentQuery.trim(), undefined, undefined, category)
        .then(setInstrumentResults)
        .catch(() => setInstrumentResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [instrumentQuery, instrumentCategory]);

  useEffect(() => {
    const q = bindInstrumentQuery.trim();
    if (!bindInstrumentOpen || q.length < 1) {
      setBindInstrumentResults([]);
      return;
    }
    const assetClass = bindInstrumentType === "all" || bindInstrumentType === "hk" ? undefined : bindInstrumentType;
    const category = bindInstrumentType === "hk" ? "hong kong" : undefined;
    const t = setTimeout(() => {
      api
        .searchInstruments(q, assetClass, undefined, category)
        .then(setBindInstrumentResults)
        .catch(() => setBindInstrumentResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [bindInstrumentOpen, bindInstrumentQuery, bindInstrumentType]);

  const addRelatedInstrument = useCallback(
    async (hit: PortfolioInstrumentSearchHit) => {
      if (!id) return;
      setAddRelatedBusy(true);
      setError(null);
      try {
        await api.addEntityRelatedInstrument(id, {
          instrument_id: hit.id,
          ...(instrumentSearchNeedsResolve(hit) ? { instrument_resolve: toInstrumentBindResolve(hit) } : {}),
        });
        setAddRelatedOpen(false);
        setInstrumentQuery("");
        setInstrumentResults([]);
        loadRelatedInstruments();
      } catch (e: unknown) {
        setError(parseApiError(e) || "Failed to add related instrument");
      } finally {
        setAddRelatedBusy(false);
      }
    },
    [id, loadRelatedInstruments]
  );

  const removeRelatedInstrument = useCallback(
    async (relatedId: string, instrumentId: string) => {
      if (!id) return;
      setError(null);
      try {
        await api.deleteEntityRelatedInstrument(id, relatedId);
        loadRelatedInstruments();
        setComparisonInstrumentIds((prev) => prev.filter((x) => x !== instrumentId));
      } catch (e: unknown) {
        setError((e as { message?: string })?.message ?? "Failed to remove");
      }
    },
    [id, loadRelatedInstruments]
  );

  const openRemoveConfirm = useCallback(
    (r: RelatedInstrument) => {
      setRemoveItemConfirm({ relatedId: r.id, instrumentId: r.instrument_id, symbol: r.symbol });
    },
    []
  );

  const closeRemoveConfirm = useCallback(() => {
    setRemoveItemConfirm(null);
  }, []);

  const closeBindInstrument = useCallback(() => {
    setBindInstrumentOpen(false);
    setBindInstrumentQuery("");
    setBindInstrumentResults([]);
  }, []);

  const updateEntityInstrument = useCallback(
    async (hit: PortfolioInstrumentSearchHit | null) => {
      if (!id) return;
      setBindInstrumentLoading(true);
      setError(null);
      try {
        if (hit === null) {
          await api.updateEntity(id, { instrument_id: null });
        } else {
          await api.updateEntity(id, {
            instrument_id: hit.id,
            ...(instrumentSearchNeedsResolve(hit) ? { instrument_resolve: toInstrumentBindResolve(hit) } : {}),
          });
        }
        const e = await api.getEntity(id);
        setEntity(e);
        setTerms((e.terms ?? []).map((t) => t.term));
        setComparisonInstrumentIds(e.instrument ? [e.instrument.id] : []);
        closeBindInstrument();
      } catch (e: unknown) {
        setError(parseApiError(e) || "Failed to update instrument");
      } finally {
        setBindInstrumentLoading(false);
      }
    },
    [id, closeBindInstrument]
  );

  const handleBindInstrumentSelect = useCallback(
    (hit: PortfolioInstrumentSearchHit) => {
      void updateEntityInstrument(hit);
    },
    [updateEntityInstrument]
  );

  const handleClearInstrument = useCallback(async () => {
    if (!id || !entity?.instrument) return;
    if (typeof window !== "undefined" && !window.confirm(t("entity.confirmClearInstrument"))) return;
    await updateEntityInstrument(null);
  }, [id, entity?.instrument, updateEntityInstrument, t]);

  const performRemoveItem = useCallback(async () => {
    if (!id || !removeItemConfirm) return;
    setRemoveItemLoading(true);
    setError(null);
    try {
      await api.deleteEntityRelatedInstrument(id, removeItemConfirm.relatedId);
      setComparisonInstrumentIds((prev) => prev.filter((x) => x !== removeItemConfirm.instrumentId));
      setRemoveItemConfirm(null);
      await loadRelatedInstruments();
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to remove");
    } finally {
      setRemoveItemLoading(false);
    }
  }, [id, removeItemConfirm, loadRelatedInstruments]);

  const allComparisonOptions = useMemo(() => {
    const out: Array<{ instrumentId: string; symbol: string; label: string }> = [];
    if (entity?.instrument?.id) {
      out.push({
        instrumentId: entity.instrument.id,
        symbol: entity.instrument.symbol,
        label: `${entity.instrument.symbol} (${t("entity.primaryInstrumentTag")})`,
      });
    }
    relatedInstruments.forEach((r) => {
      out.push({
        instrumentId: r.instrument_id,
        symbol: r.symbol,
        label: r.symbol,
      });
    });
    return out;
  }, [entity?.instrument, relatedInstruments, t]);

  const loadComparisonOhlcv = useCallback(async () => {
    if (comparisonInstrumentIds.length === 0) {
      setComparisonCandles([]);
      setComparisonLoading(false);
      return;
    }
    setComparisonLoading(true);
    try {
      const idToSymbol = new Map(allComparisonOptions.map((o) => [o.instrumentId, o.symbol]));
      const symbols = comparisonInstrumentIds
        .map((iid) => idToSymbol.get(iid))
        .filter((s): s is string => Boolean(s));
      const results = await Promise.all(
        symbols.map(async (symbol) => {
          try {
            const res = await api.marketTimeSeries(symbol, comparisonPeriod);
            return { symbol, bars: normalizeOhlcvBars(res?.bars ?? []) };
          } catch {
            return { symbol, bars: [] as CandleBar[] };
          }
        })
      );
      setComparisonCandles(results);
    } catch {
      setComparisonCandles([]);
    } finally {
      setComparisonLoading(false);
    }
  }, [comparisonInstrumentIds, comparisonPeriod, allComparisonOptions]);

  useEffect(() => {
    if (!compareAllowFetch) return;
    void loadComparisonOhlcv();
  }, [compareAllowFetch, comparisonInstrumentIds.join(","), comparisonPeriod, loadComparisonOhlcv]);

  /** Grow compare panel height with 1→3 symbols; cap at three row-heights so a 4th uses the scrollbar. */
  useEffect(() => {
    const n = comparisonInstrumentIds.length;
    if (n === 0) {
      setCompareSectionHeight(RESIZE_DEFAULT_HEIGHT);
      return;
    }
    const capped = Math.min(n, MAX_COMPARE_VISIBLE_ROWS);
    const inner =
      capped * COMPARE_ROW_BLOCK_HEIGHT + (capped > 1 ? (capped - 1) * COMPARE_ROW_GAP_PX : 0);
    const next = Math.min(
      COMPARE_SECTION_MAX_HEIGHT,
      Math.max(RESIZE_MIN_HEIGHT, inner + RESIZE_HANDLE_HEIGHT + 4)
    );
    setCompareSectionHeight(next);
  }, [comparisonInstrumentIds.join(",")]);

  const toggleComparisonInstrument = useCallback((instrumentId: string) => {
    setComparisonInstrumentIds((prev) => {
      if (prev.includes(instrumentId)) return prev.filter((x) => x !== instrumentId);
      if (prev.length >= MAX_COMPARISON) return prev;
      return [...prev, instrumentId];
    });
  }, []);

  const addTerm = useCallback((t: string) => {
    const v = t.trim().toLowerCase();
    if (!v) return;
    setTerms((prev) => (prev.includes(v) ? prev : [...prev, v].slice(0, 15)));
  }, []);

  const removeTerm = useCallback((t: string) => setTerms((prev) => prev.filter((x) => x !== t)), []);

  const saveTerms = useCallback(async () => {
    if (!entity) return;
    setSaveTermsBusy(true);
    setError(null);
    try {
      await api.replaceEntityTerms(entity.id, terms);
      loadEntity();
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? "Failed to save terms");
    } finally {
      setSaveTermsBusy(false);
    }
  }, [entity, terms, loadEntity]);

  const handleAiSuggest = useCallback(async () => {
    setAiLoading(true);
    setAiKeywords([]);
    setAiKeywordError(null);
    try {
      const res = await api.aiKeywordSuggestions({
        idea: aiIdea.trim(),
        instrument: entity?.instrument?.symbol ?? undefined,
        asset_class: entity?.instrument?.asset_class ?? undefined,
        portfolio: entity?.portfolio_name ?? undefined,
      });
      if (res.disabled) {
        setAiKeywordError("AI keyword suggestions are temporarily disabled.");
        setAiKeywords([]);
        return;
      }
      setAiKeywords((res.keywords ?? []).slice(0, 8));
    } catch (e: unknown) {
      setAiKeywordError(parseApiError(e));
    } finally {
      setAiLoading(false);
    }
  }, [aiIdea, entity]);

  const pickWorkspaceBlockType = useCallback((type: WorkspaceChartType) => {
    setWorkspaceCharts((prev) => {
      if (prev.length >= MAX_WORKSPACE_CHARTS) return prev;
      const next = addWorkspaceChart(prev, type);
      const added = next[next.length - 1];
      if (added) {
        setWorkspaceBlockHeights((h) => ({ ...h, [added.id]: RESIZE_DEFAULT_HEIGHT }));
      }
      return next;
    });
    setAddChartModalOpen(false);
  }, []);

  const confirmRemoveWorkspaceChart = useCallback(() => {
    if (!removeWorkspaceChartId) return;
    const rid = removeWorkspaceChartId;
    setWorkspaceCharts((prev) => removeWorkspaceChart(prev, rid));
    setWorkspaceBlockHeights((prev) => {
      const next = { ...prev };
      delete next[rid];
      return next;
    });
    setRemoveWorkspaceChartId(null);
  }, [removeWorkspaceChartId]);

  if (!id) {
    return (
      <Shell>
        <div className="text-slate-400">Invalid entity id.</div>
      </Shell>
    );
  }

  if (error && !entity) {
    return (
      <Shell>
        <div className="rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-amber-200">{error}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => loadEntity()}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-600"
          >
            Retry
          </button>
          <Link href="/dashboard?tab=entity" className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700">
            ← Back to Dashboard
          </Link>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="space-y-6">
        <SlowLoadBanner visible={showPageSlowBanner} />
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Link href="/dashboard?tab=entity" className="hover:text-slate-200">
            {t("nav.dashboard")}
          </Link>
          <span>/</span>
          <Link href="/dashboard?tab=entity" className="hover:text-slate-200">
            {t("dashboard.entityData")}
          </Link>
          <span>/</span>
          <span className="text-slate-200">{entity?.name ?? t("entity.loadingEntity")}</span>
        </div>

        {/* Header */}
        <header className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          {!entity ? (
            <div className="animate-pulse space-y-3" aria-hidden>
              <div className="h-6 w-56 max-w-full rounded-md bg-slate-800/90" />
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="h-4 max-w-xs rounded bg-slate-800/70" />
                <div className="h-4 max-w-xs rounded bg-slate-800/70" />
                <div className="h-4 max-w-xs rounded bg-slate-800/50" />
              </div>
            </div>
          ) : (
            <>
              <h1 className="text-lg font-semibold text-slate-100">{entity.name}</h1>
              <div className="mt-2 grid gap-1 text-sm text-slate-400 sm:grid-cols-2">
                <div>
                  <span className="text-slate-500">{t("entity.portfolio")}:</span> {entity.portfolio_name}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-slate-500">{t("entity.instrument")}:</span>
                  {entity.instrument ? (
                    <>
                      <span className="text-slate-200">
                        {entity.instrument.symbol}
                        {entity.instrument.display_name ? ` · ${entity.instrument.display_name}` : ""}
                      </span>
                      <span className="text-slate-500">·</span>
                      <button
                        type="button"
                        onClick={() => {
                          setBindInstrumentQuery("");
                          setBindInstrumentResults([]);
                          setBindInstrumentOpen(true);
                        }}
                        className="text-xs text-indigo-300 hover:text-indigo-200"
                      >
                        {t("entity.changeInstrument")}
                      </button>
                      <button
                        type="button"
                        onClick={handleClearInstrument}
                        className="text-xs text-slate-500 hover:text-red-300"
                      >
                        {t("entity.clearInstrument")}
                      </button>
                    </>
                  ) : (
                    <>
                      <span className="text-slate-500">{t("entity.noInstrumentBound")}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setBindInstrumentQuery("");
                          setBindInstrumentResults([]);
                          setBindInstrumentOpen(true);
                        }}
                        className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-500"
                      >
                        {t("entity.bindInstrument")}
                      </button>
                    </>
                  )}
                </div>
                <div>
                  <span className="text-slate-500">{t("entity.assetType")}:</span>{" "}
                  {entity.instrument?.asset_class ?? "—"}
                </div>
                {trendingData ? (
                  <div className="mt-2 flex items-center gap-2 rounded border border-slate-700 bg-slate-800/40 px-3 py-1.5">
                    <span className="text-xs text-slate-500">{t("entity.trend")}:</span>
                    <span
                      className={`text-sm font-medium ${
                        trendingData.trend_label === "Rising"
                          ? "text-emerald-400"
                          : trendingData.trend_label === "Fading"
                            ? "text-amber-400"
                            : trendingData.trend_label === "Spike"
                              ? "text-indigo-400"
                              : "text-slate-400"
                      }`}
                    >
                      {trendingData.trend_label}
                    </span>
                  </div>
                ) : null}
              </div>
            </>
          )}
        </header>

        {error ? (
          <div className="rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
            {error}
          </div>
        ) : null}

        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)] lg:items-start">
        <div ref={leftColRef} className="min-w-0 space-y-6">
        {entity ? (
          <>
        {/* Terms */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-slate-200">{t("entity.terms")}</h2>
              <SectionHelp titleKey="help.entityTermsTitle" bodyKey="help.entityTermsBody" />
            </div>
            <div className="flex gap-2">
              {userLoading ? null : isAdminUser ? (
                <button
                  type="button"
                  onClick={() => {
                    setAiOpen(true);
                    setAiIdea("");
                    setAiKeywords([]);
                    setAiKeywordError(null);
                  }}
                  className="text-xs text-indigo-300 hover:text-indigo-200"
                >
                  {t("entity.aiSuggestion")}
                </button>
              ) : (
                <span className="text-xs text-slate-500">{t("entity.aiAdminOnlyShort")}</span>
              )}
              <button
                type="button"
                onClick={saveTerms}
                disabled={saveTermsBusy}
                className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-600 disabled:opacity-60"
              >
                {saveTermsBusy ? t("common.loading") : t("entity.saveTerms")}
              </button>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            Newly added targets/terms may need up to a few hours before trend/history metrics fully appear.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5 rounded border border-slate-700 bg-slate-950 p-2">
            {terms.map((term) => (
              <span key={term} className="inline-flex items-center gap-1 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                {term}
                <button type="button" onClick={() => removeTerm(term)} className="hover:text-red-300" aria-label={t("common.remove")}>×</button>
              </span>
            ))}
            <input
              className="min-w-[80px] flex-1 bg-transparent px-1 py-0.5 text-sm text-slate-100 outline-none"
              placeholder={t("entity.addTermPlaceholder")}
              value={termInput}
              onChange={(e) => setTermInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addTerm(termInput);
                  setTermInput("");
                }
              }}
            />
          </div>
        </section>

        {/* Price chart */}
        <section ref={priceSectionRef} className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-slate-200">{t("entity.price")}</h2>
              <SectionHelp titleKey="help.entityPriceTitle" bodyKey="help.entityPriceBody" />
            </div>
            <div className="flex gap-1">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  className={`rounded px-2 py-1 text-xs ${period === p ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"}`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-3">
            <ResizableChartSection
              height={priceSectionHeight}
              onHeightChange={setPriceSectionHeight}
              minHeight={RESIZE_MIN_HEIGHT}
              maxHeight={RESIZE_MAX_HEIGHT}
            >
              {ohlcv?.bars?.length ? (
                <CandleChart
                  bars={ohlcv.bars}
                  height={priceSectionHeight - RESIZE_HANDLE_HEIGHT}
                  onVisibleTimeRangeChange={setMainChartVisibleRange}
                />
              ) : (
                <div className="flex h-full min-h-[200px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
                  {!entity.instrument
                    ? t("entity.noInstrument")
                    : ohlcvLoading
                      ? t("entity.loadingPrice")
                      : ohlcvLoaded
                        ? t("entity.noCachedPrice")
                        : t("entity.waitingPrice")}
                </div>
              )}
            </ResizableChartSection>
            {entity.instrument?.symbol ? (
              <EntityEventTimeline
                entityId={id}
                symbol={entity.instrument.symbol}
                period={period}
                chartScope="main"
                bars={ohlcv?.bars ?? []}
                visibleTimeRange={mainChartVisibleRange}
              />
            ) : null}
          </div>
        </section>

        {/* Related Market Data */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-slate-200">{t("entity.relatedMarketData")}</h2>
              <SectionHelp titleKey="help.entityRelatedMarketTitle" bodyKey="help.entityRelatedMarketBody" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">
                {t("entity.addedItems", { count: relatedInstruments.length, max: MAX_ITEMS_PER_ENTITY })}
              </span>
              <button
                type="button"
                onClick={() => setAddRelatedOpen(true)}
                disabled={relatedInstruments.length >= MAX_ITEMS_PER_ENTITY || addRelatedBusy}
                title={relatedInstruments.length >= MAX_ITEMS_PER_ENTITY ? t("entity.perEntityHint", { max: MAX_ITEMS_PER_ENTITY }) : undefined}
                className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {addRelatedBusy ? t("common.loading") : t("entity.addRelatedInstrument")}
              </button>
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-400">{t("entity.perEntityHint", { max: MAX_ITEMS_PER_ENTITY })}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {relatedInstruments.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-2 rounded border border-slate-700 bg-slate-950/60 px-3 py-2 min-w-[140px]"
              >
                <div className="flex-1">
                  <div className="text-sm font-medium text-slate-200">{r.symbol}</div>
                  <div className="text-xs text-slate-400">{r.display_name || r.asset_class}</div>
                  <div className="mt-1 text-xs text-slate-300">
                    {relatedQuotes[r.symbol]?.price != null ? `$${Number(relatedQuotes[r.symbol].price).toFixed(2)}` : "—"}
                    {(() => {
                      const q = relatedQuotes[r.symbol];
                      return q?.change_percent != null ? (
                        <span className={q.change_percent >= 0 ? "text-emerald-400" : "text-red-400"}>
                          {" "}
                          {q.change_percent >= 0 ? "+" : ""}
                          {Number(q.change_percent).toFixed(2)}%
                        </span>
                      ) : null;
                    })()}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => openRemoveConfirm(r)}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-slate-500 hover:bg-slate-800 hover:text-red-400"
                  aria-label={t("entity.removeRelatedAria")}
                  title={t("entity.removeRelatedTitle")}
                >
                  <span aria-hidden>×</span>
                  <span className="text-xs">{t("workspace.remove")}</span>
                </button>
              </div>
            ))}
            {!relatedInstruments.length ? (
              <div className="text-sm text-slate-500">{t("entity.addSomeToCompare")}</div>
            ) : null}
          </div>
        </section>

        {/* Compare Instruments */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-slate-200">{t("entity.compareInstruments")}</h2>
              <SectionHelp titleKey="help.entityCompareTitle" bodyKey="help.entityCompareBody" />
            </div>
            <div className="flex gap-1">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setComparisonPeriod(p)}
                  className={`rounded px-2 py-1 text-xs ${comparisonPeriod === p ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"}`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-400">{t("entity.compareInstrumentsHint", { max: MAX_COMPARISON })}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {allComparisonOptions.map((opt) => (
              <label key={opt.instrumentId} className="flex items-center gap-1.5 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={comparisonInstrumentIds.includes(opt.instrumentId)}
                  onChange={() => toggleComparisonInstrument(opt.instrumentId)}
                  disabled={
                    !comparisonInstrumentIds.includes(opt.instrumentId) && comparisonInstrumentIds.length >= MAX_COMPARISON
                  }
                />
                {opt.label}
              </label>
            ))}
          </div>
          <div className="mt-3">
            <ResizableChartSection
              height={compareSectionHeight}
              onHeightChange={setCompareSectionHeight}
              minHeight={RESIZE_MIN_HEIGHT}
              maxHeight={COMPARE_SECTION_MAX_HEIGHT}
            >
              {comparisonInstrumentIds.length === 0 ? (
                <div className="flex h-full min-h-[120px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-slate-500">
                  {t("entity.compareSelectHint")}
                </div>
              ) : comparisonLoading ? (
                <div className="flex h-full min-h-[200px] items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500">
                  {t("common.loading")}
                </div>
              ) : comparisonCandles.length > 0 && comparisonCandles.every((c) => !c.bars.length) ? (
                <div className="flex h-full min-h-[160px] items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm text-slate-500">
                  {t("entity.stackedCandlesNoData")}
                </div>
              ) : (
                (() => {
                  const idToSymbol = new Map(allComparisonOptions.map((o) => [o.instrumentId, o.symbol]));
                  return (
                    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto overflow-x-hidden pr-0.5">
                      {comparisonInstrumentIds.map((iid) => {
                        const sym = idToSymbol.get(iid);
                        if (!sym) return null;
                        const c = comparisonCandles.find((x) => x.symbol === sym);
                        const bars = c?.bars ?? [];
                        return (
                          <div
                            key={iid}
                            className="flex shrink-0 flex-col rounded border border-slate-700/60 bg-slate-900/30 p-2"
                          >
                            <div className="mb-1 text-xs font-medium text-slate-400">{sym}</div>
                            {bars.length > 0 ? (
                              <CandleChart
                                bars={bars}
                                height={COMPARE_ROW_CANDLE_HEIGHT}
                                onVisibleTimeRangeChange={(r) =>
                                  setCompareChartVisibleRange((prev) => ({ ...prev, [sym]: r }))
                                }
                              />
                            ) : (
                              <div
                                className="flex items-center justify-center rounded bg-slate-900/20 px-2 text-center text-xs text-slate-500"
                                style={{ minHeight: COMPARE_ROW_CANDLE_HEIGHT }}
                              >
                                {sym}: {t("common.noData")}
                              </div>
                            )}
                            <EntityEventTimeline
                              entityId={id}
                              symbol={sym}
                              period={comparisonPeriod}
                              chartScope={`compare:${sym}`}
                              bars={bars}
                              visibleTimeRange={
                                sym in compareChartVisibleRange ? compareChartVisibleRange[sym] ?? null : null
                              }
                            />
                          </div>
                        );
                      })}
                    </div>
                  );
                })()
              )}
            </ResizableChartSection>
          </div>
        </section>
          </>
        ) : (
          <>
            <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
              <div className="h-4 w-28 animate-pulse rounded bg-slate-800" />
              <div className="mt-3 h-24 animate-pulse rounded bg-slate-950/60" />
            </section>
            <section ref={priceSectionRef} className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
              <div className="h-4 w-24 animate-pulse rounded bg-slate-800" />
              <div className="mt-3 min-h-[200px] animate-pulse rounded-lg bg-slate-950/50" />
            </section>
            <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
              <div className="h-4 w-40 animate-pulse rounded bg-slate-800" />
              <div className="mt-3 h-20 animate-pulse rounded bg-slate-950/50" />
            </section>
            <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
              <div className="h-4 w-36 animate-pulse rounded bg-slate-800" />
              <div className="mt-3 min-h-[160px] animate-pulse rounded-lg bg-slate-950/50" />
            </section>
          </>
        )}
        </div>

        <aside className="min-w-0 space-y-3 lg:sticky lg:top-4 lg:self-start">
          <EntityNewsPanel
            entityId={id}
            heightPx={newsPanelHeight}
            instrument={
              entity?.instrument
                ? { symbol: entity.instrument.symbol, display_name: entity.instrument.display_name ?? null }
                : null
            }
            entityName={entity?.name ?? "\u00A0"}
            terms={terms}
            onPendingChange={setNewsPending}
          />
          {entity ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <h2 className="text-sm font-semibold text-slate-200">{t("workspace.workspaceBlocks")}</h2>
                <SectionHelp titleKey="help.workspaceBlocksTitle" bodyKey="help.workspaceBlocksBody" />
              </div>
              <button
                type="button"
                onClick={() => {
                  setChartPersistError(null);
                  setAddChartModalOpen(true);
                }}
                disabled={workspaceCharts.length >= MAX_WORKSPACE_CHARTS || chartSavePending}
                title={
                  workspaceCharts.length >= MAX_WORKSPACE_CHARTS
                    ? t("workspace.maxBlocksPerEntity", { max: MAX_WORKSPACE_CHARTS })
                    : undefined
                }
                className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t("workspace.addComponent")}
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              {t("workspace.entityComponentsHint", { used: workspaceCharts.length, max: MAX_WORKSPACE_CHARTS })}
            </p>
            {chartPersistError ? (
              <div className="mt-2 rounded border border-red-900/50 bg-red-950/20 px-2 py-1.5 text-xs text-red-200">{chartPersistError}</div>
            ) : null}
            {chartSavePending ? <div className="mt-2 text-[11px] text-slate-500">{t("workspace.savingLayout")}</div> : null}
            <div className="mt-3 space-y-3">
              {workspaceCharts.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950/40 px-3 py-8 text-center text-sm text-slate-500">
                  {t("workspace.noBlocksYet", { max: MAX_WORKSPACE_CHARTS })}
                </div>
              ) : (
                workspaceCharts.map((block) => (
                  <EntityWorkspaceChartCard
                    key={block.id}
                    block={block}
                    onRemove={() => setRemoveWorkspaceChartId(block.id)}
                  >
                    <ResizableChartSection
                      height={workspaceBlockHeights[block.id] ?? RESIZE_DEFAULT_HEIGHT}
                      onHeightChange={(h) => setWorkspaceBlockHeights((prev) => ({ ...prev, [block.id]: h }))}
                      minHeight={RESIZE_MIN_HEIGHT}
                      maxHeight={RESIZE_MAX_HEIGHT}
                    >
                      {block.type === "3d" || block.type === "analysis_3d" ? (
                        <WorkspaceChartErrorBoundary>
                          <EntityWorkspace3DChart entityId={id} />
                        </WorkspaceChartErrorBoundary>
                      ) : block.type === "quadrant" ? (
                        <EntityQuadrantBlock entityId={id} period={period} />
                      ) : block.type === "series_search_volume" ? (
                        <EntitySeriesVolumeBlock entityId={id} period={period} kind="search" />
                      ) : block.type === "series_coverage_volume" ? (
                        <EntitySeriesVolumeBlock entityId={id} period={period} kind="coverage" />
                      ) : block.type === "series_triple_signal" ? (
                        <TripleSignalChartBlock entityId={id} period={period} />
                      ) : block.type === "metric_momentum" ? (
                        <EntityMetricDerivedBlock entityId={id} period={period} metric="momentum" />
                      ) : block.type === "metric_acceleration" ? (
                        <EntityMetricDerivedBlock entityId={id} period={period} metric="acceleration" />
                      ) : block.type === "overlay_technical" ? (
                        <EntityOverlayChart entityId={id} period={period} />
                      ) : block.type === "overlay_sentiment" ? (
                        <EntityOverlaySentimentChart entityId={id} period={period} />
                      ) : block.type === "split_technical" ? (
                        <EntitySplitChart entityId={id} period={period} />
                      ) : block.type === "split_sentiment" ? (
                        <EntitySplitSentimentChart entityId={id} period={period} />
                      ) : block.type === "analysis_institution_bias" ? (
                        <EntityInstitutionBiasBlock entityId={id} />
                      ) : block.type === "analysis_rating_distribution" ? (
                        <EntityRatingDistributionBlock entityId={id} />
                      ) : (
                        <EntityWorkspaceChartPlaceholder block={block} />
                      )}
                    </ResizableChartSection>
                  </EntityWorkspaceChartCard>
                ))
              )}
            </div>
          </section>
          ) : (
            <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
              <div className="h-4 w-44 animate-pulse rounded bg-slate-800" />
              <div className="mt-3 h-32 animate-pulse rounded-lg bg-slate-950/50" />
            </section>
          )}
        </aside>
        </div>

        <EntityAddBlockModal
          open={addChartModalOpen}
          onClose={() => setAddChartModalOpen(false)}
          onPick={pickWorkspaceBlockType}
          currentCount={workspaceCharts.length}
          saving={chartSavePending}
          error={chartPersistError}
        />

        {/* AI Suggestion modal */}
        {aiOpen && isAdminUser ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-100">{t("entity.aiKeywordSuggestion")}</h3>
              <p className="mt-1 text-xs text-slate-400">{t("entity.aiSuggestionDesc")}</p>
              <textarea
                className="mt-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                rows={3}
                placeholder="Describe a target or industry (e.g. a stock you're interested in). We'll suggest up to 8 keywords."
                value={aiIdea}
                onChange={(e) => setAiIdea(e.target.value)}
              />
              <button
                type="button"
                onClick={() => {
                  void handleAiSuggest();
                }}
                disabled={aiLoading || !aiIdea.trim()}
                className="mt-2 w-full rounded bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {aiLoading ? t("entity.generating") : t("entity.generateKeywords")}
              </button>
              {aiKeywordError ? (
                <p className="mt-2 text-xs text-amber-300/90" role="alert">
                  {aiKeywordError}
                </p>
              ) : null}
              {aiKeywords.length > 0 ? (
                <div className="mt-3 rounded-lg border border-slate-700/80 bg-slate-950/50 p-2">
                  <p className="text-xs font-medium text-slate-400">Suggested keywords</p>
                  <div className="mt-2 flex flex-wrap gap-1.5" role="list" aria-label="Suggested keywords">
                    {aiKeywords.slice(0, 8).map((k) => (
                      <span
                        key={k}
                        role="listitem"
                        className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-600 bg-slate-800/90 pl-2.5 pr-1 py-0.5 text-xs text-slate-200"
                      >
                        <span className="select-all truncate" title={k}>
                          {k}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            addTerm(k);
                          }}
                          className="shrink-0 rounded-full bg-slate-600 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-slate-500"
                          title="Add to Terms"
                        >
                          +
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="mt-4 flex justify-end">
                <button type="button" onClick={() => setAiOpen(false)} className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200">
                  {t("common.close")}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Remove related instrument confirmation modal */}
        {removeItemConfirm ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-item-title"
          >
            <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 id="remove-item-title" className="text-lg font-semibold text-slate-100">
                Remove related instrument
              </h3>
              <p className="mt-2 text-sm text-slate-300">
                Are you sure you want to remove this instrument from the entity?
                {removeItemConfirm.symbol ? (
                  <span className="mt-1 block font-medium text-slate-200">
                    ({removeItemConfirm.symbol})
                  </span>
                ) : null}
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={closeRemoveConfirm}
                  disabled={removeItemLoading}
                  className="rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700 disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={performRemoveItem}
                  disabled={removeItemLoading}
                  className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-60"
                >
                  {removeItemLoading ? "Removing…" : "Remove"}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Remove workspace chart confirmation */}
        {removeWorkspaceChartId ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-workspace-chart-title"
          >
            <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 id="remove-workspace-chart-title" className="text-lg font-semibold text-slate-100">
                Remove chart
              </h3>
              <p className="mt-2 text-sm text-slate-300">
                Remove this chart from the workspace? The layout will be saved for this entity.
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setRemoveWorkspaceChartId(null)}
                  className="rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmRemoveWorkspaceChart}
                  className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
                >
                  Remove
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Bind / change primary instrument modal */}
        {bindInstrumentOpen && entity ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="bind-instrument-title">
            <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 id="bind-instrument-title" className="text-lg font-semibold text-slate-100">
                {entity.instrument ? t("entity.changeInstrument") : t("entity.bindInstrument")}
              </h3>
              <p className="mt-1 text-xs text-slate-400">{t("entity.bindInstrumentDesc")}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1 text-xs">
                {[
                  { key: "all", labelKey: "common.all" as const },
                  { key: "equity", labelKey: "macro.stock" as const },
                  { key: "etf", labelKey: "entity.etf" as const },
                  { key: "index", labelKey: "entity.index" as const },
                  { key: "futures", labelKey: "macro.futures" as const },
                  { key: "crypto", labelKey: "macro.crypto" as const },
                  { key: "hk", labelKey: "entity.hongKong" as const },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setBindInstrumentType(opt.key as typeof bindInstrumentType)}
                    className={
                      "rounded-full border px-2 py-0.5 " +
                      (bindInstrumentType === opt.key
                        ? "border-indigo-400 bg-indigo-500/20 text-indigo-100"
                        : "border-slate-700 bg-slate-900/60 text-slate-400 hover:border-slate-500 hover:text-slate-200")
                    }
                  >
                    {t(opt.labelKey)}
                  </button>
                ))}
              </div>
              <input
                type="text"
                className="mt-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500"
                placeholder={t("entity.searchInstrumentPlaceholder")}
                value={bindInstrumentQuery}
                onChange={(e) => setBindInstrumentQuery(e.target.value)}
              />
              <div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
                {bindInstrumentResults.map((inst) => (
                  <button
                    key={inst.id}
                    type="button"
                    onClick={() => handleBindInstrumentSelect(inst)}
                    disabled={bindInstrumentLoading}
                    className="w-full rounded border border-slate-700 bg-slate-950/60 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-semibold text-slate-100">
                        {inst.symbol}
                        {inst.display_name ? ` · ${inst.display_name}` : ""}
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] uppercase text-slate-300">
                          {inst.asset_class}
                        </span>
                        {inst.market ? (
                          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                            {inst.market}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {inst.description ? (
                      <div className="mt-0.5 text-xs text-slate-400">
                        {inst.description}
                      </div>
                    ) : null}
                  </button>
                ))}
                {bindInstrumentQuery.trim() && !bindInstrumentResults.length ? (
                  <div className="py-2 text-sm text-slate-500">{t("entity.noLocalInstrumentsFound")}</div>
                ) : null}
              </div>
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={closeBindInstrument}
                  disabled={bindInstrumentLoading}
                  className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 disabled:opacity-60"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Add related instrument modal */}
        {addRelatedOpen ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-100">{t("entity.addRelatedModalTitle")}</h3>
              <div className="mt-3 flex flex-wrap gap-1">
                {INSTRUMENT_CATEGORIES.map(({ value, label }) => (
                  <button
                    key={value || "all"}
                    type="button"
                    onClick={() => setInstrumentCategory(value)}
                    className={`rounded px-2 py-0.5 text-[10px] ${
                      (instrumentCategory ?? "") === value
                        ? "bg-slate-600 text-slate-100"
                        : "bg-slate-800 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <input
                type="text"
                className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500"
                placeholder={t("entity.searchInstrumentPlaceholder")}
                value={instrumentQuery}
                onChange={(e) => setInstrumentQuery(e.target.value)}
              />
              <div className="mt-2 max-h-48 overflow-y-auto space-y-1">
                {instrumentResults.map((inst) => (
                  <button
                    key={inst.id}
                    type="button"
                    onClick={() => addRelatedInstrument(inst)}
                    disabled={addRelatedBusy}
                    className="w-full rounded border border-slate-700 bg-slate-950/60 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
                  >
                    {inst.symbol}
                    {inst.display_name ? ` · ${inst.display_name}` : ""}
                    <span className="ml-2 text-xs text-slate-500">
                      {inst.asset_class}
                      {(inst.exchange || inst.country) ? ` · ${inst.exchange || inst.country}` : ""}
                    </span>
                  </button>
                ))}
                {instrumentQuery.trim() && !instrumentResults.length ? (
                  <div className="py-2 text-sm text-slate-500">{t("entity.noInstrumentsFound")}</div>
                ) : null}
              </div>
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={() => { setAddRelatedOpen(false); setInstrumentQuery(""); setInstrumentCategory(""); setInstrumentResults([]); }}
                  className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </Shell>
  );
}
