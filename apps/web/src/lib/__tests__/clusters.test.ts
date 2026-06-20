/**
 * Faz 4 — küme/artefakt/abonelik API istemci karakterizasyonu (#12 coverage).
 *
 * `src/lib/api/clusters.ts` 6 fonksiyonu (listMyClusters / unsubscribeCluster /
 * getClusterArtifacts / getArtifact / reviseArtifact / quickActionArtifact)
 * api.test.ts'te SIFIR test idi (oradaki tüm "cluster" eşleşmeleri admin/RAPTOR
 * yoluna ait). Bu test her birinin URL + method (+ POST body) sözleşmesini
 * mocked-fetch ile kilitler. apiFetch body'yi kendisi JSON.stringify eder →
 * istemciler ham object geçmeli (consent-422 dersi); body assert'i bunu da korur.
 */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { setTokens, clearTokens } from "@/lib/api";
import {
  getArtifact,
  getClusterArtifacts,
  listMyClusters,
  quickActionArtifact,
  reviseArtifact,
  unsubscribeCluster,
} from "@/lib/api/clusters";

function mockJson(body: unknown, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

/** Son fetch çağrısının [url, init] argümanları. */
function lastCall(): [string, RequestInit] {
  const calls = (global.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
  const [url, init] = calls[calls.length - 1];
  return [url as string, (init ?? {}) as RequestInit];
}

beforeEach(() => {
  if (typeof window !== "undefined") window.localStorage.clear();
  setTokens("access-test", "refresh-test"); // Authorization header için
});

afterEach(() => {
  clearTokens();
  vi.restoreAllMocks();
});

describe("clusters API client", () => {
  test("listMyClusters → GET /app/me/clusters", async () => {
    mockJson({ items: [], total: 0 });
    await listMyClusters();
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/clusters");
    expect(init.method ?? "GET").toBe("GET");
  });

  test("unsubscribeCluster → POST /app/me/clusters/{id}/unsubscribe", async () => {
    mockJson({ unsubscribed: true });
    const res = await unsubscribeCluster("cid-123");
    expect(res).toEqual({ unsubscribed: true });
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/clusters/cid-123/unsubscribe");
    expect(init.method).toBe("POST");
  });

  test("getClusterArtifacts → GET /app/me/clusters/{id}/artifacts", async () => {
    mockJson({ items: [] });
    await getClusterArtifacts("cid-9");
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/clusters/cid-9/artifacts");
    expect(init.method ?? "GET").toBe("GET");
  });

  test("getArtifact → GET /app/me/artifacts/{id}", async () => {
    mockJson({ id: "aid-1", content: "x" });
    await getArtifact("aid-1");
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/artifacts/aid-1");
    expect(init.method ?? "GET").toBe("GET");
  });

  test("reviseArtifact → POST /revise, ham object body JSON.stringify edilir", async () => {
    mockJson({ id: "aid-1", content: "yeni" });
    await reviseArtifact("aid-1", "kısalt bunu", "freetext");
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/artifacts/aid-1/revise");
    expect(init.method).toBe("POST");
    // apiFetch JSON.stringify uyguladığından body string olmalı + alanları taşımalı
    expect(typeof init.body).toBe("string");
    const parsed = JSON.parse(init.body as string);
    expect(parsed.content).toBe("kısalt bunu");
    expect(parsed.intent).toBe("freetext");
  });

  test("quickActionArtifact → POST /quick-action {intent}", async () => {
    mockJson({ id: "aid-2", content: "kısa" });
    await quickActionArtifact("aid-2", "quick_shorter");
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/artifacts/aid-2/quick-action");
    expect(init.method).toBe("POST");
    const parsed = JSON.parse(init.body as string);
    expect(parsed.intent).toBe("quick_shorter");
  });
});
