"use client";

const LABELS: Record<string, string> = {
  search_volume: "Search Trend Index",
  search_momentum: "Search Momentum",
  search_acceleration: "Search Acceleration",
  coverage_volume: "Coverage Volume",
  coverage_momentum: "Coverage Momentum",
  sentiment_score: "Sentiment Score",
  quadrant_flow: "Narrative Flow",
};

export function EntitySkillChart({
  skillId,
  onRemove,
}: {
  skillId: string;
  onRemove: () => void;
}) {
  const title = LABELS[skillId] ?? skillId;
  return (
    <div className="flex flex-col rounded-lg border border-slate-700 bg-slate-900/50 p-3">
      <div className="flex items-center justify-between border-b border-slate-700/80 pb-2">
        <span className="text-xs font-semibold text-slate-300">{title}</span>
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300"
          title="Remove chart"
        >
          ×
        </button>
      </div>
      <div className="mt-2 flex h-24 items-center justify-center rounded bg-slate-800/40 text-xs text-slate-500">
        Chart placeholder
      </div>
    </div>
  );
}
