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
import { parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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

  const [error, setError] = useState<string | null>(null);
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
