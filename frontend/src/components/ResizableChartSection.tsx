"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const MIN_HEIGHT = 220;
const MAX_HEIGHT = 700;
const DEFAULT_HEIGHT = 320;
const HANDLE_HEIGHT = 8;

export type ResizableChartSectionProps = {
  children: React.ReactNode;
  height: number;
  onHeightChange: (height: number) => void;
  minHeight?: number;
  maxHeight?: number;
  className?: string;
};

export function ResizableChartSection({
  children,
  height,
  onHeightChange,
  minHeight = MIN_HEIGHT,
  maxHeight = MAX_HEIGHT,
  className = "",
}: ResizableChartSectionProps) {
  const [isDragging, setIsDragging] = useState(false);
  const startY = useRef(0);
  const startHeight = useRef(height);

  const clamp = useCallback(
    (value: number) => Math.min(maxHeight, Math.max(minHeight, value)),
    [minHeight, maxHeight]
  );

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);
      startY.current = e.clientY;
      startHeight.current = height;
    },
    [height]
  );

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      setIsDragging(true);
      startY.current = e.touches[0].clientY;
      startHeight.current = height;
    },
    [height]
  );

  const onMove = useCallback(
    (clientY: number) => {
      const delta = clientY - startY.current;
      const next = clamp(startHeight.current + delta);
      onHeightChange(next);
    },
    [clamp, onHeightChange]
  );

  useEffect(() => {
    if (!isDragging) return;
    const onMouseMove = (e: MouseEvent) => onMove(e.clientY);
    const onMouseUp = () => setIsDragging(false);
    const onTouchMove = (e: TouchEvent) => {
      e.preventDefault();
      onMove(e.touches[0].clientY);
    };
    const onTouchEnd = () => setIsDragging(false);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };
  }, [isDragging, onMove]);

  const handleHeightPx = HANDLE_HEIGHT;

  return (
    <div
      className={`relative overflow-hidden ${className}`}
      style={{ height: `${height}px` }}
    >
      <div className="w-full overflow-hidden" style={{ height: `${height - handleHeightPx}px`, minHeight: 0 }}>
        {children}
      </div>
      <div
        role="separator"
        aria-label="Resize chart"
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
        className={`absolute bottom-0 left-0 right-0 cursor-n-resize border-t border-slate-700 bg-slate-800/80 hover:bg-slate-700/80 flex items-center justify-center transition-colors ${isDragging ? "bg-indigo-600/30" : ""}`}
        style={{ height: `${handleHeightPx}px` }}
      >
        <span className="text-slate-500 text-xs select-none" aria-hidden>
          ⋮
        </span>
      </div>
    </div>
  );
}

export const RESIZE_HANDLE_HEIGHT = HANDLE_HEIGHT;
export { MIN_HEIGHT as RESIZE_MIN_HEIGHT, MAX_HEIGHT as RESIZE_MAX_HEIGHT, DEFAULT_HEIGHT as RESIZE_DEFAULT_HEIGHT };
