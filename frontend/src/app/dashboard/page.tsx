import { Suspense } from "react";

import { DashboardLoadingFallback } from "./DashboardLoadingFallback";
import { DashboardClient } from "./DashboardClient";

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardLoadingFallback />}>
      <DashboardClient />
    </Suspense>
  );
}
