"use client";

import { EntityStackedCandleCharts } from "@/components/entity/EntityStackedCandleCharts";

/** Price + volume (OHLCV) per instrument — primary and related — stacked. */
export function EntitySplitChart({
  entityId,
  period = "1M",
  rowHeight = 200,
}: {
  entityId: string;
  period?: string;
  rowHeight?: number;
}) {
  return <EntityStackedCandleCharts entityId={entityId} period={period} rowHeight={rowHeight} />;
}
