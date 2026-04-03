"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { marked } from "marked";

import { Shell } from "@/components/Shell";
import { SectionHelp } from "@/components/SectionHelp";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { FREE_PLAN_LIMITS, LIMIT_MESSAGES } from "@/lib/limits";

function scheduleTypeLabel(t: (k: string) => string, value: string | null | undefined): string {
  const v = (value || "").trim();
  if (!v) return "—";
  const map: Record<string, string> = {
    standard_monitor: t("reports.scheduleTypeStandard"),
    ai_alert: t("reports.scheduleTypeAiAlert"),
    ai_report: t("reports.scheduleTypeAiReport"),
    general_alert: t("reports.scheduleTypeGeneral"),
  };
  return map[v] ?? v.replace(/_/g, " ");
}

export default function ReportsPage() {
  const { t } = useI18n();
  const [reports, setReports] = useState<any[]>([]);
  const [reportCount, setReportCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [filterLabel, setFilterLabel] = useState("");
  const [filterScheduleType, setFilterScheduleType] = useState("");
  const [countLoading, setCountLoading] = useState(false);

  const scheduleTypeOptions = [
    { value: "", label: t("reports.scheduleTypeAll") },
    { value: "standard_monitor", label: t("reports.scheduleTypeStandard") },
    { value: "ai_alert", label: t("reports.scheduleTypeAiAlert") },
    { value: "ai_report", label: t("reports.scheduleTypeAiReport") },
    { value: "general_alert", label: t("reports.scheduleTypeGeneral") },
  ];

  const loadReports = useCallback(async () => {
    setListLoading(true);
    try {
      const r = await api.reports(100, null, filterLabel || null, filterScheduleType || null);
      setReports(r);
      setSelected((prev: any) => {
        const still = r.find((x) => x.id === prev?.id);
        return still ?? r[0] ?? null;
      });
      setError(null);
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setListLoading(false);
    }
  }, [filterLabel, filterScheduleType]);

  const loadReportCount = useCallback(async () => {
    setCountLoading(true);
    try {
      const countRes = await api.reportCount();
      setReportCount(countRes.count);
    } catch {
      // Keep last known count; do not block list.
      setReportCount((prev) => prev);
    } finally {
      setCountLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  useEffect(() => {
    loadReportCount();
  }, [loadReportCount]);

  const anySelected = Object.values(selectedIds).some(Boolean);
  const selectedCount = Object.values(selectedIds).filter(Boolean).length;
  const allLoadedSelected = reports.length > 0 && reports.every((r) => selectedIds[r.id]);

  const toggleSelectAll = () => {
    if (allLoadedSelected) {
      setSelectedIds({});
    } else {
      setSelectedIds(Object.fromEntries(reports.map((r) => [r.id, true])));
    }
  };

  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const selectAllCheckboxRef = useRef<HTMLInputElement>(null);

  const openDeleteConfirm = () => {
    if (!anySelected) return;
    setConfirmDeleteOpen(true);
  };

  const closeDeleteConfirm = () => setConfirmDeleteOpen(false);

  useEffect(() => {
    const el = selectAllCheckboxRef.current;
    if (!el) return;
    el.indeterminate = !allLoadedSelected && selectedCount > 0;
  }, [allLoadedSelected, selectedCount]);

  async function performDeleteConfirmed() {
    const ids = Object.entries(selectedIds)
      .filter(([, v]) => v)
      .map(([k]) => k);
    if (ids.length === 0) return;
    setLoading(true);
    setError(null);
    closeDeleteConfirm();
    try {
      await api.deleteReports(ids);
      await Promise.all([loadReports(), loadReportCount()]);
      setSelectedIds({});
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }

  const selectAllActionLabel = allLoadedSelected ? t("reports.deselectAll") : t("reports.selectAll");

  return (
    <Shell>
      <div className="grid min-w-0 gap-6 md:grid-cols-[320px_1fr]">
        <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold">{t("reports.listHeading")}</div>
              <SectionHelp titleKey="help.reportsPageTitle" bodyKey="help.reportsPageBody" />
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
                onClick={toggleSelectAll}
                disabled={!reports.length}
                title={allLoadedSelected ? t("reports.deselectAllTooltip") : t("reports.selectAllTooltip")}
              >
                {selectAllActionLabel}
              </button>
              <button
                type="button"
                className="rounded bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-60"
                onClick={openDeleteConfirm}
                disabled={!anySelected || loading}
                aria-label={t("reports.deleteSelectedAria")}
              >
                {t("reports.deleteSelected")}
              </button>
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-400">{t("reports.filterHint")}</p>
          {listLoading ? <p className="mt-1 text-xs text-slate-500">{t("common.loading")}</p> : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="self-center text-xs text-slate-400">{t("reports.filterColon")}:</span>
            <input
              type="text"
              placeholder={t("reports.filterLabelPlaceholder")}
              value={filterLabel}
              onChange={(e) => setFilterLabel(e.target.value)}
              disabled={listLoading}
              className="w-28 rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 placeholder-slate-500"
            />
            <select
              value={filterScheduleType}
              onChange={(e) => setFilterScheduleType(e.target.value)}
              disabled={listLoading}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200"
            >
              {scheduleTypeOptions.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-2 flex flex-col gap-1">
            <div className="text-xs text-slate-400">
              {reportCount !== null ? (
                t("reports.retainedLine", { count: reportCount, max: FREE_PLAN_LIMITS.MAX_REPORTS })
              ) : (
                t("reports.retainedFallback")
              )}
              {countLoading ? <span className="ml-2 text-[11px] text-slate-500">{t("common.loading")}</span> : null}
            </div>
            {reportCount !== null && reportCount >= FREE_PLAN_LIMITS.MAX_REPORTS ? (
              <div className="rounded border border-amber-900/50 bg-amber-950/20 px-2 py-1.5 text-xs text-amber-200">
                {LIMIT_MESSAGES.MAX_REPORTS}
              </div>
            ) : null}
          </div>
          <div className="mt-3 space-y-2">
            {reports.length > 0 ? (
              <div className="flex items-center gap-2 rounded border border-slate-700/60 bg-slate-800/40 px-3 py-2 text-sm">
                <input
                  type="checkbox"
                  id="reports-select-all"
                  ref={selectAllCheckboxRef}
                  className="cursor-pointer"
                  checked={allLoadedSelected}
                  onChange={toggleSelectAll}
                />
                <label htmlFor="reports-select-all" className="cursor-pointer text-slate-300">
                  {t("reports.selectAllLoaded", { action: selectAllActionLabel, n: reports.length })}
                </label>
              </div>
            ) : null}
            {reports.map((r) => (
              <div
                key={r.id}
                className={
                  "flex items-start gap-2 rounded border px-3 py-2 text-left text-sm " +
                  (selected?.id === r.id
                    ? "border-slate-600 bg-slate-900"
                    : "border-slate-800 bg-slate-950/40 hover:border-slate-700")
                }
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={!!selectedIds[r.id]}
                  onChange={(e) => setSelectedIds({ ...selectedIds, [r.id]: e.target.checked })}
                />
                <button className="flex-1 text-left" onClick={() => setSelected(r)}>
                  <div className="font-medium">{r.title}</div>
                  <div className="mt-0.5 text-xs text-slate-400">
                    {[r.kind, r.label, scheduleTypeLabel(t, r.schedule_type)].filter(Boolean).join(" • ") || "—"} •{" "}
                    {new Date(r.created_at).toLocaleString()}
                  </div>
                </button>
              </div>
            ))}
            {!reports.length ? <div className="text-sm text-slate-400">{t("reports.emptyList")}</div> : null}
          </div>
        </section>

        <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="mb-2 text-sm font-semibold text-slate-300">{t("reports.detailTitle")}</div>
          {error ? <div className="text-sm text-red-200">{error}</div> : null}
          {selected ? (
            <article
              className="prose prose-invert max-w-none prose-a:text-indigo-300"
              dangerouslySetInnerHTML={{ __html: marked.parse(selected.body_markdown || "") as string }}
            />
          ) : (
            <div className="text-sm text-slate-400">{t("reports.selectOne")}</div>
          )}
        </section>
      </div>

      {confirmDeleteOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-delete-title"
        >
          <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
            <h3 id="confirm-delete-title" className="text-lg font-semibold text-slate-100">
              {t("reports.deleteModalTitle")}
            </h3>
            <p className="mt-2 text-sm text-slate-300">{t("reports.deleteModalBody", { count: selectedCount })}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeDeleteConfirm}
                className="rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={performDeleteConfirmed}
                disabled={loading}
                className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-60"
              >
                {loading ? t("reports.deleting") : t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </Shell>
  );
}
