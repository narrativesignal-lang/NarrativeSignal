"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";

import { chartVisibleRangeToUnix } from "@/lib/chartTimeUnix";
import type { ChartVisibleTimeRange } from "@/lib/chartTimeUnix";

export type { ChartVisibleTimeRange };

type Bar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

const DEFAULT_CHART_HEIGHT = 256;

export function CandleChart({
  bars,
  height = DEFAULT_CHART_HEIGHT,
  onVisibleTimeRangeChange,
}: {
  bars: Bar[];
  height?: number;
  /** Fires when the user zooms/pans or the chart fits data; null when range unknown. */
  onVisibleTimeRangeChange?: (range: ChartVisibleTimeRange | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const onRangeRef = useRef(onVisibleTimeRangeChange);
  onRangeRef.current = onVisibleTimeRangeChange;

  const data = useMemo(
    () =>
      (bars || []).map((b) => ({
        time: b.time as import("lightweight-charts").UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    [bars]
  );

  const volumes = useMemo(
    () =>
      (bars || []).map((b) => ({
        time: b.time as import("lightweight-charts").UTCTimestamp,
        value: b.volume,
        color: b.close >= b.open ? "rgba(16, 185, 129, 0.55)" : "rgba(239, 68, 68, 0.55)",
      })),
    [bars]
  );

  const emitRange = (chart: IChartApi) => {
    const cb = onRangeRef.current;
    if (!cb) return;
    const r = chart.timeScale().getVisibleRange();
    cb(chartVisibleRangeToUnix(r));
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#cbd5e1",
      },
      grid: {
        vertLines: { color: "#1f2a37" },
        horzLines: { color: "#1f2a37" },
      },
      rightPriceScale: {
        borderColor: "#334155",
      },
      timeScale: {
        borderColor: "#334155",
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "rgba(99,102,241,0.4)",
    });

    volume.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    candles.priceScale().applyOptions({
      scaleMargins: { top: 0.08, bottom: 0.28 },
    });

    chartRef.current = chart;
    candleRef.current = candles;
    volumeRef.current = volume;

    const onVisibleRangeChange = () => emitRange(chart);
    chart.timeScale().subscribeVisibleTimeRangeChange(onVisibleRangeChange);

    const resizeChart = (w: number, h: number) => {
      if (w > 0 && h > 0) chart.resize(w, h);
    };

    resizeChart(container.clientWidth, container.clientHeight);

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height: h } = entry.contentRect;
      resizeChart(width, h);
      requestAnimationFrame(() => emitRange(chart));
    });
    resizeObserver.observe(container);

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(onVisibleRangeChange);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    const chart = chartRef.current;
    if (!chart) return;
    candleRef.current.setData(data);
    volumeRef.current.setData(volumes);
    chart.timeScale().fitContent();
    requestAnimationFrame(() => emitRange(chart));
  }, [data, volumes, height]);

  return (
    <div className="relative w-full overflow-hidden" style={{ height: `${height}px` }}>
      <div ref={containerRef} className="h-full w-full" style={{ minHeight: 0 }} />
    </div>
  );
}
