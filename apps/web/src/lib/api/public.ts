/**
 * Public search API client — anonymous endpoint (#261).
 *
 * Extracted from `api.ts` L539-565 in T6 P7a PR-7a-1.
 *
 * Caller: `apps/web/src/app/search/page.tsx` (publicSearch + publicTrending).
 * Backend: `/public/search` — anonymous; `skipAuth=true`.
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api`
 * caller import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1172 — frontend test infra bootstrap (PR-7a-0)
 */

import { apiFetch } from "../api";

export interface PublicSearchItem {
  id: string;
  title: string;
  summary: string;
  published_at: string | null;
  source_name: string | null;
  source_url: string;
  country: string | null;
  relevance_score: number;
}

export interface PublicSearchResponse {
  query: string;
  total: number;
  items: PublicSearchItem[];
  rate_limit_remaining: number;
}

export async function publicSearch(
  q: string,
  limit = 10,
): Promise<PublicSearchResponse> {
  const url = `/public/search?q=${encodeURIComponent(q)}&limit=${limit}`;
  return apiFetch<PublicSearchResponse>(url, { skipAuth: true });
}

// ---- Anonim gündem radarı (#1745) — /search boş-durumu için ----------------

export interface PublicTrendingItem {
  entity_name: string;
  entity_type: string;
  /** breaking | developing */
  trend_state: string;
  article_count: number;
}

export interface PublicTrendingResponse {
  items: PublicTrendingItem[];
  rate_limit_remaining: number;
}

export async function publicTrending(limit = 10): Promise<PublicTrendingResponse> {
  return apiFetch<PublicTrendingResponse>(`/public/trending?limit=${limit}`, {
    skipAuth: true,
  });
}
