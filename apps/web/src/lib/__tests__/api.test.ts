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
  getRefreshToken,
  publicSearch,
  setTokens,
  type DiskBreakdownResponse,
  type DiskCleanupResponse,
  type PublicSearchResponse,
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
