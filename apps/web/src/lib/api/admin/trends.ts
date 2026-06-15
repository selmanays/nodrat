/**
 * Admin Trends API client — Trend Intelligence Faz 1 (#1500).
 *
 * Transient read-only trend overview. Backend mevcut event_clusters/
 * event_articles'tan CANLI SQL ile hesaplar (persistence yok). Flag
 * `trends.enabled` OFF iken `enabled:false` + boş `data` döner (no-op).
 *
 * Backend endpoint:
 *   - GET /admin/trends{query} — listTrends (read-only)
 *
 * Pattern: admin/clusters.ts (PR-7a-17) — apiFetch + buildQuery, `@/lib/api`
 * üzerinden re-export.
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export type TrendWindow = "1h" | "6h" | "24h" | "7d";
export type TrendSort =
  | "momentum"
  | "article_count"
  | "source_count"
  | "novelty"
  | "credibility";
export type TrendState = "breaking" | "developing" | "stable" | "fading";

export interface TrendSparkPoint {
  bucket_start: string;
  article_count: number;
}

export interface TrendListItem {
  cluster_id: string;
  title: string;
  status: string;
  trend_state: TrendState;
  article_count: number;
  previous_article_count: number;
  momentum: number | null; // null = yeni (önceki pencerede baseline yok)
  unique_source_count: number;
  source_diversity: number;
  credibility_score: number | null;
  novelty_score: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  sparkline: TrendSparkPoint[];
}

export interface TrendListResponse {
  enabled: boolean;
  window: TrendWindow;
  sort: TrendSort;
  limit: number;
  offset: number;
  total: number;
  data: TrendListItem[];
  generated_at: string;
}

export async function listTrends(params?: {
  window?: TrendWindow;
  sort?: TrendSort;
  limit?: number;
  offset?: number;
}): Promise<TrendListResponse> {
  return apiFetch<TrendListResponse>(
    `/admin/trends${buildQuery(params as Record<string, unknown>)}`,
  );
}
