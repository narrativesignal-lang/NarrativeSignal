"use client";

import { EntityMathOverlayChart } from "@/components/entity/EntityMathOverlayChart";

/** Multi-series math overlay on the entity period timeline (normalized per series). */
export function EntityOverlayChart({
  entityId,
  period = "1M",
  height = 260,
  overlaySeries,
}: {
  entityId: string;
  period?: string;
  height?: number;
  /** Persisted keys; legacy blocks without this default to price close only. */
  overlaySeries?: readonly string[] | null;
}) {
  const keys =
    overlaySeries && overlaySeries.length > 0 ? overlaySeries : (["price_close"] as const);
  return <EntityMathOverlayChart entityId={entityId} period={period} height={height} seriesKeys={keys} />;
}
