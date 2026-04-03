"use client";

import { useMemo } from "react";

export type BlockStateKind =
  | "loading"
  | "ai_computing"
  | "partial_ai"
  | "no_data"
  | "disabled"
  | "admin_only_ai"
  | "error";

export function BlockStateMessage({
  kind,
  height,
  reason,
  etaSeconds,
  message,
}: {
  kind: BlockStateKind;
  /** Optional fixed height to keep chart area stable. */
  height?: number;
  /** Optional reason appended for no_data. */
  reason?: string | null;
  /** Optional ETA for ai_computing. */
  etaSeconds?: number | null;
  /** Optional custom message (e.g. error detail). */
  message?: string | null;
}) {
  const text = useMemo(() => {
    if (message && kind === "error") return message;
    if (kind === "loading") return "Loading data...";
    if (kind === "disabled") return "Disabled by system";
    if (kind === "admin_only_ai") return "Admin only (AI feature)";
    if (kind === "partial_ai") return "Updating... (AI)";
    if (kind === "ai_computing") {
      const eta = typeof etaSeconds === "number" && etaSeconds > 0 ? ` ~${Math.round(etaSeconds)} seconds` : "";
      return `Computing (AI)...${eta}`;
    }
    if (kind === "no_data") return `No data yet${reason ? ` — ${reason}` : ""}`;
    return message || "—";
  }, [kind, message, reason, etaSeconds]);

  const cls =
    kind === "error"
      ? "text-amber-200"
      : kind === "disabled" || kind === "admin_only_ai"
        ? "text-slate-400"
        : "text-slate-500";

  return (
    <div
      className={`flex items-center justify-center rounded bg-slate-900/50 px-3 text-center text-sm ${cls}`}
      style={height ? { height } : undefined}
    >
      <span className="text-balance break-words whitespace-pre-line">{text}</span>
    </div>
  );
}

