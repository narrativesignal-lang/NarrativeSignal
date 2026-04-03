"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Shell } from "@/components/Shell";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

type FlagRow = {
  key: string;
  value_bool: boolean;
  updated_at: string | null;
  updated_by: string | null;
};

type RuntimeLogRow = {
  created_at: string;
  level: string;
  category: string;
  job_name: string | null;
  provider: string | null;
  status: string | null;
  message: string;
  disabled_by_runtime_flag: boolean;
  no_provider_call: boolean;
  request_count: number | null;
  fallback_count: number | null;
  symbol_count: number | null;
};

type FlagMeta = {
  key: string;
  group: "External Providers" | "AI Features" | "Jobs / Schedules" | "News / Trends / Warmups";
  label: string;
  description: string;
};

const META: FlagMeta[] = [
  {
    key: "ENABLE_EXTERNAL_PROVIDERS",
    group: "External Providers",
    label: "Global external providers",
    description: "Global kill switch for any outbound provider calls. Snapshot-only reads still work.",
  },
  { key: "ENABLE_TWELVE_QUOTES", group: "External Providers", label: "Twelve: quotes", description: "Allow Twelve batch quote refresh." },
  { key: "ENABLE_TWELVE_OHLCV", group: "External Providers", label: "Twelve: OHLCV", description: "Allow Twelve time_series OHLCV refresh (batch-shaped adapter)." },
  { key: "ENABLE_YAHOO_QUOTES", group: "External Providers", label: "Yahoo: quotes", description: "Allow Yahoo batch quote refresh (yfinance)." },
  { key: "ENABLE_YAHOO_OHLCV", group: "External Providers", label: "Yahoo: OHLCV", description: "Allow Yahoo batch OHLCV refresh (yfinance)." },
  { key: "ENABLE_STOOQ_FALLBACK", group: "External Providers", label: "Fallback provider (Stooq)", description: "Allow fallback provider adapter for quotes/OHLCV when primary stages miss." },

  { key: "ENABLE_PYTRENDS", group: "News / Trends / Warmups", label: "Google Trends (pytrends)", description: "Allow search trend collection. When off, search trend becomes unavailable without breaking sync." },
  { key: "ENABLE_FETCH_MACRO_NEWS", group: "News / Trends / Warmups", label: "Macro news fetch", description: "Allow macro news fetching/refresh tasks." },
  { key: "ENABLE_STARTUP_WARMUPS", group: "News / Trends / Warmups", label: "Startup warmups", description: "Allow API-process startup warmups (may call external providers in background)." },

  { key: "ENABLE_MASSIVE_BACKFILL", group: "Jobs / Schedules", label: "Massive market repair (background)", description: "Enables the rolling repair scan (sole Massive API path). Backfill job does not call Massive; hard quotas apply in massive_api_client." },
  { key: "ENABLE_MASSIVE_ANALYSIS", group: "Jobs / Schedules", label: "Narrative heuristic analysis job", description: "Allow scheduled entity_analysis upserts from stored metrics (no Massive API)." },

  { key: "ENABLE_AI_FEATURES", group: "AI Features", label: "Global AI features", description: "Global kill switch for all AI features. When off, no AI provider calls happen." },
  { key: "ENABLE_AI_KEYWORD_SUGGESTIONS", group: "AI Features", label: "AI: keyword suggestions", description: "Enable POST /api/ai/keyword-suggestions (Gemini role=verify)." },
  { key: "ENABLE_AI_TIMELINE_SUMMARY", group: "AI Features", label: "AI: timeline summary", description: "Enable timeline AI summary endpoint. When off, returns structured disabled payload." },
  { key: "ENABLE_AI_RANGE_ANALYSIS", group: "AI Features", label: "AI: range summary", description: "Enable POST /api/ai/range-summary (OpenAI; stored context only)." },
  { key: "ENABLE_AI_REPORT_GENERATION", group: "AI Features", label: "AI: report generation", description: "Enable AI report schedule pipeline." },
  { key: "ENABLE_AI_ALERTS", group: "AI Features", label: "AI: alerts", description: "Enable AI alert schedule pipeline." },
  { key: "ENABLE_AI_DOCUMENT_ANALYSIS", group: "AI Features", label: "AI: document analysis", description: "Enable document analysis LLM calls." },
  { key: "ENABLE_AI_NEWS_SUMMARY", group: "AI Features", label: "AI: news summary", description: "Enable AI news summarization endpoints/pipelines." },
  { key: "ENABLE_AI_SIMILAR_EVENT_ANALYSIS", group: "AI Features", label: "AI: similar event analysis", description: "Enable similar-event analysis endpoints/pipelines." },
  { key: "ENABLE_AI_NARRATIVE_ANALYSIS", group: "AI Features", label: "AI: narrative analysis", description: "Enable narrative analysis endpoints/pipelines." },
  { key: "ENABLE_AI_PRICE_MOVE_EXPLANATION", group: "AI Features", label: "AI: price move explanation", description: "Enable structured price move explanation endpoint (schema-only)." },
  { key: "ENABLE_AI_COMPARE_SUMMARY", group: "AI Features", label: "AI: compare summary", description: "Enable structured compare summary endpoint (schema-only)." },
];

function groupOrder(g: FlagMeta["group"]) {
  if (g === "External Providers") return 0;
  if (g === "AI Features") return 1;
  if (g === "Jobs / Schedules") return 2;
  return 3;
}

export default function AdminRuntimeFlagsPage() {
  const { user, loading: userLoading } = useUser();
  const { t } = useI18n();
  const [rows, setRows] = useState<FlagRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [patchingKey, setPatchingKey] = useState<string | null>(null);
  const [logs, setLogs] = useState<RuntimeLogRow[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logsCategory, setLogsCategory] = useState<"all" | "provider" | "job" | "ai">("all");
  const [logsMinLevel, setLogsMinLevel] = useState<"all" | "warning-error">("all");
  const flagsLoadedOnceRef = useRef(false);

  useEffect(() => {
    if (userLoading) return;
    if (!user?.is_admin) {
      setLoading(false);
      return;
    }
    if (flagsLoadedOnceRef.current) {
      console.log("[runtime-flags] skip reloading flags (already loaded once)");
      return;
    }
    setLoading(true);
    console.log("[runtime-flags] loading flags (initial)");
    api
      .listRuntimeFlags()
      .then((r) => {
        console.log("[runtime-flags] loaded flags count", Array.isArray(r) ? r.length : -1);
        setRows(r);
        flagsLoadedOnceRef.current = true;
      })
      .catch((e: unknown) => setError(parseApiError(e)))
      .finally(() => setLoading(false));
  }, [userLoading, user?.is_admin, user?.id]);

  const loadLogs = async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const rows2 = await api.listRuntimeLogs({
        limit: 50,
        category: logsCategory,
        min_level: logsMinLevel === "warning-error" ? "warning" : undefined,
      });
      setLogs(rows2);
    } catch (e: unknown) {
      setLogsError(parseApiError(e));
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    if (!user?.is_admin) return;
    if (loading) return;
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.is_admin, loading, logsCategory, logsMinLevel]);

  const map = useMemo(() => {
    const m = new Map<string, FlagRow>();
    for (const r of rows) m.set(r.key, r);
    return m;
  }, [rows]);

  const visible = useMemo(() => {
    // Prefer showing known flags (META ordering), but also show any unknown flags returned by backend.
    const known = META.map((m) => ({ meta: m, row: map.get(m.key) })).filter((x) => !!x.row) as Array<{
      meta: FlagMeta;
      row: FlagRow;
    }>;
    const knownKeys = new Set(known.map((x) => x.row.key));
    const unknown = rows
      .filter((r) => !knownKeys.has(r.key))
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((r) => ({
        meta: {
          key: r.key,
          group: "Jobs / Schedules" as const,
          label: r.key,
          description: "No UI metadata (new flag discovered from backend).",
        },
        row: r,
      }));
    const all = [...known, ...unknown];
    all.sort((a, b) => {
      const go = groupOrder(a.meta.group) - groupOrder(b.meta.group);
      if (go !== 0) return go;
      return a.meta.key.localeCompare(b.meta.key);
    });
    return all;
  }, [rows, map]);

  if (userLoading) {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl p-6">
          <p className="text-sm text-slate-400">{t("common.loading")}</p>
        </div>
      </Shell>
    );
  }

  if (!user?.is_admin) {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl p-6">
          <p className="text-amber-200">{t("admin.accessRequired")}</p>
        </div>
      </Shell>
    );
  }

  const groups: Array<FlagMeta["group"]> = ["External Providers", "AI Features", "Jobs / Schedules", "News / Trends / Warmups"];

  return (
    <Shell>
      <div className="mx-auto max-w-4xl p-6">
        <h1 className="text-xl font-semibold text-slate-100">{t("nav.admin")} — Runtime flags</h1>
        <p className="mt-1 text-sm text-slate-400">Toggle flags live. No restart required. Schedules keep their natural next run.</p>

        {loading ? (
          <p className="mt-6 text-sm text-slate-500">Loading data...</p>
        ) : error ? (
          <div className="mt-6 rounded border border-red-900/50 bg-red-950/20 px-4 py-2 text-sm text-red-200">{error}</div>
        ) : (
          <div className="mt-6 space-y-6">
            {groups.map((g) => {
              const items = visible.filter((x) => x.meta.group === g);
              if (!items.length) return null;
              return (
                <section key={g} className="rounded-lg border border-slate-700 bg-slate-900/50">
                  <div className="border-b border-slate-700 px-4 py-3">
                    <h2 className="text-sm font-semibold text-slate-100">{g}</h2>
                  </div>
                  <div className="divide-y divide-slate-800/70">
                    {items.map(({ meta, row }) => (
                      <div key={row.key} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-slate-300">{row.key}</span>
                            <span className="text-sm font-medium text-slate-100">{meta.label}</span>
                          </div>
                          <p className="mt-0.5 text-xs text-slate-400">{meta.description}</p>
                          {row.updated_at ? (
                            <p className="mt-1 text-[11px] text-slate-500">
                              Updated {new Date(row.updated_at).toLocaleString()} {row.updated_by ? `by ${row.updated_by}` : ""}
                            </p>
                          ) : (
                            <p className="mt-1 text-[11px] text-slate-500">Default (not set in DB)</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={patchingKey === row.key}
                            onClick={async () => {
                              console.log("[runtime-flags] toggle click", { key: row.key, from: row.value_bool });
                              setPatchingKey(row.key);
                              setError(null);
                              const nextVal = !row.value_bool;
                              try {
                                // Optimistic: flip immediately, and only revert on failure.
                                setRows((prev) =>
                                  prev.map((r) => (r.key === row.key ? { ...r, value_bool: nextVal } : r))
                                );
                                console.log("[runtime-flags] PATCH sending", { key: row.key, value_bool: nextVal });
                                const patched = await api.patchRuntimeFlag(row.key, { value_bool: nextVal });
                                console.log("[runtime-flags] PATCH response", patched);
                                // Persist patched metadata (updated_at/updated_by) without forcing full refetch.
                                setRows((prev) =>
                                  prev.map((r) =>
                                    r.key === row.key
                                      ? {
                                          ...r,
                                          value_bool: Boolean(patched.value_bool),
                                          updated_at: patched.updated_at,
                                          updated_by: patched.updated_by,
                                        }
                                      : r
                                  )
                                );
                              } catch (e: unknown) {
                                console.log("[runtime-flags] PATCH error", e);
                                setError(parseApiError(e));
                                // Revert only on failure.
                                setRows((prev) =>
                                  prev.map((r) => (r.key === row.key ? { ...r, value_bool: !nextVal } : r))
                                );
                              } finally {
                                setPatchingKey(null);
                              }
                            }}
                            className={`rounded border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide disabled:opacity-50 ${
                              row.value_bool
                                ? "border-emerald-700/60 bg-emerald-950/30 text-emerald-200 hover:bg-emerald-950/40"
                                : "border-slate-600 bg-slate-950/20 text-slate-300 hover:bg-slate-800/40"
                            }`}
                          >
                            {row.value_bool ? "On" : "Off"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}

            <section className="rounded-lg border border-slate-700 bg-slate-900/50">
              <div className="flex flex-col gap-2 border-b border-slate-700 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-100">Recent Runtime Logs</h2>
                  <p className="mt-0.5 text-xs text-slate-400">Most recent 50 key runtime events (bounded buffer).</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={logsCategory}
                    onChange={(e) => setLogsCategory(e.target.value as any)}
                    className="rounded border border-slate-700 bg-slate-950/30 px-2 py-1 text-xs text-slate-200"
                  >
                    <option value="all">all</option>
                    <option value="provider">provider</option>
                    <option value="job">job</option>
                    <option value="ai">ai</option>
                  </select>
                  <select
                    value={logsMinLevel}
                    onChange={(e) => setLogsMinLevel(e.target.value as any)}
                    className="rounded border border-slate-700 bg-slate-950/30 px-2 py-1 text-xs text-slate-200"
                  >
                    <option value="all">all</option>
                    <option value="warning-error">warning+error</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => loadLogs()}
                    className="rounded border border-slate-700 bg-slate-950/20 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-800/40"
                  >
                    Refresh
                  </button>
                </div>
              </div>
              <div className="px-4 py-3">
                {logsError ? (
                  <div className="rounded border border-red-900/50 bg-red-950/20 px-3 py-2 text-xs text-red-200">{logsError}</div>
                ) : null}
                {logsLoading ? (
                  <div className="text-xs text-slate-500">Loading data...</div>
                ) : logs.length === 0 ? (
                  <div className="text-xs text-slate-500">No recent logs yet.</div>
                ) : (
                  <div className="overflow-x-auto rounded border border-slate-800/70">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-800/70 bg-slate-950/30">
                          <th className="px-3 py-2 font-medium text-slate-300">Time</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Level</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Category</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Job</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Provider</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Status</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Counts</th>
                          <th className="px-3 py-2 font-medium text-slate-300">Message</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {logs.map((r, idx) => {
                          const lvl = (r.level || "info").toLowerCase();
                          const lvlCls =
                            lvl === "error"
                              ? "text-red-200"
                              : lvl === "warning"
                                ? "text-amber-200"
                                : "text-slate-300";
                          const counts = [
                            r.request_count != null ? `req:${r.request_count}` : null,
                            r.fallback_count != null ? `fb:${r.fallback_count}` : null,
                            r.symbol_count != null ? `sym:${r.symbol_count}` : null,
                            r.disabled_by_runtime_flag ? "flag:off" : null,
                            r.no_provider_call ? "no_call" : null,
                          ]
                            .filter(Boolean)
                            .join(" ");
                          return (
                            <tr key={`${r.created_at}-${idx}`} className="bg-slate-950/10">
                              <td className="px-3 py-2 text-slate-400">{new Date(r.created_at).toLocaleString()}</td>
                              <td className={`px-3 py-2 ${lvlCls}`}>{lvl}</td>
                              <td className="px-3 py-2 text-slate-300">{r.category}</td>
                              <td className="px-3 py-2 font-mono text-[11px] text-slate-300">{r.job_name || "—"}</td>
                              <td className="px-3 py-2 font-mono text-[11px] text-slate-400">{r.provider || "—"}</td>
                              <td className="px-3 py-2 text-slate-300">{r.status || "—"}</td>
                              <td className="px-3 py-2 font-mono text-[11px] text-slate-400">{counts || "—"}</td>
                              <td className="px-3 py-2 text-slate-200">{r.message}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </Shell>
  );
}

