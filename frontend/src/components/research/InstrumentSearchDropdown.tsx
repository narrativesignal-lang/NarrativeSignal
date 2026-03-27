"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { INSTRUMENT_CATEGORIES } from "@/lib/instrumentCategories";
import { useI18n } from "@/lib/i18n";

/** Minimal shape for instrument search result; API returns more fields. */
export type InstrumentSearchHit = {
  id: string;
  symbol: string;
  display_name: string | null;
  asset_class: string;
  exchange?: string | null;
  country?: string | null;
};

const MAX_SUGGESTIONS = 8;

export function InstrumentSearchDropdown<T extends InstrumentSearchHit>({
  open,
  onOpenChange,
  query,
  onQueryChange,
  results,
  loading,
  onSelect,
  selectedIds,
  category,
  onCategoryChange,
  placeholder = "Search symbol…",
  triggerLabel = "+ Add instrument",
  showCategoryFilter = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  query: string;
  onQueryChange: (q: string) => void;
  results: T[];
  loading?: boolean;
  onSelect: (inst: T) => void;
  selectedIds?: string[];
  category?: string;
  onCategoryChange?: (c: string) => void;
  placeholder?: string;
  triggerLabel?: string;
  showCategoryFilter?: boolean;
}) {
  const { t } = useI18n();
  const [highlightIndex, setHighlightIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = (selectedIds?.length
    ? results.filter((r) => !selectedIds.includes(r.id))
    : results
  ).slice(0, MAX_SUGGESTIONS);

  useEffect(() => {
    setHighlightIndex(0);
  }, [query, results]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else onQueryChange("");
  }, [open, onQueryChange]);

  const addHighlighted = useCallback(() => {
    const inst = filtered[highlightIndex];
    if (inst) {
      onSelect(inst);
      onOpenChange(false);
    }
  }, [filtered, highlightIndex, onSelect, onOpenChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        onOpenChange(false);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        addHighlighted();
        return;
      }
    },
    [filtered.length, addHighlighted, onOpenChange]
  );

  const showDropdown = open && query.trim().length > 0;
  const noMatch = showDropdown && !loading && filtered.length === 0;

  return (
    <div className="relative inline-block">
      {open ? (
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              setTimeout(() => onOpenChange(false), 150);
            }}
            placeholder={placeholder}
            className="w-36 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 outline-none focus:border-slate-600"
          />
            <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="ml-1 text-xs text-slate-500 hover:text-slate-300"
          >
            {t("common.done")}
          </button>
          {showDropdown && (
            <div
              ref={listRef}
              className="absolute left-0 top-full z-10 mt-0.5 max-h-48 w-56 overflow-auto rounded border border-slate-700 bg-slate-900 py-1 shadow-lg"
            >
              {loading ? (
                <div className="px-3 py-2 text-xs text-slate-500">{t("research.searching")}</div>
              ) : noMatch ? (
                <div className="px-3 py-2 text-xs text-slate-500">{t("research.noMatches")}</div>
              ) : (
                filtered.map((inst, i) => (
                  <button
                    key={inst.id}
                    type="button"
                    onClick={() => {
                      onSelect(inst);
                      onOpenChange(false);
                    }}
                    onMouseEnter={() => setHighlightIndex(i)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs ${
                      i === highlightIndex ? "bg-slate-700 text-slate-100" : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-medium">{inst.symbol}</span>
                      {inst.display_name ? (
                        <span className="ml-1 truncate text-slate-500">· {inst.display_name}</span>
                      ) : null}
                    </div>
                    <span className="shrink-0 text-slate-500">
                      {inst.asset_class}
                      {(inst.exchange || inst.country) ? ` · ${inst.exchange || inst.country}` : ""}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className="rounded border border-dashed border-slate-600 px-1.5 py-0.5 text-xs text-slate-500 hover:border-slate-500 hover:text-slate-300"
        >
          {triggerLabel}
        </button>
      )}
    </div>
  );
}
