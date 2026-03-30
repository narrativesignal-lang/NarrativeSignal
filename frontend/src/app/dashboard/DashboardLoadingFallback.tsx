"use client";

import { SlowLoadBanner, useSlowLoadVisible } from "@/components/SlowLoadBanner";
import { useI18n } from "@/lib/i18n";

/** Shown while `DashboardClient` is inside Suspense boundary. */
export function DashboardLoadingFallback() {
  const { t } = useI18n();
  const showSlowHint = useSlowLoadVisible(true);

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-4">
      <div className="w-full max-w-lg space-y-2">
        <SlowLoadBanner visible={showSlowHint} />
        <div className="text-center text-sm text-slate-400">{t("common.loading")}</div>
      </div>
    </div>
  );
}
