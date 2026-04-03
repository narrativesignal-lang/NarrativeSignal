"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { SectionHelp } from "@/components/SectionHelp";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  getTabsFromLayoutConfig,
  getInstrumentsList,
  hasResearchTarget,
  type LayoutConfig,
  type PanelConfig,
  type ResearchTab,
  type TabSetup,
} from "./researchTypes";
import {
  ResizableChartSection,
  RESIZE_DEFAULT_HEIGHT,
  RESIZE_HANDLE_HEIGHT,
  RESIZE_MAX_HEIGHT,
  RESIZE_MIN_HEIGHT,
} from "@/components/ResizableChartSection";
import { ResearchAddBlockModal } from "./ResearchAddBlockModal";
import { ResearchChart, type ChartType } from "./ResearchChart";
import { ResearchOverlayPanel } from "./ResearchOverlayPanel";
import { ResearchInstrumentChartZone } from "./ResearchInstrumentChartZone";
import { ResearchSetupCard } from "./ResearchSetupCard";

const MAX_BLOCKS_PER_TAB = 5;
const MAX_TABS = 10;

type Project = Awaited<ReturnType<typeof api.researchProjects>>[number];
type SnapshotItem = Awaited<ReturnType<typeof api.listResearchSetupSnapshots>>[number];

export function ResearchWorkspace({
  project,
  onUpdate,
}: {
  project: Project | null;
  onUpdate: (updated: Project | null) => void;
}) {
  const { t } = useI18n();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [setupPanelOpen, setSetupPanelOpen] = useState(false);
  const [importCode, setImportCode] = useState("");
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [lastSavedCode, setLastSavedCode] = useState<string | null>(null);
  const [renameTabId, setRenameTabId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameSnapshotCode, setRenameSnapshotCode] = useState<string | null>(null);
  const [renameSnapshotValue, setRenameSnapshotValue] = useState("");
  const setupPanelRef = useRef<HTMLDivElement>(null);

  const fetchSnapshots = useCallback(() => {
    api.listResearchSetupSnapshots().then(setSnapshots).catch(() => setSnapshots([]));
  }, []);

  useEffect(() => {
    if (setupPanelOpen) fetchSnapshots();
  }, [setupPanelOpen, fetchSnapshots]);

  const config = (project?.layout_config ?? {}) as Record<string, unknown>;
  const { tabs, active_tab_id } = getTabsFromLayoutConfig(config);
  const activeTab = tabs.find((t) => t.id === active_tab_id) ?? tabs[0];
  const panels = activeTab?.panels ?? [];
  const setup = activeTab?.setup ?? {};
  const setupComplete = hasResearchTarget(setup);
  const atBlockLimit = panels.length >= MAX_BLOCKS_PER_TAB;
  const canAdd = !atBlockLimit && setupComplete;
  const canAddTab = tabs.length < MAX_TABS;

  const persistLayoutConfig = useCallback(
    (patch: Partial<LayoutConfig>) => {
      if (!project) return;
      const next: Record<string, unknown> = {
        ...project.layout_config,
        ...(patch.tabs != null && { tabs: patch.tabs }),
        ...(patch.active_tab_id != null && { active_tab_id: patch.active_tab_id }),
      };
      api
        .updateResearchProject(project.id, { layout_config: next })
        .then((updated) => onUpdate(updated))
        .catch(() => {});
    },
    [project, onUpdate]
  );

  const setTabs = useCallback(
    (nextTabs: ResearchTab[], activeId?: string) => {
      persistLayoutConfig({
        tabs: nextTabs,
        active_tab_id: activeId ?? active_tab_id,
      });
    },
    [persistLayoutConfig, active_tab_id]
  );

  const updateActiveTab = useCallback(
    (updater: (t: ResearchTab) => ResearchTab) => {
      if (!activeTab) return;
      const next = tabs.map((t) => (t.id === activeTab.id ? updater(t) : t));
      setTabs(next);
    },
    [tabs, activeTab, setTabs]
  );

  const chartZoneHeight = activeTab?.chart_zone_height ?? RESIZE_DEFAULT_HEIGHT;
  const setChartZoneHeight = useCallback(
    (h: number) =>
      updateActiveTab((t) => ({ ...t, chart_zone_height: h })),
    [updateActiveTab]
  );

  const instrumentsList = getInstrumentsList(activeTab?.setup);

  const setSetup = useCallback(
    (next: TabSetup) =>
      updateActiveTab((t) => ({
        ...t,
        setup: next,
        title: next.tab_title?.trim() ? next.tab_title.trim() : t.title,
      })),
    [updateActiveTab]
  );

  const setPanels = useCallback(
    (next: PanelConfig[]) => updateActiveTab((t) => ({ ...t, panels: next })),
    [updateActiveTab]
  );

  const addSingleBlock = useCallback(
    (type: ChartType, kind: "single" | "analysis") => {
      if (!activeTab || panels.length >= MAX_BLOCKS_PER_TAB) return;
      setPanels([...panels, { type, kind }]);
      setAddModalOpen(false);
    },
    [activeTab, panels, setPanels]
  );

  const addOverlayBundle = useCallback(
    (types: ChartType[]) => {
      if (!activeTab || panels.length >= MAX_BLOCKS_PER_TAB || types.length === 0) return;
      setPanels([...panels, { type: types[0]!, kind: "overlay", overlayTypes: types }]);
      setAddModalOpen(false);
    },
    [activeTab, panels, setPanels]
  );

  const removeChart = useCallback(
    (index: number) => {
      setPanels(panels.filter((_, i) => i !== index));
    },
    [panels, setPanels]
  );

  const moveChart = useCallback(
    (index: number, direction: "up" | "down") => {
      const next = [...panels];
      const j = direction === "up" ? index - 1 : index + 1;
      if (j < 0 || j >= next.length) return;
      [next[index], next[j]] = [next[j], next[index]];
      setPanels(next);
    },
    [panels, setPanels]
  );

  const addTab = useCallback(() => {
    const newTab: ResearchTab = {
      id: crypto.randomUUID(),
      title: t("research.newTabName"),
      setup: {},
      panels: [],
    };
    setTabs([...tabs, newTab], newTab.id);
  }, [tabs, setTabs, t]);

  const switchTab = useCallback(
    (id: string) => {
      persistLayoutConfig({ active_tab_id: id });
    },
    [persistLayoutConfig]
  );

  const renameTab = useCallback(
    (id: string, title: string) => {
      const trimmed = title.trim() || undefined;
      setTabs(
        tabs.map((t) =>
          t.id === id
            ? { ...t, title: trimmed ?? t.title, setup: { ...t.setup, tab_title: trimmed ?? t.setup.tab_title } }
            : t
        )
      );
      setRenameTabId(null);
      setRenameValue("");
    },
    [tabs, setTabs]
  );

  const removeTab = useCallback(() => {
    if (tabs.length <= 1) return;
    const idx = tabs.findIndex((t) => t.id === active_tab_id);
    const next = tabs.filter((t) => t.id !== active_tab_id);
    const newActive = next[Math.max(0, idx - 1)]?.id ?? next[0]?.id;
    setTabs(next, newActive);
  }, [tabs, active_tab_id, setTabs]);

  const handleSaveSetup = useCallback(() => {
    if (!activeTab) return;
    const config = {
      tab_title: activeTab.title,
      setup: activeTab.setup,
      panels: activeTab.panels,
    };
    api
      .saveResearchSetupSnapshot({ config, name: activeTab.title || undefined })
      .then(({ code }) => {
        setLastSavedCode(code);
        fetchSnapshots();
      })
      .catch(() => {});
  }, [activeTab, fetchSnapshots]);

  const handleImportSetup = useCallback(() => {
    const code = importCode.trim().toUpperCase();
    if (!code) return;
    const norm = code.startsWith("RS-") ? code : "RS-" + code;
    api
      .importResearchSetupSnapshot(norm)
      .then(({ config: imported }) => {
        const tab = imported as { tab_title?: string; setup?: TabSetup; panels?: PanelConfig[] };
        const newTab: ResearchTab = {
          id: crypto.randomUUID(),
          title: (tab.tab_title as string) || t("research.importedTabName"),
          setup: tab.setup ?? {},
          panels: Array.isArray(tab.panels) ? tab.panels : [],
        };
        setTabs([...tabs, newTab], newTab.id);
        setImportCode("");
      })
      .catch(() => {});
  }, [importCode, tabs, setTabs, t]);

  const copySnapshotCode = useCallback((code: string) => {
    void navigator.clipboard?.writeText(code).then(() => setSetupPanelOpen(false));
  }, []);

  const updateSnapshotName = useCallback(
    (code: string, name: string) => {
      api
        .updateResearchSetupSnapshot(code, { name: name.trim() || null })
        .then(() => {
          fetchSnapshots();
          setRenameSnapshotCode(null);
          setRenameSnapshotValue("");
        })
        .catch(() => {});
    },
    [fetchSnapshots]
  );

  const deleteSnapshot = useCallback(
    (code: string) => {
      if (!confirm(t("research.confirmDeleteSnapshot"))) return;
      api.deleteResearchSetupSnapshot(code).then(fetchSnapshots).catch(() => {});
    },
    [fetchSnapshots, t]
  );

  useEffect(() => {
    const el = setupPanelRef.current;
    if (!el) return;
    const onOutside = (e: MouseEvent) => {
      if (setupPanelOpen && el && !el.contains(e.target as Node)) setSetupPanelOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [setupPanelOpen]);

  if (!project) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-700 bg-slate-900/20 px-6 text-center">
        <p className="text-sm font-medium text-slate-400">{t("research.noProject")}</p>
        <p className="max-w-sm text-xs text-slate-500">
          {t("research.noProjectHint")}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[60vh] flex-col">
      {/* Tabs bar + Setup (top-right) */}
      <div className="mb-2 flex flex-wrap items-center gap-1 border-b border-slate-800 pb-2">
        {tabs.map((tab) => (
          <div key={tab.id} className="flex items-center gap-0.5">
            {renameTabId === tab.id ? (
              <input
                type="text"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={() => renameTab(tab.id, renameValue)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") renameTab(tab.id, renameValue);
                }}
                className="w-28 rounded border border-slate-600 bg-slate-900 px-1.5 py-0.5 text-xs text-slate-100"
                autoFocus
              />
            ) : (
              <button
                type="button"
                onClick={() => switchTab(tab.id)}
                onDoubleClick={() => {
                  setRenameTabId(tab.id);
                  setRenameValue(tab.title);
                }}
                className={`rounded px-2 py-1 text-xs font-medium ${
                  tab.id === active_tab_id
                    ? "bg-slate-700 text-slate-100"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                {tab.title}
              </button>
            )}
            {tabs.length > 1 && tab.id === active_tab_id && (
              <button
                type="button"
                onClick={removeTab}
                className="rounded p-0.5 text-slate-500 hover:text-red-300"
                title={t("research.removeTabTitle")}
              >
                ×
              </button>
            )}
          </div>
        ))}
        {canAddTab && (
          <button
            type="button"
            onClick={addTab}
            className="rounded border border-dashed border-slate-600 px-2 py-1 text-xs text-slate-500 hover:border-slate-500 hover:text-slate-300"
          >
            {t("research.addTabButton")}
          </button>
        )}

        {/* Compact Setup panel (top-right) */}
        <div className="relative ml-auto" ref={setupPanelRef}>
          <button
            type="button"
            onClick={() => setSetupPanelOpen((o) => !o)}
            className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-400 hover:border-slate-500 hover:text-slate-200"
          >
            {t("research.setupsButton")}
          </button>
          {setupPanelOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 w-64 rounded border border-slate-700 bg-slate-900 py-2 shadow-lg">
              <div className="border-b border-slate-700 px-2 pb-2 text-xs text-slate-500">
                {t("research.setupsPanelIntro")}
              </div>
              <div className="flex flex-col gap-1 px-2 pt-2">
                <button
                  type="button"
                  onClick={handleSaveSetup}
                  className="rounded bg-indigo-600 px-2 py-1.5 text-left text-xs text-white hover:bg-indigo-500"
                >
                  {t("research.saveSetupButton")}
                </button>
                {lastSavedCode && (
                  <div className="rounded bg-slate-800/60 px-2 py-1 text-xs text-slate-300">
                    {t("research.savedPrefix")} <span className="font-mono">{lastSavedCode}</span>
                  </div>
                )}
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={importCode}
                    onChange={(e) => setImportCode(e.target.value)}
                    placeholder={t("research.importPlaceholder")}
                    className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                  />
                  <button
                    type="button"
                    onClick={handleImportSetup}
                    className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-600"
                  >
                    {t("research.importButton")}
                  </button>
                </div>
              </div>
              {snapshots.length > 0 && (
                <div className="mt-2 border-t border-slate-700 px-2 pt-2">
                  <div className="mb-1 text-xs font-medium text-slate-400">{t("research.yourSavedSetups")}</div>
                  <ul className="max-h-40 space-y-1 overflow-y-auto">
                    {snapshots.map((s) => (
                      <li key={s.code} className="flex items-center gap-1 rounded bg-slate-800/40 px-2 py-1 text-xs">
                        {renameSnapshotCode === s.code ? (
                          <input
                            type="text"
                            value={renameSnapshotValue}
                            onChange={(e) => setRenameSnapshotValue(e.target.value)}
                            onBlur={() => updateSnapshotName(s.code, renameSnapshotValue)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") updateSnapshotName(s.code, renameSnapshotValue);
                            }}
                            className="flex-1 rounded border border-slate-600 bg-slate-950 px-1 text-slate-100"
                            autoFocus
                          />
                        ) : (
                          <>
                            <span className="min-w-0 flex-1 truncate font-mono text-slate-200" title={s.code}>
                              {s.name || s.code}
                            </span>
                            <button type="button" onClick={() => copySnapshotCode(s.code)} className="text-slate-500 hover:text-slate-300" title={t("research.copyTitle")}>
                              {t("research.copyVerb")}
                            </button>
                            <button type="button" onClick={() => { setRenameSnapshotCode(s.code); setRenameSnapshotValue(s.name || s.code); }} className="text-slate-500 hover:text-slate-300" title={t("research.renameTitle")}>
                              {t("research.renameVerb")}
                            </button>
                            <button type="button" onClick={() => deleteSnapshot(s.code)} className="text-slate-500 hover:text-red-300" title={t("research.deleteTitle")}>
                              {t("common.delete")}
                            </button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {activeTab ? (
        <>
          <ResearchSetupCard
            setup={setup}
            onSetupChange={setSetup}
            projectName={project.name}
            tabTitle={activeTab.title}
          />

          <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
            <span className="text-sm font-semibold text-slate-200">
              {activeTab.title}
            </span>
            <SectionHelp titleKey="help.researchWorkspaceBlocksTitle" bodyKey="help.researchWorkspaceBlocksBody" />
            <button
              type="button"
              onClick={() => setupComplete && setAddModalOpen(true)}
              disabled={!setupComplete || atBlockLimit}
              title={
                !setupComplete
                  ? t("research.addBlockNeedSetupTitle")
                  : atBlockLimit
                    ? t("research.maxBlocksTabLine")
                    : undefined
              }
              className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-slate-800"
            >
              {t("research.addBlock")}
            </button>
            <span className="text-xs text-slate-500">
              {t("research.blocksCount", { current: panels.length, max: MAX_BLOCKS_PER_TAB })}
            </span>
            {atBlockLimit && (
              <span className="text-xs text-amber-200/80">
                {t("research.maxBlocksTabLine")}
              </span>
            )}
          </div>

          <ResearchAddBlockModal
            open={addModalOpen}
            onClose={() => setAddModalOpen(false)}
            onAddOverlay={addOverlayBundle}
            onAddSingle={addSingleBlock}
            hasResearchTarget={setupComplete}
          />

          {/* Top: built-in instrument K-line zone (resizable) */}
          <ResizableChartSection
            height={chartZoneHeight}
            onHeightChange={setChartZoneHeight}
            minHeight={RESIZE_MIN_HEIGHT}
            maxHeight={RESIZE_MAX_HEIGHT}
            className="shrink-0"
          >
            <ResearchInstrumentChartZone
              instruments={instrumentsList}
              height={chartZoneHeight - RESIZE_HANDLE_HEIGHT}
            />
          </ResizableChartSection>

          {/* Bottom: analysis blocks (scrollable) */}
          <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
            <div className="space-y-4 rounded-lg border border-slate-800 bg-slate-900/30 p-4">
            {panels.length === 0 ? (
              <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-sm text-slate-500">
                <p>No blocks yet. Configure Research Universe above, then use <strong className="text-slate-400">Add Block</strong>.</p>
                <p className="text-xs">Overlay = same-timeline series. Split = stacked charts. Analysis = 3D, institution bias, ratings.</p>
              </div>
            ) : (
              panels.map((p, i) => (
                <div key={i} className="min-h-[140px]">
                  {p.kind === "overlay" ? (
                    <div className="rounded-lg border border-amber-800/40 bg-slate-900/50 p-2">
                      <p className="mb-1 text-xs text-amber-200/80">{t("workspace.sameTimelineNote")}</p>
                      <ResearchOverlayPanel
                        panel={p}
                        entityId={activeTab?.setup?.entity_id ?? null}
                        period={
                          typeof setup.default_time_range === "string" && setup.default_time_range
                            ? setup.default_time_range
                            : "1M"
                        }
                      />
                      <div className="mt-2 flex justify-end gap-1 border-t border-slate-800/80 pt-2">
                        {i > 0 ? (
                          <button
                            type="button"
                            onClick={() => moveChart(i, "up")}
                            className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                            title="Move up"
                          >
                            ↑
                          </button>
                        ) : null}
                        {i < panels.length - 1 ? (
                          <button
                            type="button"
                            onClick={() => moveChart(i, "down")}
                            className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                            title="Move down"
                          >
                            ↓
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeChart(i)}
                          className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300"
                          title="Remove"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  ) : (
                    <ResearchChart
                      type={p.type}
                      hasContext={setupComplete}
                      entityId={activeTab?.setup?.entity_id ?? null}
                      period={
                        typeof setup.default_time_range === "string" && setup.default_time_range
                          ? setup.default_time_range
                          : "1M"
                      }
                      onRemove={() => removeChart(i)}
                      onMoveUp={i > 0 ? () => moveChart(i, "up") : undefined}
                      onMoveDown={i < panels.length - 1 ? () => moveChart(i, "down") : undefined}
                    />
                  )}
                </div>
              ))
            )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
