/**
 * Admin Trends API client — entity-merkezli trend radarı (#1518/#1520).
 *
 * Read-only: backend `entities ⋈ articles`'tan CANLI hesaplar (kişi/kurum/yer/
 * olay, yayın zamanına göre). Flag `trends.enabled` OFF iken `enabled:false` +
 * boş `data` döner (no-op).
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
  | "score"
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
  momentum: number | null; // ham (cur-prev)/prev; null = yeni — referans (#1566)
  relative_momentum?: number | null; // #1566 A: korpus-normalize (gösterilen asıl sinyal)
  burst_z?: number | null; // #1566 B: pencere-içi son-dilim z (grafik yönü)
  unique_source_count: number;
  source_diversity: number;
  credibility_score: number | null;
  novelty_score: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  sparkline: TrendSparkPoint[];
  // entity: person|org|place|event rozeti + birleşik skor [0,1]
  entity_type?: string | null;
  trend_score?: number | null;
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
  source?: "entity"; // canlı entity-aggregation (tek okuma yolu)
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

// ---- Trend detail (drill-down, #1552) -------------------------------------

export interface TrendDetailArticle {
  id: string;
  title: string;
  url: string | null;
  published_at: string | null;
  source_name: string | null;
}

export interface TrendDetailSource {
  source_name: string | null;
  article_count: number;
}

export interface TrendDetailVariant {
  entity_normalized: string;
  surface_form: string;
  article_count: number;
}

export interface TrendDetailResponse {
  key: string;
  entity_name: string;
  entity_type: string;
  window: TrendWindow;
  canonical: boolean;
  total_articles: number;
  unique_sources: number;
  variants: TrendDetailVariant[];
  sources: TrendDetailSource[];
  articles: TrendDetailArticle[];
  sparkline: TrendSparkPoint[];
  generated_at: string;
}

export async function getTrendDetail(params: {
  key: string;
  window?: TrendWindow;
  limit?: number;
}): Promise<TrendDetailResponse> {
  return apiFetch<TrendDetailResponse>(
    `/admin/trends/detail${buildQuery(params as Record<string, unknown>)}`,
  );
}
