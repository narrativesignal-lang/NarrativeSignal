/** Session cache so /news/[id] can render macro RSS items without re-calling macroNews. */

export type MacroNewsDetailCache = {
  id: string;
  title: string;
  source: string;
  timestamp: string | null;
  category?: string | null;
  subcategory?: string | null;
  sentiment?: string | null;
  impact?: number | null;
  summary?: string | null;
  url?: string | null;
  duplicate_count?: number;
  related_publishers?: string[];
};

const PREFIX = "narrative_macro_news_item:";

export function writeMacroNewsArticleToSession(article: MacroNewsDetailCache): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(PREFIX + article.id, JSON.stringify(article));
  } catch {
    /* quota / private mode */
  }
}

export function readMacroNewsArticleFromSession(id: string): MacroNewsDetailCache | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(PREFIX + id);
    if (!raw) return null;
    const p = JSON.parse(raw) as MacroNewsDetailCache;
    if (!p || typeof p.id !== "string" || p.id !== id) return null;
    return p;
  } catch {
    return null;
  }
}
