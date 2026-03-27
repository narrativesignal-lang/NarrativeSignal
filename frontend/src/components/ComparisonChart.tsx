"use client";

type Point = { t: string; value: number };
type SeriesLine = { symbol: string; points: Point[] };

const COLORS = ["#818cf8", "#34d399", "#f59e0b", "#f472b6"];

export function ComparisonChart({
  series,
  height = 240,
}: {
  series: SeriesLine[];
  height?: number;
}) {
  if (!series.length || series.every((s) => !s.points.length)) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500"
        style={{ height }}
      >
        No data
      </div>
    );
  }

  const allPoints = series.flatMap((s) => s.points);
  const values = allPoints.map((p) => p.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const padding = { top: 12, right: 12, bottom: 24, left: 44 };
  const w = 600;
  const h = height - padding.top - padding.bottom;
  const xScale = (i: number, n: number) => (n <= 1 ? padding.left : padding.left + (i / (n - 1)) * (w - padding.left - padding.right));
  const yScale = (v: number) => {
    const range = maxVal - minVal || 1;
    const normalized = (v - minVal) / range;
    return padding.top + h - normalized * h;
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg width={w} height={height} className="min-w-[300px]">
        {series.map((line, idx) => {
          const points = line.points;
          if (!points.length) return null;
          const d = points
            .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(i, points.length)} ${yScale(p.value)}`)
            .join(" ");
          return (
            <path
              key={line.symbol}
              d={d}
              fill="none"
              stroke={COLORS[idx % COLORS.length]}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs">
        {series.map((line, idx) => (
          <span key={line.symbol} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-3 rounded-sm"
              style={{ backgroundColor: COLORS[idx % COLORS.length] }}
            />
            {line.symbol}
          </span>
        ))}
      </div>
    </div>
  );
}
