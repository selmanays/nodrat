/**
 * Admin disk panel API client (#570).
 *
 * Extracted from `api.ts` L2005-2041 in T6 P7a PR-7a-2.
 *
 * Caller: `apps/web/src/app/admin/system/disk/page.tsx` (1 caller).
 * Backend:
 *   - `GET /admin/system/disk` — disk breakdown (read-only)
 *   - `POST /admin/system/disk/cleanup` — disk reclaim (state-changing)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api`
 * caller import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1173 — Public search extract (PR-7a-1) pattern source
 */

import { apiFetch } from "../../api";

export interface DiskCategory {
  key: string;
  label: string;
  bytes: number;
  reclaimable_bytes: number;
}

export interface DiskBreakdownResponse {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  used_percent: number;
  categories: DiskCategory[];
  docker_total_bytes: number;
  reclaimable_bytes: number;
  timestamp: string;
}

export interface DiskCleanupResponse {
  reclaimed_bytes: number;
  items_deleted: number;
  duration_seconds: number;
  timestamp: string;
}

export async function adminDiskBreakdown(): Promise<DiskBreakdownResponse> {
  return apiFetch<DiskBreakdownResponse>("/admin/system/disk");
}

export async function adminDiskCleanup(): Promise<DiskCleanupResponse> {
  return apiFetch<DiskCleanupResponse>("/admin/system/disk/cleanup", {
    method: "POST",
  });
}
