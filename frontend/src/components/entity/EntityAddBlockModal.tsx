"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ENTITY_AI_ANALYSIS_TAB_TYPES,
  ENTITY_CLASSIC_ANALYSIS_TAB_TYPES,
  ENTITY_OVERLAY_SERIES_META,
  ENTITY_OVERLAY_SERIES_ORDER,
  entityOverlaySeriesLabel,
  ENTITY_WORKSPACE_IMPLEMENTED_TYPES,
  ENTITY_SPLIT_TAB_TYPES,
  getExistingOverlaySeriesKeys,
  MAX_WORKSPACE_CHARTS,
  WORKSPACE_BLOCK_AI_COST,
  WORKSPACE_CHART_DESCRIPTIONS,
  WORKSPACE_CHART_LABELS,
  type EntityOverlaySeriesKey,
  type WorkspaceChartBlock,
  type WorkspaceChartType,
} from "@/lib/entityWorkspaceCharts";
import { canUseWorkspaceAiCost } from "@/lib/workspaceAiAccess";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

type ModalTab = "data" | "analysis" | "ai_analysis";

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
  const sl = q.trim().toLowerCase();
  if (!sl) return types.filter((ty) => (ENTITY_WORKSPACE_IMPLEMENTED_TYPES as readonly string[]).includes(ty));
  return types.filter((type) => {
    if (!(ENTITY_WORKSPACE_IMPLEMENTED_TYPES as readonly string[]).includes(type)) return false;
    const blob = `${type} ${entityCompTitle(t, type)} ${entityCompDesc(t, type)}`.toLowerCase();
    return blob.includes(sl);
  });
}

type Props = {
  open: boolean;
  onClose: () => void;
  /** Single block add (split or analysis tab). */
  onPickBlockType: (type: WorkspaceChartType) => void;
  /** Merge selected overlay series into the one `overlay_technical` block. */
  onPickOverlayKeys: (keys: string[]) => void;
  workspaceBlocks: WorkspaceChartBlock[];
  currentCount: number;
  saving?: boolean;
  error?: string | null;
};

export function EntityAddBlockModal({
  open,
  onClose,
  onPickBlockType,
  onPickOverlayKeys,
  workspaceBlocks,
  currentCount,
  saving,
  error,
}: Props) {
  const { t } = useI18n();
  const { user } = useUser();
  const isAdmin = user?.is_admin ?? false;
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<ModalTab>("data");
  const [overlaySelected, setOverlaySelected] = useState<Set<string>>(new Set());
  const [splitPick, setSplitPick] = useState<WorkspaceChartType | null>(null);
  const [analysisPick, setAnalysisPick] = useState<WorkspaceChartType | null>(null);
  const [aiAnalysisPick, setAiAnalysisPick] = useState<WorkspaceChartType | null>(null);

  const splitTypes = useMemo(
    () => filterTypes(ENTITY_SPLIT_TAB_TYPES, query, t),
    [query, t]
  );
  const analysisTypes = useMemo(
    () => filterTypes(ENTITY_CLASSIC_ANALYSIS_TAB_TYPES, query, t),
    [query, t]
  );
  const aiAnalysisTypes = useMemo(
    () => filterTypes(ENTITY_AI_ANALYSIS_TAB_TYPES, query, t),
    [query, t]
  );

  const existingOverlayKeys = useMemo(() => getExistingOverlaySeriesKeys(workspaceBlocks), [workspaceBlocks]);
  const hasOverlayBlock = workspaceBlocks.some((b) => b.type === "overlay_technical");
  const atLimit = currentCount >= MAX_WORKSPACE_CHARTS;
  const canCreateOverlayBlock = hasOverlayBlock || !atLimit;

  useEffect(() => {
    if (open) {
      setQuery("");
      setTab("data");
      setOverlaySelected(new Set());
      setSplitPick(null);
      setAnalysisPick(null);
      setAiAnalysisPick(null);
    }
  }, [open]);

  const canSubmitAiAnalysis = useMemo(() => {
    if (!aiAnalysisPick) return false;
    const c = WORKSPACE_BLOCK_AI_COST[aiAnalysisPick] ?? "none";
    if (c !== "none" && !canUseWorkspaceAiCost(user ?? null, c)) return false;
    return true;
  }, [aiAnalysisPick, user]);

  if (!open) return null;

  const premiumSet = new Set<string>([]);

  const overlayKeysOrdered = ENTITY_OVERLAY_SERIES_ORDER.filter(() => true);

  const toggleOverlayKey = (key: string) => {
    if (existingOverlayKeys.has(key)) return;
    setSplitPick(null);
    setOverlaySelected((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  };

  const newOverlaySelections = [...overlaySelected].filter((k) => !existingOverlayKeys.has(k));
  const canSubmitOverlay = newOverlaySelections.length > 0 && canCreateOverlayBlock;

  const handleOverlayAdd = () => {
    if (!canSubmitOverlay) return;
    onPickOverlayKeys(newOverlaySelections);
    setOverlaySelected(new Set());
    setQuery("");
    onClose();
  };

  const handleSplitAdd = () => {
    if (!splitPick || saving || atLimit) return;
    const isPremium = premiumSet.has(splitPick);
    if (isPremium && !isAdmin) return;
    onPickBlockType(splitPick);
    setSplitPick(null);
    setQuery("");
    onClose();
  };

  const handleAnalysisAdd = () => {
    if (!analysisPick || saving || atLimit) return;
    const isPremium = premiumSet.has(analysisPick);
    if (isPremium && !isAdmin) return;
    onPickBlockType(analysisPick);
    setAnalysisPick(null);
    setQuery("");
    onClose();
  };

  const handleAiAnalysisAdd = () => {
    if (!aiAnalysisPick || saving || atLimit) return;
    const isPremium = premiumSet.has(aiAnalysisPick);
    if (isPremium && !isAdmin) return;
    const aiCost = WORKSPACE_BLOCK_AI_COST[aiAnalysisPick] ?? "none";
    if (aiCost !== "none" && !canUseWorkspaceAiCost(user ?? null, aiCost)) return;
    onPickBlockType(aiAnalysisPick);
    setAiAnalysisPick(null);
    setQuery("");
    onClose();
  };

  const TAB_LABEL: Record<ModalTab, string> = {
    data: t("workspace.tabData"),
    analysis: t("workspace.tabAnalysis"),
    ai_analysis: t("workspace.tabAiAnalysis"),
  };

  const renderSplitRow = (type: WorkspaceChartType) => {
    const isPremium = premiumSet.has(type);
    const disabled = saving || atLimit || (isPremium && !isAdmin);
    const selected = splitPick === type;
    return (
      <li key={type}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            if (disabled) return;
            setOverlaySelected(new Set());
            setSplitPick(type);
          }}
          className={`w-full rounded-lg border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
            selected
              ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
              : "border-slate-600 bg-slate-800/60 hover:border-indigo-500/60 hover:bg-slate-800"
          }`}
        >
          <div className="font-medium text-slate-100">
            {entityCompTitle(t, type)}
            {isPremium && !isAdmin && (
              <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                {t("schedules.comingUp")}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">{entityCompDesc(t, type)}</div>
        </button>
      </li>
    );
  };

  const renderAiAnalysisRow = (type: WorkspaceChartType) => {
    const isPremium = premiumSet.has(type);
    const aiCost = WORKSPACE_BLOCK_AI_COST[type] ?? "none";
    const aiAllowed = aiCost === "none" || canUseWorkspaceAiCost(user ?? null, aiCost);
    const disabled = saving || atLimit || (isPremium && !isAdmin) || !aiAllowed;
    const selected = aiAnalysisPick === type;
    return (
      <li key={type}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setAiAnalysisPick(type)}
          className={`w-full rounded-lg border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
            selected
              ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
              : "border-slate-600 bg-slate-800/60 hover:border-indigo-500/60 hover:bg-slate-800"
          }`}
        >
          <div className="font-medium text-slate-100">
            {entityCompTitle(t, type)}
            {aiCost !== "none" ? (
              <span
                className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] font-medium text-amber-200"
                title={t("workspace.blockAiTooltip")}
              >
                {t("workspace.blockAiBadge")}
              </span>
            ) : null}
            {isPremium && !isAdmin && (
              <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                {t("schedules.comingUp")}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">{entityCompDesc(t, type)}</div>
          {!aiAllowed ? (
            <p className="mt-1 text-[11px] text-amber-200/90">{t("workspace.aiPlanLockedShort")}</p>
          ) : null}
        </button>
      </li>
    );
  };

  const renderAnalysisRow = (type: WorkspaceChartType) => {
    const isPremium = premiumSet.has(type);
    const disabled = saving || atLimit || (isPremium && !isAdmin);
    const selected = analysisPick === type;
    return (
      <li key={type}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setAnalysisPick(type)}
          className={`w-full rounded-lg border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
            selected
              ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
              : "border-slate-600 bg-slate-800/60 hover:border-indigo-500/60 hover:bg-slate-800"
          }`}
        >
          <div className="font-medium text-slate-100">
            {entityCompTitle(t, type)}
            {isPremium && !isAdmin && (
              <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                {t("schedules.comingUp")}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">{entityCompDesc(t, type)}</div>
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

        <div className="mt-3 flex flex-wrap gap-1">
          {(["data", "analysis", "ai_analysis"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => {
                setTab(k);
                setSplitPick(null);
                setAnalysisPick(null);
                setAiAnalysisPick(null);
                if (k !== "data") setOverlaySelected(new Set());
              }}
              className={`rounded border px-2 py-1 text-xs font-medium transition ${
                tab === k
                  ? "border-indigo-500 bg-indigo-900/40 text-indigo-200"
                  : "border-slate-600 bg-slate-800/60 text-slate-400 hover:border-slate-500 hover:text-slate-200"
              }`}
            >
              {TAB_LABEL[k]}
            </button>
          ))}
        </div>

        {error ? (
          <div className="mt-3 rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
            {error}
          </div>
        ) : null}

        {tab === "data" && atLimit && !hasOverlayBlock ? (
          <div className="mt-3 rounded border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-400">
            {t("workspace.maxBlocksPerEntity", { max: MAX_WORKSPACE_CHARTS })}
          </div>
        ) : null}

        {tab === "data" ? (
          <div className="mt-4 space-y-6">
            <div className="space-y-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {t("workspace.entityDataOverlayHeading")}
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500">{t("workspace.entityDataOverlaySub")}</p>
              </div>
              <p className="text-xs text-slate-400">{t("workspace.overlayTabHint")}</p>
              <p className="text-[11px] text-slate-500">{t("workspace.sameTimelineNote")}</p>
              <p className="text-xs font-medium text-slate-300">
                {t("workspace.overlaySelectedCount", { count: overlaySelected.size })}
              </p>
              {overlayKeysOrdered.length === 0 ? (
                <p className="text-sm text-slate-500">{t("workspace.modalNoOverlayOptions")}</p>
              ) : (
                <ul className="space-y-2">
                  {overlayKeysOrdered.map((key) => {
                    const overlayKey = key as EntityOverlaySeriesKey;
                    const meta = ENTITY_OVERLAY_SERIES_META[overlayKey];
                    const seriesTitle = entityOverlaySeriesLabel(t, overlayKey);
                    const already = existingOverlayKeys.has(key);
                    const checked = overlaySelected.has(key) || already;
                    return (
                      <li key={key}>
                        <label
                          className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                            already
                              ? "border-slate-700 bg-slate-950/50 text-slate-500"
                              : "border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500"
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={checked}
                            disabled={already || saving}
                            onChange={() => toggleOverlayKey(key)}
                            aria-label={seriesTitle}
                          />
                          <span>
                            <span className="font-medium">{seriesTitle}</span>
                            <span className="mt-0.5 block text-xs text-slate-400">{meta.description}</span>
                            {already ? (
                              <span className="mt-1 block text-[10px] text-slate-500">
                                {t("workspace.overlayAlreadyInChart")}
                              </span>
                            ) : null}
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="border-t border-slate-800 pt-4 space-y-2">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {t("workspace.entityDataSingleHeading")}
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500">{t("workspace.entityDataSingleSub")}</p>
              </div>
              {splitTypes.length === 0 ? (
                <p className="text-sm text-slate-500">{t("workspace.modalNoSplitOptions")}</p>
              ) : (
                <ul className="space-y-2">{splitTypes.map(renderSplitRow)}</ul>
              )}
            </div>
          </div>
        ) : null}

        {tab === "analysis" ? (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-slate-500">{t("workspace.entityAnalysisTabSub")}</p>
            {analysisTypes.length === 0 ? (
              <p className="text-sm text-slate-500">{t("workspace.modalNoAnalysisOptions")}</p>
            ) : (
              <ul className="space-y-2">{analysisTypes.map(renderAnalysisRow)}</ul>
            )}
          </div>
        ) : null}

        {tab === "ai_analysis" ? (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-slate-500">{t("workspace.entityAiAnalysisTabSub")}</p>
            {aiAnalysisTypes.length === 0 ? (
              <p className="text-sm text-slate-500">{t("workspace.modalNoAnalysisOptions")}</p>
            ) : (
              <ul className="space-y-2">{aiAnalysisTypes.map(renderAiAnalysisRow)}</ul>
            )}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2 border-t border-slate-800 pt-4">
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
          {tab === "data" ? (
            <>
              <button
                type="button"
                onClick={handleOverlayAdd}
                disabled={!canSubmitOverlay || saving}
                className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t("workspace.addOverlayButton")}
              </button>
              <button
                type="button"
                onClick={handleSplitAdd}
                disabled={!splitPick || saving || atLimit}
                className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t("workspace.addChartButton")}
              </button>
            </>
          ) : null}
          {tab === "analysis" ? (
            <button
              type="button"
              onClick={handleAnalysisAdd}
              disabled={!analysisPick || saving || atLimit}
              className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("common.add")}
            </button>
          ) : null}
          {tab === "ai_analysis" ? (
            <button
              type="button"
              onClick={handleAiAnalysisAdd}
              disabled={!aiAnalysisPick || saving || atLimit || !canSubmitAiAnalysis}
              className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("common.add")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
