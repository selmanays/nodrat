/**
 * Admin Articles API client — article list/detail/stats + dashboard time-series.
 *
 * Extracted from `api.ts` L492-640 (`// ---- Articles ----`) in T6 P7a PR-7a-11.
 *
 * Primary callers (3, all admin):
 *   - apps/web/src/app/admin/articles/page.tsx — article list + stats
 *   - apps/web/src/app/admin/articles/[id]/page.tsx — detail + reprocess
 *   - apps/web/src/app/admin/page.tsx — dashboard (stats + hourly + provider-calls)
 *
 * Backend endpoints:
 *   - GET  /admin/articles{query}                    — listArticles (read-only)
 *   - GET  /admin/articles/stats                     — articleStats (read-only)
 *   - GET  /admin/dashboard/hourly                   — dashboardHourly (read-only)
 *   - GET  /admin/dashboard/provider-calls?period=   — dashboardProviderCalls (read-only)
 *   - GET  /admin/articles/{id}                      — getArticle (read-only)
 *   - POST /admin/articles/{id}/reprocess            — reprocessArticle (STATE-CHANGING; reprocess task dispatch)
 *
 * NOTE: `getMyQuota` (`/app/quota`) lives in a SEPARATE block (App: Generation
 * residue) and is NOT part of this Articles section — left untouched in api.ts.
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1186 (api/admin/legal.ts) — admin sub-folder + shared buildQuery pattern
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export interface ArticleSummary {
  id: string;
  source_id: string;
  source_name: string | null;
  canonical_url: string;
  title: string;
  author: string | null;
  published_at: string | null;
  status: string;
  language: string;
  extraction_confidence: number | null;
  text_length: number;
  has_images: boolean;
  created_at: string;
}

export interface ArticleListResponse {
  data: ArticleSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArticleImagePublic {
  id: string;
  original_url: string;
  alt_text: string | null;
  caption: string | null;
  vlm_caption: string | null;
  ocr_text: string | null;
  depicts: string[] | null;
  discovered_from: string | null;
  status: string;
  position: number | null;
  processed_at: string | null;
  created_at: string;
}

export interface ArticleDetail {
  id: string;
  source_id: string;
  source_name: string | null;
  source_slug: string | null;
  canonical_url: string;
  source_url: string;
  title: string;
  subtitle: string | null;
  author: string | null;
  published_at: string | null;
  fetched_at: string;
  crawled_at: string;
  body_html: string | null;
  clean_text: string | null;
  language: string;
  content_hash: string;
  title_hash: string;
  extraction_confidence: number | null;
  status: string;
  created_at: string;
  updated_at: string;
  images: ArticleImagePublic[];
}

export interface ArticleStat {
  status: string;
  count: number;
}

export interface ArticleStatsResponse {
  by_status: ArticleStat[];
  total: number;
  by_source: Array<{ name: string; slug: string; count: number }>;
  embedded_count: number;
}

export interface ArticleListFilters {
  source_id?: string;
  status?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export async function listArticles(
  filters?: ArticleListFilters,
): Promise<ArticleListResponse> {
  return apiFetch<ArticleListResponse>(
    `/admin/articles${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function articleStats(): Promise<ArticleStatsResponse> {
  return apiFetch<ArticleStatsResponse>("/admin/articles/stats");
}

export interface HourlyBucket {
  hour: string;
  count: number;
}

export interface ProviderSeries {
  provider: string;
  buckets: HourlyBucket[];
}

export interface DashboardHourlyResponse {
  articles: HourlyBucket[];
  jobs: HourlyBucket[];
  generations: HourlyBucket[];
  provider_calls: HourlyBucket[];
  provider_calls_by_provider: ProviderSeries[];
}

export async function dashboardHourly(): Promise<DashboardHourlyResponse> {
  return apiFetch<DashboardHourlyResponse>("/admin/dashboard/hourly");
}

export type ProviderCallsPeriod = "7d" | "30d" | "3m";

export interface ProviderCallsRangeResponse {
  period: ProviderCallsPeriod;
  bucket: "hour" | "day" | "week";
  series: ProviderSeries[];
}

export async function dashboardProviderCalls(
  period: ProviderCallsPeriod = "7d",
): Promise<ProviderCallsRangeResponse> {
  return apiFetch<ProviderCallsRangeResponse>(
    `/admin/dashboard/provider-calls?period=${period}`,
  );
}

export async function getArticle(id: string): Promise<ArticleDetail> {
  return apiFetch<ArticleDetail>(`/admin/articles/${id}`);
}

export async function reprocessArticle(
  id: string,
): Promise<{ article_id: string; status: string; dispatched_task: string | null }> {
  return apiFetch(`/admin/articles/${id}/reprocess`, {
    method: "POST",
    body: {},
  });
}
