/**
 * Admin Media API client — list / stats / reprocess (NIM VLM image observability).
 *
 * Extracted from `api.ts` L1681-1750 in T6 P7a PR-7a-8.
 *
 * Primary caller (1):
 *   - apps/web/src/app/admin/media/page.tsx — media observability dashboard
 *
 * Backend endpoints:
 *   - GET  /admin/media{query}        — listAdminMedia (read-only)
 *   - GET  /admin/media/stats         — adminMediaStats (read-only)
 *   - POST /admin/media/{id}/reprocess — reprocessMedia (STATE-CHANGING; VLM trigger)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1174 (api/admin/disk.ts) — admin sub-folder + state-changing-smoke-skip pattern
 * - PR #1178 (api/admin/users.ts), PR #1180 (api/admin/audit.ts) — buildQuery non-exported copy
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

export type MediaStatus = "pending" | "processed" | "failed" | "skipped";

export interface MediaImage {
  id: string;
  article_id: string;
  article_title: string | null;
  article_url: string | null;
  source_id: string;
  source_name: string | null;
  original_url: string;
  alt_text: string | null;
  caption: string | null;
  vlm_caption: string | null;
  ocr_text: string | null;
  depicts: string[] | null;
  status: MediaStatus;
  error_message?: string | null;
  position: number | null;
  created_at: string;
  processed_at: string | null;
}

export interface MediaListResponse {
  data: MediaImage[];
  total: number;
  limit: number;
  offset: number;
}

export interface MediaStatsResponse {
  total: number;
  processed: number;
  failed: number;
  pending: number;
  skipped: number;
  last_24h_processed: number;
}

export interface MediaListFilters {
  source_id?: string;
  status?: MediaStatus;
  date_from?: string; // ISO 8601 (YYYY-MM-DD)
  date_to?: string;
  limit?: number;
  offset?: number;
}

export async function listAdminMedia(
  filters?: MediaListFilters,
): Promise<MediaListResponse> {
  return apiFetch<MediaListResponse>(
    `/admin/media${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function adminMediaStats(): Promise<MediaStatsResponse> {
  return apiFetch<MediaStatsResponse>("/admin/media/stats");
}

export async function reprocessMedia(id: string): Promise<MediaImage> {
  return apiFetch<MediaImage>(`/admin/media/${id}/reprocess`, {
    method: "POST",
    body: {},
  });
}
