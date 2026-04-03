"use client";

import dynamic from "next/dynamic";
import { EntityInstitutionBiasBlock } from "@/components/entity/EntityInstitutionBiasBlock";
import { EntityRatingDistributionBlock } from "@/components/entity/EntityRatingDistributionBlock";
import { EntitySeriesVolumeBlock } from "@/components/entity/EntitySeriesVolumeBlock";
import { EntitySplitChart } from "@/components/entity/EntitySplitChart";

const Research3DViewer = dynamic(
  () => import("./Research3DViewer").then((m) => ({ default: m.Research3DViewer })),
  { ssr: false }
);

export const CHART_TYPES = [
  "asset_price",
  "sentiment",
  "momentum",
  "coverage",
  "custom_index",
  "three_d",
  "three_d_narrative",
  "three_d_derivative",
  "institution_bias",
  "rating_distribution",
] as const;

export type ChartType = (typeof CHART_TYPES)[number];

export const CHART_LABELS: Record<ChartType, string> = {
  asset_price: "Asset price",
  sentiment: "Sentiment",
  momentum: "Momentum",
  coverage: "Coverage",
  custom_index: "Custom index",
  three_d: "3D",
  three_d_narrative: "3D Narrative Space",
  three_d_derivative: "3D Derivative Space",
  institution_bias: "Institution bias",
  rating_distribution: "Rating distribution",
};

export type ResearchChartProps = {
  type: ChartType;
  hasContext?: boolean;
  entityId?: string | null;
  /** Entity-metric series period (same API as Target Data blocks). Defaults to 1M. */
  period?: string;
  onRemove?: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
};

function is3DType(t: ChartType): t is "three_d" | "three_d_narrative" | "three_d_derivative" {
  return t === "three_d" || t === "three_d_narrative" || t === "three_d_derivative";
}

function isDbBackedAnalysisType(t: ChartType): t is "institution_bias" | "rating_distribution" {
  return t === "institution_bias" || t === "rating_distribution";
}

function entitySeriesKind(
  type: ChartType
): "coverage" | "target_search" | "keywords_search" | null {
  if (type === "coverage") return "coverage";
  if (type === "momentum") return "target_search";
  if (type === "sentiment" || type === "custom_index") return "keywords_search";
  return null;
}

export function ResearchChart({
  type,
  hasContext = false,
  entityId,
  period = "1M",
  onRemove,
  onMoveUp,
  onMoveDown,
}: ResearchChartProps) {
  if (isDbBackedAnalysisType(type)) {
    return (
      <div className="relative flex h-full min-h-[120px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-6 text-center">
        {hasContext && entityId ? (
          <div className="w-full rounded-lg border border-slate-700 bg-slate-900/50">
            {type === "institution_bias" ? (
              <EntityInstitutionBiasBlock entityId={entityId} />
            ) : (
              <EntityRatingDistributionBlock entityId={entityId} />
            )}
          </div>
        ) : (
          <>
            <span className="rounded bg-slate-700/60 px-2 py-1 text-xs font-medium text-slate-400">Needs entity target</span>
            <p className="mt-2 text-sm text-slate-300">{CHART_LABELS[type]}</p>
            <p className="mt-1 text-xs text-slate-500">Set an Entity in Research Universe to enable this block.</p>
          </>
        )}
        <div className="absolute right-2 top-2 flex gap-1">
          {onMoveUp && <button type="button" onClick={onMoveUp} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move up">↑</button>}
          {onMoveDown && <button type="button" onClick={onMoveDown} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move down">↓</button>}
          {onRemove && <button type="button" onClick={onRemove} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300" title="Remove">×</button>}
        </div>
      </div>
    );
  }
  if (is3DType(type)) {
    const variant = type === "three_d_derivative" ? "derivative" : "narrative";
    return (
      <Research3DViewer
        variant={variant}
        hasContext={hasContext}
        onRemove={onRemove}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
      />
    );
  }

  if (hasContext && entityId && type === "asset_price") {
    return (
      <div className="relative flex h-full min-h-[120px] flex-col rounded-lg border border-slate-700 bg-slate-900/50 p-2">
        <div className="flex items-center justify-between gap-1">
          <span className="text-xs font-medium text-slate-400">{CHART_LABELS[type]}</span>
          <div className="flex items-center gap-0.5">
            {onMoveUp && (
              <button type="button" onClick={onMoveUp} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move up">
                ↑
              </button>
            )}
            {onMoveDown && (
              <button type="button" onClick={onMoveDown} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move down">
                ↓
              </button>
            )}
            {onRemove && (
              <button type="button" onClick={onRemove} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300" title="Remove block">
                ×
              </button>
            )}
          </div>
        </div>
        <div className="mt-1 min-h-0 flex-1 overflow-hidden">
          <EntitySplitChart entityId={entityId} period={period} rowHeight={200} />
        </div>
      </div>
    );
  }

  const seriesKind = entitySeriesKind(type);
  if (hasContext && entityId && seriesKind) {
    return (
      <div className="relative flex h-full min-h-[120px] flex-col rounded-lg border border-slate-700 bg-slate-900/50 p-2">
        <div className="flex items-center justify-between gap-1">
          <span className="text-xs font-medium text-slate-400">{CHART_LABELS[type]}</span>
          <div className="flex items-center gap-0.5">
            {onMoveUp && (
              <button type="button" onClick={onMoveUp} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move up">
                ↑
              </button>
            )}
            {onMoveDown && (
              <button type="button" onClick={onMoveDown} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move down">
                ↓
              </button>
            )}
            {onRemove && (
              <button type="button" onClick={onRemove} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300" title="Remove block">
                ×
              </button>
            )}
          </div>
        </div>
        <div className="mt-1 min-h-0 flex-1">
          <EntitySeriesVolumeBlock entityId={entityId} period={period} kind={seriesKind} />
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-[120px] flex-col rounded-lg border border-slate-700 bg-slate-900/50 p-3">
      <div className="flex items-center justify-between gap-1">
        <span className="text-xs font-medium text-slate-400">{CHART_LABELS[type]}</span>
        <div className="flex items-center gap-0.5">
          {onMoveUp && (
            <button
              type="button"
              onClick={onMoveUp}
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
              title="Move up"
            >
              ↑
            </button>
          )}
          {onMoveDown && (
            <button
              type="button"
              onClick={onMoveDown}
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
              title="Move down"
            >
              ↓
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300"
              title="Remove block"
            >
              ×
            </button>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-1 rounded bg-slate-800/40 p-3 text-center text-sm text-slate-500">
        {hasContext ? (
          <>
            <span className="font-medium text-slate-300">Not available</span>
            <span className="text-xs text-slate-500">This block type is not wired in this build.</span>
          </>
        ) : (
          <>
            <span className="font-medium text-amber-200/90">No research target configured</span>
            <span className="text-xs">Set instruments or target in Research Universe above.</span>
          </>
        )}
      </div>
    </div>
  );
}
