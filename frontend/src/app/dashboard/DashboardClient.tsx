"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EntityDataLayout } from "@/components/entity/EntityDataLayout";
import { EntityFeatureGuideModal } from "@/components/entity/EntityFeatureGuideModal";
import { MacroFeatureGuideModal } from "@/components/macro/MacroFeatureGuideModal";
import { MacroLayout } from "@/components/macro/MacroLayout";
import { Shell } from "@/components/Shell";
import { SectionHelp } from "@/components/SectionHelp";
import { featureGuideContent } from "@/content/featureGuide";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Group = Awaited<ReturnType<typeof api.listGroups>>[number];

type DataTab = "macro" | "entity";

function toFeatureGuideLocale(locale: string): "en" | "zh" | "pt" {
  if (locale === "zh") return "zh";
  if (locale === "pt") return "pt";
  return "en";
}

export function DashboardClient() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<DataTab>(
    tabParam === "entity" ? "entity" : "macro"
  );
  const [macroGuideOpen, setMacroGuideOpen] = useState(false);
  const [entityGuideOpen, setEntityGuideOpen] = useState(false);
  const [macroMounted, setMacroMounted] = useState(activeTab === "macro");
  const [entityMounted, setEntityMounted] = useState(activeTab === "entity");
  const shellPrefetchStartedRef = useRef(false);

  useEffect(() => {
    if (tabParam === "entity") setActiveTab("entity");
    else if (tabParam === "macro") setActiveTab("macro");
  }, [tabParam]);

  useEffect(() => {
    if (activeTab === "macro") setMacroMounted(true);
    if (activeTab === "entity") setEntityMounted(true);
  }, [activeTab]);

  useEffect(() => {
    if (shellPrefetchStartedRef.current) return;
    shellPrefetchStartedRef.current = true;

    let cancelled = false;
    let kickoffId: ReturnType<typeof setTimeout> | null = null;
    let warmId: ReturnType<typeof setTimeout> | null = null;
    let idleId: number | null = null;

    const warmPageShells = () => {
      if (cancelled) return;
      // Shell/chunk warmup only. Keep real API fetching tied to page entry.
      router.prefetch("/research");
      router.prefetch("/reports");
      router.prefetch("/schedules");
      router.prefetch("/dashboard?tab=entity");

      void import("@/app/research/page");
      void import("@/app/reports/page");
      void import("@/app/schedules/page");
      void import("@/app/dashboard/entities/[id]/page");
      void import("@/app/dashboard/entities/[id]/EntityDetailPageClient");
    };

    kickoffId = setTimeout(() => {
      if (typeof window !== "undefined" && "requestIdleCallback" in window) {
        idleId = window.requestIdleCallback(
          () => {
            warmId = setTimeout(warmPageShells, 250);
          },
          { timeout: 3000 }
        );
      } else {
        warmId = setTimeout(warmPageShells, 900);
      }
    }, 700);

    return () => {
      cancelled = true;
      if (kickoffId) clearTimeout(kickoffId);
      if (warmId) clearTimeout(warmId);
      if (idleId && typeof window !== "undefined" && "cancelIdleCallback" in window) {
        window.cancelIdleCallback(idleId);
      }
    };
  }, [router]);

  const [groups, setGroups] = useState<Group[]>([]);
  const [selected, setSelected] = useState<Group | null>(null);
  const [series, setSeries] = useState<any[] | null>(null);
  const [asset, setAsset] = useState<any | null>(null);
  const [symbolInput, setSymbolInput] = useState("");
  const [period, setPeriod] = useState<string>("1M");
  const [ohlcv, setOhlcv] = useState<any | null>(null);
  const [newName, setNewName] = useState("");
  const [newTerms, setNewTerms] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [entityConfig, setEntityConfig] = useState<{ charts: string[]; market_data: string[] }>({
    charts: [],
    market_data: [],
  });
  const [addChartOpen, setAddChartOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const g = await api.listGroups();
        setGroups(g);
        setSelected(g[0] ?? null);
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    })();
  }, []);

  useEffect(() => {
    if (!selected) {
      setSeries(null);
      setAsset(null);
      setOhlcv(null);
      setSymbolInput("");
      setEntityConfig({ charts: [], market_data: [] });
      return;
    }
    (async () => {
      try {
        const [s, a, configRes] = await Promise.all([
          api.series(selected.id, 72),
          api.getGroupAsset(selected.id),
          api.getEntityConfig(selected.id).catch(() => ({ config: { charts: [], market_data: [] } })),
        ]);
        setSeries(
          s.points.map((p: any) => ({
            t: new Date(p.bucket_start).toLocaleString(),
            volume: p.mention_volume,
            momentum: p.momentum,
            pos: p.sentiment_positive,
            neg: p.sentiment_negative
          }))
        );
        setAsset(a);
        setSymbolInput(a?.symbol || "");
        const cfg = configRes.config || {};
        setEntityConfig({
          charts: Array.isArray(cfg.charts) ? cfg.charts : [],
          market_data: Array.isArray(cfg.market_data) ? cfg.market_data : [],
        });
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    })();
  }, [selected?.id]);

  const saveEntityConfig = useCallback(
    (updater: (prev: { charts: string[]; market_data: string[] }) => { charts: string[]; market_data: string[] }) => {
      if (!selected) return;
      setEntityConfig((prev) => {
        const next = updater(prev);
        api.putEntityConfig(selected.id, next).catch(() => {});
        return next;
      });
    },
    [selected]
  );

  useEffect(() => {
    (async () => {
      if (!asset?.symbol) {
        setOhlcv(null);
        return;
      }
      try {
        const res = await api.ohlcv(asset.symbol, period);
        setOhlcv(res);
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    })();
  }, [asset?.symbol, period]);

  const bars = useMemo(() => (ohlcv?.bars || []) as any[], [ohlcv]);

  const selectedTerms = useMemo(() => {
    if (!selected) return "";
    return selected.terms.map((t) => t.term).join(", ");
  }, [selected]);

  async function createGroup() {
    setError(null);
    const terms = newTerms
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((term) => ({ term, is_required: false }));
    try {
      await api.createGroup({ name: newName, terms });
      const g = await api.listGroups();
      setGroups(g);
      setSelected(g[0] ?? null);
      setNewName("");
      setNewTerms("");
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function deleteGroup(id: string) {
    setError(null);
    try {
      await api.deleteGroup(id);
      const g = await api.listGroups();
      setGroups(g);
      setSelected(g[0] ?? null);
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function saveSymbol() {
    if (!selected) return;
    setError(null);
    try {
      const next = await api.setGroupAsset(selected.id, { symbol: symbolInput.trim().toUpperCase(), provider: "stooq" });
      setAsset(next);
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  const guideLocale = toFeatureGuideLocale(locale);
  const macroGuideLabel = featureGuideContent.macroData[guideLocale].buttonLabel;
  const entityGuideLabel = featureGuideContent.entityData[guideLocale].buttonLabel;

  return (
    <Shell>
      <div className="min-w-0 space-y-4">
        <div className="space-y-2">
          <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/30 p-1">
            <button
              type="button"
              onClick={() => {
                setActiveTab("macro");
                router.replace("/dashboard", { scroll: false });
              }}
              className={
                "rounded-md px-4 py-2 text-sm font-medium transition-colors " +
                (activeTab === "macro"
                  ? "bg-slate-700 text-slate-50"
                  : "text-slate-300 hover:bg-slate-800 hover:text-slate-100")
              }
            >
              {t("dashboard.macroData")}
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("entity");
                router.replace("/dashboard?tab=entity", { scroll: false });
              }}
              className={
                "rounded-md px-4 py-2 text-sm font-medium transition-colors " +
                (activeTab === "entity"
                  ? "bg-slate-700 text-slate-50"
                  : "text-slate-300 hover:bg-slate-800 hover:text-slate-100")
              }
            >
              {t("dashboard.entityData")}
            </button>
            <SectionHelp titleKey="help.dashboardTabsTitle" bodyKey="help.dashboardTabsBody" className="ml-1" />
          </div>
          {activeTab === "macro" && (
            <button
              type="button"
              onClick={() => setMacroGuideOpen(true)}
              className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
            >
              {macroGuideLabel}
            </button>
          )}
          {activeTab === "entity" && (
            <button
              type="button"
              onClick={() => setEntityGuideOpen(true)}
              className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
            >
              {entityGuideLabel}
            </button>
          )}
        </div>

        {macroMounted ? (
          <div
            className={activeTab === "macro" ? "block min-w-0" : "hidden"}
            aria-hidden={activeTab !== "macro"}
          >
            <MacroLayout isActive={activeTab === "macro"} />
          </div>
        ) : null}
        {entityMounted ? (
          <div
            className={activeTab === "entity" ? "block min-w-0" : "hidden"}
            aria-hidden={activeTab !== "entity"}
          >
            <EntityDataLayout isActive={activeTab === "entity"} />
          </div>
        ) : null}
      </div>
      {macroGuideOpen && (
        <MacroFeatureGuideModal onClose={() => setMacroGuideOpen(false)} locale={locale} />
      )}
      {entityGuideOpen && (
        <EntityFeatureGuideModal onClose={() => setEntityGuideOpen(false)} locale={locale} />
      )}
    </Shell>
  );
}
