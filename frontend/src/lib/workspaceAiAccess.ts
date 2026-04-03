import type { MeUser } from "@/lib/UserContext";
import type { WorkspaceAiCost } from "@/lib/entityWorkspaceCharts";

/**
 * Mirrors `app.core.feature_access._non_admin_ai_entitled` + plan codes.
 * Keep in sync when backend rules change.
 */
export function canUseWorkspaceAiCost(user: MeUser | null, cost: WorkspaceAiCost): boolean {
  if (cost === "none") return true;
  if (!user) return false;
  if (user.is_admin) return true;

  const plan = (user.plan_code ?? "free").toLowerCase();
  const level = (user.ai_access_level ?? "none").toLowerCase();

  if (cost === "light") {
    if (plan === "basic_ai") return level === "light";
    if (plan === "full_ai") return level === "light" || level === "heavy";
    return false;
  }

  if (cost === "heavy") {
    return plan === "full_ai" && level === "heavy";
  }

  return false;
}
