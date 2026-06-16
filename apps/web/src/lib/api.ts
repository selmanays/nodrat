/**
 * API client — Nodrat backend (FastAPI) ile iletişim.
 *
 * docs/engineering/api-contracts.md
 *
 * Authentication: access_token + refresh_token (JWT) localStorage'da
 * tutulur. Production'da httpOnly cookie yapacağız (#71 backlog).
 */

// Exported for streamResearchMessage raw-fetch SSE client (api/research.ts, PR-7a-19b).
// Value/logic unchanged.
export const API_BASE = (
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
// tamamen `api/admin/sources.ts`'te. `createConfig` 0-caller wrapper'ı dead-code
// cleanup PR ile silindi (backend endpoint dokunulmadı).
export type {
  SourceConfigPublic,
  ConfigListResponse,
} from "./api/admin/sources";
export {
  listConfigs,
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
// Fully extracted to ./api/research.ts (PR-7a-19a non-SSE + PR-7a-19b SSE client).
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
export type {
  ResearchConversationItem,
  ResearchConversationList,
  ResearchMessageSource,
  ResearchMessage,
  ResearchThread,
  MessageFeedbackResponse,
} from "./api/research";
export {
  listResearchConversations,
  createResearchConversation,
  getResearchConversation,
  archiveResearchConversation,
  flagResearchMessageHalu,
  recordResearchMessageAction,
  streamResearchMessage,
} from "./api/research";

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

// ---- Admin clusters (#1028) — extracted to ./api/admin/clusters.ts (PR-7a-17)
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
//
// Refs:
// - apps/web/src/lib/api/admin/clusters.ts — extracted module
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
export type { ClusterListItem, ClusterListResponse } from "./api/admin/clusters";
export { listClusters } from "./api/admin/clusters";

// ---- Admin trends (#1518/#1520/#1552) — entity-merkezli trend radarı (read-only)
export type {
  TrendDetailArticle,
  TrendDetailResponse,
  TrendDetailSource,
  TrendDetailVariant,
  TrendListItem,
  TrendListResponse,
  TrendSort,
  TrendSparkPoint,
  TrendState,
  TrendWindow,
} from "./api/admin/trends";
export { getTrendDetail, listTrends } from "./api/admin/trends";

// ---- Admin canonical entities (#1554) — merge/split/manuel alias yönetimi
export type {
  AliasRow,
  CanonicalDetailResponse,
  CanonicalEntityType,
  CanonicalListResponse,
  CanonicalRow,
} from "./api/admin/entities";
export {
  addAliases,
  createCanonical,
  getCanonical,
  listCanonical,
  mergeCanonical,
  removeAlias,
} from "./api/admin/entities";

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
  ResearchInterestItem,
  ResearchInterestsResponse,
  UserMePublic,
} from "./api/account";
export {
  deleteMe,
  exportMe,
  getMe,
  getMyResearchInterests,
  updateMe,
} from "./api/account";

// ============================================================================
// Admin RAG (Epic #189 — observability dashboard)
// ============================================================================

// Read-only observability — extracted to ./api/admin/rag.ts (PR-7a-18a, Part 1/2).
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
// Trigger/pipeline (ragBenchmarkRun/ragRaptorTrigger/ragInspectQuery) + ilgili
// interface'ler AŞAĞIDA INLINE; PR-7a-18b ile api/admin/rag.ts'e taşınacak.
export type {
  RagFeatureFlags,
  RagHealthCounts,
  RagLastEval,
  RagWarmUpInfo,
  RagHealthResponse,
  BenchmarkRunSummary,
  BenchmarkHistoryResponse,
  CitationStatsResponse,
  RerankStatsResponse,
  CacheCallTypeRow,
  CacheSegmentAvg,
  CacheTelemetryResponse,
  WeeklyClusterRow,
  RaptorClustersResponse,
  RagBenchmarkStatus,
  RagNerStatsResponse,
  PeriodMetrics,
  PipelineComparisonResponse,
  PipelineComparisonParams,
} from "./api/admin/rag";
export {
  ragHealth,
  ragBenchmarkHistory,
  ragBenchmarkStatus,
  ragCitationStats,
  ragRerankStats,
  ragCacheTelemetry,
  ragRaptorClusters,
  ragNerStats,
  ragPipelineComparison,
} from "./api/admin/rag";

// ---- Admin RAG triggers (#189) — extracted to ./api/admin/rag.ts (PR-7a-18b, Part 2/2).
// STATE-CHANGING / pipeline trigger: production smoke'da ASLA çağrılmaz.
// Re-exported below for backward-compat (`@/lib/api` caller path unchanged).
export type {
  BenchmarkTriggerResponse,
  RaptorTriggerResponse,
  InspectRow,
  InspectParentDocMerge,
  InspectPlannerInfo,
  InspectNerInfo,
  InspectTimeframeInfo,
  InspectSufficiencyInfo,
  InspectQueryResponse,
} from "./api/admin/rag";
export {
  ragBenchmarkRun,
  ragRaptorTrigger,
  ragInspectQuery,
} from "./api/admin/rag";

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
