function decodeBasicHtmlEntities(s: string): string {
  return s
    .replace(/&nbsp;/gi, " ")
    .replace(/&#160;/gi, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\u0022")
    .replace(/&#(\d+);/g, (full, n) => {
      const code = Number(n);
      if (!Number.isFinite(code)) return full;
      try {
        return String.fromCodePoint(code);
      } catch {
        return full;
      }
    })
    .replace(/&#x([0-9a-f]+);/gi, (full, h) => {
      const code = parseInt(h, 16);
      if (!Number.isFinite(code)) return full;
      try {
        return String.fromCodePoint(code);
      } catch {
        return full;
      }
    });
}

/** Strip HTML-ish markup to plain text (regex path; used where DOM is unavailable). */
export function stripHtmlToPlain(raw: string | null | undefined, maxLen = 2000): string {
  if (!raw) return "";
  const t = decodeBasicHtmlEntities(raw.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
  if (t.length > maxLen) return `${t.slice(0, maxLen - 1)}…`;
  return t;
}

/**
 * Convert HTML snippets (e.g. macro RSS summaries) to readable plain text.
 * Uses a temporary DOM in the browser so tags like <a> do not leak into the UI.
 */
export function htmlToPlainText(raw: string | null | undefined, maxLen = 8000): string {
  if (!raw) return "";
  let text = "";
  if (typeof document !== "undefined") {
    try {
      const el = document.createElement("div");
      el.innerHTML = raw;
      text = (el.textContent || el.innerText || "").replace(/\s+/g, " ").trim();
    } catch {
      text = stripHtmlToPlain(raw, maxLen * 2);
    }
  } else {
    text = stripHtmlToPlain(raw, maxLen * 2);
  }
  if (text.length > maxLen) return `${text.slice(0, maxLen - 1)}…`;
  return text;
}

/**
 * Drop trailing " — SomePublisher" when the tail looks like a hostname (hides domains in list titles).
 */
export function cleanMacroNewsTitle(raw: string | null | undefined): string {
  if (!raw) return "";
  const t = htmlToPlainText(raw, 2000).trim();
  const m = t.match(/^(.*)\s+[-–—]\s+([\w.-]+\.[a-z]{2,})\s*$/i);
  if (m) return m[1].trim();
  return t;
}
