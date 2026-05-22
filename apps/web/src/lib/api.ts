/**
 * API client — Nodrat backend (FastAPI) ile iletişim.
 *
 * docs/engineering/api-contracts.md
 *
 * Authentication: access_token + refresh_token (JWT) localStorage'da
 * tutulur. Production'da httpOnly cookie yapacağız (#71 backlog).
 */

// Shared internal query helper (api/_query.ts) — consolidated in PR-7a-9.
// NOT re-exported (no public `@/lib/api` surface change).
import { buildQuery } from "./api/_query";

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
      // TokenResponse extracted to ./api/auth.ts; same-file forward-reference
      // requires explicit import here (TS bundler resolution).
      const data = (await resp.json()) as import("./api/auth").TokenResponse;
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

// ---- Auth endpoints — extracted to ./api/auth.ts (PR-7a-3 + PR-7a-4) ------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/auth.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  UserPublic,
} from "./api/auth";
export {
  login,
  logout,
  register,
  requestVerifyResend,
} from "./api/auth";

// ---- Admin Sources core — extracted to ./api/admin/sources.ts (PR-7a-16a) -
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// Part 1 of 3: selector test (#70) + config versioning (#75) aşağıda INLINE
// kalır; PR-7a-16b / PR-7a-16c ile aynı dosyaya taşınacak.
//
// Refs:
// - apps/web/src/lib/api/admin/sources.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  SourceType,
  PollingTier,
  TierMetadata,
  SourcePublic,
  SourceUpdatePayload,
  SourceCreatePayload,
  ComplianceChecklist,
  ActivatePayload,
  FeedReportPublic,
  RobotsReportPublic,
  SourceListFilters,
} from "./api/admin/sources";
export {
  listSources,
  createSource,
  getSource,
  activateSource,
  updateSource,
  testFeed,
  robotsCheck,
} from "./api/admin/sources";

// ---- Admin Sources selector test — extracted to ./api/admin/sources.ts (PR-7a-16b)
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// Part 2 of 3: config versioning (#75) aşağıda INLINE kalır; PR-7a-16c ile taşınacak.
export type {
  SelectorMap,
  TestListingCard,
  TestListingResponse,
  SourceExtractionStats,
} from "./api/admin/sources";
export { testListing, sourceExtractionStats } from "./api/admin/sources";

// ---- Admin Sources config versioning — extracted to ./api/admin/sources.ts (PR-7a-16c)
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// Part 3 of 3: Admin Sources (core + selector test + config versioning) artık
// tamamen `api/admin/sources.ts`'te. `createConfig` 0-caller dead-code olarak
// korundu (cleanup/deletion ayrı PR).
export type {
  SourceConfigPublic,
  ConfigListResponse,
} from "./api/admin/sources";
export {
  listConfigs,
  createConfig,
  rollbackConfig,
} from "./api/admin/sources";

// ---- Public search (#261) — extracted to ./api/public.ts (PR-7a-1) --------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/public.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type { PublicSearchItem, PublicSearchResponse } from "./api/public";
export { publicSearch } from "./api/public";

// ---- Articles — extracted to ./api/admin/articles.ts (PR-7a-11) -----------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// NOTE: getMyQuota (/app/quota) is in the separate block below — untouched.
//
// Refs:
// - apps/web/src/lib/api/admin/articles.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  ArticleDetail,
  ArticleImagePublic,
  ArticleListFilters,
  ArticleListResponse,
  ArticleStat,
  ArticleStatsResponse,
  ArticleSummary,
  DashboardHourlyResponse,
  HourlyBucket,
  ProviderCallsPeriod,
  ProviderCallsRangeResponse,
  ProviderSeries,
} from "./api/admin/articles";
export {
  articleStats,
  dashboardHourly,
  dashboardProviderCalls,
  getArticle,
  listArticles,
  reprocessArticle,
} from "./api/admin/articles";

// ---- App: Generation block silindi (#800 S1A — research-only migration) ----
// Tüm generation function'ları + tip'leri /research/* endpointlerine devredildi.
//
// App quota (getMyQuota / QuotaResponse) — extracted to ./api/account.ts (PR-7a-12)
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
export type { QuotaResponse } from "./api/account";
export { getMyQuota } from "./api/account";

// ============================================================================
// Research (#793 Perplexity-style conversation mode)
// ============================================================================

export interface ResearchConversationItem {
  id: string;
  title: string;
  summary?: string | null;
  message_count: number;
  last_answer_snippet?: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResearchConversationList {
  items: ResearchConversationItem[];
  total: number;
}

export interface ResearchMessageSource {
  // #813 Faz 2 2B — source_type ile "haber" vs "wikipedia" ayrımı.
  source_type?: "news" | "wikipedia";
  article_id?: string;
  chunk_id?: string;
  title?: string;
  url?: string;
  source_name?: string;
  license?: string;          // CC BY-SA 4.0 (Wikipedia) gibi
  cite?: string;             // #845 — bu kaynağın citation token'ı ([3]/[W1])
}

export interface ResearchMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources_used?: ResearchMessageSource[] | null;
  sources_considered?: ResearchMessageSource[] | null;
  thinking_steps?: Array<{
    phase: string;
    detail?: string;
    latency_ms?: number;
    // Faza göre değişen opsiyonel alanlar (planner/confidence/tool_use)
    type?: string;
    topic_query?: string;
    confidence_score?: number;
    missing_signals?: string[];
    source_type?: string;
    article_count?: number;
  }> | null;
  followup_suggestions?: string[] | null; // #961
  // S1C feedback fields
  halu_flagged_at?: string | null;
  user_action?: string | null;
  user_action_at?: string | null;
  sft_eligible?: boolean;
  dpo_rejected?: boolean;
  created_at: string;
}

export interface ResearchThread {
  id: string;
  title: string;
  summary?: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
  messages: ResearchMessage[];
}

export async function listResearchConversations(opts?: {
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}): Promise<ResearchConversationList> {
  return apiFetch<ResearchConversationList>(
    `/research/conversations${buildQuery(opts as Record<string, unknown> | undefined)}`,
  );
}

export async function createResearchConversation(
  title?: string,
): Promise<ResearchConversationItem> {
  return apiFetch<ResearchConversationItem>("/research/conversations", {
    method: "POST",
    body: { title: title || null },
  });
}

export async function getResearchConversation(id: string): Promise<ResearchThread> {
  return apiFetch<ResearchThread>(`/research/conversations/${id}`);
}

export async function renameResearchConversation(
  id: string,
  title: string,
): Promise<ResearchConversationItem> {
  return apiFetch<ResearchConversationItem>(`/research/conversations/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export async function archiveResearchConversation(id: string): Promise<void> {
  return apiFetch(`/research/conversations/${id}`, { method: "DELETE" });
}

// ---- Message feedback (#802 S1C) ----

export interface MessageFeedbackResponse {
  id: string;
  halu_flagged_at: string | null;
  user_action: string | null;
  user_action_at: string | null;
  sft_eligible: boolean;
  sft_excluded_reason: string | null;
  dpo_rejected: boolean;
}

export async function flagResearchMessageHalu(
  msgId: string,
  reason?: string | null,
  chosenContent?: string | null,
): Promise<MessageFeedbackResponse> {
  return apiFetch<MessageFeedbackResponse>(
    `/research/messages/${msgId}/flag-halu`,
    {
      method: "POST",
      body: { reason: reason || null, chosen_content: chosenContent || null },
    },
  );
}

export async function recordResearchMessageAction(
  msgId: string,
  action: "copied" | "posted" | "edited" | "none",
  opts?: { edit_distance?: number; edited_content?: string | null },
): Promise<MessageFeedbackResponse> {
  return apiFetch<MessageFeedbackResponse>(
    `/research/messages/${msgId}/action`,
    {
      method: "POST",
      body: {
        action,
        edit_distance: opts?.edit_distance,
        edited_content: opts?.edited_content,
      },
    },
  );
}

/**
 * Research mesaj SSE streaming — POST /research/conversations/{id}/messages.
 * Event types: thinking_step, source_discovered, chunk, done, error,
 *   confidence_score (telemetri). Wikipedia LLM tool-use ile (#822) —
 *   ayrı consent endpoint/event yok.
 * onEvent her event'i (parsed JSON data) ile çağrılır.
 */
export async function streamResearchMessage(
  conversationId: string,
  payload: {
    content: string;
    // ResearchSettings (#803 S1D)
    output_type?: string;
    tone?: string | null;
    length?: string | null;
    max_posts?: number | null;
    style_profile_id?: string | null;
    show_sources?: boolean;
  },
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_BASE}/research/conversations/${conversationId}/messages`;
  const token = getAccessToken();
  const resp = await fetch(url, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const txt = await resp.text();
    throw new ApiException({
      status: resp.status,
      title: txt || resp.statusText,
    });
  }
  if (!resp.body) {
    throw new ApiException({ status: 500, title: "Stream body missing" });
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE format: "event: name\ndata: {...}\n\n"
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!raw.trim()) continue;
      let eventName = "message";
      let dataLine = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (dataLine) {
        try {
          const parsed = JSON.parse(dataLine) as Record<string, unknown>;
          onEvent(eventName, parsed);
        } catch {
          // ignore parse error
        }
      }
    }
  }
}

// ---- Legal admin — extracted to ./api/admin/legal.ts (PR-7a-10) -----------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/legal.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  TakedownAdminPublic,
  TakedownListResponse,
  TakedownUpdateRequest,
} from "./api/admin/legal";
export {
  getTakedownRequest,
  listTakedownRequests,
  updateTakedownRequest,
} from "./api/admin/legal";

// ---- Admin Users — extracted to ./api/admin/users.ts (PR-7a-5) ----------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/users.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  AdminUserDetail,
  AdminUserListResponse,
  AdminUserStatsResponse,
  AdminUserSummary,
  AdminUserUpdate,
} from "./api/admin/users";
export {
  getAdminUser,
  getAdminUserStats,
  listAdminUsers,
  restoreAdminUser,
  updateAdminUser,
} from "./api/admin/users";

// ---- Admin Queue — extracted to ./api/admin/queue.ts (PR-7a-15) -----------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/queue.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  QueueStat,
  QueueOverviewResponse,
  FailedJobPublic,
  FailedJobListResponse,
  BulkResultItem,
  BulkResponse,
  MaintenanceLastRun,
  MaintenanceTaskInfo,
  MaintenanceListResponse,
} from "./api/admin/queue";
export {
  getQueueOverview,
  listFailedJobs,
  retryFailedJob,
  bulkRetryFailedJobs,
  bulkResolveFailedJobs,
  listMaintenanceTasks,
  runMaintenanceNow,
  resolveFailedJob,
} from "./api/admin/queue";

// ---- Admin Audit Log — extracted to ./api/admin/audit.ts (PR-7a-6) --------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/audit.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  AuditLogEntry,
  AuditLogFilters,
  AuditLogListResponse,
} from "./api/admin/audit";
export { listAuditLog } from "./api/admin/audit";

// ---- Admin: /admin/clusters — Pivot araştırma kümesi gözlem (#1028) -------

export interface ClusterListItem {
  cluster_id: string;
  cluster_key: string;
  canonical_name: string;
  cluster_type: string;
  parent_cluster_id: string | null;
  member_count: number;
  distinct_users: number;
  last_at: string | null;
}

export interface ClusterListResponse {
  // Backend (admin_clusters.py ClusterListResponse) `data` döndürür —
  // FE eski `items` adıyla uyumsuzdu → resp.items=undefined → sayfa
  // çökmesi (#1044 regresyonu, prod-audit'te yakalandı). BE sözleşmesi
  // kaynak doğruluğu (F3c #1028 deployed) → FE hizalandı.
  data: ClusterListItem[];
  total: number;
  limit: number;
  offset: number;
}

export async function listClusters(params?: {
  limit?: number;
  offset?: number;
}): Promise<ClusterListResponse> {
  return apiFetch<ClusterListResponse>(
    `/admin/clusters${buildQuery(params as Record<string, unknown>)}`,
  );
}

// ---- App: /app/me — extracted to ./api/account.ts (PR-7a-13) -------------
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// Joins getMyQuota (PR-7a-12) in the user-facing account module.
//
// Refs:
// - apps/web/src/lib/api/account.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  AccountDeleteResponse,
  ExportResponse,
  ProfileUpdatePayload,
  UserMePublic,
} from "./api/account";
export {
  deleteMe,
  exportMe,
  getMe,
  updateMe,
} from "./api/account";

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

export interface RagWarmUpInfo {
  // #696 (B6)
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  embedding_ms: number | null;
  rerank_ms: number | null;
  ok: boolean;
}

export interface RagHealthResponse {
  flags: RagFeatureFlags;
  counts: RagHealthCounts;
  last_eval: RagLastEval | null;
  warm_up: RagWarmUpInfo | null;  // #696 (B6)
}

export interface BenchmarkRunSummary {
  id: string;
  golden_set: string;
  started_at: string;
  completed_at: string | null;
  n_queries: number;
  suite: string | null;  // #712 B4 — chart suite-aware filtre
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

export interface CacheCallTypeRow {
  call_type: string;
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  miss_tokens: number;
  cache_hit_ratio: number | null;
  tools_present_rate: number | null;
}

export interface CacheSegmentAvg {
  seg_system: number | null;
  seg_tools_schema: number | null;
  seg_msg1_question: number | null;
  seg_rag_tool: number | null;
  seg_assistant_intermediate: number | null;
}

export interface CacheTelemetryResponse {
  window_hours: number;
  total_calls: number;
  overall_cache_hit_ratio: number | null;
  total_input_tokens: number;
  total_cached_tokens: number;
  total_miss_tokens: number;
  by_call_type: CacheCallTypeRow[];
  segment_avg: CacheSegmentAvg;
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
  // #742 (Faz 7c Aşama 1) — diagnostic answer extraction
  answer_span_candidates?: string[];
  chunk_excerpt?: string | null;
  article_id?: string | null;
}

export interface InspectParentDocMerge {
  // #742 (Faz 7c Aşama 1) — aynı article'dan 2+ chunk top-K'de
  article_id: string;
  article_title: string | null;
  chunk_count: number;
  chunks: { chunk_id: string; rank: number; excerpt: string }[];
}

export interface InspectPlannerInfo {
  used: boolean;
  enriched_query: string | null;
  keywords: string[];
  topic_query: string | null;
  intent: string | null;
}

export interface InspectNerInfo {
  // #696 (B4) — chunks suite'inde NER pipeline telemetri
  enabled: boolean;
  query_entities: string[];
  df_map: Record<string, number>;
  mode: "multi_and" | "multi_and_common" | "single_rare" | "no_match" | "error";
  target_aids_count: number;
  target_aids_sample: string[];
}

export interface InspectTimeframeInfo {
  // #725 — Planner timeframe SQL filter telemetri (production parity)
  enabled: boolean;
  timeframes: { label: string; from: string; to: string }[];
  effective_from: string | null;
  effective_to: string | null;
  span_days: number | null;
}

export interface InspectSufficiencyInfo {
  // #725 — Sufficiency gate telemetri (gate olarak DEĞİL, tanı amaçlı)
  enabled: boolean;
  sufficient: boolean;
  mode: string;
  counts_per_period: Record<string, number>;
  min_evidence_per_period: number;
  reason: string | null;
  would_have_exited: boolean;
}

export interface InspectQueryResponse {
  query: string;
  suite: "cards" | "chunks" | "production";  // #696 + #718
  levels: string[];
  rows: InspectRow[];
  rrf_only_top: InspectRow[];
  reranked_top: InspectRow[];
  planner: InspectPlannerInfo | null;
  ner?: InspectNerInfo | null;  // #696 (B4) + #718 cards için de dolu
  timeframe?: InspectTimeframeInfo | null;  // #725
  sufficiency?: InspectSufficiencyInfo | null;  // #725
  parent_doc_merge?: InspectParentDocMerge[];  // #742 (Faz 7c Aşama 1)
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
  suite: "cards" | "chunks" = "chunks",
  top_k = 20,
  candidate_pool = 50,
): Promise<BenchmarkTriggerResponse> {
  // #696 — `suite` default 'chunks' (production path; NER + IDF dahil)
  // #700 — Endpoint async background — anında "started" döner
  const qs = new URLSearchParams({
    golden,
    suite,
    top_k: String(top_k),
    candidate_pool: String(candidate_pool),
  });
  return apiFetch<BenchmarkTriggerResponse>(
    `/admin/rag/benchmark/run?${qs.toString()}`,
    { method: "POST" },
  );
}

// #700 — Background benchmark koşum durumu (polling)
export interface RagBenchmarkStatus {
  running: boolean;
  started_at: string | null;
  completed_at: string | null;  // #712 B4 — false-erken-aktifleşme önlemi
  triggered_by: string | null;
  suite: string | null;
  golden: string | null;
  error: string | null;
}

export async function ragBenchmarkStatus(): Promise<RagBenchmarkStatus> {
  return apiFetch<RagBenchmarkStatus>("/admin/rag/benchmark/status");
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

export async function ragCacheTelemetry(
  hours = 24,
): Promise<CacheTelemetryResponse> {
  return apiFetch<CacheTelemetryResponse>(
    `/admin/rag/cache-telemetry?hours=${hours}`,
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
  suite: "cards" | "chunks" | "production" = "production",
): Promise<InspectQueryResponse> {
  return apiFetch<InspectQueryResponse>("/admin/rag/inspect-query", {
    method: "POST",
    body: {
      query,
      top_k: topK,
      candidate_pool: candidatePool,
      use_planner: usePlanner,
      suite,
    },
  });
}

// #696 (B5) — NER pipeline mode telemetri
export interface RagNerStatsResponse {
  total: number;
  distribution: Record<string, number>;
  ratios: Record<string, number>;
  first_seen: string | null;
  last_seen: string | null;
  note: string;
}

export async function ragNerStats(): Promise<RagNerStatsResponse> {
  return apiFetch<RagNerStatsResponse>("/admin/rag/ner-stats");
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
// Admin Settings — extracted to ./api/admin/settings.ts (PR-7a-14)
// ===========================================================================
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/settings.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  AdminSettingItem,
  AdminSettingsListResponse,
} from "./api/admin/settings";
export {
  adminSettingReset,
  adminSettingUpdate,
  adminSettingsList,
} from "./api/admin/settings";

// ============================================================================
// Admin Media — extracted to ./api/admin/media.ts (PR-7a-8)
// ============================================================================
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/media.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  MediaImage,
  MediaListFilters,
  MediaListResponse,
  MediaStatsResponse,
  MediaStatus,
} from "./api/admin/media";
export {
  adminMediaStats,
  listAdminMedia,
  reprocessMedia,
} from "./api/admin/media";

// ============================================================================
// Admin /system — extracted to ./api/admin/system.ts (PR-7a-7)
// ============================================================================
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/system.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  BackupInfo,
  BucketInfo,
  ContaboInfo,
  CpuInfo,
  DiskInfo,
  MinioInfo,
  PostgresInfo,
  RamInfo,
  SystemHealthResponse,
  TableSize,
  VpsInfo,
} from "./api/admin/system";
export { adminSystemHealth } from "./api/admin/system";

// ============================================================================
// Admin disk panel (#570) — extracted to ./api/admin/disk.ts (PR-7a-2)
// ============================================================================
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/disk.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type {
  DiskBreakdownResponse,
  DiskCategory,
  DiskCleanupResponse,
} from "./api/admin/disk";
export { adminDiskBreakdown, adminDiskCleanup } from "./api/admin/disk";
