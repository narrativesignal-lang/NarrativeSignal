"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Shell } from "@/components/Shell";
import { SectionHelp } from "@/components/SectionHelp";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
import { FREE_PLAN_LIMITS, LIMIT_MESSAGES } from "@/lib/limits";

const MAX_SCHEDULES = FREE_PLAN_LIMITS.MAX_SAVED_SCHEDULES;
const MAX_ACTIVE_SCHEDULES = FREE_PLAN_LIMITS.MAX_ACTIVE_SCHEDULES;

const COMING_UP_TYPES = ["ai_alert", "ai_report", "general_alert", "high_alert"] as const;
const isComingUp = (ty: string) => COMING_UP_TYPES.includes(ty as (typeof COMING_UP_TYPES)[number]);

type Portfolio = Awaited<ReturnType<typeof api.listPortfolios>>[number];
type Entity = Awaited<ReturnType<typeof api.listEntities>>[number];

function ScheduleTypesHelpModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="schedule-help-title"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 id="schedule-help-title" className="text-lg font-semibold text-slate-100">
            {t("schedules.typesHelpTitle")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label={t("schedules.typesHelpClose")}
          >
            ×
          </button>
        </div>
        <div className="mt-4 space-y-4 text-sm">
          <section>
            <h4 className="font-medium text-slate-200">{t("schedules.helpStandardTitle")}</h4>
            <p className="mt-1 text-slate-400">{t("schedules.helpStandardBody")}</p>
          </section>
          <section>
            <h4 className="font-medium text-slate-200">
              {t("schedules.highAlertOption")}{" "}
              <span className="text-amber-400">({t("schedules.highAlertComingSoon")})</span>
            </h4>
            <p className="mt-1 text-slate-400">{t("schedules.highAlertDetailBody")}</p>
          </section>
          <section>
            <h4 className="font-medium text-slate-200">
              {t("schedules.helpAiAlertTitle")}{" "}
              <span className="text-amber-400">({t("schedules.highAlertComingSoon")})</span>
            </h4>
            <p className="mt-1 text-slate-400">{t("schedules.helpAiAlertBody")}</p>
          </section>
          <section>
            <h4 className="font-medium text-slate-200">
              {t("schedules.helpAiReportTitle")}{" "}
              <span className="text-amber-400">({t("schedules.highAlertComingSoon")})</span>
            </h4>
            <p className="mt-1 text-slate-400">{t("schedules.helpAiReportBody")}</p>
          </section>
          <section>
            <h4 className="font-medium text-slate-200">
              {t("schedules.helpGeneralAlertTitle")}{" "}
              <span className="text-amber-400">({t("schedules.highAlertComingSoon")})</span>
            </h4>
            <p className="mt-1 text-slate-400">{t("schedules.helpGeneralAlertBody")}</p>
          </section>
          <section>
            <h4 className="font-medium text-slate-200">{t("schedules.helpImpactTitle")}</h4>
            <p className="mt-1 text-xs text-slate-400">{t("schedules.helpImpactBody")}</p>
          </section>
        </div>
      </div>
    </div>
  );
}

function HighAlertComingSoonModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-slate-100">{t("schedules.highAlertDetailTitle")}</h3>
        <p className="mt-2 text-sm text-slate-400">{t("schedules.highAlertDetailBody")}</p>
        <p className="mt-1 text-xs font-medium text-amber-200/90">{t("schedules.highAlertComingSoon")}</p>
        <button
          type="button"
          className="mt-4 w-full rounded bg-slate-700 py-2 text-sm text-slate-100 hover:bg-slate-600"
          onClick={onClose}
        >
          {t("schedules.highAlertModalClose")}
        </button>
      </div>
    </div>
  );
}

/** Rough client check: standard schedules must not fire more than once per hour (same as backend intent). */
function cronStepAppearsSubHourly(expr: string): boolean {
  const parts = expr.trim().split(/\s+/).filter(Boolean);
  if (parts.length < 5) return true;
  const [minField] = parts;
  if (minField === "*") return true;
  const step = minField.match(/^\*\/(\d+)$/);
  if (step) {
    const n = parseInt(step[1], 10);
    if (n > 0 && n < 60) return true;
  }
  const list = minField.split(",").map((x) => parseInt(x, 10));
  if (list.length >= 2 && list.every((x) => !Number.isNaN(x))) {
    const d = list[1] - list[0];
    if (d > 0 && d < 60) return true;
  }
  return false;
}

export default function SchedulesPage() {
  const { user, loading: userLoading } = useUser();
  const { t } = useI18n();
  const isAdmin = Boolean(user?.is_admin);

  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [scheduleType, setScheduleType] = useState("standard_monitor");
  const [model, setModel] = useState("");
  const [impactThreshold, setImpactThreshold] = useState<number | "">(60);
  const [cron, setCron] = useState("0 * * * *");
  const [bucketMinutes, setBucketMinutes] = useState(60);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedEntityIds, setSelectedEntityIds] = useState<Record<string, boolean>>({});
  const [helpOpen, setHelpOpen] = useState(false);
  const [highAlertOpen, setHighAlertOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const highAlertExplained = useRef(false);
  const defaultNameSeeded = useRef(false);

  useEffect(() => {
    if (defaultNameSeeded.current) return;
    defaultNameSeeded.current = true;
    setName(t("schedules.standardMonitorName"));
  }, [t]);

  const refresh = useCallback(async () => {
    const fetchAlerts = typeof api.alerts === "function" ? api.alerts() : Promise.resolve([]);
    const [portfoliosRes, s, a] = await Promise.all([
      api.listPortfolios(),
      api.schedules(),
      fetchAlerts.catch(() => []),
    ]);
    setPortfolios(portfoliosRes);
    setSchedules(s);
    setAlerts(Array.isArray(a) ? a : []);
    setSelectedPortfolioId((pid) => pid || portfoliosRes[0]?.id || null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await refresh();
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    })();
  }, [refresh]);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setEntities([]);
      setSelectedEntityIds({});
      return;
    }
    api
      .listEntities(selectedPortfolioId)
      .then((list) => {
        setEntities(list);
        setSelectedEntityIds({});
      })
      .catch(() => setEntities([]));
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (scheduleType === "standard_monitor" && bucketMinutes < 60) {
      setBucketMinutes(60);
    }
  }, [scheduleType, bucketMinutes]);

  useEffect(() => {
    if (userLoading) return;
    if (!isAdmin && ["ai_alert", "ai_report", "general_alert"].includes(scheduleType)) {
      setScheduleType("standard_monitor");
    }
  }, [userLoading, isAdmin, scheduleType]);

  useEffect(() => {
    if (scheduleType === "high_alert" && !highAlertExplained.current) {
      highAlertExplained.current = true;
      setHighAlertOpen(true);
    }
  }, [scheduleType]);

  async function create() {
    if (scheduleType === "high_alert") {
      setHighAlertOpen(true);
      return;
    }
    if (isComingUp(scheduleType) && !isAdmin) {
      setError(t("schedules.plannedNotAvailable"));
      return;
    }
    setError(null);
    if (!name.trim()) {
      setError(t("schedules.errorNameRequired"));
      return;
    }
    if (scheduleType === "standard_monitor") {
      if (bucketMinutes < 60) {
        setError(t("schedules.minAggregationStandard"));
        return;
      }
      if (cronStepAppearsSubHourly(cron)) {
        setError(t("schedules.minIntervalStandard"));
        return;
      }
    }
    const entity_ids = Object.entries(selectedEntityIds)
      .filter(([, v]) => v)
      .map(([k]) => k);
    if (!entity_ids.length) {
      setError(t("schedules.selectOneEntity"));
      return;
    }
    setCreateSubmitting(true);
    try {
      await api.createSchedule({
        name: name.trim(),
        cron,
        group_ids: [],
        entity_ids,
        bucket_minutes: bucketMinutes,
        is_active: true,
        schedule_type: scheduleType,
        label: label.trim() || undefined,
        model: model.trim() || undefined,
        impact_threshold: typeof impactThreshold === "number" ? impactThreshold : undefined,
      });
      await refresh();
      setToast(t("schedules.createSuccessToast"));
      window.setTimeout(() => setToast(null), 6500);
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setCreateSubmitting(false);
    }
  }

  async function trigger(id: string) {
    setError(null);
    try {
      await api.triggerSchedule(id);
      setToast(t("schedules.triggerToast"));
      window.setTimeout(() => setToast(null), 6500);
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function pause(id: string) {
    setError(null);
    try {
      await api.pauseSchedule(id);
      await refresh();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function resume(id: string) {
    setError(null);
    try {
      await api.resumeSchedule(id);
      await refresh();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteSchedule(id);
      await refresh();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  const totalSchedules = schedules.length;
  const activeCount = schedules.filter((s) => s.status === "active").length;
  const atScheduleLimit = totalSchedules >= MAX_SCHEDULES;
  const atActiveLimit = activeCount >= MAX_ACTIVE_SCHEDULES;

  const bucketMin = scheduleType === "standard_monitor" ? 60 : 5;

  return (
    <Shell>
      <div className="space-y-6">
        {error ? (
          <div className="rounded border border-red-900 bg-red-950/30 p-3 text-sm text-red-200 break-words text-balance">
            {error}
          </div>
        ) : null}
        {toast ? (
          <div className="rounded border border-emerald-900/50 bg-emerald-950/25 p-3 text-sm text-emerald-200">{toast}</div>
        ) : null}

        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold">{t("schedules.title")}</h1>
            <SectionHelp titleKey="help.schedulesPageTitle" bodyKey="help.schedulesPageBody" />
          </div>
          <p className="mt-1 text-sm text-slate-300">{t("schedules.introP1")}</p>
          <p className="mt-2 text-xs text-slate-400">{t("schedules.introP2")}</p>
          <p className="mt-2 text-xs text-slate-500">{t("schedules.beatNote")}</p>
        </section>

        <section className="grid min-w-0 gap-6 md:grid-cols-2">
          <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-sm font-semibold">{t("schedules.createSchedule")}</div>
              <SectionHelp titleKey="help.schedulesFormTitle" bodyKey="help.schedulesFormBody" />
            </div>
            <p className="mt-1 text-xs text-slate-400">
              {totalSchedules} / {MAX_SCHEDULES} saved &nbsp;•&nbsp; {activeCount} / {MAX_ACTIVE_SCHEDULES} active
            </p>
            <div className="mt-3 space-y-2">
              <label className="block">
                <div className="text-xs text-slate-400">{t("schedules.scheduleName")}</div>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("schedules.standardMonitorName")}
                />
              </label>
              <label className="block">
                <div className="flex flex-wrap items-center gap-1 text-xs text-slate-400">
                  {t("schedules.typeLabel")}
                  <button
                    type="button"
                    className="cursor-help rounded bg-slate-700 px-1.5 py-0.5 text-slate-300 hover:bg-slate-600"
                    onClick={() => setHelpOpen(true)}
                    aria-label={t("schedules.typeHelpAria")}
                  >
                    ?
                  </button>
                </div>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-slate-500"
                  value={scheduleType}
                  onChange={(e) => setScheduleType(e.target.value)}
                >
                  <option value="standard_monitor">{t("schedules.standardOption")}</option>
                  <option value="high_alert">{t("schedules.highAlertOption")} ({t("schedules.highAlertComingSoon")})</option>
                  {!userLoading && isAdmin ? (
                    <>
                      <option value="ai_alert">{t("schedules.aiAlertOption")}</option>
                      <option value="ai_report">{t("schedules.aiReportOption")}</option>
                      <option value="general_alert">{t("schedules.generalAlertOption")}</option>
                    </>
                  ) : null}
                </select>
              </label>
              {isComingUp(scheduleType) && !userLoading && !isAdmin && (
                <div className="rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                  {t("schedules.plannedNotAvailable")}
                  <span className="ml-1 text-amber-300/80">{t("schedules.premiumPlanned")}</span>
                </div>
              )}
              {isComingUp(scheduleType) && !userLoading && isAdmin && (
                <div className="rounded border border-indigo-900/50 bg-indigo-950/20 px-3 py-2 text-xs text-indigo-200">
                  {t("schedules.adminBypass")}
                </div>
              )}
              {isComingUp(scheduleType) && !userLoading && isAdmin && (
                <>
                  <label className="block">
                    <div className="flex items-center gap-1 text-xs text-slate-400">{t("schedules.labelOptional")}</div>
                    <input
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                    />
                  </label>
                  <label className="block">
                    <div className="flex items-center gap-1 text-xs text-slate-400">{t("schedules.modelLabel")}</div>
                    <select
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-slate-500"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                    >
                      <option value="">{t("schedules.modelNone")}</option>
                      <option value="gemini">Gemini</option>
                      <option value="gpt">GPT</option>
                      <option value="claude">Claude</option>
                      <option value="grok">Grok</option>
                      <option value="qwen">Qwen</option>
                    </select>
                  </label>
                  {scheduleType === "ai_alert" && (
                    <label className="block">
                      <div className="flex items-center gap-1 text-xs text-slate-400">{t("schedules.impactThreshold")}</div>
                      <input
                        className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                        type="number"
                        min={0}
                        max={100}
                        value={impactThreshold}
                        onChange={(e) => setImpactThreshold(e.target.value === "" ? "" : parseInt(e.target.value || "60", 10))}
                      />
                    </label>
                  )}
                </>
              )}
              <label className="block">
                <div className="text-xs font-medium text-slate-400">{t("schedules.timingRuleLabel")}</div>
                <p className="mt-0.5 text-[11px] text-slate-500">{t("schedules.timingRuleHint")}</p>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  value={cron}
                  onChange={(e) => setCron(e.target.value)}
                  placeholder="0 * * * *"
                />
              </label>
              <label className="block">
                <div className="text-xs font-medium text-slate-400">{t("schedules.aggregationLabel")}</div>
                <p className="mt-0.5 text-[11px] text-slate-500">{t("schedules.aggregationHint")}</p>
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  value={bucketMinutes}
                  onChange={(e) => {
                    const v = parseInt(e.target.value || String(bucketMin), 10);
                    setBucketMinutes(Number.isNaN(v) ? bucketMin : Math.max(bucketMin, v));
                  }}
                  type="number"
                  min={bucketMin}
                  max={1440}
                />
              </label>
              {scheduleType === "standard_monitor" ? (
                <p className="text-[11px] text-amber-200/90">{t("schedules.minIntervalStandard")}</p>
              ) : null}
              <div className="pt-2">
                <div className="text-xs font-semibold text-slate-300">{t("schedules.portfolioLabel")}</div>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-slate-500"
                  value={selectedPortfolioId ?? ""}
                  onChange={(e) => setSelectedPortfolioId(e.target.value || null)}
                >
                  <option value="">{t("schedules.selectPortfolio")}</option>
                  {portfolios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-xs font-semibold text-slate-300">{t("schedules.entitiesLabel")}</div>
                <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                  {entities.map((ent) => (
                    <label key={ent.id} className="flex items-center gap-2 text-sm text-slate-200">
                      <input
                        type="checkbox"
                        checked={!!selectedEntityIds[ent.id]}
                        onChange={(e) =>
                          setSelectedEntityIds({ ...selectedEntityIds, [ent.id]: e.target.checked })
                        }
                      />
                      {ent.name}
                      {ent.instrument ? ` (${ent.instrument.symbol})` : ""}
                    </label>
                  ))}
                  {selectedPortfolioId && !entities.length ? (
                    <div className="text-sm text-slate-400">{t("schedules.noEntitiesInPortfolio")}</div>
                  ) : null}
                </div>
              </div>
              <button
                className="mt-3 w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
                onClick={() => void create()}
                disabled={atScheduleLimit || atActiveLimit || createSubmitting}
                title={
                  atScheduleLimit
                    ? LIMIT_MESSAGES.MAX_SAVED_SCHEDULES
                    : atActiveLimit
                      ? LIMIT_MESSAGES.MAX_ACTIVE_SCHEDULES
                      : undefined
                }
              >
                {createSubmitting ? t("schedules.createSubmitting") : t("schedules.createSchedule")}
              </button>
            </div>
          </div>

          <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="text-sm font-semibold">{t("schedules.existingSchedules")}</div>
                <SectionHelp titleKey="help.schedulesListTitle" bodyKey="help.schedulesListBody" />
              </div>
              <span className="text-xs text-slate-400">
                {totalSchedules} / {MAX_SCHEDULES} &nbsp;•&nbsp; {activeCount} / {MAX_ACTIVE_SCHEDULES} active
              </span>
            </div>
            <div className="mt-3 space-y-2">
              {schedules.map((s) => (
                <div key={s.id} className="rounded border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-medium">{s.name}</div>
                        <span
                          className={
                            "rounded px-2 py-0.5 text-xs " +
                            (s.status === "paused"
                              ? "border border-amber-900 bg-amber-950/60 text-amber-200"
                              : "border border-emerald-900 bg-emerald-950/60 text-emerald-200")
                          }
                        >
                          {s.status === "paused" ? t("schedules.statusPaused") : t("schedules.statusActive")}
                        </span>
                      </div>
                      <div className="mt-1 break-words text-xs text-slate-400">
                        {s.schedule_type !== "standard_monitor" ? (
                          <span className="mr-1 rounded bg-indigo-900/40 px-1 text-indigo-200">
                            {s.schedule_type.replace(/_/g, " ")}
                          </span>
                        ) : null}
                        {t("schedules.rowTiming")}: <code className="text-slate-200">{s.cron}</code>
                        {" · "}
                        {t("schedules.rowWindow")}: {s.bucket_minutes}m
                        {" · "}
                        {(s.entity_labels as { symbol?: string }[] | undefined)?.length
                          ? `${t("schedules.rowTargets")}: ${(s.entity_labels as { symbol?: string }[]).map((l) => l.symbol ?? "").join(", ")}`
                          : `${(s.group_ids as string[] | undefined)?.length ?? 0} groups`}
                      </div>
                    </div>
                    <div className="flex flex-shrink-0 flex-col items-end gap-2 sm:flex-row">
                      <button
                        className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
                        onClick={() => trigger(s.id)}
                      >
                        {t("schedules.triggerNow")}
                      </button>
                      {s.status === "paused" ? (
                        <button
                          className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                          onClick={() => resume(s.id)}
                          disabled={atActiveLimit}
                          title={atActiveLimit ? LIMIT_MESSAGES.MAX_ACTIVE_SCHEDULES : undefined}
                        >
                          {t("schedules.resume")}
                        </button>
                      ) : (
                        <button
                          className="rounded bg-amber-700 px-3 py-1.5 text-sm text-white hover:bg-amber-600"
                          onClick={() => pause(s.id)}
                        >
                          {t("schedules.pause")}
                        </button>
                      )}
                      <button
                        className="rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-600"
                        onClick={() => remove(s.id)}
                      >
                        {t("schedules.delete")}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {!schedules.length ? <div className="text-sm text-slate-400">{t("schedules.noSchedulesYet")}</div> : null}
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 md:col-span-2">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold">{t("schedules.triggeredAlertsTitle")}</div>
              <SectionHelp titleKey="help.schedulesAlertsTitle" bodyKey="help.schedulesAlertsBody" />
            </div>
            <p className="mt-1 text-xs text-slate-400">{t("schedules.triggeredAlertsSubtitle")}</p>
            <div className="mt-3 max-h-60 space-y-2 overflow-y-auto">
              {alerts.map((a) => (
                <div key={a.id} className="rounded border border-amber-900/40 bg-amber-950/20 p-2">
                  <div className="font-medium text-amber-200">{a.title}</div>
                  <div className="mt-0.5 text-xs text-slate-400">
                    {a.schedule_type} • impact {a.impact_score ?? "—"} • {new Date(a.created_at).toLocaleString()}
                  </div>
                  {a.body_markdown ? (
                    <p className="mt-1 line-clamp-2 text-xs text-slate-300">{a.body_markdown.replace(/#+/g, "").trim()}</p>
                  ) : null}
                </div>
              ))}
              {!alerts.length ? <div className="text-sm text-slate-400">{t("schedules.noAlertsYet")}</div> : null}
            </div>
          </div>
        </section>
      </div>
      {helpOpen ? <ScheduleTypesHelpModal onClose={() => setHelpOpen(false)} /> : null}
      {highAlertOpen ? <HighAlertComingSoonModal onClose={() => setHighAlertOpen(false)} /> : null}
    </Shell>
  );
}
