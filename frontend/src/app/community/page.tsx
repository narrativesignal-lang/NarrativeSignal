"use client";

import { useState } from "react";

import { Shell } from "@/components/Shell";
import { SectionHelp } from "@/components/SectionHelp";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

const CATEGORY_IDS = ["analysis_tool", "indicator_index", "ai_workflow", "data_request", "integration_idea"] as const;

const PRIORITY_IDS = ["low", "medium", "high", "critical"] as const;

const DEMO_LIBRARY_IDS = ["1", "2", "3", "4", "5", "6", "7", "8"] as const;

type DemoStatus = "active" | "experimental" | "coming_up";

const DEMO_STATUS: Record<string, DemoStatus> = {
  "1": "active",
  "2": "active",
  "3": "experimental",
  "4": "active",
  "5": "active",
  "6": "experimental",
  "7": "coming_up",
  "8": "coming_up",
};

function statusClass(s: DemoStatus) {
  if (s === "active") return "border border-emerald-800 bg-emerald-950/50 text-emerald-200";
  if (s === "experimental") return "border border-amber-800 bg-amber-950/50 text-amber-200";
  return "border border-slate-600 bg-slate-800/60 text-slate-400";
}

export default function CommunityPage() {
  const { t } = useI18n();
  const { user, loading } = useUser();
  const [activeTab, setActiveTab] = useState<"general" | "data_request">("general");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState("analysis_tool");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [problemSolves, setProblemSolves] = useState("");
  const [platformDataUsed, setPlatformDataUsed] = useState("");
  const [hasDataSource, setHasDataSource] = useState(false);
  const [dataSourceAccess, setDataSourceAccess] = useState("");
  const [contactInfo, setContactInfo] = useState("");
  const [notes, setNotes] = useState("");

  const [requestedDataName, setRequestedDataName] = useState("");
  const [dataRequestDesc, setDataRequestDesc] = useState("");
  const [useCase, setUseCase] = useState("");
  const [sourceKnown, setSourceKnown] = useState(false);
  const [howToObtain, setHowToObtain] = useState("");
  const [sourceDetails, setSourceDetails] = useState("");
  const [dataRequestContact, setDataRequestContact] = useState("");
  const [priority, setPriority] = useState("medium");
  const [dataRequestNotes, setDataRequestNotes] = useState("");

  function priorityLabel(id: string) {
    const map: Record<string, string> = {
      low: t("community.priorityLow"),
      medium: t("community.priorityMedium"),
      high: t("community.priorityHigh"),
      critical: t("community.priorityCritical"),
    };
    return map[id] ?? id;
  }

  function statusLabel(s: DemoStatus) {
    if (s === "active") return t("community.statusLabel.active");
    if (s === "experimental") return t("community.statusLabel.experimental");
    return t("community.statusLabel.coming_up");
  }

  async function handleGeneralSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await api.community.submit({
        category,
        title: title.trim(),
        description: description.trim(),
        problem_solves: problemSolves.trim(),
        platform_data_used: platformDataUsed.trim(),
        has_data_source: hasDataSource,
        data_source_access: dataSourceAccess.trim(),
        contact_info: contactInfo.trim(),
        notes: notes.trim(),
      });
      setSuccess(t("community.successGeneral"));
      setTitle("");
      setDescription("");
      setProblemSolves("");
      setPlatformDataUsed("");
      setDataSourceAccess("");
      setNotes("");
    } catch (err: unknown) {
      setError(parseApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDataRequestSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await api.community.submitDataRequest({
        requested_data_name: requestedDataName.trim(),
        description: dataRequestDesc.trim(),
        use_case: useCase.trim(),
        source_known: sourceKnown,
        how_to_obtain: howToObtain.trim(),
        source_details: sourceDetails.trim(),
        contact_info: dataRequestContact.trim(),
        priority,
        notes: dataRequestNotes.trim(),
      });
      setSuccess(t("community.successData"));
      setRequestedDataName("");
      setDataRequestDesc("");
      setUseCase("");
      setHowToObtain("");
      setSourceDetails("");
      setDataRequestNotes("");
    } catch (err: unknown) {
      setError(parseApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Shell>
      <div className="space-y-6">
        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold">{t("community.title")}</h1>
            <SectionHelp titleKey="help.communityIntroTitle" bodyKey="help.communityIntroBody" />
          </div>
          <p className="mt-2 text-sm text-slate-300">{t("community.introP1")}</p>
          <p className="mt-1 text-xs text-slate-400">{t("community.introP2")}</p>
          <div className="mt-3 rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
            {t("community.gatingNote")}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-700/80 bg-slate-950/50 p-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("community.metricCorrelationTitle")}</span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">{t("community.previewBadge")}</span>
              </div>
              <p className="mt-2 text-2xl font-semibold text-slate-300">{t("community.metricSampleValue")}</p>
              <p className="mt-1 text-xs text-slate-500">{t("community.metricCorrelationDesc")}</p>
            </div>
            <div className="rounded-lg border border-slate-700/80 bg-slate-950/50 p-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("community.metricRatingTitle")}</span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">{t("community.previewBadge")}</span>
              </div>
              <p className="mt-2 text-2xl font-semibold text-slate-300">{t("community.metricSampleValue")}</p>
              <p className="mt-1 text-xs text-slate-500">{t("community.metricRatingDesc")}</p>
            </div>
          </div>
          {!loading && !user && <p className="mt-2 text-sm text-slate-400">{t("community.loginToSubmit")}</p>}
        </section>

        <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">{t("community.libraryTitle")}</h2>
            <SectionHelp titleKey="help.communityLibraryTitle" bodyKey="help.communityLibraryBody" />
          </div>
          <p className="mt-1 text-sm text-slate-400">{t("community.librarySubtitle")}</p>
          <div className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DEMO_LIBRARY_IDS.map((id) => {
              const st = DEMO_STATUS[id];
              return (
                <div
                  key={id}
                  className="rounded-xl border border-slate-700/80 bg-slate-950/60 p-4 transition-colors hover:border-slate-600"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-medium text-slate-100">{t(`community.lib.${id}.name`)}</div>
                      <span className={"mt-1 inline-block rounded px-2 py-0.5 text-xs " + statusClass(st)}>{statusLabel(st)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
                      >
                        {t("community.view")}
                      </button>
                      <SectionHelp titleKey="community.libraryTitle" bodyKey="community.cardHelpHint" />
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-slate-400">{t(`community.lib.${id}.category`)}</p>
                  <p className="mt-2 text-sm text-slate-300">{t(`community.lib.${id}.desc`)}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {t(`community.lib.${id}.tags`)
                      .split("·")
                      .map((tag) => tag.trim())
                      .filter(Boolean)
                      .map((tag) => (
                        <span key={tag} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">
                          {tag}
                        </span>
                      ))}
                  </div>
                  <p className="mt-2 text-xs text-slate-500">{t("community.byAuthor", { author: "User_preview" })}</p>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold">{t("community.submitIntro")}</h2>
              <SectionHelp titleKey="help.communitySubmitTitle" bodyKey="help.communitySubmitBody" />
            </div>
          </div>
          <p className="mb-3 mt-2 text-sm text-slate-400">{t("community.emailSoon")}</p>
          <div className="flex gap-2 border-b border-slate-700 pb-2">
            <button
              type="button"
              className={`rounded px-3 py-1.5 text-sm ${activeTab === "general" ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"}`}
              onClick={() => setActiveTab("general")}
            >
              {t("community.tabGeneral")}
            </button>
            <button
              type="button"
              className={`rounded px-3 py-1.5 text-sm ${activeTab === "data_request" ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"}`}
              onClick={() => setActiveTab("data_request")}
            >
              {t("community.tabDataRequest")}
            </button>
          </div>

          {activeTab === "general" && (
            <div className="mt-4">
              <p className="mb-3 text-xs text-slate-400">{t("community.submissionCategoriesHeading")}</p>
              <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {CATEGORY_IDS.filter((c) => c !== "data_request").map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`rounded border p-2 text-left text-sm ${
                      category === c ? "border-indigo-600 bg-indigo-950/40" : "border-slate-700 hover:border-slate-600"
                    }`}
                    onClick={() => setCategory(c)}
                  >
                    <div className="font-medium">{t(`community.cat.${c}.label`)}</div>
                    <div className="mt-0.5 text-xs text-slate-400">{t(`community.cat.${c}.desc`)}</div>
                  </button>
                ))}
              </div>

              <form className="space-y-3" onSubmit={handleGeneralSubmit}>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldTitle")}</div>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldDescription")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <label className="block">
                  <div className="flex items-center gap-1 text-xs text-slate-400">
                    {t("community.fieldProblem")}
                    <SectionHelp titleKey="help.communityProblemTitle" bodyKey="help.communityProblemBody" />
                  </div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={2}
                    value={problemSolves}
                    onChange={(e) => setProblemSolves(e.target.value)}
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldPlatformData")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={2}
                    value={platformDataUsed}
                    onChange={(e) => setPlatformDataUsed(e.target.value)}
                  />
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={hasDataSource} onChange={(e) => setHasDataSource(e.target.checked)} />
                  <span className="text-sm">{t("community.fieldHasSource")}</span>
                </label>
                {hasDataSource && (
                  <label className="block">
                    <div className="text-xs text-slate-400">{t("community.fieldHowAccess")}</div>
                    <input
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                      value={dataSourceAccess}
                      onChange={(e) => setDataSourceAccess(e.target.value)}
                    />
                  </label>
                )}
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldContact")}</div>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    type="email"
                    value={contactInfo}
                    onChange={(e) => setContactInfo(e.target.value)}
                    placeholder={t("community.fieldContactPlaceholder")}
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldNotes")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </label>
                {error && <div className="rounded border border-red-900 bg-red-950/30 p-2 text-sm text-red-200">{error}</div>}
                {success && <div className="rounded border border-emerald-900 bg-emerald-950/30 p-2 text-sm text-emerald-200">{success}</div>}
                <button
                  type="submit"
                  className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
                  disabled={submitting || !user}
                >
                  {submitting ? t("community.submitting") : t("community.submit")}
                </button>
              </form>
            </div>
          )}

          {activeTab === "data_request" && (
            <div className="mt-4">
              <p className="mb-3 text-xs text-slate-400">{t("community.dataRequestIntro")}</p>
              <p className="mb-3 text-xs text-amber-200/90">{t("community.emailSoon")}</p>

              <form className="space-y-3" onSubmit={handleDataRequestSubmit}>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldRequestedName")}</div>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    value={requestedDataName}
                    onChange={(e) => setRequestedDataName(e.target.value)}
                    required
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.dataRequestDescLabel")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={3}
                    value={dataRequestDesc}
                    onChange={(e) => setDataRequestDesc(e.target.value)}
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldUseCase")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={2}
                    value={useCase}
                    onChange={(e) => setUseCase(e.target.value)}
                  />
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={sourceKnown} onChange={(e) => setSourceKnown(e.target.checked)} />
                  <span className="text-sm">{t("community.fieldSourceKnown")}</span>
                </label>
                {sourceKnown && (
                  <label className="block">
                    <div className="text-xs text-slate-400">{t("community.fieldHowObtain")}</div>
                    <input
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                      value={howToObtain}
                      onChange={(e) => setHowToObtain(e.target.value)}
                    />
                  </label>
                )}
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldSourceDetails")}</div>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    value={sourceDetails}
                    onChange={(e) => setSourceDetails(e.target.value)}
                    placeholder={t("community.fieldSourcePlaceholder")}
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldYourContact")}</div>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    type="email"
                    value={dataRequestContact}
                    onChange={(e) => setDataRequestContact(e.target.value)}
                    placeholder={t("community.fieldContactPlaceholder")}
                  />
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldPriority")}</div>
                  <select
                    className="mt-1 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                  >
                    {PRIORITY_IDS.map((p) => (
                      <option key={p} value={p}>
                        {priorityLabel(p)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <div className="text-xs text-slate-400">{t("community.fieldNotes")}</div>
                  <textarea
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    rows={2}
                    value={dataRequestNotes}
                    onChange={(e) => setDataRequestNotes(e.target.value)}
                  />
                </label>
                {error && <div className="rounded border border-red-900 bg-red-950/30 p-2 text-sm text-red-200">{error}</div>}
                {success && <div className="rounded border border-emerald-900 bg-emerald-950/30 p-2 text-sm text-emerald-200">{success}</div>}
                <button
                  type="submit"
                  className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
                  disabled={submitting || !user}
                >
                  {submitting ? t("community.submitting") : t("community.submitDataRequest")}
                </button>
              </form>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}
