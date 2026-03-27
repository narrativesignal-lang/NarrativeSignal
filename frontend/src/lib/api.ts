import { clearTokens, getAccessToken } from "@/lib/auth";
import { normalizeOhlcvBars, type CandleBar } from "@/lib/ohlcvBars";

// Use relative URL so the browser hits same origin; Next.js rewrites /api/* to the backend.
const API_BASE = "";

export type ApiError = { status: number; message: string };

/** Normalize FastAPI / Starlette error bodies so UI never shows "[object Object]". */
export function formatFastApiDetail(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const msg = String((item as { msg?: unknown }).msg ?? "Invalid value");
          const loc = (item as { loc?: unknown }).loc;
          const locStr = Array.isArray(loc)
            ? loc
                .filter((x) => typeof x === "string" || typeof x === "number")
                .map(String)
                .join(".")
            : "";
          return locStr ? `${locStr}: ${msg}` : msg;
        }
        try {
          return JSON.stringify(item);
        } catch {
          return "Invalid request";
        }
      })
      .filter(Boolean)
      .join("; ");
  }
  if (typeof detail === "object") {
    const o = detail as Record<string, unknown>;
    if (typeof o.message === "string") return o.message;
    try {
      return JSON.stringify(detail);
    } catch {
      return "Request failed";
    }
  }
  return String(detail);
}

export function parseApiError(e: unknown): string {
  if (e && typeof e === "object" && "message" in e) {
    const raw = (e as ApiError).message;
    if (typeof raw === "string") {
      const t = raw.trim();
      if (t && t !== "[object Object]") return t;
    }
  }
  if (e instanceof Error) {
    const m = e.message.trim();
    if (m && m !== "[object Object]") return m;
  }
  if (typeof e === "string" && e.trim()) return e;
  return "Something went wrong. Please try again.";
}

export type Alert = {
  id: string;
  schedule_id: string | null;
  schedule_type: string;
  title: string;
  body_markdown: string;
  impact_score: number | null;
  payload: Record<string, unknown>;
  created_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? getAccessToken() : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined)
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const doFetch = async () =>
    fetch(`${API_BASE}${path}`, {
      credentials: "include",
      ...init,
      headers
    });

  let res = await doFetch();
  if (
    typeof window !== "undefined" &&
    res.status === 401 &&
    !path.startsWith("/api/auth/login") &&
    !path.startsWith("/api/auth/refresh")
  ) {
    try {
      const refreshed = await api.refresh();
      localStorage.setItem("narrative_access_token", refreshed.access_token);
      headers.Authorization = `Bearer ${refreshed.access_token}`;
      res = await doFetch();
    } catch {
      // fall through to normal error handling
    }
  }
  if (!res.ok) {
    const text = await res.text();
    let message = text || res.statusText;
    try {
      const json = JSON.parse(text) as { detail?: unknown };
      if (json.detail != null) {
        message = formatFastApiDetail(json.detail) || message;
      }
    } catch {
      if (text.startsWith("<") || text.length > 200) message = `Request failed (${res.status})`;
    }
    // 401: clear token and refresh cookie to avoid redirect loop
    if (typeof window !== "undefined" && res.status === 401) {
      clearTokens();
      fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
      if (message.includes("signed in somewhere else") || message.includes("Session expired")) {
        sessionStorage.setItem("narrative_session_expired_msg", message);
      }
      const last = (window as any).__narrative_auth_clear_ts;
      const now = Date.now();
      if (!last || now - last > 300) {
        (window as any).__narrative_auth_clear_ts = now;
        window.dispatchEvent(new Event("narrative:auth-change"));
      }
    }
    throw { status: res.status, message } as ApiError;
  }
  if (res.status === 204) return undefined as T;
  const bodyText = await res.text();
  if (!bodyText.trim()) return undefined as T;
  return JSON.parse(bodyText) as T;
}

export const api = {
  register: (email: string, password: string) =>
    request<{
      id: string;
      username: string;
      email: string;
      profile_name?: string;
      credits_balance: number;
      paid_access?: boolean;
      is_admin?: boolean;
    }>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  refresh: () => request<{ access_token: string; token_type: string }>("/api/auth/refresh", { method: "POST" }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  listUsers: () =>
    request<
      Array<{
        id: string;
        username: string;
        email: string;
        is_admin: boolean;
        paid_access: boolean;
        credits_balance: number;
        created_at: string | null;
        token_version: number;
      }>
    >("/api/admin/users", { credentials: "include" }),
  patchAdminUser: (userId: string, payload: { paid_access: boolean }) =>
    request<{ id: string; username: string; paid_access: boolean; credits_balance: number }>(
      `/api/admin/users/${userId}`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),
  me: () =>
    request<{
      id: string;
      username: string;
      email: string;
      profile_name: string;
      credits_balance: number;
      paid_access: boolean;
      is_admin: boolean;
    }>("/api/auth/me"),
  patchProfile: (profile_name: string) =>
    request<{
      id: string;
      username: string;
      email: string;
      profile_name: string;
      credits_balance: number;
      paid_access: boolean;
      is_admin: boolean;
    }>("/api/auth/profile", { method: "PATCH", body: JSON.stringify({ profile_name }) }),
  changePassword: (payload: { current_password: string; new_password: string; confirm_new_password: string }) =>
    request<{ ok: boolean }>("/api/auth/change-password", { method: "POST", body: JSON.stringify(payload) }),

  community: {
    submit: (payload: {
      category: string;
      title: string;
      description?: string;
      problem_solves?: string;
      platform_data_used?: string;
      has_data_source?: boolean;
      data_source_access?: string;
      contact_info?: string;
      notes?: string;
    }) =>
      request<{ id: string; category: string; title: string; created_at: string }>("/api/community/submissions", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    submitDataRequest: (payload: {
      requested_data_name: string;
      description?: string;
      use_case?: string;
      source_known?: boolean;
      how_to_obtain?: string;
      source_details?: string;
      contact_info?: string;
      priority?: string;
      notes?: string;
    }) =>
      request<{ id: string; requested_data_name: string; created_at: string }>("/api/community/data-requests", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },

  listGroups: () =>
    request<
      Array<{
        id: string;
        name: string;
        description: string | null;
        is_active: boolean;
        terms: Array<{ id: string; term: string; is_required: boolean }>;
        created_at: string;
        updated_at: string;
      }>
    >("/api/keyword-groups"),
  createGroup: (payload: { name: string; description?: string | null; terms: Array<{ term: string; is_required?: boolean }> }) =>
    request("/api/keyword-groups", { method: "POST", body: JSON.stringify(payload) }),
  deleteGroup: (id: string) => request(`/api/keyword-groups/${id}`, { method: "DELETE" }),
  getGroup: (id: string) => request<any>(`/api/keyword-groups/${id}`),

  listPortfolios: () =>
    request<Array<{ id: string; name: string; description: string | null; created_at: string; updated_at: string }>>("/api/portfolios"),
  createPortfolio: (p: { name: string; description?: string | null }) =>
    request<{ id: string; name: string; description: string | null; created_at: string; updated_at: string }>("/api/portfolios", { method: "POST", body: JSON.stringify(p) }),
  updatePortfolio: (id: string, p: { name?: string; description?: string | null }) =>
    request<{ id: string; name: string; description: string | null; created_at: string; updated_at: string }>(`/api/portfolios/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
  deletePortfolio: (id: string) => request<void>(`/api/portfolios/${id}`, { method: "DELETE" }),

  listEntities: (portfolioId: string) =>
    request<
      Array<{
        id: string;
        portfolio_id: string;
        name: string;
        instrument_id: string | null;
        instrument: { id: string; symbol: string; display_name: string | null; asset_class: string; market: string | null } | null;
        terms: Array<{ id: string; term: string; normalized_term: string; created_at: string }>;
        created_at: string;
        updated_at: string;
      }>
    >(`/api/portfolios/${portfolioId}/entities`),
  getEntity: (entityId: string) =>
    request<{
      id: string;
      portfolio_id: string;
      portfolio_name: string;
      name: string;
      instrument_id: string | null;
      instrument: { id: string; symbol: string; display_name: string | null; asset_class: string; market: string | null } | null;
      terms: Array<{ id: string; term: string; normalized_term: string; created_at: string }>;
      chart_layout?: { charts?: string[]; blockHeights?: Record<string, number>; quadrantPeriod?: string; narrativeFlowPeriod?: string } | null;
      created_at: string;
      updated_at: string;
    }>(`/api/entities/${entityId}`),
  createEntity: (p: { portfolio_id: string; name: string; instrument_id?: string | null; terms?: string[] }) =>
    request<any>("/api/entities", { method: "POST", body: JSON.stringify(p) }),
  updateEntity: (id: string, p: { name?: string; instrument_id?: string | null; chart_layout?: Record<string, unknown> | null }) =>
    request<any>(`/api/entities/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
  deleteEntity: (id: string) => request<void>(`/api/entities/${id}`, { method: "DELETE" }),
  replaceEntityTerms: (entityId: string, terms: string[]) =>
    request<Array<{ id: string; term: string; normalized_term: string; created_at: string }>>(`/api/entities/${entityId}/terms`, { method: "PUT", body: JSON.stringify({ terms }) }),

  getEntityRelatedInstruments: (entityId: string) =>
    request<Array<{ id: string; instrument_id: string; symbol: string; display_name: string | null; asset_class: string }>>(
      `/api/entities/${entityId}/related-instruments`
    ),
  addEntityRelatedInstrument: (entityId: string, payload: { instrument_id: string }) =>
    request<{ id: string; instrument_id: string; symbol: string; display_name: string | null; asset_class: string }>(
      `/api/entities/${entityId}/related-instruments`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  deleteEntityRelatedInstrument: (entityId: string, relatedId: string) =>
    request<void>(`/api/entities/${entityId}/related-instruments/${relatedId}`, { method: "DELETE" }),
  getEntityComparisonSeries: (entityId: string, instrumentIds: string, period?: string) =>
    request<{
      period: string;
      series: Array<{ instrument_id: string; symbol: string; points: Array<{ t: string; value: number }> }>;
    }>(
      `/api/entities/${entityId}/comparison-series?instrument_ids=${encodeURIComponent(instrumentIds)}&period=${period ?? "1M"}`
    ),

  getEntitySearchVolumeSeries: (entityId: string, period?: string) =>
    request<{ period: string; points: Array<{ t: string; value: number }> }>(
      `/api/entities/${entityId}/search-volume-series?period=${encodeURIComponent(period ?? "1M")}`
    ),
  getEntityCoverageVolumeSeries: (entityId: string, period?: string) =>
    request<{ period: string; points: Array<{ t: string; value: number }> }>(
      `/api/entities/${entityId}/coverage-volume-series?period=${encodeURIComponent(period ?? "1M")}`
    ),
  getEntityQuadrant: (entityId: string) =>
    request<{ search_momentum: number; coverage_momentum: number }>(`/api/entities/${entityId}/quadrant`),

  getEntityQuadrantHistory: (entityId: string, period?: string) =>
    request<{
      period: string;
      points: Array<{ t: string; coverage_momentum: number; search_momentum: number }>;
    }>(
      `/api/entities/${entityId}/quadrant-history?period=${encodeURIComponent(period ?? "1M")}`
    ),

  getEntitySentimentSeries: (entityId: string, period?: string) =>
    request<{ period: string; points: Array<{ t: string; value: number }> }>(
      `/api/entities/${entityId}/sentiment-series?period=${encodeURIComponent(period ?? "1M")}`
    ),

  getEntityTrending: (entityId: string) =>
    request<{
      search_momentum: number;
      coverage_momentum: number;
      sentiment_change: number;
      trend_label: string;
    }>(`/api/entities/${entityId}/trending`),

  getEntityPriceTimelinePoints: (
    entityId: string,
    params: { symbol: string; period: string; chart_scope: string }
  ) =>
    request<{
      access: {
        can_interact: boolean;
        is_admin: boolean;
        paid_access: boolean;
        credits_balance: number;
        reason: string | null;
      };
      symbol: string;
      period: string;
      chart_scope: string;
      range_start: number;
      range_end: number;
      points: Array<{
        id: string;
        point_type: "volatility" | "official";
        time: number;
        score: number | null;
        label_hint: string | null;
      }>;
    }>(
      `/api/entities/${entityId}/price-timeline/points?symbol=${encodeURIComponent(params.symbol)}&period=${encodeURIComponent(params.period)}&chart_scope=${encodeURIComponent(params.chart_scope)}`
    ),

  getEntityPriceTimelineWindow: (entityId: string, pointId: string) =>
    request<{
      point_id: string;
      point_type: "volatility" | "official";
      focus_time: number;
      window_start_iso: string;
      window_end_iso: string;
      symbol: string;
      items: Array<{
        id: string;
        title: string;
        source_name: string;
        source_url: string | null;
        summary: string;
        sentiment: "bullish" | "bearish" | "neutral";
        category: string;
      }>;
      data_mode: "placeholder" | "live";
    }>(
      `/api/entities/${entityId}/price-timeline/window?point_id=${encodeURIComponent(pointId)}`
    ),

  postEntityPriceTimelineAiSummary: (
    entityId: string,
    body: {
      point_id: string;
      provider: "gemini" | "openai" | "anthropic" | "qwen";
      summary_window?: "point" | "24h" | "72h" | "7d" | "custom";
      custom_start_iso?: string | null;
      custom_end_iso?: string | null;
    }
  ) =>
    request<{
      status: "placeholder" | "ok" | "error";
      provider: string;
      interpretation: string | null;
      summary: string;
      citations: Array<{ title: string; url: string | null }>;
      model_label: string | null;
      detail: string | null;
    }>(`/api/entities/${entityId}/price-timeline/ai-summary`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Narrative 3D: time × search_trend (0–100) × coverage_volume — from backend, not client mock. */
  getEntityChart3dData: (entityId: string, range?: "1m" | "3m" | "6m") =>
    request<{
      entity_id: string;
      range: string;
      mode: string;
      points: Array<{ date: string; search_trend: number; coverage_volume: number }>;
      source_status: { search_trend: string; coverage_volume: string };
    }>(`/api/entities/${entityId}/charts/3d-data?range=${encodeURIComponent(range ?? "1m")}`),
  getEntityMetricSeries: (
    entityId: string,
    metric: "search_trend" | "coverage_volume" | "sentiment_score" | "momentum" | "acceleration",
    range?: "1m" | "3m" | "6m"
  ) =>
    request<{
      entity_id: string;
      metric: string;
      range: string;
      points: Array<{ date: string; value: number }>;
    }>(`/api/entities/${entityId}/metric-series/${encodeURIComponent(metric)}?range=${encodeURIComponent(range ?? "3m")}`),

  searchInstruments: (q: string, assetClass?: string, exchange?: string, category?: string) =>
    request<
      Array<{
        id: string;
        symbol: string;
        display_name: string | null;
        asset_class: string;
        market: string | null;
        exchange: string | null;
        description: string | null;
        country: string | null;
        currency: string | null;
      }>
    >(
      `/api/instruments/search?q=${encodeURIComponent(q)}${
        assetClass ? `&asset_class=${encodeURIComponent(assetClass)}` : ""
      }${exchange ? `&exchange=${encodeURIComponent(exchange)}` : ""}${
        category ? `&category=${encodeURIComponent(category)}` : ""
      }`
    ),

  aiKeywordSuggestions: (p: { idea: string; instrument?: string | null; asset_class?: string | null; portfolio?: string | null }) =>
    request<{ keywords: string[] }>("/api/ai/keyword-suggestions", { method: "POST", body: JSON.stringify(p) }),

  series: (groupId: string, hours = 72) => request<{ group_id: string; points: any[] }>(`/api/indices/series/${groupId}?hours=${hours}`),

  reports: (limit = 50, kind?: string | null, label?: string | null, scheduleType?: string | null) => {
    const p = new URLSearchParams();
    p.set("limit", String(limit));
    if (kind) p.set("kind", kind);
    if (label) p.set("label", label);
    if (scheduleType) p.set("schedule_type", scheduleType);
    return request<any[]>(`/api/reports?${p.toString()}`);
  },
  reportCount: () =>
    request<{ count: number; max: number; at_limit: boolean }>("/api/reports/count"),
  deleteReports: (ids: string[]) =>
    request<{ deleted: number }>("/api/reports", {
      method: "DELETE",
      body: JSON.stringify(ids)
    }),

  schedules: () => request<any[]>("/api/schedules"),
  createSchedule: (payload: any) => request("/api/schedules", { method: "POST", body: JSON.stringify(payload) }),
  triggerSchedule: (id: string) => request(`/api/schedules/${id}/trigger`, { method: "POST" }),
  pauseSchedule: (id: string) => request(`/api/schedules/${id}/pause`, { method: "POST" }),
  resumeSchedule: (id: string) => request(`/api/schedules/${id}/resume`, { method: "POST" }),
  deleteSchedule: (id: string) => request(`/api/schedules/${id}`, { method: "DELETE" }),

  alerts(limit = 50) {
    return request<Alert[]>(`/api/alerts?limit=${limit}`);
  },

  groupFeeds: (groupId: string) => request<any[]>(`/api/groups/${groupId}/feeds`),
  addGroupFeed: (groupId: string, payload: { name?: string | null; url: string; is_active?: boolean }) =>
    request<any>(`/api/groups/${groupId}/feeds`, { method: "POST", body: JSON.stringify(payload) }),
  deleteGroupFeed: (groupId: string, feedId: string) => request(`/api/groups/${groupId}/feeds/${feedId}`, { method: "DELETE" }),

  groupArticles: (groupId: string, limit = 50) => request<any>(`/api/groups/${groupId}/articles?limit=${limit}`),

  getGroupAsset: (groupId: string) => request<any | null>(`/api/groups/${groupId}/asset`),
  setGroupAsset: (groupId: string, payload: { symbol: string; provider?: string }) =>
    request<any>(`/api/groups/${groupId}/asset`, { method: "PUT", body: JSON.stringify(payload) }),

  ohlcv: async (symbol: string, period: string) => {
    const res = await request<any>(`/api/market/ohlcv?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}`);
    return res?.data ?? res;
  },

  /** Same bars as GET /market/ohlcv, normalized for CandleChart; keys are uppercase symbols. */
  ohlcvBatch: async (symbols: string[], period: string): Promise<Record<string, CandleBar[]>> => {
    const uniq = [...new Set(symbols.map((s) => s.trim().toUpperCase()).filter(Boolean))];
    if (uniq.length === 0) return {};
    const res = await request<any>(`/api/market/ohlcv-batch`, {
      method: "POST",
      body: JSON.stringify({ symbols: uniq, period }),
    });
    const payload = res?.data ?? res;
    const items = (payload?.items ?? {}) as Record<string, { bars?: unknown } | undefined>;
    const out: Record<string, CandleBar[]> = {};
    for (const sym of uniq) {
      out[sym] = normalizeOhlcvBars(items[sym]?.bars ?? []);
    }
    return out;
  },
  quote: async (symbol: string) => {
    const res = await request<any>(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`);
    return res?.data ?? res;
  },

  marketIndices: (category: string) =>
    request<{
      data: Array<{ name: string; symbol: string; price: number | null; change_percent: number | null }>;
      stale?: boolean;
    }>(`/api/market/indices?category=${encodeURIComponent(category)}`),

  addMarketIndex: (payload: { category: string; name: string; symbol: string; asset_type?: string }) =>
    request(`/api/market/indices`, {
      method: "POST",
      body: JSON.stringify({ asset_type: "index", ...payload }),
    }),

  macroNews: (category: string, subcategory?: string | null, limit = 40) =>
    request<
      Array<{
        id: string;
        title: string;
        source: string;
        timestamp: string;
        url: string | null;
        category: string;
        subcategory: string;
        summary: string | null;
        sentiment: string | null;
        impact: number | null;
      }>
    >(
      `/api/macro/news?category=${encodeURIComponent(category)}${
        subcategory ? `&subcategory=${encodeURIComponent(subcategory)}` : ""
      }&limit=${limit}`
    ),

  macroEvents: (limit = 50, category?: string | null) =>
    request<
      Array<{
        id: string;
        category: string;
        title: string;
        source: string;
        timestamp: string;
        sentiment: string | null;
        importance_score: number | null;
      }>
    >(
      category
        ? `/api/macro/events?limit=${limit}&category=${encodeURIComponent(category)}`
        : `/api/macro/events?limit=${limit}`
    ),
  macroCategories: () =>
    request<Array<{ id: string; name: string; created_at: string }>>("/api/macro/categories"),
  createMacroCategory: (name: string) =>
    request<{ id: string; name: string; created_at: string }>("/api/macro/categories", {
      method: "POST",
      body: JSON.stringify({ name })
    }),
  deleteMacroCategory: (id: string) =>
    request<{ ok: boolean }>(`/api/macro/categories/${id}`, { method: "DELETE" }),

  researchFolders: () =>
    request<Array<{ id: string; name: string; parent_id: string | null; created_at: string }>>("/api/research/folders"),
  createResearchFolder: (payload: { name: string; parent_id?: string | null }) =>
    request<{ id: string; name: string; parent_id: string | null; created_at: string }>("/api/research/folders", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateResearchFolder: (id: string, payload: { name?: string; parent_id?: string | null }) =>
    request<{ id: string; name: string; parent_id: string | null; created_at: string }>(`/api/research/folders/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteResearchFolder: (id: string) =>
    request<{ ok: boolean }>(`/api/research/folders/${id}`, { method: "DELETE" }),

  researchProjects: (folderId?: string | null) =>
    request<
      Array<{
        id: string;
        folder_id: string;
        name: string;
        layout_type: string;
        layout_config: Record<string, unknown>;
        created_at: string;
      }>
    >(folderId ? `/api/research/projects?folder_id=${folderId}` : "/api/research/projects"),
  createResearchProject: (payload: { folder_id: string; name: string; layout_type: string }) =>
    request<{
      id: string;
      folder_id: string;
      name: string;
      layout_type: string;
      layout_config: Record<string, unknown>;
      created_at: string;
    }>("/api/research/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateResearchProject: (
    id: string,
    payload: { folder_id?: string; name?: string; layout_type?: string; layout_config?: Record<string, unknown> }
  ) =>
    request<{
      id: string;
      folder_id: string;
      name: string;
      layout_type: string;
      layout_config: Record<string, unknown>;
      created_at: string;
    }>(`/api/research/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteResearchProject: (id: string) =>
    request<{ ok: boolean }>(`/api/research/projects/${id}`, { method: "DELETE" }),

  listResearchSetupSnapshots: () =>
    request<Array<{ code: string; name: string | null; created_at: string }>>(
      "/api/research/setup-snapshots"
    ),
  saveResearchSetupSnapshot: (payload: { config: Record<string, unknown>; name?: string | null }) =>
    request<{ code: string; name?: string | null }>("/api/research/setup-snapshot", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importResearchSetupSnapshot: (code: string) =>
    request<{ config: Record<string, unknown> }>(
      `/api/research/setup-snapshot?code=${encodeURIComponent(code.trim())}`
    ),
  updateResearchSetupSnapshot: (code: string, payload: { name?: string | null }) =>
    request<{ code: string; name: string | null; created_at: string }>(
      `/api/research/setup-snapshots/${encodeURIComponent(code)}`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),
  deleteResearchSetupSnapshot: (code: string) =>
    request<void>(
      `/api/research/setup-snapshots/${encodeURIComponent(code)}`,
      { method: "DELETE" }
    ),

  getEntityConfig: (groupId: string) =>
    request<{ group_id: string; config: { charts?: string[]; market_data?: string[] } }>(
      `/api/groups/${groupId}/entity-config`
    ),
  putEntityConfig: (groupId: string, config: { charts: string[]; market_data: string[] }) =>
    request<{ group_id: string; config: { charts: string[]; market_data: string[] } }>(
      `/api/groups/${groupId}/entity-config`,
      { method: "PUT", body: JSON.stringify({ config }) }
    ),

  assetsSearch: (q: string) =>
    request<Array<{ symbol: string; name?: string }>>(`/api/assets/search?q=${encodeURIComponent(q)}`)
};

