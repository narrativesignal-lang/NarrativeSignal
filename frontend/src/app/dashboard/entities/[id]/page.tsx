import { Shell } from "@/components/Shell";
import EntityDetailPageClient from "./EntityDetailPageClient";

type PageProps = { params: { id: string } };

/**
 * Server entry: passes `params.id` into the client tree so we avoid `useParams()`
 * SSR/client hydration mismatches (which can produce a blank white page on refresh).
 */
export default function EntityDetailPage({ params }: PageProps) {
  const raw = params?.id;
  const id = typeof raw === "string" && raw.trim() ? raw.trim() : "";
  if (!id) {
    return (
      <Shell>
        <div className="rounded border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">Invalid entity id.</div>
      </Shell>
    );
  }
  return <EntityDetailPageClient entityId={id} />;
}
