"use client";

import { EntityStackedCandleCharts } from "@/components/entity/EntityStackedCandleCharts";

/** Same OHLCV + volume stack as split; overlay layout choice lives on Research only. */
export function EntityOverlayChart({
  entityId,
  period = "1M",
  height = 200,
}: {
  entityId: string;
  period?: string;
  height?: number;
}) {
  return <EntityStackedCandleCharts entityId={entityId} period={period} rowHeight={height} />;
}
