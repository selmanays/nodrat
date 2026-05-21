/**
 * Admin Audit Log API client — list (read-only).
 *
 * Extracted from `api.ts` L1130-1170 in T6 P7a PR-7a-6.
 *
 * Primary caller (1):
 *   - apps/web/src/app/admin/audit/page.tsx — admin audit log dashboard
 *
 * Backend endpoint:
 *   - GET /admin/audit{query} — listAuditLog (read-only; no state-changing)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1178 (api/admin/users.ts) — admin sub-folder + buildQuery non-exported pattern
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 *
 * `buildQuery` helper duplicated as non-exported local copy (preserves null/
 * undefined skip behavior). Shared `_query.ts` deferred to later housekeeping
 * PR (Admin Sources extract will share the same need).
 */

import { apiFetch } from "../../api";

// Local copy of `buildQuery` from api.ts — kept non-exported to preserve
// internal-only API surface. Behavior must remain identical: undefined/null
// values are skipped (URLSearchParams would emit "undefined").
function buildQuery(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export interface AuditLogEntry {
  id: string;
  actor_id: string;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  event_metadata: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  data: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogFilters {
  action?: string;
  actor_id?: string;
  target_type?: string;
  target_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export async function listAuditLog(
  filters?: AuditLogFilters,
): Promise<AuditLogListResponse> {
  return apiFetch<AuditLogListResponse>(
    `/admin/audit${buildQuery(filters as Record<string, unknown>)}`,
  );
}
