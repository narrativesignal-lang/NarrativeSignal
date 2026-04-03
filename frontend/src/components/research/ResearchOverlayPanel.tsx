"use client";

import { EntityMathOverlayChart } from "@/components/entity/EntityMathOverlayChart";
import { RESEARCH_OVERLAY_TYPE_TO_ENTITY_KEY } from "./researchBlockRegistry";
import type { PanelConfig } from "./researchTypes";
import type { ChartType } from "./ResearchChart";

export function ResearchOverlayPanel({
  panel,
  entityId,
  period = "1M",
}: {
  panel: PanelConfig;
  entityId: string | null;
  period?: string;
}) {
  const types: ChartType[] =
    panel.overlayTypes && panel.overlayTypes.length > 0 ? panel.overlayTypes : [panel.type];
  const keys = [
    ...new Set(
      types
        .map((t) => RESEARCH_OVERLAY_TYPE_TO_ENTITY_KEY[t])
        .filter((k): k is string => typeof k === "string" && k.length > 0)
    ),
  ];

  if (entityId && keys.length > 0) {
    return <EntityMathOverlayChart entityId={entityId} period={period} seriesKeys={keys} height={260} />;
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/50 px-4 py-6 text-center text-sm text-slate-400">
      <p className="font-medium text-slate-300">Overlay chart</p>
      <p className="mt-2 text-xs text-slate-500">
        Attach an <strong className="text-slate-400">entity</strong> target in Research Universe to load aligned
        metric series for this overlay.
      </p>
    </div>
  );
}
