/**
 * Admin Clusters API client — pivot research cluster observation (#1028).
 *
 * Extracted from `api.ts` L622-653 in T6 P7a PR-7a-17.
 *
 * Primary callers (1):
 *   - apps/web/src/app/admin/clusters/page.tsx — cluster list (read-only)
 *
 * Backend endpoints:
 *   - GET /admin/clusters{query} — listClusters (read-only)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1180 / #1186 — admin sub-folder extract pattern
 * - PR #1184 — shared buildQuery (api/_query.ts)
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export interface ClusterListItem {
  cluster_id: string;
  cluster_key: string;
  canonical_name: string;
  cluster_type: string;
  parent_cluster_id: string | null;
  member_count: number; // talep: küme içi mesaj sayısı
  distinct_users: number; // talep: ilgilenen kullanıcı sayısı
  last_at: string | null;
  // arz (#1570): aynı entity'nin canlı trend durumu (trends.enabled OFF → null)
  trend_state?: string | null; // breaking|developing|stable|fading|quiet
  relative_momentum?: number | null;
  article_count_window?: number | null;
}

export interface ClusterListResponse {
  // Backend (admin_clusters.py ClusterListResponse) `data` döndürür —
  // FE eski `items` adıyla uyumsuzdu → resp.items=undefined → sayfa
  // çökmesi (#1044 regresyonu, prod-audit'te yakalandı). BE sözleşmesi
  // kaynak doğruluğu (F3c #1028 deployed) → FE hizalandı.
  data: ClusterListItem[];
  total: number;
  limit: number;
  offset: number;
}

export async function listClusters(params?: {
  limit?: number;
  offset?: number;
  window?: string; // #1570 trend penceresi: 1h|6h|24h|7d
}): Promise<ClusterListResponse> {
  return apiFetch<ClusterListResponse>(
    `/admin/clusters${buildQuery(params as Record<string, unknown>)}`,
  );
}
