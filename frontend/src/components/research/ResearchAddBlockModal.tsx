"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { researchChartTypeLabel, type ChartType } from "./ResearchChart";
import {
  RESEARCH_ANALYSIS_CHART_TYPES,
  RESEARCH_OVERLAY_CHART_TYPES,
  RESEARCH_SPLIT_CHART_TYPES,
} from "./researchBlockRegistry";
type KindTab = "overlay" | "single" | "analysis";

type Props = {
  open: boolean;
  onClose: () => void;
  onAddOverlay: (types: ChartType[]) => void;
  onAddSingle: (type: ChartType, kind: "single" | "analysis") => void;
  hasResearchTarget: boolean;
};

export function ResearchAddBlockModal({
  open,
  onClose,
  onAddOverlay,
  onAddSingle,
  hasResearchTarget,
}: Props) {
  const { t } = useI18n();
  const [kind, setKind] = useState<KindTab>("single");
  const KIND_LABELS: Record<KindTab, string> = {
    overlay: t("workspace.overlayChart"),
    single: t("workspace.splitChart"),
    analysis: t("workspace.analysis"),
  };
  const [overlaySelected, setOverlaySelected] = useState<Set<ChartType>>(new Set());
  const [splitType, setSplitType] = useState<ChartType | null>(null);
  const [analysisType, setAnalysisType] = useState<ChartType | null>(null);

  useEffect(() => {
    if (open) {
      setKind("single");
      setOverlaySelected(new Set());
      setSplitType(null);
      setAnalysisType(null);
    }
  }, [open]);

  if (!open) return null;

  const toggleOverlay = (ct: ChartType) => {
    setOverlaySelected((prev) => {
      const n = new Set(prev);
      if (n.has(ct)) n.delete(ct);
      else n.add(ct);
      return n;
    });
  };

  const newOverlayPicks = [...overlaySelected];
  const canAddOverlay = hasResearchTarget && newOverlayPicks.length > 0;

  const handleOverlayAdd = () => {
    if (!canAddOverlay) return;
    onAddOverlay(newOverlayPicks);
    setOverlaySelected(new Set());
    onClose();
  };

  const handleSplitAdd = () => {
    if (!splitType || !hasResearchTarget) return;
    onAddSingle(splitType, "single");
    setSplitType(null);
    onClose();
  };

  const handleAnalysisAdd = () => {
    if (!analysisType || !hasResearchTarget) return;
    onAddSingle(analysisType, "analysis");
    setAnalysisType(null);
    onClose();
  };

  const emptyOverlay = RESEARCH_OVERLAY_CHART_TYPES.length === 0;
  const emptySplit = RESEARCH_SPLIT_CHART_TYPES.length === 0;
  const emptyAnalysis = RESEARCH_ANALYSIS_CHART_TYPES.length === 0;

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
          <p className="mt-2 text-sm text-amber-200/90">{t("workspace.noResearchTarget")}</p>
        ) : null}

        <div className="mt-3 flex flex-wrap gap-1">
          {(["overlay", "single", "analysis"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => {
                setKind(k);
                setSplitType(null);
                setAnalysisType(null);
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
          <>
            <p className="mt-2 text-xs text-slate-400">{t("workspace.overlayTabHint")}</p>
            <p className="mt-1 text-[11px] text-slate-500">{t("workspace.sameTimelineNote")}</p>
            <p className="mt-2 text-xs font-medium text-slate-300">
              {t("workspace.overlaySelectedCount", { count: overlaySelected.size })}
            </p>
          </>
        ) : null}

        <ul className="mt-3 space-y-2">
          {kind === "overlay" ? (
            emptyOverlay ? (
              <li className="rounded border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-400">
                {t("workspace.modalNoOverlayOptions")}
              </li>
            ) : (
              RESEARCH_OVERLAY_CHART_TYPES.map((chartType) => (
                <li key={chartType}>
                  <label
                    className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                      !hasResearchTarget
                        ? "cursor-not-allowed border-slate-700 bg-slate-900/60 text-slate-500 opacity-70"
                        : "border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      disabled={!hasResearchTarget}
                      checked={overlaySelected.has(chartType)}
                      onChange={() => hasResearchTarget && toggleOverlay(chartType)}
                      aria-label={researchChartTypeLabel(t, chartType)}
                    />
                    <span className="font-medium">{researchChartTypeLabel(t, chartType)}</span>
                  </label>
                </li>
              ))
            )
          ) : kind === "single" ? (
            emptySplit ? (
              <li className="rounded border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-400">
                {t("workspace.modalNoSplitOptions")}
              </li>
            ) : (
              RESEARCH_SPLIT_CHART_TYPES.map((chartType) => (
                <li key={chartType}>
                  <button
                    type="button"
                    disabled={!hasResearchTarget}
                    onClick={() => hasResearchTarget && setSplitType(chartType)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                      splitType === chartType
                        ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
                        : !hasResearchTarget
                          ? "cursor-not-allowed border-slate-700 bg-slate-900/60 text-slate-500 opacity-70"
                          : "border-slate-600 bg-slate-800/60 text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                    }`}
                  >
                    {researchChartTypeLabel(t, chartType)}
                  </button>
                </li>
              ))
            )
          ) : emptyAnalysis ? (
            <li className="rounded border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-400">
              {t("workspace.modalNoAnalysisOptions")}
            </li>
          ) : (
            RESEARCH_ANALYSIS_CHART_TYPES.map((chartType) => (
              <li key={chartType}>
                <button
                  type="button"
                  disabled={!hasResearchTarget}
                  onClick={() => hasResearchTarget && setAnalysisType(chartType)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                    analysisType === chartType
                      ? "border-indigo-500 bg-indigo-900/30 text-indigo-100"
                      : !hasResearchTarget
                        ? "cursor-not-allowed border-slate-700 bg-slate-900/60 text-slate-500 opacity-70"
                        : "border-slate-600 bg-slate-800/60 text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                  }`}
                >
                  {researchChartTypeLabel(t, chartType)}
                </button>
              </li>
            ))
          )}
        </ul>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800"
          >
            {t("common.cancel")}
          </button>
          {kind === "overlay" ? (
            <button
              type="button"
              onClick={handleOverlayAdd}
              disabled={!canAddOverlay}
              className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("common.add")}
            </button>
          ) : null}
          {kind === "single" ? (
            <button
              type="button"
              onClick={handleSplitAdd}
              disabled={!splitType || !hasResearchTarget}
              className="rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("common.add")}
            </button>
          ) : null}
          {kind === "analysis" ? (
            <button
              type="button"
              onClick={handleAnalysisAdd}
              disabled={!analysisType || !hasResearchTarget}
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
