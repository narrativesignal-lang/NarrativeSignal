"use client";

const LABELS: Record<string, string> = {
  search_volume: "Search Volume",
  search_momentum: "Search Momentum",
  search_acceleration: "Search Acceleration",
  coverage_volume: "Coverage Volume",
  coverage_momentum: "Coverage Momentum",
  coverage_acceleration: "Coverage Acceleration",
  sentiment_score: "Sentiment Score",
  quadrant_flow: "Narrative Flow",
  order_flow: "Order Flow",
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
      {skillId === "order_flow" ? (
        <div className="mt-2 rounded bg-slate-800/40 p-3 text-[11px] text-slate-300">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium">Order Flow</span>
            <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-medium uppercase text-amber-300">
              Placeholder
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Live order flow feed not connected yet. This block will use market depth and trade-flow data when available.
          </p>
          <ul className="mt-2 list-inside list-disc space-y-0.5 text-[11px] text-slate-400">
            <li>Bid/Ask Imbalance</li>
            <li>Aggressive Buy vs Sell</li>
            <li>Depth Pressure</li>
            <li>Liquidity Absorption</li>
            <li>Flow Delta</li>
          </ul>
        </div>
      ) : (
        <div className="mt-2 flex h-24 items-center justify-center rounded bg-slate-800/40 text-xs text-slate-500">
          Chart placeholder
        </div>
      )}
    </div>
  );
}
