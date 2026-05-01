/**
 * API client — Nodrat backend (FastAPI) ile iletişim.
 *
 * docs/engineering/api-contracts.md
 *
 * Authentication: access_token + refresh_token (JWT) localStorage'da
 * tutulur. Production'da httpOnly cookie yapacağız (#71 backlog).
 */

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "/api"
).replace(/\/$/, "");

const TOKEN_KEY = "nodrat_access_token";
const REFRESH_KEY = "nodrat_refresh_token";

export interface ApiError {
  status: number;
  code?: string;
  title?: string;
  detail?: string;
}

export class ApiException extends Error {
  status: number;
  code?: string;
  detail?: string;

  constructor(error: ApiError) {
    super(error.title || `HTTP ${error.status}`);
    this.status = error.status;
    this.code = error.code;
    this.detail = error.detail;
  }
}

// ---- Token storage --------------------------------------------------------

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ---- Core fetch -----------------------------------------------------------

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, skipAuth, headers, ...rest } = options;

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...((headers as Record<string, string>) ?? {}),
  };

  if (!skipAuth) {
    const token = getAccessToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let json: unknown = undefined;
  try {
    json = text ? JSON.parse(text) : undefined;
  } catch {
    json = text;
  }

  if (!response.ok) {
    const detail =
      typeof json === "object" && json !== null && "detail" in json
        ? (json as { detail: { code?: string; title?: string } | string })
            .detail
        : undefined;

    if (typeof detail === "object" && detail !== null) {
      throw new ApiException({
        status: response.status,
        code: detail.code,
        title: detail.title,
        detail:
          typeof detail === "object" && "detail" in detail
            ? (detail as { detail?: string }).detail
            : undefined,
      });
    }

    throw new ApiException({
      status: response.status,
      title: typeof detail === "string" ? detail : `HTTP ${response.status}`,
    });
  }

  return json as T;
}

// ---- Auth endpoints -------------------------------------------------------

export interface LoginPayload {
  email: string;
  password: string;
}

export interface UserPublic {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: UserPublic;
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: { refresh_token: refresh },
        skipAuth: true,
      });
    } catch {
      // Silent fail — token revoked anyway
    }
  }
  clearTokens();
}

// ---- Sources --------------------------------------------------------------

export type SourceType = "rss" | "category_page" | "manual";

export interface SourcePublic {
  id: string;
  name: string;
  slug: string;
  domain: string;
  type: SourceType;
  base_url: string;
  language: string;
  country: string;
  category: string | null;
  reliability_score: number;
  is_active: boolean;
  crawl_interval_minutes: number;
  robots_txt_compliant: boolean | null;
  tos_acknowledged: boolean;
}

export interface SourceCreatePayload {
  name: string;
  slug: string;
  domain: string;
  type: SourceType;
  base_url: string;
  language?: string;
  country?: string;
  category?: string | null;
  crawl_interval_minutes?: number;
  config_json?: Record<string, unknown> | null;
}

export interface ComplianceChecklist {
  robots_txt_checked: boolean;
  not_paywalled: boolean;
  tos_allows_scraping: boolean;
  publicly_accessible: boolean;
  commercial_risk_assessed: boolean;
}

export interface ActivatePayload {
  checklist: ComplianceChecklist;
  note?: string;
}

export interface FeedReportPublic {
  feed_url: string;
  fetched: boolean;
  status_code: number;
  error: string | null;
  feed_title: string;
  feed_description: string;
  feed_language: string | null;
  item_count: number;
  sample_items: Array<{
    title: string;
    link: string;
    summary: string;
    author: string | null;
    published_at: string | null;
    image_url: string | null;
  }>;
}

export interface RobotsReportPublic {
  domain: string;
  robots_url: string;
  fetched: boolean;
  status_code: number;
  base_url_allowed: boolean;
  crawl_delay_sec: number;
  sitemaps: string[];
  error: string | null;
}

export interface SourceListFilters {
  is_active?: boolean;
  type?: SourceType;
  limit?: number;
  offset?: number;
}

function buildQuery(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export async function listSources(
  filters?: SourceListFilters,
): Promise<SourcePublic[]> {
  return apiFetch<SourcePublic[]>(
    `/admin/sources${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function createSource(
  payload: SourceCreatePayload,
): Promise<SourcePublic> {
  return apiFetch<SourcePublic>("/admin/sources", {
    method: "POST",
    body: payload,
  });
}

export async function getSource(id: string): Promise<SourcePublic> {
  return apiFetch<SourcePublic>(`/admin/sources/${id}`);
}

export async function activateSource(
  id: string,
  payload: ActivatePayload,
): Promise<SourcePublic> {
  return apiFetch<SourcePublic>(`/admin/sources/${id}/activate`, {
    method: "POST",
    body: payload,
  });
}

export async function testFeed(feedUrl: string): Promise<FeedReportPublic> {
  return apiFetch<FeedReportPublic>("/admin/sources/test-feed", {
    method: "POST",
    body: { feed_url: feedUrl },
  });
}

export async function robotsCheck(id: string): Promise<RobotsReportPublic> {
  return apiFetch<RobotsReportPublic>(`/admin/sources/${id}/robots-check`);
}
