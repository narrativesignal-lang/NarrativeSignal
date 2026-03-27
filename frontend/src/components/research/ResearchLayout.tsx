"use client";

import { useCallback, useState } from "react";

import { SectionHelp } from "@/components/SectionHelp";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ResearchSidebar } from "./ResearchSidebar";
import { ResearchWorkspace } from "./ResearchWorkspace";

type Project = Awaited<ReturnType<typeof api.researchProjects>>[number];

export function ResearchLayout() {
  const { t } = useI18n();
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const refreshProjects = useCallback(async () => {
    try {
      const list = await api.researchProjects(undefined);
      setSelectedProject((prev) => {
        if (!prev) return null;
        const found = list.find((p) => p.id === prev.id);
        return found ?? null;
      });
    } catch {
      // ignore
    }
  }, []);

  const onProjectsChange = useCallback((createdOrUpdated?: Project | null) => {
    if (createdOrUpdated !== undefined) {
      setSelectedProject(createdOrUpdated);
      return;
    }
    refreshProjects();
  }, [refreshProjects]);

  const handleProjectUpdate = useCallback((updated: Project | null) => {
    if (updated) setSelectedProject(updated);
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-slate-200">{t("research.title")}</h1>
          <SectionHelp titleKey="help.researchMainTitle" bodyKey="help.researchMainBody" />
        </div>
        <p className="mt-1 text-sm text-slate-500">{t("research.subtitle")}</p>
      </div>
      <div className="flex min-w-0 flex-col gap-6 md:grid md:min-h-[60vh] md:grid-cols-[240px_1fr]">
        <aside className="flex min-h-0 min-w-0 shrink-0 flex-col rounded-lg border border-slate-800 bg-slate-900/40 p-3 md:min-w-0">
          <ResearchSidebar
            selectedProjectId={selectedProject?.id ?? null}
            onSelectProject={setSelectedProject}
            onProjectsChange={onProjectsChange}
          />
        </aside>
        <section className="min-h-0 min-w-0 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <ResearchWorkspace
            project={selectedProject}
            onUpdate={handleProjectUpdate}
          />
        </section>
      </div>
    </div>
  );
}
