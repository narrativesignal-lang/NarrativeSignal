"use client";

import { useMemo, useState } from "react";
import {
  ENTITY_ADD_MODAL_ANALYSIS_TYPES,
  ENTITY_ADD_MODAL_DATA_TYPES,
  ENTITY_PREMIUM_WORKSPACE_TYPES,
  WORKSPACE_CHART_LABELS,
  WORKSPACE_CHART_DESCRIPTIONS,
  MAX_WORKSPACE_CHARTS,
  type WorkspaceChartType,
} from "@/lib/entityWorkspaceCharts";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

function entityCompTitle(t: (key: string) => string, type: WorkspaceChartType): string {
  const k = `workspace.ec.${type}`;
  const v = t(k);
  return v !== k ? v : (WORKSPACE_CHART_LABELS[type] ?? type);
}

function entityCompDesc(t: (key: string) => string, type: WorkspaceChartType): string {
  const k = `workspace.ec.${type}Desc`;
  const v = t(k);
  return v !== k ? v : (WORKSPACE_CHART_DESCRIPTIONS[type] ?? "");
}

function filterTypes(
  types: readonly WorkspaceChartType[],
  q: string,
  t: (key: string) => string
): WorkspaceChartType[] {
  const s = q.trim().toLowerCase();
  if (!s) return [...types];
  return types.filter((type) => {
    const blob = `${type} ${entityCompTitle(t, type)} ${entityCompDesc(t, type)}`.toLowerCase();
    return blob.includes(s);
  });
}

type Props = {
  open: boolean;
  onClose: () => void;
  onPick: (type: WorkspaceChartType) => void;
  currentCount: number;
  saving?: boolean;
  error?: string | null;
};

export function EntityAddBlockModal({
  open,
  onClose,
  onPick,
  currentCount,
  saving,
  error,
}: Props) {
  const { t } = useI18n();
  const { user } = useUser();
  const isAdmin = user?.is_admin ?? false;
  const [query, setQuery] = useState("");

  const dataTypes = useMemo(
    () => filterTypes(ENTITY_ADD_MODAL_DATA_TYPES, query, t),
    [query, t]
  );
  const analysisTypes = useMemo(
    () => filterTypes(ENTITY_ADD_MODAL_ANALYSIS_TYPES, query, t),
    [query, t]
  );

  if (!open) return null;

  const atLimit = currentCount >= MAX_WORKSPACE_CHARTS;

  const handlePick = (type: WorkspaceChartType) => {
    onPick(type);
    onClose();
    setQuery("");
  };

  const premiumSet = new Set<string>(ENTITY_PREMIUM_WORKSPACE_TYPES);

  const renderRow = (type: WorkspaceChartType) => {
    const isPremium = premiumSet.has(type);
    const disabled = saving || atLimit || (isPremium && !isAdmin);
    return (
      <li key={type}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && handlePick(type)}
          className="w-full rounded-lg border border-slate-600 bg-slate-800/60 px-3 py-3 text-left transition hover:border-indigo-500/60 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <div className="font-medium text-slate-100">
            {entityCompTitle(t, type)}
            {isPremium && !isAdmin && (
              <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                {t("schedules.comingUp")}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">
            {entityCompDesc(t, type)}
            {isPremium && !isAdmin && (
              <span className="block mt-1 text-amber-300/80">{t("schedules.premiumPlanned")}</span>
            )}
          </div>
        </button>
      </li>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="entity-add-component-title"
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
        <h2 id="entity-add-component-title" className="text-lg font-semibold text-slate-100">
          {t("workspace.addComponent")}
        </h2>
        <p className="mt-1 text-sm text-slate-400">{t("workspace.addComponentDesc")}</p>

        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("workspace.addComponentSearch")}
          className="mt-3 w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500"
          aria-label={t("workspace.addComponentSearch")}
        />

        {error ? (
          <div className="mt-3 rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
            {error}
          </div>
        ) : null}

        {atLimit ? (
          <div className="mt-3 rounded border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-400">
            {t("workspace.maxBlocksPerEntity", { max: MAX_WORKSPACE_CHARTS })}
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                {t("workspace.sentimentData")}
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">{t("workspace.sentimentDataDesc")}</p>
              {dataTypes.length === 0 ? (
                <p className="mt-2 text-xs text-slate-600">{t("common.noResults")}</p>
              ) : (
                <ul className="mt-2 space-y-2">{dataTypes.map(renderRow)}</ul>
              )}
            </section>

            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                {t("workspace.sentimentAnalysis")}
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">{t("workspace.sentimentAnalysisDesc")}</p>
              {analysisTypes.length === 0 ? (
                <p className="mt-2 text-xs text-slate-600">{t("common.noResults")}</p>
              ) : (
                <ul className="mt-2 space-y-2">{analysisTypes.map(renderRow)}</ul>
              )}
            </section>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={() => {
              setQuery("");
              onClose();
            }}
            disabled={saving}
            className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
