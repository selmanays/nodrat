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
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9 dedup)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

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
