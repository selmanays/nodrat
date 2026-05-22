/**
 * Account API client — user-facing app quota (#80, #800 residue).
 *
 * Extracted from `api.ts` L525-536 in T6 P7a PR-7a-12. `getMyQuota` was in the
 * "App: Generation block silindi" residual block (NOT the Articles section);
 * moved here to a user-facing account module.
 *
 * Primary caller (1):
 *   - apps/web/src/app/app/layout.tsx — quota badge in app shell
 *
 * Backend endpoint:
 *   - GET /app/quota — getMyQuota (read-only)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1187 — Admin Articles extract that left getMyQuota untouched
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 */

import { apiFetch } from "../api";

export interface QuotaResponse {
  tier: string;
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
  window_seconds: number;
}

export async function getMyQuota(): Promise<QuotaResponse> {
  return apiFetch<QuotaResponse>("/app/quota");
}
