"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
import { CHART_LABELS, type ChartType } from "./ResearchChart";

const PREMIUM_RESEARCH_TYPES: ChartType[] = ["institution_bias", "rating_distribution"];
import type { TabSetup } from "./researchTypes";

const OVERLAY_TYPES: ChartType[] = [
  "asset_price",
  "sentiment",
  "momentum",
  "coverage",
  "custom_index",
];

const SPLIT_TYPES: ChartType[] = [...OVERLAY_TYPES];

const ANALYSIS_TYPES: ChartType[] = [
  "three_d",
  "three_d_narrative",
  "three_d_derivative",
  "institution_bias",
  "rating_distribution",
];

type Kind = "overlay" | "single" | "analysis";

type Props = {
  open: boolean;
  onClose: () => void;
  onAdd: (type: ChartType, kind: Kind) => void;
  setup: TabSetup;
  hasResearchTarget: boolean;
};

export function ResearchAddBlockModal({
  open,
  onClose,
  onAdd,
  setup,
  hasResearchTarget,
}: Props) {
  const { t } = useI18n();
  const { user } = useUser();
  const isAdmin = user?.is_admin ?? false;
  const [kind, setKind] = useState<Kind>("single");
  const KIND_LABELS: Record<Kind, string> = {
    overlay: t("workspace.overlayChart"),
    single: t("workspace.splitChart"),
    analysis: t("workspace.analysis"),
  };
  const [type, setType] = useState<ChartType | null>(null);

  useEffect(() => {
    if (open) {
      setKind("single");
      setType(null);
    }
  }, [open]);

  if (!open) return null;

  const typesForKind =
    kind === "overlay"
      ? OVERLAY_TYPES
      : kind === "single"
        ? SPLIT_TYPES
        : ANALYSIS_TYPES;

  const handleAdd = () => {
    if (!type) return;
    if (PREMIUM_RESEARCH_TYPES.includes(type) && !isAdmin) return;
    onAdd(type, kind);
    setType(null);
    setKind("single");
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="research-add-block-title"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
        <h2 id="research-add-block-title" className="text-lg font-semibold text-slate-100">
          {t("workspace.addBlock")}
        </h2>

        {!hasResearchTarget ? (
          <p className="mt-2 text-sm text-amber-200/90">
            {t("workspace.noResearchTarget")}
          </p>
        ) : null}

        <div className="mt-3 flex flex-wrap gap-1">
          {(["overlay", "single", "analysis"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => {
                setKind(k);
                setType(null);
              }}
              className={`rounded border px-2 py-1 text-xs font-medium transition ${
                kind === k
                  ? "border-indigo-500 bg-indigo-900/40 text-indigo-200"
                  : "border-slate-600 bg-slate-800/60 text-slate-400 hover:border-slate-500 hover:text-slate-200"
              }`}
            >
              {KIND_LABELS[k]}
            </button>
          ))}
        </div>

        {kind === "overlay" ? (
          <p className="mt-2 text-xs text-slate-400">
            {t("workspace.sameTimelineNote")}
          </p>
        ) : null}

        <ul className="mt-3 space-y-2">
          {typesForKind.map((chartType) => {
            const isPremium = PREMIUM_RESEARCH_TYPES.includes(chartType);
            const disabled = isPremium && !isAdmin;
            return (
              <li key={chartType}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => !disabled && setType(chartType)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                    type === chartType
                      ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
                      : disabled
                        ? "cursor-not-allowed border-slate-700 bg-slate-900/60 text-slate-500 opacity-70"
                        : "border-slate-600 bg-slate-800/60 text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                  }`}
                >
                  <span>
                    {CHART_LABELS[chartType]}
                    {isPremium && !isAdmin && (
                      <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                        {t("schedules.comingUp")}
                      </span>
                    )}
                  </span>
                  {isPremium && !isAdmin && (
                    <span className="block mt-0.5 text-[11px] text-amber-300/80">
                      {t("schedules.premiumPlanned")}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={handleAdd}
            disabled={!type || !hasResearchTarget || (type && PREMIUM_RESEARCH_TYPES.includes(type) && !isAdmin)}
            className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("common.add")}
          </button>
        </div>
      </div>
    </div>
  );
}
