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

interface MacroFeatureGuideModalProps {
  onClose: () => void;
  locale: Locale;
}

export function MacroFeatureGuideModal({ onClose, locale }: MacroFeatureGuideModalProps) {
  const content = featureGuideContent.macroData[toFeatureGuideLocale(locale)];
  const sections = [
    content.overview,
    content.category,
    content.news,
    content.index,
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
