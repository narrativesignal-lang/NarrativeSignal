"use client";

import { useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

const LABELS: Record<Locale, string> = {
  en: "EN",
  zh: "中文",
  es: "ES",
  pt: "PT",
};

export function LanguageSelector() {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:border-slate-500 hover:text-slate-200"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label="Select language"
      >
        {LABELS[locale]}
      </button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            aria-hidden
            onClick={() => setOpen(false)}
          />
          <div
            className="absolute right-0 top-full z-50 mt-0.5 min-w-[6rem] rounded border border-slate-700 bg-slate-900 py-1 shadow-lg"
            role="listbox"
          >
            {(["en", "zh", "es", "pt"] as Locale[]).map((l) => (
              <button
                key={l}
                type="button"
                role="option"
                aria-selected={locale === l}
                onClick={() => {
                  setLocale(l);
                  setOpen(false);
                }}
                className={`block w-full px-3 py-1.5 text-left text-xs ${
                  locale === l ? "bg-slate-700 text-slate-100" : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                {LABELS[l]}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
