"use client";

import { FeatureGuideModal } from "@/components/FeatureGuideModal";
import type { FeatureGuideLocale } from "@/content/featureGuide";
import { featureGuideContent } from "@/content/featureGuide";
import type { Locale } from "@/lib/i18n";

function toFeatureGuideLocale(locale: Locale): FeatureGuideLocale {
  if (locale === "zh") return "zh";
  if (locale === "pt") return "pt";
  return "en";
}

interface EntityConceptGuideModalProps {
  onClose: () => void;
  locale: Locale;
}

/** Conceptual guide: Entity Data vs Research (what is this?). */
export function EntityConceptGuideModal({ onClose, locale }: EntityConceptGuideModalProps) {
  const content = featureGuideContent.entityConcept[toFeatureGuideLocale(locale)];
  const sections = [
    content.entityData,
    content.research,
    content.difference,
    content.why,
    content.principle,
  ];

  return (
    <FeatureGuideModal
      title={content.modalTitle}
      sections={sections}
      onClose={onClose}
    />
  );
}
