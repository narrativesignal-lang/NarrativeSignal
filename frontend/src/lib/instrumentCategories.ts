/** Instrument search category filter (maps to backend). */
export const INSTRUMENT_CATEGORIES = [
  { value: "", label: "All" },
  { value: "stock", label: "Stock" },
  { value: "etf", label: "ETF" },
  { value: "index", label: "Index" },
  { value: "futures", label: "Futures" },
  { value: "crypto", label: "Crypto" },
  { value: "hong kong", label: "Hong Kong" },
] as const;
