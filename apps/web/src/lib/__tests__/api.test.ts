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
  adminSystemHealth,
  apiFetch,
  clearTokens,
  getAccessToken,
  getAdminUser,
  getAdminUserStats,
  getRefreshToken,
  listAdminUsers,
  listAuditLog,
  login,
  logout,
  publicSearch,
  register,
  requestVerifyResend,
  restoreAdminUser,
  setTokens,
  updateAdminUser,
  type AdminUserDetail,
  type AdminUserListResponse,
  type AdminUserStatsResponse,
  type AuditLogListResponse,
  type DiskBreakdownResponse,
  type DiskCleanupResponse,
  type LoginPayload,
  type PublicSearchResponse,
  type RegisterPayload,
  type SystemHealthResponse,
  type TokenResponse,
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
