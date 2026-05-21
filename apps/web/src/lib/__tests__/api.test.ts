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
  apiFetch,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
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
