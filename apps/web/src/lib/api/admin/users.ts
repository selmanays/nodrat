/**
 * Admin Users API client — list / detail / update / restore / stats.
 *
 * Extracted from `api.ts` L1014-1104 in T6 P7a PR-7a-5.
 *
 * Primary callers (3):
 *   - apps/web/src/app/admin/page.tsx (getAdminUserStats + type)
 *   - apps/web/src/app/admin/users/page.tsx (listAdminUsers + getAdminUserStats + types)
 *   - apps/web/src/app/admin/users/[id]/page.tsx (getAdminUser + updateAdminUser + restoreAdminUser + type)
 *
 * Backend endpoints:
 *   - GET  /admin/users{query}          — listAdminUsers (read-only)
 *   - GET  /admin/users/{id}            — getAdminUser   (read-only)
 *   - PATCH /admin/users/{id}           — updateAdminUser (STATE-CHANGING)
 *   - POST /admin/users/{id}/restore    — restoreAdminUser (STATE-CHANGING)
 *   - GET  /admin/users/stats           — getAdminUserStats (read-only)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1174 (admin/disk.ts) — admin sub-folder extract pattern
 * - PR #1175 / #1177 — Auth + verifyResend extract patterns
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9 dedup)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export interface AdminUserSummary {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  deleted_at: string | null;
}

export interface AdminUserDetail extends AdminUserSummary {
  kvkk_acknowledgment_at: string | null;
  data_processing_consent_at: string | null;
  foreign_transfer_consent_at: string | null;
  marketing_consent_at: string | null;
  last_login_ip: string | null;
  updated_at: string;
}

export interface AdminUserListResponse {
  data: AdminUserSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminUserStatsResponse {
  total: number;
  active: number;
  inactive: number;
  deleted: number;
  email_verified: number;
  by_tier: Array<{ tier: string; count: number }>;
  by_role: Array<{ role: string; count: number }>;
}

export interface AdminUserUpdate {
  role?: string;
  tier?: string;
  is_active?: boolean;
}

export async function listAdminUsers(filters?: {
  role?: string;
  tier?: string;
  is_active?: boolean;
  deleted?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUserListResponse> {
  return apiFetch<AdminUserListResponse>(
    `/admin/users${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function getAdminUser(id: string): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`);
}

export async function updateAdminUser(
  id: string,
  payload: AdminUserUpdate & { note?: string },
): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function restoreAdminUser(
  id: string,
  note?: string,
): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}/restore`, {
    method: "POST",
    body: { note: note || null },
  });
}

export async function getAdminUserStats(): Promise<AdminUserStatsResponse> {
  return apiFetch<AdminUserStatsResponse>("/admin/users/stats");
}
