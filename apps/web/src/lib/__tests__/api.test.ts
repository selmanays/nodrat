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
  apiFetch,
  clearTokens,
  getAccessToken,
  getAdminUser,
  getAdminUserStats,
  getRefreshToken,
  listAdminUsers,
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
  type DiskBreakdownResponse,
  type DiskCleanupResponse,
  type LoginPayload,
  type PublicSearchResponse,
  type RegisterPayload,
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
