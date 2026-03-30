"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";

const DEFAULT_DELAY_MS = 1200;

/** After `delayMs`, sets true while `pending` remains true; resets when `pending` becomes false. */
export function useSlowLoadVisible(pending: boolean, delayMs = DEFAULT_DELAY_MS): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!pending) {
      setVisible(false);
      return;
    }
    const t = window.setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(t);
  }, [pending, delayMs]);

  return visible;
}

export function SlowLoadBanner({ visible }: { visible: boolean }) {
  const { t } = useI18n();
  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-slate-700/70 bg-slate-900/85 px-3 py-2 text-[11px] leading-snug text-slate-400 shadow-sm backdrop-blur-sm"
    >
      {t("common.slowInitialLoad")}
    </div>
  );
}
