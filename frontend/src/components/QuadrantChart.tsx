"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { BlockStateMessage } from "@/components/BlockStateMessage";

/** Centered 4-quadrant plot: x = coverage deviation from period mean, y = keywords search deviation from period mean. */
const PADDING = { top: 28, right: 28, bottom: 44, left: 56 };
const EPS = 1e-9;
const MAX_DISPLAY_POINTS = 40;

export type QuadrantPoint = { t: string; coverage_volume: number; keywords_search_volume: number };

function mean(nums: number[]): number {
  if (!nums.length) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function sampleForDisplay(points: QuadrantPoint[], maxPoints: number): QuadrantPoint[] {
  if (points.length <= maxPoints) return points;
  const step = (points.length - 1) / (maxPoints - 1);
  const out: QuadrantPoint[] = [];
  for (let i = 0; i < maxPoints; i++) {
    const idx = i === maxPoints - 1 ? points.length - 1 : Math.round(i * step);
    out.push(points[idx]);
  }
  return out;
}

/** Label placement in axis space: x = cx0 + ox·halfW, y = cy0 − oy·halfH (oy>0 is upper half of chart). */
const QUADRANT_CORNER_LABELS: { ox: number; oy: number; label: string }[] = [
  { ox: 0.62, oy: 0.62, label: "Coverage above avg · Search above avg" },
  { ox: -0.62, oy: 0.62, label: "Coverage below avg · Search above avg" },
  { ox: -0.62, oy: -0.62, label: "Coverage below avg · Search below avg" },
  { ox: 0.62, oy: -0.62, label: "Coverage above avg · Search below avg" },
];

export function QuadrantChart({
  points: historyPoints,
  periodLabel,
}: {
  points?: QuadrantPoint[] | null;
  periodLabel?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [plot, setPlot] = useState(400);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      const side = Math.max(240, Math.min(w || 400, h || w || 400, 720));
      setPlot(side);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const points = useMemo(() => {
    if (!historyPoints?.length) return [];
    return historyPoints.filter(
      (p) => Number.isFinite(p.coverage_volume) && Number.isFinite(p.keywords_search_volume)
    );
  }, [historyPoints]);

  const displayPoints = useMemo(
    () => (points.length > MAX_DISPLAY_POINTS ? sampleForDisplay(points, MAX_DISPLAY_POINTS) : points),
    [points]
  );

  const devs = useMemo(() => {
    if (!points.length) return [];
    const mx = mean(points.map((p) => p.coverage_volume));
    const my = mean(points.map((p) => p.keywords_search_volume));
    return points.map((p) => ({
      t: p.t,
      dx: p.coverage_volume - mx,
      dy: p.keywords_search_volume - my,
    }));
  }, [points]);

  const displayDevs = useMemo(() => {
    if (!displayPoints.length) return [];
    const mx = mean(points.map((p) => p.coverage_volume));
    const my = mean(points.map((p) => p.keywords_search_volume));
    return displayPoints.map((p) => ({
      t: p.t,
      dx: p.coverage_volume - mx,
      dy: p.keywords_search_volume - my,
    }));
  }, [displayPoints, points]);

  const { maxAbsX, maxAbsY } = useMemo(() => {
    if (!devs.length) return { maxAbsX: EPS, maxAbsY: EPS };
    const ax = Math.max(EPS, ...devs.map((d) => Math.abs(d.dx)));
    const ay = Math.max(EPS, ...devs.map((d) => Math.abs(d.dy)));
    return { maxAbsX: ax, maxAbsY: ay };
  }, [devs]);

  const width = plot;
  const height = plot;
  const chartW = width - PADDING.left - PADDING.right;
  const chartH = height - PADDING.top - PADDING.bottom;
  const cx0 = PADDING.left + chartW / 2;
  const cy0 = PADDING.top + chartH / 2;
  const halfW = chartW / 2;
  const halfH = chartH / 2;

  const toSvg = (dx: number, dy: number) => ({
    x: cx0 + (dx / maxAbsX) * halfW,
    y: cy0 - (dy / maxAbsY) * halfH,
  });

  const pathD =
    displayDevs.length >= 2
      ? displayDevs
          .map((d, i) => {
            const { x, y } = toSvg(d.dx, d.dy);
            return `${i === 0 ? "M" : "L"} ${x} ${y}`;
          })
          .join(" ")
      : "";

  const last = devs.length ? devs[devs.length - 1] : null;
  const lastSvg = last ? toSvg(last.dx, last.dy) : null;

  if (!points.length) {
    return (
      <div ref={containerRef} className="h-full min-h-[200px] w-full min-w-0">
        <BlockStateMessage
          kind="no_data"
          height={200}
          reason="Insufficient quadrant data for this period (need coverage and keywords search history)."
        />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex h-full min-h-0 w-full min-w-0 flex-col items-center">
      <p className="mb-1 max-w-xl text-center text-xs text-slate-400">
        Axes centered at period mean. X = coverage volume minus mean; Y = keywords search volume minus mean.
        {periodLabel ? ` · ${periodLabel}` : ""}
      </p>
      {last ? (
        <p className="mb-1 text-center text-[11px] text-slate-500">
          Latest Δ mean: coverage {last.dx >= 0 ? "+" : ""}
          {last.dx.toFixed(2)}, search {last.dy >= 0 ? "+" : ""}
          {last.dy.toFixed(2)}
        </p>
      ) : null}
      <svg
        width={width}
        height={height}
        className="max-h-[85vh] max-w-full shrink-0"
        aria-label="Quadrant chart: coverage vs search deviation from mean"
      >
        <line
          x1={PADDING.left}
          y1={cy0}
          x2={PADDING.left + chartW}
          y2={cy0}
          stroke="#475569"
          strokeWidth={1.2}
        />
        <line
          x1={cx0}
          y1={PADDING.top}
          x2={cx0}
          y2={PADDING.top + chartH}
          stroke="#475569"
          strokeWidth={1.2}
        />
        {QUADRANT_CORNER_LABELS.map((q) => {
          const tx = cx0 + q.ox * halfW;
          const ty = cy0 - q.oy * halfH;
          return (
            <text
              key={q.label}
              x={tx}
              y={ty}
              textAnchor="middle"
              className="fill-slate-600"
              style={{ fontSize: 9 }}
            >
              {q.label}
            </text>
          );
        })}
        {pathD ? (
          <path
            d={pathD}
            fill="none"
            stroke="#64748b"
            strokeWidth={1.2}
            strokeOpacity={0.45}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : null}
        {displayDevs.length > 1
          ? displayDevs.slice(0, -1).map((d, i) => {
              const { x, y } = toSvg(d.dx, d.dy);
              return <circle key={i} cx={x} cy={y} r={2} fill="#475569" fillOpacity={0.55} />;
            })
          : null}
        {lastSvg ? (
          <>
            <circle
              cx={lastSvg.x}
              cy={lastSvg.y}
              r={9}
              fill="#818cf8"
              fillOpacity={0.95}
              stroke="#c7d2fe"
              strokeWidth={2}
            />
            <text
              x={lastSvg.x}
              y={lastSvg.y - 14}
              textAnchor="middle"
              className="fill-slate-200"
              style={{ fontSize: 9 }}
            >
              ({last!.dx.toFixed(1)}, {last!.dy.toFixed(1)})
            </text>
          </>
        ) : null}
        <text
          x={cx0}
          y={height - 12}
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: 10 }}
        >
          Coverage Δ vs period mean
        </text>
        <text
          x={14}
          y={cy0}
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: 10 }}
          transform={`rotate(-90, 14, ${cy0})`}
        >
          Keywords search Δ vs period mean
        </text>
      </svg>
    </div>
  );
}
