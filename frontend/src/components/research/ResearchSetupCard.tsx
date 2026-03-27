"use client";

import { useCallback, useEffect, useState } from "react";

import { SectionHelp } from "@/components/SectionHelp";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { InstrumentSearchDropdown } from "./InstrumentSearchDropdown";
import { getInstrumentsList, type TabSetup } from "./researchTypes";

type Portfolio = Awaited<ReturnType<typeof api.listPortfolios>>[number];
type Entity = Awaited<ReturnType<typeof api.listEntities>>[number];
type InstrumentHit = Awaited<ReturnType<typeof api.searchInstruments>>[number];
type KeywordGroup = Awaited<ReturnType<typeof api.listGroups>>[number];

export function ResearchSetupCard({
  setup,
  onSetupChange,
  projectName,
  tabTitle,
}: {
  setup: TabSetup;
  onSetupChange: (next: TabSetup) => void;
  projectName: string;
  /** Display-only; edit tab name in the tab bar (inline edit). */
  tabTitle?: string;
}) {
  const { t } = useI18n();
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [instrumentResults, setInstrumentResults] = useState<InstrumentHit[]>([]);
  const [instrumentSearchLoading, setInstrumentSearchLoading] = useState(false);
  const [instrumentSearchOpen, setInstrumentSearchOpen] = useState(false);
  const [instrumentCategory, setInstrumentCategory] = useState("");
  const [termInput, setTermInput] = useState("");
  const [relatedSearchLoading, setRelatedSearchLoading] = useState(false);
  const [relatedSearchOpen, setRelatedSearchOpen] = useState(false);
  const [relatedSearchQuery, setRelatedSearchQuery] = useState("");
  const [relatedSearchResults, setRelatedSearchResults] = useState<InstrumentHit[]>([]);
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[]>([]);

  const instrumentsList = getInstrumentsList(setup);

  useEffect(() => {
    api.listPortfolios().then(setPortfolios).catch(() => setPortfolios([]));
    api.listGroups().then(setKeywordGroups).catch(() => setKeywordGroups([]));
  }, []);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setEntities([]);
      return;
    }
    api.listEntities(selectedPortfolioId).then(setEntities).catch(() => setEntities([]));
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!instrumentQuery.trim() && !instrumentSearchOpen) return;
    if (!instrumentQuery.trim()) {
      setInstrumentResults([]);
      setInstrumentSearchLoading(false);
      return;
    }
    setInstrumentSearchLoading(true);
    const t = setTimeout(() => {
      api
        .searchInstruments(
          instrumentQuery.trim(),
          undefined,
          undefined,
          instrumentCategory || undefined
        )
        .then((r) => {
          setInstrumentResults(r);
          setInstrumentSearchLoading(false);
        })
        .catch(() => {
          setInstrumentResults([]);
          setInstrumentSearchLoading(false);
        });
    }, 300);
    return () => clearTimeout(t);
  }, [instrumentQuery, instrumentSearchOpen, instrumentCategory]);

  useEffect(() => {
    if (!relatedSearchQuery.trim()) {
      setRelatedSearchResults([]);
      setRelatedSearchLoading(false);
      return;
    }
    setRelatedSearchLoading(true);
    const t = setTimeout(() => {
      api
        .searchInstruments(relatedSearchQuery.trim())
        .then((r) => {
          setRelatedSearchResults(r);
          setRelatedSearchLoading(false);
        })
        .catch(() => {
          setRelatedSearchResults([]);
          setRelatedSearchLoading(false);
        });
    }, 300);
    return () => clearTimeout(t);
  }, [relatedSearchQuery]);

  const applyEntity = useCallback(
    (entityId: string) => {
      api
        .getEntity(entityId)
        .then((e) => {
          const nextInstruments = getInstrumentsList(setup).length
            ? setup.instruments
            : e.instrument
              ? [{ id: e.instrument.id, symbol: e.instrument.symbol }]
              : undefined;
          onSetupChange({
            ...setup,
            entity_id: e.id,
            entity_name: e.name,
            instruments: nextInstruments ?? setup.instruments,
            primary_instrument_id: setup.primary_instrument_id ?? e.instrument_id ?? undefined,
            primary_instrument_symbol: setup.primary_instrument_symbol ?? e.instrument?.symbol ?? undefined,
            terms: setup.terms?.length ? setup.terms : e.terms.map((t) => t.term),
          });
        })
        .catch(() => {});
    },
    [setup, onSetupChange]
  );

  const clearEntity = useCallback(() => {
    onSetupChange({
      ...setup,
      entity_id: null,
      entity_name: undefined,
    });
  }, [setup, onSetupChange]);

  const addInstrument = useCallback(
    (inst: InstrumentHit) => {
      const list = getInstrumentsList(setup);
      if (list.some((x) => x.id === inst.id)) return;
      const next = [...list, { id: inst.id, symbol: inst.symbol }].slice(0, 20);
      onSetupChange({ ...setup, instruments: next });
      setInstrumentSearchOpen(false);
      setInstrumentQuery("");
      setInstrumentResults([]);
    },
    [setup, onSetupChange]
  );

  const removeInstrument = useCallback(
    (index: number) => {
      const list = getInstrumentsList(setup);
      const next = list.filter((_, i) => i !== index);
      onSetupChange({
        ...setup,
        instruments: next.length ? next : undefined,
        primary_instrument_id: next.length === 0 ? null : undefined,
        primary_instrument_symbol: next.length === 0 ? undefined : setup.primary_instrument_symbol,
      });
    },
    [setup, onSetupChange]
  );

  const addTerm = useCallback(
    (t: string) => {
      const v = t.trim().toLowerCase();
      if (!v) return;
      const terms = setup.terms ?? [];
      if (terms.includes(v)) return;
      onSetupChange({ ...setup, terms: [...terms, v].slice(0, 20) });
      setTermInput("");
    },
    [setup, onSetupChange]
  );

  const removeTerm = useCallback(
    (t: string) => {
      onSetupChange({ ...setup, terms: (setup.terms ?? []).filter((x) => x !== t) });
    },
    [setup, onSetupChange]
  );

  const addRelatedInstrument = useCallback(
    (inst: InstrumentHit) => {
      const ids = setup.related_instrument_ids ?? [];
      const labels = setup.related_instrument_labels ?? [];
      if (ids.includes(inst.id)) return;
      onSetupChange({
        ...setup,
        related_instrument_ids: [...ids, inst.id],
        related_instrument_labels: [...labels, inst.symbol],
      });
      setRelatedSearchOpen(false);
      setRelatedSearchQuery("");
    },
    [setup, onSetupChange]
  );

  const removeRelatedInstrument = useCallback(
    (index: number) => {
      const ids = [...(setup.related_instrument_ids ?? [])];
      const labels = [...(setup.related_instrument_labels ?? [])];
      ids.splice(index, 1);
      labels.splice(index, 1);
      onSetupChange({ ...setup, related_instrument_ids: ids, related_instrument_labels: labels });
    },
    [setup, onSetupChange]
  );

  return (
    <div className="mb-4 rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold text-slate-200">{t("research.universe")}</h3>
          <SectionHelp titleKey="help.researchUniverseTitle" bodyKey="help.researchUniverseBody" />
        </div>
        {tabTitle != null && tabTitle !== "" && (
          <span className="text-xs text-slate-500">{t("research.tabBadge", { tab: tabTitle })}</span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-slate-500">{t("research.scopeHint")}</p>

      <div className="mt-4 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.instruments")}</label>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {instrumentsList.map((inst, i) => (
              <span key={inst.id} className="inline-flex items-center gap-1 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                {inst.symbol}
                <button type="button" onClick={() => removeInstrument(i)} className="hover:text-red-300" aria-label="Remove">×</button>
              </span>
            ))}
            <InstrumentSearchDropdown
              open={instrumentSearchOpen}
              onOpenChange={setInstrumentSearchOpen}
              query={instrumentQuery}
              onQueryChange={setInstrumentQuery}
              results={instrumentResults}
              loading={instrumentSearchLoading}
              onSelect={addInstrument}
              selectedIds={instrumentsList.map((x) => x.id)}
              category={instrumentCategory}
              onCategoryChange={setInstrumentCategory}
              showCategoryFilter
              placeholder={t("research.searchSymbol")}
              triggerLabel={t("research.addInstrument")}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.entityOrGroup")}</label>
          {setup.entity_id ? (
            <div className="mt-1 flex items-center gap-2">
              <span className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-200">{setup.entity_name ?? setup.entity_id}</span>
              <button type="button" onClick={clearEntity} className="text-xs text-slate-500 hover:text-red-300">
                {t("common.clear")}
              </button>
            </div>
          ) : (
            <div className="mt-1 flex flex-wrap gap-2">
              <select
                value={selectedPortfolioId ?? ""}
                onChange={(e) => setSelectedPortfolioId(e.target.value || null)}
                className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300"
              >
                <option value="">{t("research.selectPortfolio")}</option>
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                value={setup.entity_id ?? ""}
                onChange={(e) => (e.target.value ? applyEntity(e.target.value) : clearEntity())}
                className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300"
              >
                <option value="">{t("research.selectEntity")}</option>
                {entities.map((ent) => (
                  <option key={ent.id} value={ent.id}>
                    {ent.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.keywordGroup")}</label>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <select
              value={setup.keyword_group_id ?? ""}
              onChange={(e) => {
                const gid = e.target.value || null;
                const found = keywordGroups.find((g) => g.id === gid);
                onSetupChange({
                  ...setup,
                  keyword_group_id: gid,
                  keyword_group_name: found?.name,
                });
              }}
              className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300"
            >
              <option value="">{t("research.none")}</option>
              {keywordGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            {setup.keyword_group_name ? (
              <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">{setup.keyword_group_name}</span>
            ) : null}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.relatedInstruments")}</label>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {(setup.related_instrument_labels ?? []).map((label, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                {label}
                <button type="button" onClick={() => removeRelatedInstrument(i)} className="hover:text-red-300" aria-label="Remove">
                  ×
                </button>
              </span>
            ))}
            <InstrumentSearchDropdown
              open={relatedSearchOpen}
              onOpenChange={setRelatedSearchOpen}
              query={relatedSearchQuery}
              onQueryChange={setRelatedSearchQuery}
              results={relatedSearchResults}
              loading={relatedSearchLoading}
              onSelect={addRelatedInstrument}
              selectedIds={setup.related_instrument_ids ?? []}
              placeholder="Search symbol…"
              triggerLabel={t("research.addRelated")}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.terms")}</label>
          <div className="mt-1 flex flex-wrap gap-1.5 rounded border border-slate-700 bg-slate-950/60 p-2">
            {(setup.terms ?? []).map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                {t}
                <button type="button" onClick={() => removeTerm(t)} className="hover:text-red-300" aria-label="Remove">
                  ×
                </button>
              </span>
            ))}
            <input
              type="text"
              value={termInput}
              onChange={(e) => setTermInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addTerm(termInput);
                }
              }}
              placeholder={t("research.termsPlaceholder")}
              className="min-w-[120px] flex-1 bg-transparent px-1 py-0.5 text-xs text-slate-100 outline-none placeholder:text-slate-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.timeframe")}</label>
          <select
            value={setup.default_time_range ?? "3m"}
            onChange={(e) => onSetupChange({ ...setup, default_time_range: e.target.value })}
            className="mt-1 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300"
          >
            <option value="1m">1 month</option>
            <option value="3m">3 months</option>
            <option value="6m">6 months</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400">{t("research.notes")}</label>
          <textarea
            value={setup.notes ?? ""}
            onChange={(e) => onSetupChange({ ...setup, notes: e.target.value })}
            rows={3}
            placeholder={t("research.notesPlaceholder")}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
          />
        </div>
      </div>
    </div>
  );
}

/** Re-export for callers that still use TabSetup from researchTypes. */
export { hasResearchTarget } from "./researchTypes";
