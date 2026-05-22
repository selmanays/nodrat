/**
 * Frontend characterization safety-net bootstrap (T6 P7a PR-7a-0).
 *
 * Locks current behavior of `src/lib/api.ts` pure helpers BEFORE any split.
 * 5 minimal characterization tests = backend Phase 4 PR-A pattern (extractor
 * char) + Phase 6 PR-A (SSE helper char) for the frontend.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - apps/web/src/lib/api.ts — refactor hedefi (2041 LoC / 199 export / 60 caller)
 * - apps/api/tests/unit/test_research_stream_helpers.py — backend mirror pattern
 *
 * Scope (this PR):
 * - ApiException constructor invariant
 * - Token storage: set/get round-trip, clear semantics, SSR safety
 * - apiFetch: success path (parsed JSON return)
 *
 * Deferred (PR-7a-N):
 * - apiFetch 401 → refresh + retry path (complex async re-entry)
 * - apiFetch error → ApiException throw with detail extraction
 * - Component-level tests (no @testing-library/react installed yet)
 * - api.ts split (PR-7a-1 Public search extract starts after this PR merges)
 */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  ApiException,
  adminDiskBreakdown,
  adminDiskCleanup,
  adminMediaStats,
  adminSettingReset,
  adminSettingUpdate,
  adminSettingsList,
  adminSystemHealth,
  apiFetch,
  articleStats,
  clearTokens,
  dashboardHourly,
  dashboardProviderCalls,
  deleteMe,
  exportMe,
  getAccessToken,
  getAdminUser,
  getAdminUserStats,
  getArticle,
  getMe,
  getMyQuota,
  getRefreshToken,
  getTakedownRequest,
  listAdminMedia,
  listAdminUsers,
  listArticles,
  listAuditLog,
  listTakedownRequests,
  login,
  logout,
  publicSearch,
  register,
  reprocessArticle,
  reprocessMedia,
  requestVerifyResend,
  restoreAdminUser,
  setTokens,
  updateAdminUser,
  updateMe,
  updateTakedownRequest,
  getQueueOverview,
  listFailedJobs,
  retryFailedJob,
  bulkRetryFailedJobs,
  bulkResolveFailedJobs,
  listMaintenanceTasks,
  runMaintenanceNow,
  resolveFailedJob,
  listSources,
  getSource,
  createSource,
  activateSource,
  updateSource,
  testFeed,
  robotsCheck,
  testListing,
  sourceExtractionStats,
  listConfigs,
  createConfig,
  rollbackConfig,
  type AdminUserDetail,
  type AdminUserListResponse,
  type AdminUserStatsResponse,
  type ArticleListResponse,
  type ArticleStatsResponse,
  type AuditLogListResponse,
  type DashboardHourlyResponse,
  type DiskBreakdownResponse,
  type DiskCleanupResponse,
  type LoginPayload,
  type ExportResponse,
  type MediaListResponse,
  type MediaStatsResponse,
  type ProviderCallsRangeResponse,
  type PublicSearchResponse,
  type QuotaResponse,
  type UserMePublic,
  type RegisterPayload,
  type AdminSettingsListResponse,
  type SystemHealthResponse,
  type TakedownListResponse,
  type TokenResponse,
  type QueueOverviewResponse,
  type FailedJobListResponse,
  type BulkResponse,
  type MaintenanceListResponse,
  type SourcePublic,
  type FeedReportPublic,
  type RobotsReportPublic,
  type SelectorMap,
  type TestListingResponse,
  type SourceExtractionStats,
  type SourceConfigPublic,
  type ConfigListResponse,
} from "@/lib/api";

// ============================================================================
// Test fixtures
// ============================================================================

beforeEach(() => {
  // Her test öncesi localStorage temizliği — token storage testleri arasında
  // izolasyon (jsdom otomatik temizlemez).
  if (typeof window !== "undefined") {
    window.localStorage.clear();
  }
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ============================================================================
// ApiException — constructor + property invariant
// ============================================================================

describe("ApiException", () => {
  test("constructor sets status/code/detail + message from title", () => {
    const err = new ApiException({
      status: 404,
      code: "NOT_FOUND",
      title: "Kaynak bulunamadı",
      detail: "Detay açıklaması",
    });
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiException);
    expect(err.status).toBe(404);
    expect(err.code).toBe("NOT_FOUND");
    expect(err.detail).toBe("Detay açıklaması");
    expect(err.message).toBe("Kaynak bulunamadı");
  });
});

// ============================================================================
// Token storage — localStorage round-trip + SSR safety
// ============================================================================

describe("token storage helpers", () => {
  test("setTokens + getAccessToken/getRefreshToken round-trip", () => {
    setTokens("access-abc-123", "refresh-xyz-789");
    expect(getAccessToken()).toBe("access-abc-123");
    expect(getRefreshToken()).toBe("refresh-xyz-789");
  });

  test("clearTokens removes both access and refresh tokens", () => {
    setTokens("a", "b");
    expect(getAccessToken()).toBe("a");
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});

// ============================================================================
// apiFetch — success path (parsed JSON return)
// ============================================================================

describe("apiFetch", () => {
  test("success path returns parsed JSON body", async () => {
    const mockResponse = { hello: "world", count: 42 };
    // Mock global fetch — caller-wrap pattern (PR #1160 dersi):
    // production caller behavior'ı birebir taklit; gerçek HTTP yok.
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiFetch<typeof mockResponse>("/healthz", {
      skipAuth: true,
    });

    expect(result).toEqual(mockResponse);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test("204 No Content returns undefined (not parsed body)", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );

    const result = await apiFetch("/delete", { skipAuth: true });

    expect(result).toBeUndefined();
  });
});

// ============================================================================
// publicSearch — extracted to api/public.ts (PR-7a-1)
//
// Lock'lar:
// - Endpoint URL format: /public/search?q=<encoded>&limit=<n>
// - Query parameter encoding (Türkçe karakter, &, vb. URL-safe)
// - skipAuth=true → no Authorization header (anonymous endpoint)
// - Default limit=10 when omitted
// ============================================================================

describe("publicSearch (extracted to api/public.ts)", () => {
  test("calls /public/search with URL-encoded query + default limit=10", async () => {
    const mockResponse: PublicSearchResponse = {
      query: "Türkçe sorgu",
      total: 0,
      items: [],
      rate_limit_remaining: 100,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await publicSearch("Türkçe sorgu");

    expect(result).toEqual(mockResponse);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    // URL: encodeURIComponent("Türkçe sorgu") + default limit=10
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain(
      "/public/search?q=T%C3%BCrk%C3%A7e%20sorgu&limit=10",
    );
  });

  test("passes custom limit + skipAuth=true (no Authorization header)", async () => {
    setTokens("should-not-be-sent", "refresh-x");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          query: "test",
          total: 0,
          items: [],
          rate_limit_remaining: 50,
        } satisfies PublicSearchResponse),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await publicSearch("test", 25);

    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("&limit=25");
    // skipAuth=true → Authorization header set EDİLMEZ
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = (calledInit?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});

// ============================================================================
// adminDisk* — extracted to api/admin/disk.ts (PR-7a-2)
//
// Lock'lar:
// - adminDiskBreakdown → GET /admin/system/disk (no method override; auth)
// - adminDiskCleanup → POST /admin/system/disk/cleanup (method=POST)
// - Both admin endpoints → Authorization header set edilir (token varsa)
// ============================================================================

describe("adminDisk* (extracted to api/admin/disk.ts)", () => {
  test("adminDiskBreakdown calls GET /admin/system/disk with Authorization header", async () => {
    setTokens("admin-token-xyz", "refresh-x");
    const mockResponse: DiskBreakdownResponse = {
      total_bytes: 100_000_000_000,
      used_bytes: 50_000_000_000,
      free_bytes: 50_000_000_000,
      used_percent: 50,
      categories: [],
      docker_total_bytes: 0,
      reclaimable_bytes: 0,
      timestamp: "2026-05-21T14:00:00Z",
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminDiskBreakdown();

    expect(result).toEqual(mockResponse);
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("/admin/system/disk");
    // Method default GET (no explicit method override)
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(calledInit?.method).toBeUndefined();
    // Admin endpoint → Authorization header gönderilir
    const headers = (calledInit?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer admin-token-xyz");
  });

  test("adminDiskCleanup calls POST /admin/system/disk/cleanup", async () => {
    setTokens("admin-token-xyz", "refresh-x");
    const mockResponse: DiskCleanupResponse = {
      reclaimed_bytes: 1_000_000,
      items_deleted: 5,
      duration_seconds: 2.5,
      timestamp: "2026-05-21T14:00:00Z",
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminDiskCleanup();

    expect(result).toEqual(mockResponse);
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("/admin/system/disk/cleanup");
    // Method POST (state-changing)
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(calledInit?.method).toBe("POST");
  });
});

// ============================================================================
// login / register / logout — extracted to api/auth.ts (PR-7a-3)
//
// Lock'lar:
// - login: POST /auth/login + skipAuth=true + payload body
// - register: POST /auth/register + skipAuth=true + payload body
// - logout (refresh varsa): POST /auth/logout silent fail + clearTokens()
// - logout (refresh yoksa): backend call YOK, sadece clearTokens()
// ============================================================================

const SAMPLE_TOKEN_RESPONSE: TokenResponse = {
  access_token: "access-fake",
  refresh_token: "refresh-fake",
  expires_in: 3600,
  user: {
    id: "user-1",
    email: "test@example.com",
    full_name: "Test User",
    role: "user",
    tier: "free",
    locale: "tr",
    email_verified: false,
  },
};

describe("login / register / logout (extracted to api/auth.ts)", () => {
  test("login → POST /auth/login + skipAuth + payload body", async () => {
    const payload: LoginPayload = {
      email: "test@example.com",
      password: "p@ssw0rd!",
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(SAMPLE_TOKEN_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await login(payload);

    expect(result).toEqual(SAMPLE_TOKEN_RESPONSE);
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("/auth/login");
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(calledInit?.method).toBe("POST");
    expect(calledInit?.body).toBe(JSON.stringify(payload));
    // skipAuth=true → Authorization header set EDİLMEZ (anonymous endpoint)
    const headers = (calledInit?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  test("register → POST /auth/register + skipAuth + KVKK payload body", async () => {
    const payload: RegisterPayload = {
      email: "new@example.com",
      password: "Yeni#2026",
      full_name: "Yeni Kullanıcı",
      kvkk_acknowledgment: true,
      data_processing_consent: true,
      foreign_transfer_consent: true,
      age_18_plus: true,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(SAMPLE_TOKEN_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await register(payload);

    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("/auth/register");
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(calledInit?.method).toBe("POST");
    // KVKK fields body içinde
    const parsedBody = JSON.parse(String(calledInit?.body ?? "null"));
    expect(parsedBody.kvkk_acknowledgment).toBe(true);
    expect(parsedBody.data_processing_consent).toBe(true);
    expect(parsedBody.foreign_transfer_consent).toBe(true);
    expect(parsedBody.age_18_plus).toBe(true);
    // skipAuth=true → Authorization header yok
    const headers = (calledInit?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  test("logout with refresh token → POST /auth/logout + clearTokens", async () => {
    setTokens("access-x", "refresh-y");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );

    await logout();

    // POST /auth/logout çağrıldı
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("/auth/logout");
    const calledInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(calledInit?.method).toBe("POST");
    // Body refresh_token içerir
    const parsedBody = JSON.parse(String(calledInit?.body ?? "null"));
    expect(parsedBody.refresh_token).toBe("refresh-y");
    // Token storage TEMİZLENDİ
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  test("logout without refresh token → only clearTokens (no backend call)", async () => {
    // Token yok
    clearTokens();
    const fetchSpy = vi.spyOn(global, "fetch");

    await logout();

    // Backend call YAPILMADI
    expect(fetchSpy).not.toHaveBeenCalled();
    // clearTokens hâlâ çalıştı (zaten boştu, ama side-effect lock'lu)
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});

describe("requestVerifyResend (extracted to api/auth.ts, PR-7a-4)", () => {
  test("POSTs /auth/verify-resend with email body + skipAuth (no Authorization header)", async () => {
    // Token mevcut olsa bile gönderilmemeli (skipAuth=true).
    setTokens("ACCESS_TOKEN_SHOULD_NOT_LEAK", "REFRESH_TOKEN_SHOULD_NOT_LEAK");

    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, detail: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await requestVerifyResend("user@example.com");

    expect(result).toEqual({ ok: true, detail: null });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain("/auth/verify-resend");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ email: "user@example.com" }),
    );
    // skipAuth=true → Authorization header EKLENMEDİ
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers["Content-Type"]).toBe("application/json");
  });

  test("parses { ok, detail } response shape with detail string", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          detail: "Bir dakika sonra tekrar deneyiniz.",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await requestVerifyResend("user@example.com");

    expect(result.ok).toBe(true);
    expect(result.detail).toBe("Bir dakika sonra tekrar deneyiniz.");
  });

  test("429 rate-limit propagates ApiException (apiFetch default error handling)", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "rate_limit_exceeded",
          title: "Çok sık istek",
          detail: "Yeniden gönderim için bir süre bekleyin.",
        }),
        {
          status: 429,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(requestVerifyResend("user@example.com")).rejects.toThrow(
      ApiException,
    );
  });
});

describe("admin users (extracted to api/admin/users.ts, PR-7a-5)", () => {
  test("listAdminUsers with filters produces correct query string (null/undefined skipped)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: AdminUserListResponse = {
      data: [],
      total: 0,
      limit: 50,
      offset: 0,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listAdminUsers({
      role: "admin",
      tier: "pro",
      is_active: true,
      q: "ali",
      limit: 25,
      offset: 50,
      // null/undefined skip davranışı (buildQuery internal helper)
      deleted: undefined,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/users?");
    expect(urlStr).toContain("role=admin");
    expect(urlStr).toContain("tier=pro");
    expect(urlStr).toContain("is_active=true");
    expect(urlStr).toContain("q=ali");
    expect(urlStr).toContain("limit=25");
    expect(urlStr).toContain("offset=50");
    // null/undefined value query string'e dahil edilmedi (buildQuery davranışı)
    expect(urlStr).not.toContain("deleted=");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("listAdminUsers without filters omits query string entirely", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, limit: 50, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listAdminUsers();

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/users");
    // filters yoksa "?" eklenmemeli (buildQuery boş string döner)
    expect(urlStr.endsWith("/admin/users")).toBe(true);
  });

  test("getAdminUser(id) calls GET /admin/users/{id}", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const detail: Partial<AdminUserDetail> = {
      id: "uid-123",
      email: "u@example.com",
      role: "user",
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(detail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getAdminUser("uid-123");

    expect(result.id).toBe("uid-123");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/users/uid-123");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("getAdminUserStats calls GET /admin/users/stats", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const stats: AdminUserStatsResponse = {
      total: 100,
      active: 80,
      inactive: 15,
      deleted: 5,
      email_verified: 75,
      by_tier: [{ tier: "free", count: 90 }],
      by_role: [{ role: "user", count: 95 }],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(stats), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getAdminUserStats();

    expect(result.total).toBe(100);
    expect(result.by_tier).toHaveLength(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/users/stats");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("updateAdminUser(id, payload) calls PATCH /admin/users/{id} with body", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "uid-7" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await updateAdminUser("uid-7", {
      role: "admin",
      tier: "pro",
      is_active: false,
      note: "Promoting to admin",
    });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/users/uid-7");
    expect((init as RequestInit).method).toBe("PATCH");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({
        role: "admin",
        tier: "pro",
        is_active: false,
        note: "Promoting to admin",
      }),
    );
  });

  test("restoreAdminUser(id, note) calls POST /admin/users/{id}/restore with {note}", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "uid-9" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await restoreAdminUser("uid-9", "Reactivation per support ticket");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/users/uid-9/restore");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ note: "Reactivation per support ticket" }),
    );
  });
});

describe("admin audit (extracted to api/admin/audit.ts, PR-7a-6)", () => {
  test("listAuditLog with filters produces correct query string + Authorization header", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: AuditLogListResponse = {
      data: [],
      total: 0,
      limit: 50,
      offset: 0,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listAuditLog({
      action: "user_update",
      actor_id: "uid-actor-123",
      target_type: "user",
      target_id: "uid-target-456",
      date_from: "2026-05-01T00:00:00Z",
      date_to: "2026-05-21T23:59:59Z",
      limit: 25,
      offset: 50,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/audit?");
    expect(urlStr).toContain("action=user_update");
    expect(urlStr).toContain("actor_id=uid-actor-123");
    expect(urlStr).toContain("target_type=user");
    expect(urlStr).toContain("target_id=uid-target-456");
    // ISO timestamps URL-encoded (`:` → `%3A`)
    expect(urlStr).toContain("date_from=2026-05-01T00%3A00%3A00Z");
    expect(urlStr).toContain("date_to=2026-05-21T23%3A59%3A59Z");
    expect(urlStr).toContain("limit=25");
    expect(urlStr).toContain("offset=50");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("listAuditLog without filters omits query string entirely", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, limit: 50, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listAuditLog();

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/audit");
    // filters yoksa "?" eklenmemeli (buildQuery boş string döner)
    expect(urlStr.endsWith("/admin/audit")).toBe(true);
  });

  test("listAuditLog skips null/undefined filter values (buildQuery semantics)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, limit: 50, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listAuditLog({
      action: "login",
      actor_id: undefined,
      // @ts-expect-error — testing runtime null skip (filter type forbids null but buildQuery handles it)
      target_type: null,
      limit: 10,
    });

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    // Tutulan field'lar var
    expect(urlStr).toContain("action=login");
    expect(urlStr).toContain("limit=10");
    // null/undefined skip kilitlendi (buildQuery semantics)
    expect(urlStr).not.toContain("actor_id");
    expect(urlStr).not.toContain("target_type");
  });

  test("listAuditLog parses response shape correctly", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: AuditLogListResponse = {
      data: [
        {
          id: "audit-1",
          actor_id: "uid-1",
          actor_email: "admin@example.com",
          action: "user_update",
          target_type: "user",
          target_id: "uid-2",
          event_metadata: { field: "role", new_value: "admin" },
          ip_address: "10.0.0.1",
          user_agent: "Mozilla/5.0",
          created_at: "2026-05-21T10:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await listAuditLog();

    expect(result.data).toHaveLength(1);
    expect(result.data[0].id).toBe("audit-1");
    expect(result.data[0].action).toBe("user_update");
    expect(result.data[0].event_metadata).toEqual({
      field: "role",
      new_value: "admin",
    });
    expect(result.total).toBe(1);
  });
});

describe("admin system health (extracted to api/admin/system.ts, PR-7a-7)", () => {
  test("adminSystemHealth calls GET /admin/system/health with auth header", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: SystemHealthResponse = {
      vps: {
        hostname: "vps-prod",
        cpu: {
          cores: 8,
          load_1m: 1.5,
          load_5m: 1.2,
          load_15m: 0.9,
          usage_pct: 42.5,
        },
        ram: { total_mb: 16384, used_mb: 8192, free_mb: 8192, used_pct: 50.0 },
        disk: { total_gb: 500, used_gb: 200, free_gb: 300, used_pct: 40.0 },
      },
      postgres: { db_size_gb: 12.5, tables: [] },
      minio: { endpoint: "minio:9000", buckets: [] },
      contabo_os: {
        endpoint: "contabo",
        bucket: "nodrat",
        size_gb: 100,
        object_count: 5000,
        by_prefix: {},
      },
      backups: {
        last_snapshot_at: "2026-05-21T00:00:00Z",
        last_snapshot_age_h: 12,
        snapshot_count: 7,
        total_size_gb: 50,
        last_check_status: "ok",
      },
      timestamp: "2026-05-21T12:00:00Z",
      cache_age_seconds: 30,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminSystemHealth();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/system/health");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
    expect(result.vps.hostname).toBe("vps-prod");
    expect(result.cache_age_seconds).toBe(30);
  });

  test("adminSystemHealth parses nested VPS/Postgres/MinIO/Contabo/Backup response shape", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: SystemHealthResponse = {
      vps: {
        hostname: "host-a",
        cpu: {
          cores: 4,
          load_1m: 0.5,
          load_5m: 0.4,
          load_15m: 0.3,
          usage_pct: 25.0,
        },
        ram: { total_mb: 8192, used_mb: 4096, free_mb: 4096, used_pct: 50.0 },
        disk: { total_gb: 250, used_gb: 100, free_gb: 150, used_pct: 40.0 },
      },
      postgres: {
        db_size_gb: 5.0,
        tables: [
          { name: "articles", size_mb: 1024, row_count: 50000, index_size_mb: 256 },
          { name: "chunks", size_mb: 2048, row_count: 250000, index_size_mb: 512 },
        ],
      },
      minio: {
        endpoint: "minio:9000",
        buckets: [
          { name: "media", size_gb: 25, object_count: 10000 },
        ],
      },
      contabo_os: {
        endpoint: "https://eu2.contabostorage.com",
        bucket: "nodrat-prod",
        size_gb: 75,
        object_count: 15000,
        by_prefix: {
          "articles/": { name: "articles", size_gb: 50, object_count: 10000 },
          "media/": { name: "media", size_gb: 25, object_count: 5000 },
        },
      },
      backups: {
        last_snapshot_at: null,
        last_snapshot_age_h: null,
        snapshot_count: 0,
        total_size_gb: 0,
        last_check_status: "pending",
      },
      timestamp: "2026-05-21T15:00:00Z",
      cache_age_seconds: 0,
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminSystemHealth();

    // Nested VPS shape
    expect(result.vps.cpu.cores).toBe(4);
    expect(result.vps.ram.total_mb).toBe(8192);
    // Postgres tables array
    expect(result.postgres.tables).toHaveLength(2);
    expect(result.postgres.tables[0].name).toBe("articles");
    // MinIO buckets nested
    expect(result.minio.buckets[0].size_gb).toBe(25);
    // Contabo by_prefix Record<string, BucketInfo>
    expect(result.contabo_os.by_prefix["articles/"].size_gb).toBe(50);
    expect(result.contabo_os.by_prefix["media/"].object_count).toBe(5000);
    // Backups nullable fields
    expect(result.backups.last_snapshot_at).toBeNull();
    expect(result.backups.last_snapshot_age_h).toBeNull();
    expect(result.backups.last_check_status).toBe("pending");
  });

  test("adminSystemHealth handles backups status string variants", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    // Backup last_check_status field is a free-form string; backend may return
    // "ok" / "warning" / "error" / "pending" — locking the type-only contract
    // (string, not enum). This protects against future backend changes that
    // add a new status without breaking the frontend type.
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          vps: {
            hostname: "h",
            cpu: { cores: 1, load_1m: 0, load_5m: 0, load_15m: 0, usage_pct: 0 },
            ram: { total_mb: 0, used_mb: 0, free_mb: 0, used_pct: 0 },
            disk: { total_gb: 0, used_gb: 0, free_gb: 0, used_pct: 0 },
          },
          postgres: { db_size_gb: 0, tables: [] },
          minio: { endpoint: "", buckets: [] },
          contabo_os: {
            endpoint: "",
            bucket: "",
            size_gb: 0,
            object_count: 0,
            by_prefix: {},
          },
          backups: {
            last_snapshot_at: "2026-05-20T00:00:00Z",
            last_snapshot_age_h: 36,
            snapshot_count: 5,
            total_size_gb: 25,
            last_check_status: "warning_age_threshold_exceeded",
          },
          timestamp: "2026-05-21T15:00:00Z",
          cache_age_seconds: 60,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await adminSystemHealth();
    // String contract preserved (free-form, not enum)
    expect(typeof result.backups.last_check_status).toBe("string");
    expect(result.backups.last_check_status).toBe(
      "warning_age_threshold_exceeded",
    );
  });
});

describe("admin media (extracted to api/admin/media.ts, PR-7a-8)", () => {
  test("listAdminMedia with filters produces correct query string (null/undefined skipped)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: MediaListResponse = {
      data: [],
      total: 0,
      limit: 50,
      offset: 0,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listAdminMedia({
      source_id: "src-123",
      status: "processed",
      date_from: "2026-05-01",
      date_to: "2026-05-21",
      limit: 25,
      offset: 50,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/media?");
    expect(urlStr).toContain("source_id=src-123");
    expect(urlStr).toContain("status=processed");
    expect(urlStr).toContain("date_from=2026-05-01");
    expect(urlStr).toContain("date_to=2026-05-21");
    expect(urlStr).toContain("limit=25");
    expect(urlStr).toContain("offset=50");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("listAdminMedia without filters omits query string entirely", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, limit: 50, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listAdminMedia();

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/media");
    // filters yoksa "?" eklenmemeli (buildQuery boş string döner)
    expect(urlStr.endsWith("/admin/media")).toBe(true);
  });

  test("adminMediaStats calls GET /admin/media/stats", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const stats: MediaStatsResponse = {
      total: 1000,
      processed: 800,
      failed: 50,
      pending: 100,
      skipped: 50,
      last_24h_processed: 120,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(stats), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminMediaStats();

    expect(result.total).toBe(1000);
    expect(result.last_24h_processed).toBe(120);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/media/stats");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("reprocessMedia(id) calls POST /admin/media/{id}/reprocess with empty body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real VLM reprocess
    // is triggered. Production smoke NEVER calls reprocessMedia (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "img-7", status: "pending" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await reprocessMedia("img-7");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/media/img-7/reprocess");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify({}));
  });
});

describe("admin legal (extracted to api/admin/legal.ts, PR-7a-10)", () => {
  test("listTakedownRequests with filters produces correct query string (null/undefined skipped)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: TakedownListResponse = {
      data: [],
      total: 0,
      overdue_count: 0,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listTakedownRequests({
      request_type: "takedown",
      status: "investigating",
      only_overdue: true,
      limit: 25,
      offset: 50,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/legal/requests?");
    expect(urlStr).toContain("request_type=takedown");
    expect(urlStr).toContain("status=investigating");
    expect(urlStr).toContain("only_overdue=true");
    expect(urlStr).toContain("limit=25");
    expect(urlStr).toContain("offset=50");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("listTakedownRequests without filters omits query string entirely", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, overdue_count: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listTakedownRequests();

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/legal/requests");
    // filters yoksa "?" eklenmemeli (buildQuery boş string döner)
    expect(urlStr.endsWith("/admin/legal/requests")).toBe(true);
  });

  test("getTakedownRequest(ticketId) calls GET /admin/legal/requests/{ticketId}", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ id: "uuid-1", ticket_id: "TKT-001", overdue: false }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await getTakedownRequest("TKT-001");

    expect(result.ticket_id).toBe("TKT-001");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/legal/requests/TKT-001");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("updateTakedownRequest(ticketId, payload) calls PATCH with body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real legal request
    // is mutated. Production smoke NEVER calls updateTakedownRequest (legal
    // compliance / state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ id: "uuid-1", ticket_id: "TKT-001", status: "resolved" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await updateTakedownRequest("TKT-001", {
      status: "resolved",
      action_taken: "Content removed",
      assign_to_self: true,
    });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/legal/requests/TKT-001");
    expect((init as RequestInit).method).toBe("PATCH");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({
        status: "resolved",
        action_taken: "Content removed",
        assign_to_self: true,
      }),
    );
  });
});

describe("admin articles (extracted to api/admin/articles.ts, PR-7a-11)", () => {
  test("listArticles with filters produces correct query string (null/undefined skipped)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: ArticleListResponse = {
      data: [],
      total: 0,
      limit: 50,
      offset: 0,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listArticles({
      source_id: "src-1",
      status: "extracted",
      q: "deprem",
      limit: 25,
      offset: 50,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/articles?");
    expect(urlStr).toContain("source_id=src-1");
    expect(urlStr).toContain("status=extracted");
    expect(urlStr).toContain("q=deprem");
    expect(urlStr).toContain("limit=25");
    expect(urlStr).toContain("offset=50");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("listArticles without filters omits query string entirely", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [], total: 0, limit: 50, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await listArticles();

    const [url] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/articles");
    // filters yoksa "?" eklenmemeli (buildQuery boş string döner)
    expect(urlStr.endsWith("/admin/articles")).toBe(true);
  });

  test("articleStats calls GET /admin/articles/stats", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const stats: ArticleStatsResponse = {
      by_status: [{ status: "extracted", count: 900 }],
      total: 1000,
      by_source: [{ name: "Source A", slug: "source-a", count: 500 }],
      embedded_count: 850,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(stats), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await articleStats();

    expect(result.total).toBe(1000);
    expect(result.embedded_count).toBe(850);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/articles/stats");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("dashboardHourly calls GET /admin/dashboard/hourly", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: DashboardHourlyResponse = {
      articles: [{ hour: "2026-05-21T10:00:00Z", count: 5 }],
      jobs: [],
      generations: [],
      provider_calls: [],
      provider_calls_by_provider: [],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await dashboardHourly();

    expect(result.articles).toHaveLength(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/dashboard/hourly");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("dashboardProviderCalls calls GET /admin/dashboard/provider-calls with ?period=", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: ProviderCallsRangeResponse = {
      period: "30d",
      bucket: "day",
      series: [],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await dashboardProviderCalls("30d");

    expect(result.period).toBe("30d");
    const [url, init] = fetchSpy.mock.calls[0];
    // inline ?period= preserved (buildQuery DEĞİL)
    expect(String(url)).toContain("/admin/dashboard/provider-calls?period=30d");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("getArticle(id) calls GET /admin/articles/{id}", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ id: "art-7", title: "Test", images: [] }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await getArticle("art-7");

    expect(result.id).toBe("art-7");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/articles/art-7");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("reprocessArticle(id) calls POST /admin/articles/{id}/reprocess with empty body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real reprocess task
    // is dispatched. Production smoke NEVER calls reprocessArticle (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          article_id: "art-7",
          status: "queued",
          dispatched_task: "tasks.articles.reprocess",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await reprocessArticle("art-7");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/articles/art-7/reprocess");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify({}));
  });
});

describe("getMyQuota (extracted to api/account.ts, PR-7a-12)", () => {
  test("getMyQuota calls GET /app/quota with auth header", async () => {
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          tier: "free",
          limit: 10,
          used: 3,
          remaining: 7,
          reset_at: "2026-05-22T12:00:00Z",
          window_seconds: 86400,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await getMyQuota();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/app/quota");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer USER_ACCESS");
    expect(result.tier).toBe("free");
    expect(result.remaining).toBe(7);
  });

  test("getMyQuota parses QuotaResponse shape", async () => {
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fixture: QuotaResponse = {
      tier: "pro",
      limit: 1000,
      used: 250,
      remaining: 750,
      reset_at: "2026-05-23T00:00:00Z",
      window_seconds: 2592000,
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getMyQuota();

    expect(result.tier).toBe("pro");
    expect(result.limit).toBe(1000);
    expect(result.used).toBe(250);
    expect(result.remaining).toBe(750);
    expect(result.reset_at).toBe("2026-05-23T00:00:00Z");
    expect(result.window_seconds).toBe(2592000);
  });
});

describe("account /app/me (extracted to api/account.ts, PR-7a-13)", () => {
  test("getMe calls GET /app/me with auth header", async () => {
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ id: "u-1", email: "u@example.com", role: "user" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await getMe();

    expect(result.id).toBe("u-1");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/app/me");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer USER_ACCESS");
  });

  test("getMe parses UserMePublic shape (KVKK consent timestamps)", async () => {
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fixture: UserMePublic = {
      id: "u-2",
      email: "kvkk@example.com",
      full_name: "Ada Lovelace",
      role: "user",
      tier: "pro",
      locale: "tr",
      email_verified: true,
      is_active: true,
      totp_enabled: false,
      kvkk_acknowledgment_at: "2026-05-01T00:00:00Z",
      data_processing_consent_at: "2026-05-01T00:00:00Z",
      foreign_transfer_consent_at: null,
      marketing_consent_at: null,
      last_login_at: "2026-05-21T10:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getMe();

    expect(result.tier).toBe("pro");
    expect(result.email_verified).toBe(true);
    expect(result.kvkk_acknowledgment_at).toBe("2026-05-01T00:00:00Z");
    expect(result.foreign_transfer_consent_at).toBeNull();
    expect(result.marketing_consent_at).toBeNull();
  });

  test("updateMe calls PATCH /app/me with body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real profile mutation
    // is triggered. Production smoke NEVER calls updateMe (state-changing).
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "u-1", full_name: "New Name" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await updateMe({ full_name: "New Name", marketing_consent: true });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/app/me");
    expect((init as RequestInit).method).toBe("PATCH");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ full_name: "New Name", marketing_consent: true }),
    );
  });

  test("exportMe calls GET /app/me/export and parses ExportResponse shape", async () => {
    // NOTE: This test only exercises the mocked fetch — no real PII/KVKK export
    // is generated. Production smoke NEVER calls exportMe (PII data dump).
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fixture: ExportResponse = {
      exported_at: "2026-05-22T00:00:00Z",
      user: { id: "u-1", email: "u@example.com" },
      generations: [],
      saved_generations: [],
      usage_events: [{ event: "login" }],
      sessions: [{ id: "sess-1" }],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await exportMe();

    expect(result.exported_at).toBe("2026-05-22T00:00:00Z");
    expect(result.usage_events).toHaveLength(1);
    expect(result.sessions).toHaveLength(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/app/me/export");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("deleteMe calls DELETE /app/me with confirmation + reason body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real account deletion
    // is triggered. Production smoke NEVER calls deleteMe (account deletion DANGER).
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "scheduled", deletion_at: "2026-06-21T00:00:00Z" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await deleteMe("HESABIMI SIL", "no longer needed");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/app/me");
    expect((init as RequestInit).method).toBe("DELETE");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ confirmation: "HESABIMI SIL", reason: "no longer needed" }),
    );
  });

  test("deleteMe sends reason: null when reason is undefined", async () => {
    setTokens("USER_ACCESS", "USER_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "scheduled", deletion_at: "2026-06-21T00:00:00Z" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await deleteMe("HESABIMI SIL");

    const [, init] = fetchSpy.mock.calls[0];
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ confirmation: "HESABIMI SIL", reason: null }),
    );
  });
});

describe("admin settings (extracted to api/admin/settings.ts, PR-7a-14)", () => {
  test("adminSettingsList calls GET /admin/settings (+ ?group= when given)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [], groups: ["rag", "llm"] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await adminSettingsList("rag");

    const [url, init] = fetchSpy.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain("/admin/settings?group=rag");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("adminSettingsList without group omits query string", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: AdminSettingsListResponse = {
      data: [
        {
          key: "rag.top_k",
          value: 10,
          default: 8,
          type: "int",
          group: "rag",
          description: "Retrieval top-k",
          min_value: 1,
          max_value: 50,
          allowed_values: null,
          requires_restart: false,
          is_overridden: true,
          updated_at: "2026-05-21T10:00:00Z",
          updated_by: "admin@example.com",
        },
      ],
      groups: ["rag"],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await adminSettingsList();

    const [url] = fetchSpy.mock.calls[0];
    expect(String(url).endsWith("/admin/settings")).toBe(true);
    // response shape parse
    expect(result.data[0].key).toBe("rag.top_k");
    expect(result.data[0].is_overridden).toBe(true);
    expect(result.groups).toEqual(["rag"]);
  });

  test("adminSettingUpdate calls PUT /admin/settings/{key} with {value} body", async () => {
    // NOTE: This test only exercises the mocked fetch — no real runtime config
    // mutation. Production smoke NEVER calls adminSettingUpdate (runtime config).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ key: "rag.top_k", value: 12 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await adminSettingUpdate("rag.top_k", 12);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/settings/rag.top_k");
    expect((init as RequestInit).method).toBe("PUT");
    expect((init as RequestInit).body).toBe(JSON.stringify({ value: 12 }));
  });

  test("adminSettingReset calls DELETE /admin/settings/{key} (reset to default)", async () => {
    // NOTE: This test only exercises the mocked fetch — no real runtime config
    // reset. Production smoke NEVER calls adminSettingReset (runtime config reset).
    // Method is DELETE (resets override to code default), preserved verbatim.
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ key: "rag.top_k", value: 8, is_overridden: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await adminSettingReset("rag.top_k");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/settings/rag.top_k");
    expect((init as RequestInit).method).toBe("DELETE");
  });
});

describe("admin queue (extracted to api/admin/queue.ts, PR-7a-15)", () => {
  test("getQueueOverview calls GET /admin/queue/overview (+ auth + shape)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: QueueOverviewResponse = {
      queues: [
        {
          name: "rag",
          queued_count: 3,
          running_count: 1,
          succeeded_count_24h: 120,
          failed_count_24h: 2,
        },
      ],
      failed_jobs_unresolved: 5,
      worker_count: 4,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getQueueOverview();

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/overview");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
    // response shape parse
    expect(result.queues[0].name).toBe("rag");
    expect(result.failed_jobs_unresolved).toBe(5);
  });

  test("listFailedJobs encodes filters into query string", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: FailedJobListResponse = { data: [], total: 0 };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listFailedJobs({
      job_type: "embedding",
      unresolved_only: true,
      limit: 20,
    });

    const urlStr = String(fetchSpy.mock.calls[0][0]);
    expect(urlStr).toContain("/admin/queue/failed?");
    expect(urlStr).toContain("job_type=embedding");
    expect(urlStr).toContain("unresolved_only=true");
    expect(urlStr).toContain("limit=20");
  });

  test("listFailedJobs without filters omits the query string (no '?')", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [], total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listFailedJobs();

    const urlStr = String(fetchSpy.mock.calls[0][0]);
    expect(urlStr.endsWith("/admin/queue/failed")).toBe(true);
    expect(urlStr).not.toContain("?");
  });

  test("listMaintenanceTasks calls GET /admin/queue/maintenance (+ shape)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: MaintenanceListResponse = {
      tasks: [
        {
          task_name: "cleanup_orphans",
          label: "Cleanup orphan rows",
          pipeline: "maintenance",
          interval_human: "daily",
          queue: "maintenance",
          last_run: null,
        },
      ],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await listMaintenanceTasks();

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/maintenance");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    // response shape parse
    expect(result.tasks[0].task_name).toBe("cleanup_orphans");
    expect(result.tasks[0].last_run).toBeNull();
  });

  test("retryFailedJob calls POST /admin/queue/jobs/{id}/retry", async () => {
    // NOTE: mocked fetch only — re-enqueues a Celery job in production.
    // Production smoke NEVER calls retryFailedJob (manual job trigger).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ new_job_id: "job-2", scheduled_at: "2026-05-22T10:00:00Z" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await retryFailedJob("failed-123");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/jobs/failed-123/retry");
    expect((init as RequestInit).method).toBe("POST");
  });

  test("bulkRetryFailedJobs calls POST /admin/queue/failed/bulk-retry with {ids}", async () => {
    // NOTE: mocked fetch only — bulk re-enqueue in production.
    // Production smoke NEVER calls bulkRetryFailedJobs (manual job trigger).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: BulkResponse = { succeeded: 2, failed: 0, results: [] };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await bulkRetryFailedJobs(["a", "b"]);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/failed/bulk-retry");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify({ ids: ["a", "b"] }));
  });

  test("bulkResolveFailedJobs calls POST /admin/queue/failed/bulk-resolve with {ids, note}", async () => {
    // NOTE: mocked fetch only — marks jobs resolved (DB write) in production.
    // Production smoke NEVER calls bulkResolveFailedJobs (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ succeeded: 1, failed: 0, results: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await bulkResolveFailedJobs(["x"], "manual review");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/failed/bulk-resolve");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ ids: ["x"], note: "manual review" }),
    );
  });

  test("runMaintenanceNow calls POST /admin/queue/maintenance/{name}/run-now (encoded)", async () => {
    // NOTE: mocked fetch only — runMaintenanceNow is a MANUAL MAINTENANCE TASK
    // TRIGGER. Production smoke NEVER calls it (no maintenance task triggered).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          task_name: "cleanup orphans",
          celery_task_id: "ct-1",
          triggered_at: "2026-05-22T10:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await runMaintenanceNow("cleanup orphans");

    const [url, init] = fetchSpy.mock.calls[0];
    // encodeURIComponent → space becomes %20
    expect(String(url)).toContain("/admin/queue/maintenance/cleanup%20orphans/run-now");
    expect((init as RequestInit).method).toBe("POST");
  });

  test("resolveFailedJob calls DELETE /admin/queue/failed/{id} with {note}", async () => {
    // NOTE: mocked fetch only — marks a job resolved (DB write) in production.
    // Production smoke NEVER calls resolveFailedJob (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    await resolveFailedJob("failed-999", "duplicate");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/queue/failed/failed-999");
    expect((init as RequestInit).method).toBe("DELETE");
    expect((init as RequestInit).body).toBe(JSON.stringify({ note: "duplicate" }));
  });
});

describe("admin sources core (extracted to api/admin/sources.ts, PR-7a-16a)", () => {
  test("listSources encodes filters into query string", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listSources({ is_active: true, type: "rss", limit: 10 });

    const urlStr = String(fetchSpy.mock.calls[0][0]);
    expect(urlStr).toContain("/admin/sources?");
    expect(urlStr).toContain("is_active=true");
    expect(urlStr).toContain("type=rss");
    expect(urlStr).toContain("limit=10");
  });

  test("listSources without filters omits the query string (no '?')", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listSources();

    const urlStr = String(fetchSpy.mock.calls[0][0]);
    expect(urlStr.endsWith("/admin/sources")).toBe(true);
    expect(urlStr).not.toContain("?");
  });

  test("getSource calls GET /admin/sources/{id} (+ auth + shape)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture = {
      id: "src-1",
      name: "Evrensel",
      slug: "evrensel",
      domain: "evrensel.net",
      type: "rss",
      base_url: "https://evrensel.net",
      language: "tr",
      country: "TR",
      category: null,
      reliability_score: 0.8,
      is_active: true,
      crawl_interval_minutes: 30,
      robots_txt_compliant: true,
      tos_acknowledged: true,
      realtime_enabled: false,
      polling_tier: "normal",
      would_be_tier: null,
      tier_changed_at: null,
      tier_metadata: null,
      consecutive_unchanged: 0,
    } satisfies SourcePublic;
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getSource("src-1");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
    expect(result.slug).toBe("evrensel");
    expect(result.polling_tier).toBe("normal");
  });

  test("createSource calls POST /admin/sources with payload body", async () => {
    // NOTE: mocked fetch only — creates a source in production.
    // Production smoke NEVER calls createSource (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "src-2" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const payload = {
      name: "Yeni Kaynak",
      slug: "yeni-kaynak",
      domain: "example.com",
      type: "rss" as const,
      base_url: "https://example.com",
    };
    await createSource(payload);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify(payload));
  });

  test("activateSource calls POST /admin/sources/{id}/activate with checklist body", async () => {
    // NOTE: mocked fetch only — activates a source (enables crawling) in production.
    // Production smoke NEVER calls activateSource (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "src-1", is_active: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const payload = {
      checklist: {
        robots_txt_checked: true,
        not_paywalled: true,
        tos_allows_scraping: true,
        publicly_accessible: true,
        commercial_risk_assessed: true,
      },
      note: "ok",
    };
    await activateSource("src-1", payload);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/activate");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify(payload));
  });

  test("updateSource calls PATCH /admin/sources/{id} with payload body", async () => {
    // NOTE: mocked fetch only — mutates a source (DB write) in production.
    // Production smoke NEVER calls updateSource (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "src-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const payload = { crawl_interval_minutes: 60, realtime_enabled: true };
    await updateSource("src-1", payload);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1");
    expect((init as RequestInit).method).toBe("PATCH");
    expect((init as RequestInit).body).toBe(JSON.stringify(payload));
  });

  test("testFeed calls POST /admin/sources/test-feed with {feed_url} body", async () => {
    // NOTE: mocked fetch only — triggers an OUTBOUND feed fetch in production.
    // Production smoke NEVER calls testFeed (outbound external fetch).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture = {
      feed_url: "https://example.com/feed",
      fetched: true,
      status_code: 200,
      error: null,
      feed_title: "Example",
      feed_description: "",
      feed_language: "tr",
      item_count: 3,
      sample_items: [],
    } satisfies FeedReportPublic;
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await testFeed("https://example.com/feed");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/test-feed");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ feed_url: "https://example.com/feed" }),
    );
  });

  test("robotsCheck calls GET /admin/sources/{id}/robots-check", async () => {
    // NOTE: mocked fetch only — triggers an OUTBOUND robots.txt fetch in production.
    // Production smoke NEVER calls robotsCheck (outbound external fetch).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture = {
      domain: "example.com",
      robots_url: "https://example.com/robots.txt",
      fetched: true,
      status_code: 200,
      base_url_allowed: true,
      crawl_delay_sec: 0,
      sitemaps: [],
      error: null,
    } satisfies RobotsReportPublic;
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await robotsCheck("src-1");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/robots-check");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    expect(result.base_url_allowed).toBe(true);
  });
});

describe("admin sources selector test (extracted to api/admin/sources.ts, PR-7a-16b)", () => {
  test("testListing calls POST /admin/sources/{id}/test-listing (+ auth)", async () => {
    // NOTE: mocked fetch only — testListing triggers an OUTBOUND URL fetch+parse
    // in production. Production smoke NEVER calls testListing (outbound external).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: TestListingResponse = {
      url: "https://example.com/list",
      fetch_status: 200,
      fetch_error: null,
      card_count: 2,
      cards: [],
      warnings: [],
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const selectors: SelectorMap = { card: ".item", title: "h2", link: "a" };
    await testListing("src-1", "https://example.com/list", selectors);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/test-listing");
    expect((init as RequestInit).method).toBe("POST");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
  });

  test("testListing sends {url, selectors} body verbatim", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          url: "https://example.com/list",
          fetch_status: 200,
          fetch_error: null,
          card_count: 0,
          cards: [],
          warnings: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const selectors: SelectorMap = { card: ".card", title: ".t", date: ".d" };
    await testListing("src-9", "https://example.com/list", selectors);

    const [, init] = fetchSpy.mock.calls[0];
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ url: "https://example.com/list", selectors }),
    );
  });

  test("sourceExtractionStats calls GET /admin/sources/{id}/extraction-stats", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          avg_confidence: 0.9,
          quarantine_rate: 0.05,
          cleaned_7d: 40,
          miss_7d: 2,
          buckets: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await sourceExtractionStats("src-1");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/extraction-stats");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  test("sourceExtractionStats parses SourceExtractionStats response shape", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: SourceExtractionStats = {
      avg_confidence: 0.82,
      quarantine_rate: 0.1,
      cleaned_7d: 18,
      miss_7d: 2,
      buckets: [{ day: "2026-05-21", avg: 0.8, cleaned: 3, miss: 0 }],
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await sourceExtractionStats("src-1");

    expect(result.avg_confidence).toBe(0.82);
    expect(result.cleaned_7d).toBe(18);
    expect(result.buckets[0].day).toBe("2026-05-21");
  });
});

describe("admin sources config versioning (extracted to api/admin/sources.ts, PR-7a-16c)", () => {
  test("listConfigs calls GET /admin/sources/{id}/configs (+ auth + shape)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: ConfigListResponse = {
      items: [
        {
          id: "cfg-1",
          source_id: "src-1",
          version: 2,
          is_active: true,
          config_json: { selectors: { card: ".item" } },
          created_at: "2026-05-21T10:00:00Z",
          created_by: "admin@example.com",
        },
      ],
      active_version: 2,
      total: 1,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await listConfigs("src-1");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/configs");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer ADMIN_ACCESS");
    expect(result.active_version).toBe(2);
    expect(result.items[0].version).toBe(2);
  });

  test("createConfig calls POST /admin/sources/{id}/configs with {config_json, note} body", async () => {
    // NOTE: createConfig has 0 callers (dead-code, preserved intentionally per
    // PR-7a-16c). mocked fetch only — creates a config version (DB write) in
    // production. Production smoke NEVER calls createConfig (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "cfg-2", version: 3 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const cfg: Record<string, unknown> = { selectors: { title: "h1" } };
    await createConfig("src-1", cfg, "v3 note");

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/configs");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ config_json: cfg, note: "v3 note" }),
    );
  });

  test("createConfig without note omits the note key (undefined guard)", async () => {
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "cfg-3" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const cfg: Record<string, unknown> = { a: 1 };
    await createConfig("src-1", cfg);

    const body = (fetchSpy.mock.calls[0][1] as RequestInit).body as string;
    // JSON.stringify drops undefined-valued keys → note absent, current behavior
    expect(body).toBe(JSON.stringify({ config_json: cfg }));
    expect(body).not.toContain("note");
  });

  test("rollbackConfig calls POST /admin/sources/{id}/configs/{version}/rollback", async () => {
    // NOTE: mocked fetch only — activates an old config version (DB write) in
    // production. Production smoke NEVER calls rollbackConfig (state-changing).
    setTokens("ADMIN_ACCESS", "ADMIN_REFRESH");
    const fixture: SourceConfigPublic = {
      id: "cfg-1",
      source_id: "src-1",
      version: 1,
      is_active: true,
      config_json: {},
      created_at: "2026-05-20T10:00:00Z",
      created_by: null,
    };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await rollbackConfig("src-1", 1);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/admin/sources/src-1/configs/1/rollback");
    expect((init as RequestInit).method).toBe("POST");
  });
});
