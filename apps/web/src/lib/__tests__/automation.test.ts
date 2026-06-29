/**
 * Faz 5.3b — Otomasyon Stüdyosu API istemci karakterizasyonu (#1791).
 *
 * `src/lib/api/automation.ts` fonksiyonlarının URL + method (+ POST/PATCH body)
 * sözleşmesini mocked-fetch ile kilitler. apiFetch body'yi kendisi JSON.stringify
 * eder → istemciler ham object geçmeli (consent-422 dersi); body assert'i bunu korur.
 */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { clearTokens, setTokens } from "@/lib/api";
import {
  approveAutomationRun,
  createAutomationRule,
  deleteAutomationRule,
  listAutomationRules,
  listAutomationRuns,
  rejectAutomationRun,
  updateAutomationRule,
} from "@/lib/api/automation";

function mockJson(body: unknown, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function lastCall(): [string, RequestInit] {
  const calls = (global.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
  const [url, init] = calls[calls.length - 1];
  return [url as string, (init ?? {}) as RequestInit];
}

beforeEach(() => {
  if (typeof window !== "undefined") window.localStorage.clear();
  setTokens("access-test", "refresh-test");
});

afterEach(() => {
  clearTokens();
  vi.restoreAllMocks();
});

describe("automation API client", () => {
  test("listAutomationRules → GET /app/me/automation/rules", async () => {
    mockJson({ rules: [], total: 0 });
    await listAutomationRules();
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/rules");
    expect(init.method ?? "GET").toBe("GET");
  });

  test("createAutomationRule → POST /rules + body", async () => {
    mockJson({ rule_id: "r1" });
    await createAutomationRule({ cluster_id: "cid-1" });
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/rules");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ cluster_id: "cid-1" });
  });

  test("updateAutomationRule → PATCH /rules/{id} + body", async () => {
    mockJson({ updated: true });
    await updateAutomationRule("r1", { status: "paused", enabled: false });
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/rules/r1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ status: "paused", enabled: false });
  });

  test("deleteAutomationRule → DELETE /rules/{id}", async () => {
    mockJson({ deleted: true });
    const res = await deleteAutomationRule("r1");
    expect(res).toEqual({ deleted: true });
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/rules/r1");
    expect(init.method).toBe("DELETE");
  });

  test("listAutomationRuns → GET /runs?status_filter=pending", async () => {
    mockJson({ runs: [], total: 0 });
    await listAutomationRuns();
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/runs?status_filter=pending");
    expect(init.method ?? "GET").toBe("GET");
  });

  test("approveAutomationRun → POST /runs/{id}/approve", async () => {
    mockJson({ status: "posted" });
    const res = await approveAutomationRun("run-1");
    expect(res).toEqual({ status: "posted" });
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/runs/run-1/approve");
    expect(init.method).toBe("POST");
  });

  test("rejectAutomationRun → POST /runs/{id}/reject", async () => {
    mockJson({ status: "rejected" });
    await rejectAutomationRun("run-1");
    const [url, init] = lastCall();
    expect(url).toContain("/app/me/automation/runs/run-1/reject");
    expect(init.method).toBe("POST");
  });
});
