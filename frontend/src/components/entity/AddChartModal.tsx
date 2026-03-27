"use client";

type SkillCategory = "index" | "analysis" | "ai_analysis";

const ENTITY_SKILLS = [
  // Index: direct data indicators
  { id: "search_volume", label: "Search Volume", category: "index" as SkillCategory },
  { id: "coverage_volume", label: "Coverage Volume", category: "index" as SkillCategory },
  { id: "sentiment_score", label: "Sentiment", category: "index" as SkillCategory },
  {
    id: "order_flow",
    label: "Order Flow",
    category: "index" as SkillCategory,
    placeholder: true,
    description: "Live order flow feed not connected yet. Will use market depth and trade-flow data when available.",
  },
  // Analysis: derived metrics from one or more indicators
  { id: "search_momentum", label: "Search Momentum", category: "analysis" as SkillCategory },
  { id: "search_acceleration", label: "Search Acceleration", category: "analysis" as SkillCategory },
  { id: "coverage_momentum", label: "Coverage Momentum", category: "analysis" as SkillCategory },
  { id: "coverage_acceleration", label: "Coverage Acceleration", category: "analysis" as SkillCategory },
  { id: "quadrant_flow", label: "Narrative Flow", category: "analysis" as SkillCategory },
  // AI Analysis: scaffold for future AI-powered blocks
  // No concrete AI blocks yet; section is shown in UI to set expectations.
] as const;

export type EntitySkillId = (typeof ENTITY_SKILLS)[number]["id"];

export function AddChartModal({
  open,
  onClose,
  existingCharts,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  existingCharts: string[];
  onSelect: (skillId: EntitySkillId) => void;
}) {
  if (!open) return null;
  const atLimit = existingCharts.length >= 5;
  const available = atLimit ? [] : ENTITY_SKILLS.filter((s) => !existingCharts.includes(s.id));

  const sections: { key: SkillCategory; title: string; subtitle: string }[] = [
    { key: "index", title: "Index", subtitle: "Direct data indicators" },
    { key: "analysis", title: "Analysis", subtitle: "Derived metrics from one or more indicators" },
    { key: "ai_analysis", title: "AI Analysis", subtitle: "AI-powered analysis tools (token usage may apply later)" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 shadow-xl">
        <div className="border-b border-slate-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-200">Select Skill</h2>
        </div>
        <div className="max-h-80 overflow-y-auto p-3">
          {atLimit ? (
            <p className="text-xs text-slate-500">Maximum 5 charts. Remove one to add another.</p>
          ) : available.length === 0 ? (
            <p className="text-xs text-slate-500">All skills are already added.</p>
          ) : (
            <div className="space-y-3">
              {sections.map((section) => {
                const group = available.filter((s) => s.category === section.key);
                return (
                  <div key={section.key} className="space-y-1.5">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                        {section.title}
                      </div>
                      <div className="text-[11px] text-slate-500">{section.subtitle}</div>
                    </div>
                    {group.length === 0 ? (
                      <p className="text-[11px] text-slate-600">
                        {section.key === "ai_analysis"
                          ? "AI analysis blocks will appear here in a future update."
                          : "No additional blocks available in this category."}
                      </p>
                    ) : (
                      <ul className="space-y-0.5">
                        {group.map((s) => (
                          <li key={s.id}>
                            <button
                              type="button"
                              onClick={() => onSelect(s.id)}
                              className="w-full rounded border border-slate-700 bg-slate-800/50 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-700/50"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span>{s.label}</span>
                                {s.category === "ai_analysis" ? (
                                  <span className="rounded-full bg-indigo-600/20 px-2 py-0.5 text-[10px] font-medium text-indigo-200">
                                    AI
                                  </span>
                                ) : null}
                              </div>
                              {"description" in s && s.description ? (
                                <div className="mt-0.5 text-[11px] text-slate-400">{s.description}</div>
                              ) : null}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="border-t border-slate-800 px-4 py-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
