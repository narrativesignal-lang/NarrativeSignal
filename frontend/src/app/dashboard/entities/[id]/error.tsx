"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Shell } from "@/components/Shell";
import { useI18n } from "@/lib/i18n";

export default function EntityDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useI18n();
  useEffect(() => {
    console.error("[Entity page error]", error);
  }, [error]);

  return (
    <Shell>
      <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-4 text-sm text-red-100">
        <p className="font-medium">Something went wrong loading this entity.</p>
        <p className="mt-2 text-xs text-red-200/80">{error.message || "Unknown error"}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => reset()}
            className="rounded bg-slate-700 px-3 py-1.5 text-slate-100 hover:bg-slate-600"
          >
            Try again
          </button>
          <Link
            href="/dashboard?tab=entity"
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-slate-200 hover:bg-slate-700"
          >
            ← {t("dashboard.entityData")}
          </Link>
        </div>
      </div>
    </Shell>
  );
}
