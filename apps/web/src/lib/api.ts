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
  storage_url: string | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  file_size: number | null;
  sha256_hash: string | null;
  discovered_from: string | null;
  status: string;
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
}

export interface FailedJobPublic {
  id: string;
  original_job_id: string | null;
  job_type: string;
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
  limit?: number;
  offset?: number;
}): Promise<FailedJobListResponse> {
  return apiFetch<FailedJobListResponse>(
    `/admin/queue/failed${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function retryFailedJob(
  failedId: string,
): Promise<{ new_job_id: string; scheduled_at: string }> {
  return apiFetch(`/admin/queue/jobs/${failedId}/retry`, {
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
