"use client";

import type { WorkspaceChartBlock } from "@/lib/entityWorkspaceCharts";
import {
  getWorkspaceChartDisplayTitle,
  getBlockKind,
  WORKSPACE_BLOCK_AI_COST,
  WORKSPACE_CHART_LABELS,
  type WorkspaceChartType,
} from "@/lib/entityWorkspaceCharts";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
import { canUseWorkspaceAiCost } from "@/lib/workspaceAiAccess";

const AI_TOOLTIP = "Uses AI on the server · may take several seconds · may consume AI credits";

function typeBadgeClass(type: WorkspaceChartType | string): string {
  const kind = getBlockKind(type);
  switch (kind) {
    case "overlay":
      return "bg-sky-900/50 text-sky-200 border-sky-700/60";
    case "split":
      return "bg-violet-900/50 text-violet-200 border-violet-700/60";
    case "analysis":
      return "bg-emerald-900/50 text-emerald-200 border-emerald-700/60";
    default:
      return "bg-slate-800 text-slate-300 border-slate-600";
  }
}

export function EntityWorkspaceChartCard({
  block,
  onRemove,
  children,
}: {
  block: WorkspaceChartBlock;
  onRemove: () => void;
  children?: React.ReactNode;
}) {
  const { t } = useI18n();
  const { user } = useUser();
  const ecKey = `workspace.ec.${block.type}`;
  const typeLabelI18n = t(ecKey);
  const typeLabel =
    typeLabelI18n !== ecKey ? typeLabelI18n : (WORKSPACE_CHART_LABELS[block.type] ?? block.type);
  const chartTitle = getWorkspaceChartDisplayTitle(block);
  const aiCost = WORKSPACE_BLOCK_AI_COST[block.type as WorkspaceChartType] ?? "none";
  const showAi = aiCost !== "none";
  const aiLocked = showAi && !canUseWorkspaceAiCost(user ?? null, aiCost);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 overflow-hidden">
      <div className="flex items-center gap-3 border-b border-slate-700 bg-slate-800/50 px-3 py-2.5">
        <span
          className={`shrink-0 rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${typeBadgeClass(block.type)}`}
        >
          {typeLabel}
        </span>
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-100" title={chartTitle}>
          {chartTitle}{" "}
          {showAi ? (
            <span className="inline-flex items-center gap-1 align-middle">
              <span
                className="rounded bg-amber-900/50 px-1.5 py-0.5 text-[10px] font-medium text-amber-200"
                title={AI_TOOLTIP}
              >
                {t("workspace.blockAiBadge")}
              </span>
              {aiLocked ? (
                <span className="text-[10px] text-amber-200/90" title={t("workspace.aiPlanLockedShort")}>
                  🔒
                </span>
              ) : null}
            </span>
          ) : null}
        </h3>
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 rounded border border-slate-600 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-300 hover:border-red-800/60 hover:bg-red-950/30 hover:text-red-300"
        >
          {t("workspace.remove")}
        </button>
      </div>
      <div className="min-h-0 overflow-hidden p-0">{children}</div>
    </div>
  );
}

export function EntityWorkspaceChartPlaceholder({ block }: { block: WorkspaceChartBlock }) {
  const { t } = useI18n();
  const ecKey = `workspace.ec.${block.type}`;
  const labelI18n = t(ecKey);
  const label = labelI18n !== ecKey ? labelI18n : (WORKSPACE_CHART_LABELS[block.type] ?? block.type);
  return (
    <div className="flex h-full min-h-[140px] flex-col justify-between rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-3">
      <div>
        <span className="rounded bg-amber-900/40 px-2 py-0.5 text-[10px] font-medium uppercase text-amber-200">
          {t("workspace.placeholderLabel")}
        </span>
        <p className="mt-2 text-xs text-slate-400">
          <strong className="text-slate-300">{label}</strong> {t("workspace.notFullyWired")}
        </p>
      </div>
      <div className="mt-3 rounded border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-500">
        {t("workspace.noFakeCards")}
      </div>
    </div>
  );
}

/** Placeholder for analysis blocks marked "Coming up" (institution bias, rating distribution). */
export function EntityAnalysisComingUpPlaceholder({ block }: { block: WorkspaceChartBlock }) {
  const { t } = useI18n();
  const ecKey = `workspace.ec.${block.type}`;
  const labelI18n = t(ecKey);
  const label = labelI18n !== ecKey ? labelI18n : (WORKSPACE_CHART_LABELS[block.type] ?? block.type);
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-6 text-center">
      <span className="rounded bg-slate-700/60 px-2 py-1 text-xs font-medium text-slate-400">
        {t("schedules.comingUp")}
      </span>
      <p className="mt-2 text-sm text-slate-300">{label}</p>
      <p className="mt-1 text-xs text-slate-500">
        {t("workspace.comingUpNote")}
      </p>
    </div>
  );
}
