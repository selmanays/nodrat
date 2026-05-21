/**
 * Admin Legal API client — takedown/abuse/copyright/privacy requests (#35).
 *
 * Extracted from `api.ts` L886-955 in T6 P7a PR-7a-10.
 *
 * Primary callers (3):
 *   - apps/web/src/app/admin/legal/page.tsx — takedown request list
 *   - apps/web/src/app/admin/legal/[ticket]/page.tsx — request detail + update
 *   - apps/web/src/app/admin/page.tsx — admin dashboard (overdue count)
 *
 * Backend endpoints:
 *   - GET   /admin/legal/requests{query}      — listTakedownRequests (read-only)
 *   - GET   /admin/legal/requests/{ticketId}  — getTakedownRequest   (read-only)
 *   - PATCH /admin/legal/requests/{ticketId}  — updateTakedownRequest (STATE-CHANGING; legal compliance)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1178 / #1180 / #1183 — admin sub-folder extract pattern
 * - PR #1184 — shared buildQuery (api/_query.ts); first extract to consume it directly
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export interface TakedownAdminPublic {
  id: string;
  ticket_id: string;
  request_type: "abuse" | "takedown" | "copyright" | "privacy_request";
  requester_name: string | null;
  requester_email: string;
  requester_phone: string | null;
  requester_organization: string | null;
  authority_claim: string | null;
  subject_url: string | null;
  description: string;
  evidence_urls: string[];
  status: string;
  priority: string;
  submitted_at: string;
  triaged_at: string | null;
  investigating_at: string | null;
  resolved_at: string | null;
  sla_due_at: string;
  action_taken: string | null;
  rejection_reason: string | null;
  assigned_to: string | null;
  internal_notes: string | null;
  overdue: boolean;
}

export interface TakedownListResponse {
  data: TakedownAdminPublic[];
  total: number;
  overdue_count: number;
}

export interface TakedownUpdateRequest {
  status?: string;
  priority?: string;
  action_taken?: string;
  rejection_reason?: string;
  internal_notes?: string;
  assign_to_self?: boolean;
}

export async function listTakedownRequests(filters?: {
  request_type?: string;
  status?: string;
  only_overdue?: boolean;
  limit?: number;
  offset?: number;
}): Promise<TakedownListResponse> {
  return apiFetch<TakedownListResponse>(
    `/admin/legal/requests${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function getTakedownRequest(
  ticketId: string,
): Promise<TakedownAdminPublic> {
  return apiFetch<TakedownAdminPublic>(`/admin/legal/requests/${ticketId}`);
}

export async function updateTakedownRequest(
  ticketId: string,
  payload: TakedownUpdateRequest,
): Promise<TakedownAdminPublic> {
  return apiFetch<TakedownAdminPublic>(`/admin/legal/requests/${ticketId}`, {
    method: "PATCH",
    body: payload,
  });
}
