"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { SectionHelp } from "@/components/SectionHelp";
import { api, parseApiError, type ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type MenuTarget = { type: "folder"; id: string } | { type: "project"; id: string };

type Folder = Awaited<ReturnType<typeof api.researchFolders>>[number];
type Project = Awaited<ReturnType<typeof api.researchProjects>>[number];

/** Blocks (charts, 3D, analysis) are managed in the project workspace via Add Block, not here. */

export function ResearchSidebar({
  selectedProjectId,
  onSelectProject,
  onProjectsChange,
}: {
  selectedProjectId: string | null;
  onSelectProject: (project: Project | null) => void;
  onProjectsChange: (createdOrUpdated?: Project | null) => void;
}) {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [expandedFolderIds, setExpandedFolderIds] = useState<Set<string>>(new Set());
  const [newFolderParentId, setNewFolderParentId] = useState<string | null>(null);
  const ROOT_FOLDER_SENTINEL = "__root__";
  const [newFolderName, setNewFolderName] = useState("");
  const [newProjectFolderId, setNewProjectFolderId] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState("");
  const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [openMenu, setOpenMenu] = useState<MenuTarget | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<{ x: number; y: number } | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const successClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const { t } = useI18n();

  useEffect(() => {
    if (!openMenu) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (menuTriggerRef.current?.contains(target)) return;
      setOpenMenu(null);
      setMenuAnchor(null);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openMenu]);

  const loadAll = useCallback(async () => {
    try {
      setFoldersLoading(true);
      setProjectsLoading(true);
      const fData = await api.researchFolders();
      setFolders(fData);
      setFoldersLoading(false);
      // Projects can be slower; do not block folder render.
      const pData = await api.researchProjects(undefined);
      setProjects(pData);
      setProjectsLoading(false);
      setError(null);
    } catch (e: unknown) {
      console.error("Failed to load research data", e);
      const parsed = parseApiError(e);
      const status = (e as Partial<ApiError>)?.status;
      const looksLikeServer =
        status === 502 ||
        status === 503 ||
        status === 500 ||
        /internal server error/i.test(parsed) ||
        /^request failed \(5\d\d\)$/i.test(parsed);
      setError(looksLikeServer ? `${t("research.loadTreeFailed")}\n\n${t("research.loadTreeFailedServer")}` : parsed);
      setFoldersLoading(false);
      setProjectsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    return () => {
      if (successClearRef.current) clearTimeout(successClearRef.current);
    };
  }, []);

  /** Tree must show ONLY folders and projects. Never render layout_config.tabs, panels, or charts. */
  const isValidFolder = (f: { id?: unknown; name?: unknown; parent_id?: unknown }): f is Folder =>
    typeof f?.id === "string" && typeof f?.name === "string" && (f.parent_id === null || typeof f.parent_id === "string");
  const isValidProject = (p: { id?: unknown; folder_id?: unknown; name?: unknown; layout_config?: unknown }): p is Project =>
    typeof p?.id === "string" && typeof p?.folder_id === "string" && typeof p?.name === "string";
  /** Exclude legacy chart-only entries: layout_config.charts present but no tabs/panels (chart nodes, not projects). */
  const isChartBlockNode = (p: Project): boolean => {
    const cfg = p.layout_config;
    if (!cfg || typeof cfg !== "object") return false;
    const c = cfg as Record<string, unknown>;
    const hasCharts = Array.isArray(c.charts) && c.charts.length > 0;
    const hasTabs = Array.isArray(c.tabs) && c.tabs.length > 0;
    const hasPanels = Array.isArray(c.panels) && c.panels.length > 0;
    return hasCharts && !hasTabs && !hasPanels;
  };

  const safeFolders = folders.filter(isValidFolder);
  const safeProjects = projects.filter((p) => isValidProject(p) && !isChartBlockNode(p as Project));

  const rootFolders = safeFolders.filter((f) => !f.parent_id);
  const childFolders = (parentId: string) => safeFolders.filter((f) => f.parent_id === parentId);
  const projectsInFolder = (folderId: string) => safeProjects.filter((p) => p.folder_id === folderId);

  async function createFolder(parentId: string | null) {
    const name = newFolderName.trim();
    if (!name) {
      setSuccessMsg(null);
      setError(t("research.enterFolderName"));
      return;
    }
    if (loading) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    try {
      await api.createResearchFolder({
        name,
        parent_id: parentId && parentId !== ROOT_FOLDER_SENTINEL ? parentId : undefined,
      });
      setNewFolderName("");
      setNewFolderParentId(null);
      await loadAll();
      setSuccessMsg(t("research.folderCreatedToast"));
      if (successClearRef.current) clearTimeout(successClearRef.current);
      successClearRef.current = setTimeout(() => setSuccessMsg(null), 4000);
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }

  async function createProject(folderId: string) {
    const name = newProjectName.trim();
    if (!name || loading) return;
    setError(null);
    setLoading(true);
    try {
      const created = await api.createResearchProject({ folder_id: folderId, name, layout_type: "single" });
      setNewProjectName("");
      setNewProjectFolderId(null);
      await loadAll();
      onProjectsChange(created);
    } catch (e: unknown) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }

  async function renameFolder(folderId: string, name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      await api.updateResearchFolder(folderId, { name: trimmed });
      setEditingFolderId(null);
      setEditName("");
      await loadAll();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function renameProject(projectId: string, name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      await api.updateResearchProject(projectId, { name: trimmed });
      setEditingProjectId(null);
      setEditName("");
      await loadAll();
      onProjectsChange();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function deleteFolder(folderId: string) {
    setError(null);
    if (typeof window !== "undefined" && !window.confirm(t("research.confirmDeleteFolder"))) return;
    try {
      await api.deleteResearchFolder(folderId);
      setExpandedFolderIds((prev) => {
        const next = new Set(prev);
        next.delete(folderId);
        return next;
      });
      await loadAll();
      onProjectsChange();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  async function deleteProject(projectId: string) {
    setError(null);
    if (typeof window !== "undefined" && !window.confirm(t("research.confirmDeleteProject"))) return;
    try {
      await api.deleteResearchProject(projectId);
      if (selectedProjectId === projectId) onSelectProject(null);
      await loadAll();
      onProjectsChange();
    } catch (e: unknown) {
      setError(parseApiError(e));
    }
  }

  function toggleExpand(folderId: string) {
    setExpandedFolderIds((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  }

  /** Auto-expand folder and all ancestors so create input is visible. */
  function ensureExpandedForCreate(folderId: string) {
    const ids = new Set<string>();
    let fid: string | undefined = folderId;
    while (fid) {
      ids.add(fid);
      const f = folders.find((x) => x.id === fid);
      fid = f?.parent_id ?? undefined;
    }
    setExpandedFolderIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  }

  function startEditFolder(f: Folder) {
    setEditingFolderId(f.id);
    setEditName(f.name);
  }

  function startEditProject(p: Project) {
    setEditingProjectId(p.id);
    setEditName(p.name);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-center gap-1.5 border-b border-slate-700/80 pb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{t("nav.research")}</span>
        <SectionHelp titleKey="help.researchSidebarTitle" bodyKey="help.researchSidebarBody" />
      </div>
      {foldersLoading && folders.length === 0 ? (
        <div className="rounded border border-slate-800 bg-slate-950/30 px-2 py-1.5 text-xs text-slate-400">
          {t("common.loading")}
        </div>
      ) : null}
      {!foldersLoading && projectsLoading && folders.length > 0 ? (
        <div className="rounded border border-slate-800 bg-slate-950/30 px-2 py-1.5 text-xs text-slate-500">
          Loading projects…
        </div>
      ) : null}
      {error ? (
        <div className="rounded border border-amber-900/50 bg-amber-950/20 px-2 py-1.5 text-xs text-amber-200 whitespace-pre-line break-words text-balance">
          {error}
        </div>
      ) : null}
      {successMsg ? (
        <div className="rounded border border-emerald-900/50 bg-emerald-950/25 px-2 py-1.5 text-xs text-emerald-200">
          {successMsg}
        </div>
      ) : null}

      <nav className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto rounded border border-slate-700/80 bg-slate-900/30 py-1">
        {rootFolders.length === 0 && !newFolderParentId ? (
          <p className="px-2 py-2 text-xs text-slate-500 text-balance break-words">{t("research.noFoldersYet")}</p>
        ) : null}
        {rootFolders.map((folder) => {
          const isExpanded = expandedFolderIds.has(folder.id);
          const children = projectsInFolder(folder.id);
          const subfolders = childFolders(folder.id);
          const isAddingFolder = newFolderParentId === folder.id;
          const isAddingProject = newProjectFolderId === folder.id;

          return (
            <div key={folder.id} className="w-full min-w-0">
              <div className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-800/50">
                <button
                  type="button"
                  onClick={() => toggleExpand(folder.id)}
                  className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:text-slate-200"
                  aria-label={isExpanded ? t("research.collapseAria") : t("research.expandAria")}
                >
                  {isExpanded ? "▾" : "▸"}
                </button>
                {editingFolderId === folder.id ? (
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") renameFolder(folder.id, editName);
                      if (e.key === "Escape") setEditingFolderId(null);
                    }}
                    onBlur={() => renameFolder(folder.id, editName)}
                    className="min-w-[80px] flex-1 rounded border border-slate-600 bg-slate-950 px-1.5 py-0.5 text-sm text-slate-100"
                    autoFocus
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => toggleExpand(folder.id)}
                    className="min-w-[80px] flex-1 truncate text-left text-sm font-medium text-slate-100"
                  >
                    {folder.name}
                  </button>
                )}
                {editingFolderId !== folder.id && (
                  <div className="flex-shrink-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                        if (openMenu?.type === "folder" && openMenu?.id === folder.id) {
                          setOpenMenu(null);
                          setMenuAnchor(null);
                        } else {
                          menuTriggerRef.current = e.currentTarget as HTMLButtonElement;
                          setMenuAnchor({ x: rect.right - 120, y: rect.bottom + 4 });
                          setOpenMenu({ type: "folder", id: folder.id });
                        }
                      }}
                      className="flex h-7 w-7 items-center justify-center rounded bg-slate-700/80 text-base text-slate-200 hover:bg-slate-600"
                      title={t("research.menuAria")}
                      aria-label={t("research.menuAria")}
                    >
                      &#8230;
                    </button>
                  </div>
                )}
              </div>

              {isExpanded && (
                <div className="ml-4 space-y-1 border-l border-slate-700/60 pl-1">
                  {children.map((proj) => {
                    const projSelected = selectedProjectId === proj.id;
                    return (
                    <div
                      key={proj.id}
                      data-selected={projSelected}
                      className={
                        "flex w-full items-center gap-2 rounded border py-1.5 pl-2 pr-1 transition-colors " +
                        (projSelected
                          ? "border-indigo-500 bg-indigo-950/70 shadow-sm"
                          : "border-transparent bg-slate-900/50 hover:bg-slate-800/60")
                      }
                    >
                      <span className="w-4 flex-shrink-0" aria-hidden />
                      {editingProjectId === proj.id ? (
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") renameProject(proj.id, editName);
                            if (e.key === "Escape") setEditingProjectId(null);
                          }}
                          onBlur={() => renameProject(proj.id, editName)}
                          className="min-w-[80px] flex-1 rounded border border-slate-600 bg-slate-950 px-1.5 py-0.5 text-sm text-slate-100"
                          autoFocus
                        />
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => onSelectProject(projSelected ? null : proj)}
                            className={"min-w-[80px] flex-1 truncate text-left text-sm " + (projSelected ? "font-medium text-slate-100" : "text-slate-300 hover:text-slate-50")}
                          >
                            {proj.name}
                          </button>
                          <div className="flex-shrink-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                                if (openMenu?.type === "project" && openMenu?.id === proj.id) {
                                  setOpenMenu(null);
                                  setMenuAnchor(null);
                                } else {
                                  menuTriggerRef.current = e.currentTarget as HTMLButtonElement;
                                  setMenuAnchor({ x: rect.right - 100, y: rect.bottom + 4 });
                                  setOpenMenu({ type: "project", id: proj.id });
                                }
                              }}
                              className="flex h-7 w-7 items-center justify-center rounded bg-slate-700/80 text-base text-slate-200 hover:bg-slate-600"
                              title={t("research.menuAria")}
                              aria-label={t("research.menuAria")}
                            >
                              &#8230;
                            </button>
                                    </div>
                                  </>
                                )}
                              </div>
                    );
                  })}

                  {subfolders.map((sub) => {
                    const subExpanded = expandedFolderIds.has(sub.id);
                    const subProjects = projectsInFolder(sub.id);
                    return (
                      <div key={sub.id} className="w-full min-w-0">
                        <div className="flex w-full items-center gap-2 py-1 pl-2">
                          <button type="button" onClick={() => toggleExpand(sub.id)} className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:text-slate-200" aria-label={subExpanded ? t("research.collapseAria") : t("research.expandAria")}>
                            {subExpanded ? "▾" : "▸"}
                          </button>
                          {editingFolderId === sub.id ? (
                            <input
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") renameFolder(sub.id, editName);
                                if (e.key === "Escape") setEditingFolderId(null);
                              }}
                              onBlur={() => renameFolder(sub.id, editName)}
                              className="min-w-[80px] flex-1 rounded border border-slate-600 bg-slate-950 px-1.5 py-0.5 text-sm text-slate-100"
                              autoFocus
                            />
                          ) : (
                            <button type="button" onClick={() => toggleExpand(sub.id)} className="min-w-[80px] flex-1 truncate text-left text-sm font-medium text-slate-100">
                              {sub.name}
                            </button>
                          )}
                          {editingFolderId !== sub.id && (
                            <div className="flex-shrink-0">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                                  if (openMenu?.type === "folder" && openMenu?.id === sub.id) {
                                    setOpenMenu(null);
                                    setMenuAnchor(null);
                                  } else {
                                    menuTriggerRef.current = e.currentTarget as HTMLButtonElement;
                                    setMenuAnchor({ x: rect.right - 120, y: rect.bottom + 4 });
                                    setOpenMenu({ type: "folder", id: sub.id });
                                  }
                                }}
                                className="flex h-7 w-7 items-center justify-center rounded bg-slate-700/80 text-base text-slate-200 hover:bg-slate-600"
                                title={t("research.menuAria")}
                                aria-label={t("research.menuAria")}
                              >
                                &#8230;
                              </button>
                            </div>
                          )}
                        </div>
                        {subExpanded && (
                          <div className="ml-4 space-y-1 border-l border-slate-700/60 pl-1">
                            {subProjects.map((proj) => {
                              const projSelected = selectedProjectId === proj.id;
                              return (
                              <div
                                key={proj.id}
                                data-selected={projSelected}
                                className={
                                  "flex w-full items-center gap-2 rounded border py-1.5 pl-2 pr-1 transition-colors " +
                                  (projSelected
                                    ? "border-indigo-500 bg-indigo-950/70 shadow-sm"
                                    : "border-transparent bg-slate-900/50 hover:bg-slate-800/60")
                                }
                              >
                                <span className="w-4 flex-shrink-0" aria-hidden />
                                {editingProjectId === proj.id ? (
                                  <input
                                    type="text"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") renameProject(proj.id, editName);
                                      if (e.key === "Escape") setEditingProjectId(null);
                                    }}
                                    onBlur={() => renameProject(proj.id, editName)}
                                    className="min-w-[80px] flex-1 rounded border border-slate-600 bg-slate-950 px-1.5 py-0.5 text-sm text-slate-100"
                                    autoFocus
                                  />
                                ) : (
                                  <>
                                    <button type="button" onClick={() => onSelectProject(projSelected ? null : proj)} className={"min-w-[80px] flex-1 truncate text-left text-sm " + (projSelected ? "font-medium text-slate-100" : "text-slate-300 hover:text-slate-50")}>
                                      {proj.name}
                                    </button>
                                    <div className="flex-shrink-0">
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                                          if (openMenu?.type === "project" && openMenu?.id === proj.id) {
                                            setOpenMenu(null);
                                            setMenuAnchor(null);
                                          } else {
                                            menuTriggerRef.current = e.currentTarget as HTMLButtonElement;
                                            setMenuAnchor({ x: rect.right - 100, y: rect.bottom + 4 });
                                            setOpenMenu({ type: "project", id: proj.id });
                                          }
                                        }}
                                        className="flex h-7 w-7 items-center justify-center rounded bg-slate-700/80 text-base text-slate-200 hover:bg-slate-600"
                                        title={t("research.menuAria")}
                                        aria-label={t("research.menuAria")}
                                      >
                                        &#8230;
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>
                              );
                            })}
                            {newProjectFolderId === sub.id && (
                              <div className="flex gap-1.5 py-1 pl-2">
                                <input
                                  type="text"
                                  value={newProjectName}
                                  onChange={(e) => setNewProjectName(e.target.value)}
                                  onKeyDown={(e) => e.key === "Enter" && createProject(sub.id)}
                                  placeholder={t("research.projectName")}
                                  className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                                  autoFocus
                                />
                                <button type="button" onClick={() => createProject(sub.id)} className="shrink-0 rounded bg-slate-600 px-2 py-1 text-xs text-slate-100 hover:bg-slate-500 disabled:opacity-50" disabled={loading || !newProjectName.trim()}>{loading ? t("research.creating") : t("research.create")}</button>
                                <button type="button" onClick={() => setNewProjectFolderId(null)} className="shrink-0 rounded px-2 py-1 text-xs text-slate-500">{t("common.cancel")}</button>
                              </div>
                            )}
                            {newFolderParentId === sub.id && (
                              <div className="flex gap-1.5 py-1 pl-2">
                                <input
                                  type="text"
                                  value={newFolderName}
                                  onChange={(e) => setNewFolderName(e.target.value)}
                                  onKeyDown={(e) => e.key === "Enter" && createFolder(sub.id)}
                                  placeholder="Subfolder name"
                                  className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                                  autoFocus
                                />
                                <button type="button" onClick={() => createFolder(sub.id)} className="shrink-0 rounded bg-slate-600 px-2 py-1 text-xs text-slate-100 hover:bg-slate-500 disabled:opacity-50" disabled={loading || !newFolderName.trim()}>{loading ? t("research.adding") : t("common.add")}</button>
                                <button type="button" onClick={() => setNewFolderParentId(null)} className="shrink-0 rounded px-2 py-1 text-xs text-slate-500">{t("common.cancel")}</button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {isAddingProject && (
                    <div className="flex gap-1.5 py-1 pl-2">
                      <input
                        type="text"
                        value={newProjectName}
                        onChange={(e) => setNewProjectName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && createProject(folder.id)}
                        placeholder={t("research.projectName")}
                        className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                        autoFocus
                      />
                      <button type="button" onClick={() => createProject(folder.id)} className="shrink-0 rounded bg-slate-600 px-2 py-1 text-xs text-slate-100 hover:bg-slate-500 disabled:opacity-50" disabled={loading || !newProjectName.trim()}>{loading ? t("research.creating") : t("research.create")}</button>
                      <button type="button" onClick={() => setNewProjectFolderId(null)} className="shrink-0 rounded px-2 py-1 text-xs text-slate-500">{t("common.cancel")}</button>
                    </div>
                  )}

                  {isAddingFolder && (
                    <div className="flex gap-1.5 py-1 pl-2">
                      <input
                        type="text"
                        value={newFolderName}
                        onChange={(e) => setNewFolderName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && createFolder(folder.id)}
                        placeholder="Subfolder name"
                        className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                        autoFocus
                      />
                      <button type="button" onClick={() => createFolder(folder.id)} className="shrink-0 rounded bg-slate-600 px-2 py-1 text-xs text-slate-100 hover:bg-slate-500 disabled:opacity-50" disabled={loading || !newFolderName.trim()}>{loading ? t("research.adding") : t("common.add")}</button>
                      <button type="button" onClick={() => setNewFolderParentId(null)} className="shrink-0 rounded px-2 py-1 text-xs text-slate-500">{t("common.cancel")}</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="shrink-0 space-y-1">
      {newFolderParentId === ROOT_FOLDER_SENTINEL ? (
        <div className="flex min-w-0 gap-1.5 rounded border border-slate-700 bg-slate-800/40 p-1.5">
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createFolder(null)}
            placeholder={t("research.folderName")}
            className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
            autoFocus
          />
          <button type="button" onClick={() => createFolder(null)} className="shrink-0 rounded bg-slate-600 px-2 py-1 text-xs text-slate-100 hover:bg-slate-500 disabled:opacity-50" disabled={loading || !newFolderName.trim()}>{loading ? t("research.adding") : t("common.add")}</button>
          <button type="button" onClick={() => setNewFolderParentId(null)} className="shrink-0 rounded px-2 py-1 text-xs text-slate-500">{t("common.cancel")}</button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setNewFolderParentId(ROOT_FOLDER_SENTINEL)}
          disabled={loading}
          className="w-full rounded border border-dashed border-slate-600 py-1.5 text-xs text-slate-500 hover:bg-slate-800/40 hover:text-slate-300 disabled:opacity-50"
        >
          {t("research.addFolder")}
        </button>
      )}
      </div>

      {openMenu && menuAnchor && typeof document !== "undefined" &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed z-50 min-w-[120px] rounded border border-slate-700 bg-slate-900 py-1 shadow-lg"
            style={{ left: menuAnchor.x, top: menuAnchor.y }}
          >
            {openMenu.type === "folder" && (() => {
              const folder = folders.find((f) => f.id === openMenu.id);
              if (!folder) return null;
              return (
                <>
                  <button type="button" onClick={() => { startEditFolder(folder); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-800">{t("research.rename")}</button>
                  <button type="button" onClick={() => { ensureExpandedForCreate(folder.id); setNewFolderParentId(folder.id); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-800">+ {t("research.addFolderMenu")}</button>
                  <button type="button" onClick={() => { ensureExpandedForCreate(folder.id); setNewProjectFolderId(folder.id); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-800">+ {t("research.addProject")}</button>
                  <button type="button" onClick={() => { deleteFolder(folder.id); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-red-400 hover:bg-slate-800">{t("common.delete")}</button>
                </>
              );
            })()}
            {openMenu.type === "project" && (() => {
              const project = projects.find((p) => p.id === openMenu.id);
              if (!project) return null;
              return (
                <>
                  <button type="button" onClick={() => { startEditProject(project); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-800">{t("research.rename")}</button>
                  <button type="button" onClick={() => { deleteProject(project.id); setOpenMenu(null); setMenuAnchor(null); }} className="block w-full px-3 py-1.5 text-left text-xs text-red-400 hover:bg-slate-800">{t("common.delete")}</button>
                </>
              );
            })()}
          </div>,
          document.body
        )}
    </div>
  );
}
