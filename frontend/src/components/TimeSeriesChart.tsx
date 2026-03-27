"use client";

type Point = { t: string; value: number };

const LINE_COLOR = "#818cf8";

export function TimeSeriesChart({
  points,
  height = 240,
}: {
  points: Point[];
  height?: number;
}) {
  if (!points.length) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/50 text-sm text-slate-500"
        style={{ height }}
      >
        No data
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const padding = { top: 12, right: 12, bottom: 24, left: 44 };
  const w = 600;
  const h = height - padding.top - padding.bottom;
  const xScale = (i: number, n: number) =>
    n <= 1 ? padding.left : padding.left + (i / (n - 1)) * (w - padding.left - padding.right);
  const yScale = (v: number) => {
    const range = maxVal - minVal || 1;
    const normalized = (v - minVal) / range;
    return padding.top + h - normalized * h;
  };

  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(i, points.length)} ${yScale(p.value)}`)
    .join(" ");

  return (
    <div className="w-full overflow-x-auto">
      <svg width={w} height={height} className="min-w-[300px]">
        <path
          d={d}
          fill="none"
          stroke={LINE_COLOR}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
