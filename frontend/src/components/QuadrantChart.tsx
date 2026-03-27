"use client";

import { useMemo } from "react";

/** V2: historical trail + current point. Readable: lighter trail, dominant current, corner labels. */
const PADDING = { top: 28, right: 28, bottom: 36, left: 48 };
const AXIS_RANGE = 60;
const MAX_DISPLAY_POINTS = 28;

export function getNarrativeLabel(searchMomentum: number, coverageMomentum: number): string {
  if (searchMomentum > 0 && coverageMomentum > 0) return "Rising Narrative";
  if (searchMomentum > 0 && coverageMomentum <= 0) return "Emerging Interest";
  if (searchMomentum <= 0 && coverageMomentum > 0) return "Media Driven";
  return "Fading Narrative";
}

export function getFlowSummary(
  points: Array<{ t: string; coverage_momentum: number; search_momentum: number }>
): { current: string; previous: string | null; flowText: string } {
  if (!points.length) return { current: "—", previous: null, flowText: "—" };
  const current = getNarrativeLabel(points[points.length - 1].search_momentum, points[points.length - 1].coverage_momentum);
  if (points.length < 2) return { current, previous: null, flowText: `Current: ${current}` };
  const previous = getNarrativeLabel(points[points.length - 2].search_momentum, points[points.length - 2].coverage_momentum);
  const flowText = current === previous
    ? `Stable in ${current}`
    : `Moving toward ${current}`;
  return { current, previous, flowText };
}

type QuadrantPoint = { t: string; coverage_momentum: number; search_momentum: number };

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

const QUADRANT_LABELS: { x: number; y: number; label: string }[] = [
  { x: 0.88, y: 0.18, label: "Rising Narrative" },
  { x: 0.12, y: 0.18, label: "Emerging Interest" },
  { x: 0.88, y: 0.82, label: "Media Driven" },
  { x: 0.12, y: 0.82, label: "Fading Narrative" },
];

export function QuadrantChart({
  searchMomentum,
  coverageMomentum,
  points: historyPoints,
  height = 240,
  periodLabel,
}: {
  searchMomentum?: number;
  coverageMomentum?: number;
  points?: QuadrantPoint[] | null;
  height?: number;
  /** Selected period for time-aware summary (e.g. "1M", "3M"). */
  periodLabel?: string;
}) {
  const points: QuadrantPoint[] =
    historyPoints && historyPoints.length > 0
      ? historyPoints
      : searchMomentum != null && coverageMomentum != null
        ? [{ t: "", coverage_momentum: coverageMomentum, search_momentum: searchMomentum }]
        : [];

  const displayPoints = useMemo(
    () => (points.length > MAX_DISPLAY_POINTS ? sampleForDisplay(points, MAX_DISPLAY_POINTS) : points),
    [points]
  );

  const current = points.length > 0 ? points[points.length - 1] : null;
  const summary = getFlowSummary(points);
  const isHistoryMode = points.length > 1;

  const w = 400;
  const h = height - PADDING.top - PADDING.bottom;
  const chartW = w - PADDING.left - PADDING.right;
  const chartH = h;

  const xToSvg = (x: number) =>
    PADDING.left + ((x + AXIS_RANGE) / (2 * AXIS_RANGE)) * chartW;
  const yToSvg = (y: number) =>
    PADDING.top + ((AXIS_RANGE - y) / (2 * AXIS_RANGE)) * chartH;

  const ox = xToSvg(0);
  const oy = yToSvg(0);

  const pathD =
    displayPoints.length >= 2
      ? displayPoints
          .map((p, i) => `${i === 0 ? "M" : "L"} ${xToSvg(p.coverage_momentum)} ${yToSvg(p.search_momentum)}`)
          .join(" ")
      : "";

  const lastSegmentD =
    displayPoints.length >= 2
      ? `M ${xToSvg(displayPoints[displayPoints.length - 2].coverage_momentum)} ${yToSvg(displayPoints[displayPoints.length - 2].search_momentum)} L ${xToSvg(current!.coverage_momentum)} ${yToSvg(current!.search_momentum)}`
      : "";

  if (!current) {
    return (
      <div className="flex h-full min-h-[180px] items-center justify-center text-sm text-slate-500">
        No data
      </div>
    );
  }

  const cx = xToSvg(current.coverage_momentum);
  const cy = yToSvg(current.search_momentum);

  const historyDots = displayPoints.length > 1 ? displayPoints.slice(0, -1) : [];

  return (
    <div className="w-full overflow-x-auto">
      <p className="mb-1 text-center text-xs font-medium text-slate-300">
        Narrative Status: <span className="text-indigo-300">{summary.current}</span>
        {periodLabel ? ` · ${periodLabel}` : ""}
      </p>
      {summary.previous != null && (
        <p className="mb-1 text-center text-xs text-slate-500">
          Previous: {summary.previous} · Flow: {summary.flowText}
        </p>
      )}
      {points.length === 1 && (
        <p className="mb-2 text-center text-xs text-slate-500">
          Single point (select period for history)
        </p>
      )}
      <svg width={w} height={height} className="min-w-[280px]" aria-label={isHistoryMode ? `Quadrant flow: ${points.length} points` : "Quadrant single point"}>
        <line x1={PADDING.left} y1={oy} x2={PADDING.left + chartW} y2={oy} stroke="#334155" strokeWidth={1} />
        <line x1={ox} y1={PADDING.top} x2={ox} y2={PADDING.top + chartH} stroke="#334155" strokeWidth={1} />
        {QUADRANT_LABELS.map((q) => (
          <text
            key={q.label}
            x={PADDING.left + q.x * chartW}
            y={PADDING.top + q.y * chartH}
            textAnchor={q.x > 0.5 ? "end" : "start"}
            className="fill-slate-500"
            style={{ fontSize: 9 }}
          >
            {q.label}
          </text>
        ))}
        {pathD && (
          <path
            d={pathD}
            fill="none"
            stroke="#64748b"
            strokeWidth={1}
            strokeOpacity={0.35}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {lastSegmentD && (
          <path
            d={lastSegmentD}
            fill="none"
            stroke="#6366f1"
            strokeWidth={1.8}
            strokeOpacity={0.65}
            strokeLinecap="round"
          />
        )}
        {historyDots.map((p, i) => (
          <circle
            key={i}
            cx={xToSvg(p.coverage_momentum)}
            cy={yToSvg(p.search_momentum)}
            r={2}
            fill="#475569"
            fillOpacity={0.5}
          />
        ))}
        <circle
          cx={cx}
          cy={cy}
          r={10}
          fill="#818cf8"
          fillOpacity={1}
          stroke="#c7d2fe"
          strokeWidth={2.5}
        />
        <text
          x={cx}
          y={cy - 14}
          textAnchor="middle"
          className="fill-slate-200"
          style={{ fontSize: 10 }}
        >
          ({current.coverage_momentum.toFixed(0)}, {current.search_momentum.toFixed(0)})
        </text>
        <text
          x={PADDING.left + chartW / 2}
          y={height - 10}
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: 10 }}
        >
          Coverage Momentum
        </text>
        <text
          x={12}
          y={PADDING.top + chartH / 2}
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: 10 }}
          transform={`rotate(-90, 12, ${PADDING.top + chartH / 2})`}
        >
          Search Momentum
        </text>
      </svg>
    </div>
  );
}
