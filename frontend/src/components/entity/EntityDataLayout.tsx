"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EntityConceptGuideModal } from "@/components/entity/EntityConceptGuideModal";
import { SlowLoadBanner, useSlowLoadVisible } from "@/components/SlowLoadBanner";
import { SectionHelp } from "@/components/SectionHelp";
import { api, instrumentSearchNeedsResolve, parseApiError, toInstrumentBindResolve } from "@/lib/api";
import type { FeatureGuideLocale } from "@/content/featureGuide";
import { featureGuideContent } from "@/content/featureGuide";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
import type { Locale } from "@/lib/i18n";
import { INSTRUMENT_CATEGORIES } from "@/lib/instrumentCategories";
import { FREE_PLAN_LIMITS } from "@/lib/limits";

function toFeatureGuideLocale(locale: Locale): FeatureGuideLocale {
  if (locale === "zh") return "zh";
  if (locale === "pt") return "pt";
  return "en";
}

type Portfolio = Awaited<ReturnType<typeof api.listPortfolios>>[number];
type Entity = Awaited<ReturnType<typeof api.listEntities>>[number];
type InstrumentHit = NonNullable<Entity["instrument"]>;
type SearchInstrumentHit = InstrumentHit & { exchange?: string | null; country?: string | null };

type EntityDataLayoutProps = {
  /** When false, data effects are paused so a hidden tab does not refetch. */
  isActive?: boolean;
};

export function EntityDataLayout({ isActive = true }: EntityDataLayoutProps) {
  const { t, locale } = useI18n();
  const { user: authUser, loading: userLoading } = useUser();
  const isAdminUser = Boolean(authUser?.is_admin);
  const [conceptGuideOpen, setConceptGuideOpen] = useState(false);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState<Portfolio | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [entityName, setEntityName] = useState("");
  const [instrumentCategory, setInstrumentCategory] = useState("");
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [instrumentResults, setInstrumentResults] = useState<SearchInstrumentHit[]>([]);
  const [selectedInstrument, setSelectedInstrument] = useState<SearchInstrumentHit | null>(null);
  const [terms, setTerms] = useState<string[]>([]);
  const [termInput, setTermInput] = useState("");
  const [aiOpen, setAiOpen] = useState(false);
  const [aiIdea, setAiIdea] = useState("");
  const [aiKeywords, setAiKeywords] = useState<string[]>([]);
  const [aiKeywordError, setAiKeywordError] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [portfolioBusy, setPortfolioBusy] = useState(false);
  const [portfolioSuccess, setPortfolioSuccess] = useState<string | null>(null);
  const [portfolioFetchPending, setPortfolioFetchPending] = useState(false);
  const [entitiesFetchPending, setEntitiesFetchPending] = useState(false);

  const dashSlowVisible = useSlowLoadVisible(
    isActive && (portfolioFetchPending || entitiesFetchPending)
  );

  const loadPortfolios = useCallback(async () => {
    setPortfolioFetchPending(true);
    try {
      const list = await api.listPortfolios();
      setPortfolios(list);
      setSelectedPortfolio((sp) => (!sp && list[0] ? list[0] : sp));
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setPortfolioFetchPending(false);
    }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    void loadPortfolios();
  }, [isActive, loadPortfolios]);

  useEffect(() => {
    if (!isActive) return;
    if (!selectedPortfolio) {
      setEntities([]);
      setEntitiesFetchPending(false);
      return;
    }
    setEntitiesFetchPending(true);
    setError(null);
    api
      .listEntities(selectedPortfolio.id)
      .then(setEntities)
      .catch((e: unknown) => setError(parseApiError(e)))
      .finally(() => setEntitiesFetchPending(false));
  }, [isActive, selectedPortfolio?.id]);

  useEffect(() => {
    if (!instrumentQuery.trim()) {
      setInstrumentResults([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .searchInstruments(instrumentQuery.trim(), undefined, undefined, instrumentCategory || undefined)
        .then((list) =>
          setInstrumentResults(
            list.map((x) => ({
              id: x.id,
              symbol: x.symbol,
              display_name: x.display_name,
              asset_class: x.asset_class,
              market: x.market,
              exchange: x.exchange,
              country: x.country,
              data_origin: x.data_origin,
            }))
          )
        )
        .catch(() => setInstrumentResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [instrumentQuery, instrumentCategory]);

  const addTerm = useCallback((t: string) => {
    const v = t.trim().toLowerCase();
    if (!v) return;
    setTerms((prev) => (prev.includes(v) ? prev : [...prev, v].slice(0, 15)));
  }, []);

  const removeTerm = useCallback((t: string) => setTerms((prev) => prev.filter((x) => x !== t)), []);

  const handleTermKey = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        addTerm(termInput);
        setTermInput("");
      }
    },
    [termInput, addTerm]
  );

  const handleCreateEntity = useCallback(async () => {
    if (!selectedPortfolio || !entityName.trim()) return;
    setError(null);
    try {
      await api.createEntity({
        portfolio_id: selectedPortfolio.id,
        name: entityName.trim(),
        instrument_id: selectedInstrument?.id ?? null,
        ...(selectedInstrument && instrumentSearchNeedsResolve(selectedInstrument)
          ? { instrument_resolve: toInstrumentBindResolve(selectedInstrument) }
          : {}),
        terms,
      });
      setEntities(await api.listEntities(selectedPortfolio.id));
      setCreateOpen(false);
      setEntityName("");
      setSelectedInstrument(null);
      setTerms([]);
      setInstrumentQuery("");
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }, [selectedPortfolio, entityName, selectedInstrument, terms]);

  const handleDeleteEntity = useCallback(
    async (entityId: string) => {
      if (!selectedPortfolio || !confirm(t("entity.confirmDeleteEntity"))) return;
      setError(null);
      try {
        await api.deleteEntity(entityId);
        setEntities(await api.listEntities(selectedPortfolio.id));
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    },
    [selectedPortfolio, t]
  );

  const handleAiSuggest = useCallback(async () => {
    setAiLoading(true);
    setAiKeywords([]);
    setAiKeywordError(null);
    try {
      const assetClassMap: Record<string, string> = {
        stock: "equity",
        etf: "etf",
        index: "index",
        futures: "futures",
        crypto: "crypto",
        "hong kong": "equity",
      };
      const res = await api.aiKeywordSuggestions({
        idea: aiIdea.trim(),
        instrument: selectedInstrument?.symbol ?? undefined,
        asset_class: selectedInstrument?.asset_class ?? (instrumentCategory ? assetClassMap[instrumentCategory] : undefined),
        portfolio: selectedPortfolio?.name ?? undefined,
      });
      setAiKeywords((res.keywords ?? []).slice(0, 8));
    } catch (e: unknown) {
      setAiKeywordError(parseApiError(e));
    } finally {
      setAiLoading(false);
    }
  }, [aiIdea, selectedInstrument, instrumentCategory, selectedPortfolio]);

  const handleDeletePortfolio = useCallback(
    async (portfolioId: string) => {
      if (!confirm(t("entity.confirmDeletePortfolio"))) return;
      setError(null);
      try {
        await api.deletePortfolio(portfolioId);
        const list = await api.listPortfolios();
        setPortfolios(list);
        if (!list.length) {
          setSelectedPortfolio(null);
          setEntities([]);
          return;
        }
        if (!selectedPortfolio || selectedPortfolio.id === portfolioId) {
          setSelectedPortfolio(list[0]);
        } else {
          const stillSelected = list.find((p) => p.id === selectedPortfolio.id);
          setSelectedPortfolio(stillSelected ?? list[0]);
        }
      } catch (e: unknown) {
        setError(parseApiError(e));
      }
    },
    [selectedPortfolio, t]
  );

  return (
    <div className="min-w-0 space-y-4">
      {isActive ? <SlowLoadBanner visible={dashSlowVisible} /> : null}
      {error ? (
        <div className="rounded border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">{error}</div>
      ) : null}
      {portfolioSuccess ? (
        <div className="rounded border border-emerald-900/50 bg-emerald-950/25 px-3 py-2 text-sm text-emerald-200">{portfolioSuccess}</div>
      ) : null}
      <div className="grid min-w-0 gap-6 md:grid-cols-[280px_1fr]">
      <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <h2 className="text-sm font-semibold text-slate-200">{t("entity.portfoliosHeading")}</h2>
            <SectionHelp titleKey="help.portfoliosTitle" bodyKey="help.portfoliosBody" />
          </div>
          <span className="text-xs text-slate-400">
            {portfolios.length} / {FREE_PLAN_LIMITS.MAX_PORTFOLIOS}
          </span>
        </div>
        <Link className="mt-1 block text-xs text-indigo-300 hover:text-indigo-200" href="/schedules">
          {t("entity.monitoringLink")}
        </Link>
        <div className="mt-3 space-y-2">
          {portfolios.map((p) => (
            <div
              key={p.id}
              className={
                "flex w-full items-center gap-2 rounded border px-3 py-2 text-sm " +
                (selectedPortfolio?.id === p.id ? "border-slate-600 bg-slate-900 text-slate-100" : "border-slate-800 bg-slate-950/40 text-slate-300 hover:border-slate-700")
              }
            >
              <button
                type="button"
                onClick={() => setSelectedPortfolio(p)}
                className="min-w-0 flex-1 truncate text-left font-medium text-inherit"
              >
                {p.name}
              </button>
              <button
                type="button"
                onClick={() => void handleDeletePortfolio(p.id)}
                className="shrink-0 rounded px-2 py-0.5 text-xs text-red-300 hover:bg-red-500/90 hover:text-white"
              >
                {t("common.delete")}
              </button>
            </div>
          ))}
        </div>
        <div className="mt-4 border-t border-slate-800 pt-4">
          <div className="text-xs font-semibold text-slate-300">{t("entity.addPortfolio")}</div>
          <div className="mt-2 flex gap-2">
            <input
              className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
              placeholder={t("entity.namePlaceholder")}
              value={newPortfolioName}
              onChange={(e) => setNewPortfolioName(e.target.value)}
              disabled={portfolios.length >= FREE_PLAN_LIMITS.MAX_PORTFOLIOS}
            />
            <button
              type="button"
              disabled={
                !newPortfolioName.trim() ||
                portfolios.length >= FREE_PLAN_LIMITS.MAX_PORTFOLIOS ||
                portfolioBusy
              }
              title={portfolios.length >= FREE_PLAN_LIMITS.MAX_PORTFOLIOS ? t("entity.maxPortfoliosReached", { max: FREE_PLAN_LIMITS.MAX_PORTFOLIOS }) : undefined}
              onClick={async () => {
                const nm = newPortfolioName.trim();
                if (!nm) {
                  setPortfolioSuccess(null);
                  setError(t("entity.portfolioNameRequired"));
                  return;
                }
                setError(null);
                setPortfolioSuccess(null);
                setPortfolioBusy(true);
                try {
                  await api.createPortfolio({ name: nm });
                  setNewPortfolioName("");
                  await loadPortfolios();
                  setPortfolioSuccess(t("entity.portfolioAddedToast"));
                  window.setTimeout(() => setPortfolioSuccess(null), 5000);
                } catch (e: unknown) {
                  setError(parseApiError(e));
                } finally {
                  setPortfolioBusy(false);
                }
              }}
              className="rounded bg-indigo-600 px-2 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {portfolioBusy ? t("common.loading") : t("common.add")}
            </button>
          </div>
        </div>
      </section>

      <section className="min-w-0 space-y-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between">
            <div className="flex min-w-0 items-center gap-1.5">
              <h2 className="min-w-0 truncate text-sm font-semibold text-slate-200">
                {selectedPortfolio ? t("entity.entitiesIn", { name: selectedPortfolio.name }) : t("entity.selectPortfolio")}
              </h2>
              <SectionHelp titleKey="help.entitiesListTitle" bodyKey="help.entitiesListBody" />
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setConceptGuideOpen(true)}
                className="rounded border border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:border-slate-500 hover:text-slate-200"
              >
                {featureGuideContent.entityConcept[toFeatureGuideLocale(locale)].buttonLabel}
              </button>
              {selectedPortfolio ? (
                <>
                  <span className="text-xs text-slate-400">
                    {entities.length} / {FREE_PLAN_LIMITS.MAX_ENTITIES_PER_PORTFOLIO}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCreateOpen(true)}
                    disabled={entities.length >= FREE_PLAN_LIMITS.MAX_ENTITIES_PER_PORTFOLIO}
                    title={entities.length >= FREE_PLAN_LIMITS.MAX_ENTITIES_PER_PORTFOLIO ? t("entity.maxEntitiesPerPortfolio", { max: FREE_PLAN_LIMITS.MAX_ENTITIES_PER_PORTFOLIO }) : undefined}
                    className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {t("entity.createEntity")}
                  </button>
                </>
              ) : null}
            </div>
          </div>
          {!selectedPortfolio ? (
            <p className="mt-3 text-sm text-slate-400">{t("entity.createOrSelectPortfolio")}</p>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {entities.map((ent) => (
                <div key={ent.id} className="flex items-start justify-between rounded border border-slate-700 bg-slate-950/50 p-3">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-slate-100">{ent.name}</div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {ent.instrument ? `${ent.instrument.symbol}${ent.instrument.display_name ? ` · ${ent.instrument.display_name}` : ""}` : t("entity.noInstrumentShort")}
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-xs text-slate-500">{t("entity.termsCount", { count: ent.terms.length })}</span>
                      <Link
                        href={`/dashboard/entities/${ent.id}`}
                        className="text-xs text-indigo-300 hover:text-indigo-200"
                      >
                        {t("entity.view")}
                      </Link>
                    </div>
                  </div>
                  <button type="button" onClick={() => handleDeleteEntity(ent.id)} className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-red-300">
                    {t("common.delete")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {createOpen && selectedPortfolio ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-100">{t("entity.createEntity")}</h3>
              <div className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-400">{t("entity.entityNameLabel")}</label>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                    value={entityName}
                    onChange={(e) => setEntityName(e.target.value)}
                    placeholder={t("entity.entityNamePlaceholder")}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400">{t("entity.assetType")}</label>
                  <select
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                    value={instrumentCategory}
                    onChange={(e) => setInstrumentCategory(e.target.value)}
                  >
                    {INSTRUMENT_CATEGORIES.map(({ value, label }) => (
                      <option key={value || "all"} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400">{t("entity.instrumentSearchLabel")}</label>
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                    value={instrumentQuery}
                    onChange={(e) => {
                      setInstrumentQuery(e.target.value);
                      if (!e.target.value) setSelectedInstrument(null);
                    }}
                    placeholder={t("entity.searchInstrumentPlaceholder")}
                  />
                  {instrumentResults.length > 0 ? (
                    <ul className="mt-1 max-h-32 overflow-auto rounded border border-slate-700 bg-slate-950">
                      {instrumentResults.map((inst) => (
                        <li key={inst.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedInstrument(inst);
                              setInstrumentQuery(inst.symbol);
                              setInstrumentResults([]);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                          >
                            {inst.symbol}{inst.display_name ? ` · ${inst.display_name}` : ""}{" "}
                            <span className="text-slate-500">
                              ({inst.asset_class}
                              {(inst.exchange || inst.country) ? ` · ${inst.exchange || inst.country}` : ""})
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {selectedInstrument ? <p className="mt-1 text-xs text-slate-500">{t("entity.selectedLabel")} {selectedInstrument.symbol}</p> : null}
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-medium text-slate-400">{t("entity.terms")}</label>
                    {userLoading ? (
                      <span className="text-xs text-slate-600"> </span>
                    ) : isAdminUser ? (
                      <button type="button" onClick={() => { setAiOpen(true); setAiKeywords([]); setAiIdea(""); setAiKeywordError(null); }} className="text-xs text-indigo-300 hover:text-indigo-200">
                        {t("entity.aiSuggestion")}
                      </button>
                    ) : (
                      <span className="text-xs text-slate-500">{t("entity.aiAdminOnlyShort")}</span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5 rounded border border-slate-700 bg-slate-950 p-2">
                    {terms.map((term) => (
                      <span key={term} className="inline-flex items-center gap-1 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                        {term}
                        <button type="button" onClick={() => removeTerm(term)} className="hover:text-red-300" aria-label={t("common.remove")}>×</button>
                      </span>
                    ))}
                    <input
                      className="min-w-[80px] flex-1 bg-transparent px-1 py-0.5 text-sm text-slate-100 outline-none"
                      placeholder={t("entity.typeAndPressEnter")}
                      value={termInput}
                      onChange={(e) => setTermInput(e.target.value)}
                      onKeyDown={handleTermKey}
                    />
                  </div>
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <button type="button" onClick={() => setCreateOpen(false)} className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200">{t("common.cancel")}</button>
                <button type="button" onClick={handleCreateEntity} disabled={!entityName.trim()} className="rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">{t("research.create")}</button>
              </div>
            </div>
          </div>
        ) : null}

        {aiOpen && isAdminUser ? (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-100">{t("entity.aiKeywordSuggestion")}</h3>
              <p className="mt-1 text-xs text-slate-400">{t("entity.aiSuggestionDesc")}</p>
              <textarea
                className="mt-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                rows={3}
                placeholder="Describe a target or industry (e.g. a stock you're interested in). We'll suggest up to 8 keywords."
                value={aiIdea}
                onChange={(e) => setAiIdea(e.target.value)}
              />
              <button type="button" onClick={handleAiSuggest} disabled={aiLoading || !aiIdea.trim()} className="mt-2 w-full rounded bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
                {aiLoading ? t("entity.generating") : t("entity.generateKeywords")}
              </button>
              {aiKeywordError ? (
                <p className="mt-2 text-xs text-amber-300/90" role="alert">
                  {aiKeywordError}
                </p>
              ) : null}
              {aiKeywords.length > 0 ? (
                <div className="mt-3 rounded-lg border border-slate-700/80 bg-slate-950/50 p-2">
                  <p className="text-xs font-medium text-slate-400">Suggested keywords</p>
                  <div className="mt-2 flex flex-wrap gap-1.5" role="list" aria-label="Suggested keywords">
                    {aiKeywords.slice(0, 8).map((k) => (
                      <span
                        key={k}
                        role="listitem"
                        className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-600 bg-slate-800/90 pl-2.5 pr-1 py-0.5 text-xs text-slate-200"
                      >
                        <span className="select-all truncate" title={k}>
                          {k}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            addTerm(k);
                          }}
                          className="shrink-0 rounded-full bg-slate-600 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-slate-500"
                          title="Add to Terms"
                        >
                          +
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="mt-4 flex justify-end">
                <button type="button" onClick={() => setAiOpen(false)} className="rounded px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200">{t("common.close")}</button>
              </div>
            </div>
          </div>
        ) : null}

        {conceptGuideOpen ? (
          <EntityConceptGuideModal locale={locale} onClose={() => setConceptGuideOpen(false)} />
        ) : null}
      </section>
      </div>
    </div>
  );
}
