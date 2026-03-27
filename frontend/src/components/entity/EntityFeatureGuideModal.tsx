"use client";

import type { FeatureGuideLocale } from "@/content/featureGuide";
import { featureGuideContent } from "@/content/featureGuide";
import type { Locale } from "@/lib/i18n";
import { FeatureGuideModal } from "@/components/FeatureGuideModal";

function toFeatureGuideLocale(locale: Locale): FeatureGuideLocale {
  if (locale === "zh") return "zh";
  if (locale === "pt") return "pt";
  return "en";
}

interface EntityFeatureGuideModalProps {
  onClose: () => void;
  locale: Locale;
}

export function EntityFeatureGuideModal({ onClose, locale }: EntityFeatureGuideModalProps) {
  const content = featureGuideContent.entityData[toFeatureGuideLocale(locale)];
  const sections = [
    content.overview,
    content.portfolios,
    content.entities,
    content.monitoring,
    content.interaction,
    content.philosophy,
  ] as const;

  return (
    <FeatureGuideModal
      title={content.modalTitle}
      sections={sections}
      onClose={onClose}
    />
  );
}
