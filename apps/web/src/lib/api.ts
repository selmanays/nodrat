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
  /** Internal: 401 sonrası refresh denenip retry edildiği işareti (loop koruması). */
  _retried?: boolean;
}

// #151: Access token expire → refresh token ile yenile + original request retry.
// Concurrent koruma: aynı anda birden çok 401 gelirse refresh sadece BIR kez
// çağrılır, diğer çağrılar aynı promise'ı bekler.
let refreshPromise: Promise<boolean> | null = null;

async function attemptTokenRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  const refresh = getRefreshToken();
  if (!refresh) return false;

  refreshPromise = (async () => {
    try {
      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!resp.ok) return false;
      const data = (await resp.json()) as TokenResponse;
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      // Sonraki 401'ler için temizle (her biri yeni refresh denemeli)
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, skipAuth, headers, _retried, ...rest } = options;

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

  // #151: 401 + auth-protected endpoint → refresh + retry (bir kez)
  if (response.status === 401 && !skipAuth && !_retried) {
    const refreshed = await attemptTokenRefresh();
    if (refreshed) {
      // Original request'i yeni token ile retry et
      return apiFetch<T>(path, { ...options, _retried: true });
    }
    // Refresh fail → token'ları temizle, kullanıcı login'e yönlendirilecek
    clearTokens();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      // Auth context state ile çakışmasın diye location.href kullanıyoruz
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`;
    }
  }

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

// ---- Register --------------------------------------------------------------

export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string | null;
  locale?: string;
  // 4 KVKK checkboxes (3 zorunlu + 1 opsiyonel) + 18+ gate
  kvkk_acknowledgment: boolean;
  data_processing_consent: boolean;
  foreign_transfer_consent: boolean;
  marketing_consent?: boolean;
  age_18_plus: boolean;
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/register", {
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

// ---- Selector test (#70 R-OPS-01) ----------------------------------------

export interface SelectorMap {
  card?: string;
  title?: string;
  link?: string;
  image?: string;
  date?: string;
  // detail-only
  subtitle?: string;
  author?: string;
  published?: string;
  body?: string;
}

export interface TestListingCard {
  title: string | null;
  link: string | null;
  image_url: string | null;
  date: string | null;
}

export interface TestListingResponse {
  url: string;
  fetch_status: number;
  fetch_error: string | null;
  card_count: number;
  cards: TestListingCard[];
  warnings: string[];
}

export interface TestDetailExtracted {
  title: string;
  subtitle: string;
  author: string | null;
  published_at: string | null;
  main_image_url: string | null;
  body_image_count: number;
  clean_text_preview: string;
  text_length: number;
  language: string;
}

export interface TestDetailMetrics {
  extraction_confidence: number;
  strategy_used: string;
  successful: boolean;
}

export interface TestDetailResponse {
  url: string;
  http_status: number;
  fetch_error: string | null;
  extracted: TestDetailExtracted | null;
  metrics: TestDetailMetrics | null;
  error: string | null;
}

export async function testListing(
  sourceId: string,
  url: string,
  selectors: SelectorMap,
): Promise<TestListingResponse> {
  return apiFetch<TestListingResponse>(
    `/admin/sources/${sourceId}/test-listing`,
    { method: "POST", body: { url, selectors } },
  );
}

export async function testDetail(
  sourceId: string,
  url: string,
  options: {
    method?: "auto" | "admin_selectors" | "trafilatura";
    selectors?: SelectorMap;
  } = {},
): Promise<TestDetailResponse> {
  return apiFetch<TestDetailResponse>(
    `/admin/sources/${sourceId}/test-detail`,
    {
      method: "POST",
      body: {
        url,
        method: options.method ?? "auto",
        selectors: options.selectors,
      },
    },
  );
}

// ---- Source config versioning (#75) --------------------------------------

export interface SourceConfigPublic {
  id: string;
  source_id: string;
  version: number;
  is_active: boolean;
  config_json: Record<string, unknown>;
  created_at: string;
  created_by: string | null;
}

export interface ConfigListResponse {
  items: SourceConfigPublic[];
  active_version: number | null;
  total: number;
}

export async function listConfigs(
  sourceId: string,
): Promise<ConfigListResponse> {
  return apiFetch<ConfigListResponse>(`/admin/sources/${sourceId}/configs`);
}

export async function createConfig(
  sourceId: string,
  configJson: Record<string, unknown>,
  note?: string,
): Promise<SourceConfigPublic> {
  return apiFetch<SourceConfigPublic>(`/admin/sources/${sourceId}/configs`, {
    method: "POST",
    body: { config_json: configJson, note },
  });
}

export async function rollbackConfig(
  sourceId: string,
  version: number,
): Promise<SourceConfigPublic> {
  return apiFetch<SourceConfigPublic>(
    `/admin/sources/${sourceId}/configs/${version}/rollback`,
    { method: "POST" },
  );
}

// ---- Public search (#261) -------------------------------------------------

export interface PublicSearchItem {
  id: string;
  title: string;
  summary: string;
  published_at: string | null;
  source_name: string | null;
  source_url: string;
  country: string | null;
  relevance_score: number;
}

export interface PublicSearchResponse {
  query: string;
  total: number;
  items: PublicSearchItem[];
  rate_limit_remaining: number;
}

export async function publicSearch(
  q: string,
  limit = 10,
): Promise<PublicSearchResponse> {
  const url = `/public/search?q=${encodeURIComponent(q)}&limit=${limit}`;
  return apiFetch<PublicSearchResponse>(url, { skipAuth: true });
}

// ---- Articles -------------------------------------------------------------

export interface ArticleSummary {
  id: string;
  source_id: string;
  source_name: string | null;
  canonical_url: string;
  title: string;
  author: string | null;
  published_at: string | null;
  status: string;
  language: string;
  extraction_confidence: number | null;
  text_length: number;
  has_images: boolean;
  created_at: string;
}

export interface ArticleListResponse {
  data: ArticleSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArticleImagePublic {
  id: string;
  original_url: string;
  alt_text: string | null;
  caption: string | null;
  vlm_caption: string | null;
  ocr_text: string | null;
  depicts: string[] | null;
  discovered_from: string | null;
  status: string;
  position: number | null;
  processed_at: string | null;
  created_at: string;
}

export interface ArticleDetail {
  id: string;
  source_id: string;
  source_name: string | null;
  source_slug: string | null;
  canonical_url: string;
  source_url: string;
  title: string;
  subtitle: string | null;
  author: string | null;
  published_at: string | null;
  fetched_at: string;
  crawled_at: string;
  raw_html_storage_path: string | null;
  body_html: string | null;
  clean_text: string | null;
  language: string;
  content_hash: string;
  title_hash: string;
  extraction_confidence: number | null;
  status: string;
  created_at: string;
  updated_at: string;
  images: ArticleImagePublic[];
}

export interface ArticleStat {
  status: string;
  count: number;
}

export interface ArticleStatsResponse {
  by_status: ArticleStat[];
  total: number;
  by_source: Array<{ name: string; slug: string; count: number }>;
  embedded_count: number;
}

export interface ArticleListFilters {
  source_id?: string;
  status?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export async function listArticles(
  filters?: ArticleListFilters,
): Promise<ArticleListResponse> {
  return apiFetch<ArticleListResponse>(
    `/admin/articles${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function articleStats(): Promise<ArticleStatsResponse> {
  return apiFetch<ArticleStatsResponse>("/admin/articles/stats");
}

export interface HourlyBucket {
  hour: string;
  count: number;
}

export interface ProviderSeries {
  provider: string;
  buckets: HourlyBucket[];
}

export interface DashboardHourlyResponse {
  articles: HourlyBucket[];
  jobs: HourlyBucket[];
  generations: HourlyBucket[];
  provider_calls: HourlyBucket[];
  provider_calls_by_provider: ProviderSeries[];
}

export async function dashboardHourly(): Promise<DashboardHourlyResponse> {
  return apiFetch<DashboardHourlyResponse>("/admin/dashboard/hourly");
}

export type ProviderCallsPeriod = "7d" | "30d" | "3m";

export interface ProviderCallsRangeResponse {
  period: ProviderCallsPeriod;
  bucket: "hour" | "day" | "week";
  series: ProviderSeries[];
}

export async function dashboardProviderCalls(
  period: ProviderCallsPeriod = "7d",
): Promise<ProviderCallsRangeResponse> {
  return apiFetch<ProviderCallsRangeResponse>(
    `/admin/dashboard/provider-calls?period=${period}`,
  );
}

export async function getArticle(id: string): Promise<ArticleDetail> {
  return apiFetch<ArticleDetail>(`/admin/articles/${id}`);
}

export async function reprocessArticle(
  id: string,
): Promise<{ article_id: string; status: string; dispatched_task: string | null }> {
  return apiFetch(`/admin/articles/${id}/reprocess`, {
    method: "POST",
    body: {},
  });
}

// ---- App: Generation (#28-#30) --------------------------------------------

export interface GenerateRequest {
  request_text: string;
  output_type?: string;
  tone?: string;
  length?: string;
  show_sources?: boolean;
  max_posts?: number;
  /** Opsiyonel mod ipucu — query planner override edebilir. */
  mode_hint?: GenerateMode;
  /** #52 Faz 5 — Pro+ tier'da stil profili uygulama (UUID). */
  style_profile_id?: string | null;
}

/**
 * Üretim modu — `current` (anlık), `weekly` (son 7-14 gün),
 * `archive` (geçmiş gündem) (api-contracts.md §11).
 */
export type GenerateMode = "current" | "weekly" | "archive";

export interface XPostPublic {
  text: string;
  angle: string;
  char_count: number;
  related_agenda_card_ids: string[];
}

export interface SummaryItemPublic {
  event: string;
  source: string;
  date: string;
  agenda_card_id: string | null;
}

export interface SuggestedImagePublic {
  image_id: string;
  article_id: string;
  original_url: string;
  vlm_caption: string | null;
  depicts: string[] | null;
  alt_text: string | null;
  score: number;
  reason: string;
}

export interface GenerateResponse {
  id: string;
  status: string;
  request_text: string;
  mode: string;
  output_type: string;
  tone: string | null;
  posts: XPostPublic[];
  summary: string;
  sources: Array<{ title: string; source: string; url: string }>;
  warnings: string[];
  suggestions: string[];
  // #173 PR-F — multi-item summary doc
  summary_doc_title: string;
  summary_doc_items: SummaryItemPublic[];
  // #305 MVP-1.4 PR-5 — process & discard suggested image
  suggested_image: SuggestedImagePublic | null;
  cost_usd: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface GenerationSummary {
  id: string;
  request_text: string;
  mode: string;
  output_type: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  saved: boolean;
  posts_count: number;
  halu_flagged: boolean;
}

export interface GenerationListResponse {
  data: GenerationSummary[];
  total: number;
}

export interface QuotaResponse {
  tier: string;
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
}

export async function generate(
  payload: GenerateRequest,
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>("/app/generate", {
    method: "POST",
    body: payload,
  });
}

// ============================================================================
// Streaming generate (issue #527)
// ============================================================================

export interface GenerateStreamHandlers {
  onMeta?: (data: {
    generation_id: string;
    mode: string;
    output_type: string;
    tone: string | null;
    plan: {
      intent: string;
      topic_query: string;
      keywords: string[];
      requested_count: number;
    };
  }) => void;
  onProgress?: (data: { stage: string; detail: string }) => void;
  onChunk?: (data: { delta: string }) => void;
  onPost?: (data: {
    index: number;
    text: string;
    angle: string;
    char_count: number;
    related_agenda_card_ids: string[];
  }) => void;
  onParsed?: (data: {
    posts: Array<{
      text: string;
      angle: string;
      char_count: number;
      related_agenda_card_ids: string[];
    }>;
    summary: string;
    sources: Array<{ title: string; source: string; url: string }>;
    warnings: string[];
    summary_doc_title: string;
    summary_doc_items: Array<{
      event: string;
      source: string;
      date: string;
      agenda_card_id: string | null;
    }>;
  }) => void;
  onCitation?: (data: {
    repairs: number;
    unsupported_warnings: string[];
    posts_after_repair: Array<{
      index: number;
      text: string;
      char_count: number;
    }>;
  }) => void;
  onImage?: (data: {
    image_id: string;
    article_id: string;
    original_url: string;
    vlm_caption: string | null;
    depicts: string[] | null;
    alt_text: string | null;
    score: number;
    reason: string;
  }) => void;
  onDone?: (data: {
    generation_id: string;
    status: string;
    cost_usd?: number;
    completed_at?: string;
    ttfb_ms?: number;
  }) => void;
  onError?: (data: {
    code: string;
    title: string;
    reason: string;
    suggestions?: string[];
  }) => void;
}

/**
 * SSE streaming generate (#527).
 *
 * Auth refresh fetch wrapper'ında entegre değil — stream ortasında 401 olursa
 * onError ile bildirilir, caller fallback'e geçebilir. Pre-stream 401 (ilk
 * response status) için access_token önceden kontrol edilmeli.
 */
export async function generateStream(
  payload: GenerateRequest,
  handlers: GenerateStreamHandlers,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    handlers.onError?.({
      code: "UNAUTHENTICATED",
      title: "Oturum yok",
      reason: "access_token bulunamadı",
    });
    return;
  }

  const resp = await fetch(`${API_BASE}/app/generate-stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
    signal: options.signal,
  });

  if (!resp.ok) {
    let detail: ApiError = { status: resp.status };
    try {
      const body = await resp.json();
      detail = {
        status: resp.status,
        code: body.detail?.code,
        title: body.detail?.title,
        detail: body.detail?.reason || body.detail?.message,
      };
    } catch {
      // ignore parse error
    }
    handlers.onError?.({
      code: detail.code || `HTTP_${resp.status}`,
      title: detail.title || `HTTP ${resp.status}`,
      reason: detail.detail || "",
    });
    return;
  }

  if (!resp.body) {
    handlers.onError?.({
      code: "NO_BODY",
      title: "Stream boş",
      reason: "response.body is null",
    });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE event boundary = "\n\n"
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        dispatchEvent(rawEvent, handlers);
      }
    }
    // flush kalan buffer
    if (buffer.trim()) {
      dispatchEvent(buffer, handlers);
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      return; // caller stopped
    }
    handlers.onError?.({
      code: "STREAM_READ_ERROR",
      title: "Stream okuma hatası",
      reason: (err as Error).message,
    });
  } finally {
    reader.releaseLock();
  }
}

function dispatchEvent(rawEvent: string, handlers: GenerateStreamHandlers) {
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^\s/, ""));
    }
  }
  if (dataLines.length === 0) return;

  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d = data as any;
  switch (eventName) {
    case "meta":
      handlers.onMeta?.(d);
      break;
    case "progress":
      handlers.onProgress?.(d);
      break;
    case "chunk":
      handlers.onChunk?.(d);
      break;
    case "post":
      handlers.onPost?.(d);
      break;
    case "parsed":
      handlers.onParsed?.(d);
      break;
    case "citation":
      handlers.onCitation?.(d);
      break;
    case "image":
      handlers.onImage?.(d);
      break;
    case "done":
      handlers.onDone?.(d);
      break;
    case "error":
      handlers.onError?.(d);
      break;
    default:
      // unknown event — ignore
      break;
  }
}

export async function listMyGenerations(filters?: {
  saved_only?: boolean;
  limit?: number;
  offset?: number;
}): Promise<GenerationListResponse> {
  return apiFetch<GenerationListResponse>(
    `/app/generations${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function getMyGeneration(id: string): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>(`/app/generations/${id}`);
}

export async function saveGeneration(
  id: string,
  note?: string,
): Promise<{ status: string; generation_id: string }> {
  return apiFetch(`/app/generations/${id}/save`, {
    method: "POST",
    body: { note: note || null },
  });
}

export async function unsaveGeneration(id: string): Promise<void> {
  return apiFetch(`/app/generations/${id}/save`, { method: "DELETE" });
}

export async function flagHalu(
  id: string,
  reason?: string,
): Promise<{ status: string; generation_id: string }> {
  return apiFetch(`/app/generations/${id}/flag-halu`, {
    method: "POST",
    body: { reason: reason || null },
  });
}

export async function getMyQuota(): Promise<QuotaResponse> {
  return apiFetch<QuotaResponse>("/app/quota");
}

// ---- Legal admin (#35) -----------------------------------------------------

export interface TakedownAdminPublic {
  id: string;
  ticket_id: string;
  request_type: "abuse" | "takedown" | "copyright" | "privacy_request";
  requester_name: string | null;
  requester_email: string;
  requester_phone: string | null;
  requester_organization: string | null;
  authority_claim: string | null;
  subject_url: string | null;
  description: string;
  evidence_urls: string[];
  status: string;
  priority: string;
  submitted_at: string;
  triaged_at: string | null;
  investigating_at: string | null;
  resolved_at: string | null;
  sla_due_at: string;
  action_taken: string | null;
  rejection_reason: string | null;
  assigned_to: string | null;
  internal_notes: string | null;
  overdue: boolean;
}

export interface TakedownListResponse {
  data: TakedownAdminPublic[];
  total: number;
  overdue_count: number;
}

export interface TakedownUpdateRequest {
  status?: string;
  priority?: string;
  action_taken?: string;
  rejection_reason?: string;
  internal_notes?: string;
  assign_to_self?: boolean;
}

export async function listTakedownRequests(filters?: {
  request_type?: string;
  status?: string;
  only_overdue?: boolean;
  limit?: number;
  offset?: number;
}): Promise<TakedownListResponse> {
  return apiFetch<TakedownListResponse>(
    `/admin/legal/requests${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function getTakedownRequest(
  ticketId: string,
): Promise<TakedownAdminPublic> {
  return apiFetch<TakedownAdminPublic>(`/admin/legal/requests/${ticketId}`);
}

export async function updateTakedownRequest(
  ticketId: string,
  payload: TakedownUpdateRequest,
): Promise<TakedownAdminPublic> {
  return apiFetch<TakedownAdminPublic>(`/admin/legal/requests/${ticketId}`, {
    method: "PATCH",
    body: payload,
  });
}

// ---- Admin Users (#69) -----------------------------------------------------

export interface AdminUserSummary {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  deleted_at: string | null;
}

export interface AdminUserDetail extends AdminUserSummary {
  kvkk_acknowledgment_at: string | null;
  data_processing_consent_at: string | null;
  foreign_transfer_consent_at: string | null;
  marketing_consent_at: string | null;
  last_login_ip: string | null;
  updated_at: string;
}

export interface AdminUserListResponse {
  data: AdminUserSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminUserStatsResponse {
  total: number;
  active: number;
  inactive: number;
  deleted: number;
  email_verified: number;
  by_tier: Array<{ tier: string; count: number }>;
  by_role: Array<{ role: string; count: number }>;
}

export interface AdminUserUpdate {
  role?: string;
  tier?: string;
  is_active?: boolean;
}

export async function listAdminUsers(filters?: {
  role?: string;
  tier?: string;
  is_active?: boolean;
  deleted?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUserListResponse> {
  return apiFetch<AdminUserListResponse>(
    `/admin/users${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function getAdminUser(id: string): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`);
}

export async function updateAdminUser(
  id: string,
  payload: AdminUserUpdate & { note?: string },
): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function restoreAdminUser(
  id: string,
  note?: string,
): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}/restore`, {
    method: "POST",
    body: { note: note || null },
  });
}

export async function getAdminUserStats(): Promise<AdminUserStatsResponse> {
  return apiFetch<AdminUserStatsResponse>("/admin/users/stats");
}

// ---- Admin Queue (#17 frontend) -------------------------------------------

export interface QueueStat {
  name: string;
  queued_count: number;
  running_count: number;
  succeeded_count_24h: number;
  failed_count_24h: number;
}

export interface QueueOverviewResponse {
  queues: QueueStat[];
  failed_jobs_unresolved: number;
  worker_count?: number;
}

export interface FailedJobPublic {
  id: string;
  original_job_id: string | null;
  job_type: string;
  severity?: "error" | "warning" | "permanent_info";
  source_id: string | null;
  article_url: string | null;
  error_message: string;
  stack_trace: string | null;
  retry_count: number;
  last_attempt_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  payload: Record<string, unknown>;
}

export interface FailedJobListResponse {
  data: FailedJobPublic[];
  total: number;
}

export async function getQueueOverview(): Promise<QueueOverviewResponse> {
  return apiFetch<QueueOverviewResponse>("/admin/queue/overview");
}

export async function listFailedJobs(filters?: {
  job_type?: string;
  unresolved_only?: boolean;
  source_id?: string;
  severity?: "error" | "warning" | "permanent_info" | "all";
  include_info?: boolean;
  limit?: number;
  offset?: number;
}): Promise<FailedJobListResponse> {
  return apiFetch<FailedJobListResponse>(
    `/admin/queue/failed${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function retryFailedJob(
  failedId: string,
): Promise<{ new_job_id: string; scheduled_at: string; celery_task_id?: string }> {
  return apiFetch(`/admin/queue/jobs/${failedId}/retry`, {
    method: "POST",
    body: {},
  });
}

// #462 — Bulk operations
export interface BulkResultItem {
  id: string;
  ok: boolean;
  code?: string | null;
  celery_task_id?: string | null;
}

export interface BulkResponse {
  succeeded: number;
  failed: number;
  results: BulkResultItem[];
}

export async function bulkRetryFailedJobs(
  ids: string[],
): Promise<BulkResponse> {
  return apiFetch("/admin/queue/failed/bulk-retry", {
    method: "POST",
    body: { ids },
  });
}

export async function bulkResolveFailedJobs(
  ids: string[],
  note?: string,
): Promise<BulkResponse> {
  return apiFetch("/admin/queue/failed/bulk-resolve", {
    method: "POST",
    body: { ids, note: note || null },
  });
}

// #468 — Maintenance task list + run-now
export interface MaintenanceLastRun {
  task_name: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  status: "succeeded" | "failed";
  summary: Record<string, unknown> | null;
  triggered_by: string;
  error: string | null;
}

export interface MaintenanceTaskInfo {
  task_name: string;
  label: string;
  pipeline: string;
  interval_human: string;
  queue: string;
  last_run: MaintenanceLastRun | null;
}

export interface MaintenanceListResponse {
  tasks: MaintenanceTaskInfo[];
}

export async function listMaintenanceTasks(): Promise<MaintenanceListResponse> {
  return apiFetch<MaintenanceListResponse>("/admin/queue/maintenance");
}

export async function runMaintenanceNow(
  taskName: string,
): Promise<{ task_name: string; celery_task_id: string; triggered_at: string }> {
  return apiFetch(`/admin/queue/maintenance/${encodeURIComponent(taskName)}/run-now`, {
    method: "POST",
    body: {},
  });
}

export async function resolveFailedJob(
  failedId: string,
  note?: string,
): Promise<void> {
  return apiFetch(`/admin/queue/failed/${failedId}`, {
    method: "DELETE",
    body: { note: note || null },
  });
}

// ---- Admin Audit Log (#132) ------------------------------------------------

export interface AuditLogEntry {
  id: string;
  actor_id: string;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  event_metadata: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  data: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogFilters {
  action?: string;
  actor_id?: string;
  target_type?: string;
  target_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export async function listAuditLog(
  filters?: AuditLogFilters,
): Promise<AuditLogListResponse> {
  return apiFetch<AuditLogListResponse>(
    `/admin/audit${buildQuery(filters as Record<string, unknown>)}`,
  );
}

// ---- App: /app/me — KVKK self-service (#80, #142) -------------------------

export interface UserMePublic {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  kvkk_acknowledgment_at: string | null;
  data_processing_consent_at: string | null;
  foreign_transfer_consent_at: string | null;
  marketing_consent_at: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface ProfileUpdatePayload {
  full_name?: string | null;
  locale?: string | null;
  marketing_consent?: boolean | null;
}

export interface AccountDeleteResponse {
  status: string;
  deletion_at: string;
}

export interface ExportResponse {
  exported_at: string;
  user: Record<string, unknown>;
  generations: Array<Record<string, unknown>>;
  saved_generations: Array<Record<string, unknown>>;
  usage_events: Array<Record<string, unknown>>;
  sessions: Array<Record<string, unknown>>;
}

export async function getMe(): Promise<UserMePublic> {
  return apiFetch<UserMePublic>("/app/me");
}

export async function requestVerifyResend(
  email: string,
): Promise<{ ok: boolean; detail: string | null }> {
  return apiFetch<{ ok: boolean; detail: string | null }>(
    "/auth/verify-resend",
    {
      method: "POST",
      body: { email },
      skipAuth: true,
    },
  );
}

export async function updateMe(
  payload: ProfileUpdatePayload,
): Promise<UserMePublic> {
  return apiFetch<UserMePublic>("/app/me", {
    method: "PATCH",
    body: payload,
  });
}

export async function exportMe(): Promise<ExportResponse> {
  return apiFetch<ExportResponse>("/app/me/export");
}

export async function deleteMe(
  confirmation: string,
  reason?: string,
): Promise<AccountDeleteResponse> {
  return apiFetch<AccountDeleteResponse>("/app/me", {
    method: "DELETE",
    body: { confirmation, reason: reason || null },
  });
}

// ============================================================================
// Admin RAG (Epic #189 — observability dashboard)
// ============================================================================

export interface RagFeatureFlags {
  reranker_enabled: boolean;
  reranker_candidate_pool: number;
  rerank_model: string;
  // #420 — use_local_embedding kaldırıldı (embedding artık tek provider:
  // local BAAI/bge-m3, NIM bge-m3 ekosistemden çıkarıldı)
}

export interface RagHealthCounts {
  daily_cards: number;
  weekly_cards: number;
  daily_with_parent: number;
  active_clusters: number;
  last_24h_generations: number;
  last_24h_insufficient: number;
}

export interface RagLastEval {
  id: string;
  golden_set: string;
  completed_at: string | null;
  ndcg_10: number | null;
  map_5: number | null;
  mrr_10: number | null;
  recall_20: number | null;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  n_queries: number;
}

export interface RagHealthResponse {
  flags: RagFeatureFlags;
  counts: RagHealthCounts;
  last_eval: RagLastEval | null;
}

export interface BenchmarkRunSummary {
  id: string;
  golden_set: string;
  started_at: string;
  completed_at: string | null;
  n_queries: number;
  ndcg_10: number | null;
  map_5: number | null;
  mrr_10: number | null;
  recall_20: number | null;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  triggered_by: string | null;
}

export interface BenchmarkHistoryResponse {
  runs: BenchmarkRunSummary[];
}

export interface BenchmarkTriggerResponse {
  started: boolean;
  run_id: string | null;
  message: string;
}

export interface CitationStatsResponse {
  sample_size: number;
  repairs_total: number;
  repairs_avg_per_gen: number;
  unsupported_warnings: number;
  unsupported_avg_per_gen: number;
}

export interface RerankStatsResponse {
  sample_size: number;
  avg_latency_ms: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  last_call_at: string | null;
}

export interface WeeklyClusterRow {
  id: string;
  title: string;
  summary: string;
  importance: number | null;
  daily_children_count: number;
  children_titles: string[];
  updated_at: string;
}

export interface RaptorClustersResponse {
  weekly: WeeklyClusterRow[];
}

export interface RaptorTriggerResponse {
  daily_count: number;
  cluster_count: number;
  ok_count: number;
}

export interface InspectRow {
  id: string;
  title: string;
  rrf_score: number | null;
  rerank_score: number | null;
  rrf_rank: number | null;
  rerank_rank: number | null;
}

export interface InspectPlannerInfo {
  used: boolean;
  enriched_query: string | null;
  keywords: string[];
  topic_query: string | null;
  intent: string | null;
}

export interface InspectQueryResponse {
  query: string;
  levels: string[];
  rows: InspectRow[];
  rrf_only_top: InspectRow[];
  reranked_top: InspectRow[];
  planner: InspectPlannerInfo | null;
}

export async function ragHealth(): Promise<RagHealthResponse> {
  return apiFetch<RagHealthResponse>("/admin/rag/health");
}

export async function ragBenchmarkHistory(
  limit = 20,
): Promise<BenchmarkHistoryResponse> {
  return apiFetch<BenchmarkHistoryResponse>(
    `/admin/rag/benchmark/history?limit=${limit}`,
  );
}

export async function ragBenchmarkRun(
  golden = "retrieval_golden_tr.yaml",
): Promise<BenchmarkTriggerResponse> {
  return apiFetch<BenchmarkTriggerResponse>(
    `/admin/rag/benchmark/run?golden=${encodeURIComponent(golden)}`,
    { method: "POST" },
  );
}

export async function ragCitationStats(
  sample = 100,
): Promise<CitationStatsResponse> {
  return apiFetch<CitationStatsResponse>(
    `/admin/rag/citation-stats?sample=${sample}`,
  );
}

export async function ragRerankStats(
  hours = 24,
): Promise<RerankStatsResponse> {
  return apiFetch<RerankStatsResponse>(
    `/admin/rag/rerank-stats?hours=${hours}`,
  );
}

export async function ragRaptorClusters(
  limit = 20,
): Promise<RaptorClustersResponse> {
  return apiFetch<RaptorClustersResponse>(
    `/admin/rag/raptor/clusters?limit=${limit}`,
  );
}

export async function ragRaptorTrigger(): Promise<RaptorTriggerResponse> {
  return apiFetch<RaptorTriggerResponse>("/admin/rag/raptor/trigger", {
    method: "POST",
  });
}

export async function ragInspectQuery(
  query: string,
  topK = 10,
  candidatePool = 80,
  usePlanner = true,
): Promise<InspectQueryResponse> {
  return apiFetch<InspectQueryResponse>("/admin/rag/inspect-query", {
    method: "POST",
    body: {
      query,
      top_k: topK,
      candidate_pool: candidatePool,
      use_planner: usePlanner,
    },
  });
}

// ---------------------------------------------------------------------------
// Pipeline Comparison (#440)
// ---------------------------------------------------------------------------

export interface PeriodMetrics {
  period_start: string;
  period_end: string;
  sample_count: number;
  avg_input_tokens: number | null;
  avg_output_tokens: number | null;
  cache_hit_ratio: number | null;
  avg_cost_usd_per_req: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  halu_flag_rate: number | null;
  insufficient_data_rate: number | null;
  completed_generation_count: number;
}

export interface PipelineComparisonResponse {
  period_a: PeriodMetrics;
  period_b: PeriodMetrics;
  delta_pct: Record<string, number | null>;
}

export interface PipelineComparisonParams {
  fromA?: string; // ISO datetime
  toA?: string;
  fromB?: string;
  toB?: string;
}

export async function ragPipelineComparison(
  params: PipelineComparisonParams = {},
): Promise<PipelineComparisonResponse> {
  const qs = new URLSearchParams();
  if (params.fromA) qs.set("from_a", params.fromA);
  if (params.toA) qs.set("to_a", params.toA);
  if (params.fromB) qs.set("from_b", params.fromB);
  if (params.toB) qs.set("to_b", params.toB);
  const queryString = qs.toString();
  const url = queryString
    ? `/admin/rag/pipeline-comparison?${queryString}`
    : "/admin/rag/pipeline-comparison";
  return apiFetch<PipelineComparisonResponse>(url);
}

// ===========================================================================
// Admin Settings (#262/#265, MVP-1.2)
// ===========================================================================

export interface AdminSettingItem {
  key: string;
  value: unknown;
  default: unknown;
  type: "float" | "int" | "bool" | "string" | "json";
  group: string;
  description: string | null;
  min_value: number | null;
  max_value: number | null;
  allowed_values: unknown[] | null;
  requires_restart: boolean;
  is_overridden: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AdminSettingsListResponse {
  data: AdminSettingItem[];
  groups: string[];
}

export async function adminSettingsList(
  group?: string,
): Promise<AdminSettingsListResponse> {
  const qs = group ? `?group=${encodeURIComponent(group)}` : "";
  return apiFetch<AdminSettingsListResponse>(`/admin/settings${qs}`);
}

export async function adminSettingUpdate(
  key: string,
  value: unknown,
): Promise<AdminSettingItem> {
  return apiFetch<AdminSettingItem>(
    `/admin/settings/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: { value },
    },
  );
}

export async function adminSettingReset(
  key: string,
): Promise<AdminSettingItem> {
  return apiFetch<AdminSettingItem>(
    `/admin/settings/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}

// ============================================================================
// Admin Media (#304 MVP-1.4 PR-4 — NIM VLM image observability)
// ============================================================================

export type MediaStatus = "pending" | "processed" | "failed" | "skipped";

export interface MediaImage {
  id: string;
  article_id: string;
  article_title: string | null;
  article_url: string | null;
  source_id: string;
  source_name: string | null;
  original_url: string;
  alt_text: string | null;
  caption: string | null;
  vlm_caption: string | null;
  ocr_text: string | null;
  depicts: string[] | null;
  status: MediaStatus;
  error_message?: string | null;
  position: number | null;
  created_at: string;
  processed_at: string | null;
}

export interface MediaListResponse {
  data: MediaImage[];
  total: number;
  limit: number;
  offset: number;
}

export interface MediaStatsResponse {
  total: number;
  processed: number;
  failed: number;
  pending: number;
  skipped: number;
  last_24h_processed: number;
}

export interface MediaListFilters {
  source_id?: string;
  status?: MediaStatus;
  date_from?: string; // ISO 8601 (YYYY-MM-DD)
  date_to?: string;
  limit?: number;
  offset?: number;
}

export async function listAdminMedia(
  filters?: MediaListFilters,
): Promise<MediaListResponse> {
  return apiFetch<MediaListResponse>(
    `/admin/media${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function adminMediaStats(): Promise<MediaStatsResponse> {
  return apiFetch<MediaStatsResponse>("/admin/media/stats");
}

export async function reprocessMedia(id: string): Promise<MediaImage> {
  return apiFetch<MediaImage>(`/admin/media/${id}/reprocess`, {
    method: "POST",
    body: {},
  });
}

// =============================================================================
// Admin /system — Sistem Durumu (#358 MVP-1.6 B1)
// =============================================================================

export interface CpuInfo {
  cores: number;
  load_1m: number;
  load_5m: number;
  load_15m: number;
  usage_pct: number;
}
export interface RamInfo {
  total_mb: number;
  used_mb: number;
  free_mb: number;
  used_pct: number;
}
export interface DiskInfo {
  total_gb: number;
  used_gb: number;
  free_gb: number;
  used_pct: number;
}
export interface VpsInfo {
  hostname: string;
  cpu: CpuInfo;
  ram: RamInfo;
  disk: DiskInfo;
}
export interface TableSize {
  name: string;
  size_mb: number;
  row_count: number;
  index_size_mb: number;
}
export interface PostgresInfo {
  db_size_gb: number;
  tables: TableSize[];
}
export interface BucketInfo {
  name: string;
  size_gb: number;
  object_count: number;
}
export interface MinioInfo {
  endpoint: string;
  buckets: BucketInfo[];
}
export interface ContaboInfo {
  endpoint: string;
  bucket: string;
  size_gb: number;
  object_count: number;
  by_prefix: Record<string, BucketInfo>;
}
export interface BackupInfo {
  last_snapshot_at: string | null;
  last_snapshot_age_h: number | null;
  snapshot_count: number;
  total_size_gb: number;
  last_check_status: string;
}
export interface SystemHealthResponse {
  vps: VpsInfo;
  postgres: PostgresInfo;
  minio: MinioInfo;
  contabo_os: ContaboInfo;
  backups: BackupInfo;
  timestamp: string;
  cache_age_seconds: number;
}

export async function adminSystemHealth(): Promise<SystemHealthResponse> {
  return apiFetch<SystemHealthResponse>("/admin/system/health");
}

// ============================================================================
// Admin disk panel (#570)
// ============================================================================

export interface DiskCategory {
  key: string;
  label: string;
  bytes: number;
  reclaimable_bytes: number;
}

export interface DiskBreakdownResponse {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  used_percent: number;
  categories: DiskCategory[];
  docker_total_bytes: number;
  reclaimable_bytes: number;
  timestamp: string;
}

export interface DiskCleanupResponse {
  reclaimed_bytes: number;
  items_deleted: number;
  duration_seconds: number;
  timestamp: string;
}

export async function adminDiskBreakdown(): Promise<DiskBreakdownResponse> {
  return apiFetch<DiskBreakdownResponse>("/admin/system/disk");
}

export async function adminDiskCleanup(): Promise<DiskCleanupResponse> {
  return apiFetch<DiskCleanupResponse>("/admin/system/disk/cleanup", {
    method: "POST",
  });
}
