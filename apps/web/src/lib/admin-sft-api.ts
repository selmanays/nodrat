/**
 * Admin SFT data pipeline API client (#569).
 *
 * Backend endpoints (apps/api/app/api/admin_sft.py — production'da):
 *   GET  /admin/sft/stats?days=30
 *   GET  /admin/sft/recent?limit=50
 *   POST /admin/sft/export
 *   POST /admin/sft/recompute-eligibility?days=30
 *   GET  /admin/sft/consent-stats
 *
 * Auth: super_admin role only (require_admin).
 */

import { apiFetch, getAccessToken } from "@/lib/api";

export interface SFTDailyPoint {
  date: string;
  count: number;
}

export interface SFTStatsResponse {
  total_samples: number;
  by_task_type: Record<string, number>;
  by_split: Record<string, number>;
  daily_curated: SFTDailyPoint[];
  quality_p50_edit_distance: number | null;
  quality_p50_char_count: number | null;
  eligible_pending: number;
  excluded_breakdown: Record<string, number>;
}

export interface SFTRecentSample {
  id: string;
  generation_id: string;
  task_type: string;
  sft_split: string;
  edit_distance: number | null;
  char_count: number | null;
  curated_at: string;
  exported_at: string | null;
  input_preview: string;
  output_preview: string;
}

export interface SFTConsentStats {
  total_users: number;
  opted_in: number;
  opted_in_revoked: number;
  never_opted_in: number;
}

export interface SFTRecomputeResponse {
  scanned: number;
  became_eligible: number;
  became_ineligible: number;
}

export interface SFTExportRequest {
  task_type?: string;
  sft_split?: string | null;
  format?: "chatml";
  mark_exported?: boolean;
}

export async function getSFTStats(days = 30): Promise<SFTStatsResponse> {
  return apiFetch<SFTStatsResponse>(`/admin/sft/stats?days=${days}`);
}

export async function getSFTRecent(limit = 50): Promise<SFTRecentSample[]> {
  return apiFetch<SFTRecentSample[]>(`/admin/sft/recent?limit=${limit}`);
}

export async function getSFTConsentStats(): Promise<SFTConsentStats> {
  return apiFetch<SFTConsentStats>("/admin/sft/consent-stats");
}

export async function recomputeSFTEligibility(
  days = 30,
): Promise<SFTRecomputeResponse> {
  return apiFetch<SFTRecomputeResponse>(
    `/admin/sft/recompute-eligibility?days=${days}`,
    { method: "POST" },
  );
}

/**
 * StreamingResponse JSONL — fetch ile direkt blob al, browser download.
 * apiFetch JSON beklediği için kullanılmaz.
 */
export async function downloadSFTExport(payload: SFTExportRequest): Promise<{
  filename: string;
  size: number;
}> {
  const apiBase = (
    process.env.NEXT_PUBLIC_API_URL || "/api"
  ).replace(/\/$/, "");
  const apiUrl = `${apiBase}/admin/sft/export`;

  const token = getAccessToken();
  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      task_type: payload.task_type ?? "content_generator",
      sft_split: payload.sft_split ?? null,
      format: payload.format ?? "chatml",
      mark_exported: payload.mark_exported ?? true,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Export failed (${response.status}): ${text}`);
  }

  const blob = await response.blob();
  const taskType = payload.task_type ?? "content_generator";
  const splitSuffix = payload.sft_split ?? "all";
  const filename = `nodrat-sft-${taskType}-${splitSuffix}.jsonl`;

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  return { filename, size: blob.size };
}
