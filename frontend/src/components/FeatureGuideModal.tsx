"use client";

import type { FeatureGuideSection } from "@/content/featureGuide";

interface FeatureGuideModalProps {
  title: string;
  sections: readonly FeatureGuideSection[];
  onClose: () => void;
}

/** Shared modal for Macro and Entity feature guides. */
export function FeatureGuideModal({ title, sections, onClose }: FeatureGuideModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="feature-guide-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          e.preventDefault();
          e.stopPropagation();
        }
      }}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-md flex-col rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-700/60 px-6 py-4">
          <h2 id="feature-guide-title" className="text-lg font-semibold text-slate-100">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="space-y-6">
            {sections.map((section) => (
              <section key={section.title}>
                <h3 className="mb-2 text-sm font-semibold text-slate-200">{section.title}</h3>
                <p className="text-sm leading-relaxed text-slate-400">{section.text}</p>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
