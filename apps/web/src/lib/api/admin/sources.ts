/**
 * Admin Sources API client — source CRUD + activation + feed/robots test (#17).
 *
 * Extracted from `api.ts` L210-373 in T6 P7a PR-7a-16a (Part 1 of 3 for Admin Sources).
 * Selector test (#70) ve config versioning (#75) alt bölümleri PR-7a-16b / PR-7a-16c
 * ile aynı dosyaya eklenecek (incremental, single-file domain).
 *
 * Primary callers:
 *   - apps/web/src/app/admin/page.tsx              — admin dashboard (source list)
 *   - apps/web/src/app/admin/sources/page.tsx      — sources list
 *   - apps/web/src/app/admin/sources/new/page.tsx  — create + feed test
 *   - apps/web/src/app/admin/sources/[id]/page.tsx — detail + activate/update/robots
 *
 * Backend endpoints:
 *   - GET   /admin/sources{query}            — listSources    (read-only)
 *   - GET   /admin/sources/{id}              — getSource      (read-only)
 *   - POST  /admin/sources                   — createSource   (STATE-CHANGING)
 *   - POST  /admin/sources/{id}/activate     — activateSource (STATE-CHANGING; compliance checklist)
 *   - PATCH /admin/sources/{id}              — updateSource   (STATE-CHANGING)
 *   - POST  /admin/sources/test-feed         — testFeed       (SIDE-EFFECT; outbound feed fetch)
 *   - GET   /admin/sources/{id}/robots-check — robotsCheck    (SIDE-EFFECT; outbound robots.txt fetch)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1186 / #1194 — admin sub-folder extract pattern
 * - PR #1184 — shared buildQuery (api/_query.ts)
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export type SourceType = "rss" | "category_page" | "manual";

export type PollingTier = "hot" | "normal" | "cold" | "hibernate";

export interface TierMetadata {
  items_1h: number | null;
  items_6h: number | null;
  last_item_at: string | null;
  hours_since_new: number | null;
  consecutive_unchanged: number;
  computed_at: string;
  cold_start: boolean;
  candidate_tier?: PollingTier;
  dwell_remaining_sec?: number;
  source_age_hours?: number;
}

export interface SourcePublic {
  id: string;
  name: string;
  slug: string;
  domain: string;
  type: SourceType;
  base_url: string;
  language: string;
  country: string;
  category: string | null;
  reliability_score: number;
  is_active: boolean;
  crawl_interval_minutes: number;
  robots_txt_compliant: boolean | null;
  tos_acknowledged: boolean;
  realtime_enabled: boolean;
  polling_tier: PollingTier;
  // #578 Faz 2 — adaptive tier shadow mode
  would_be_tier: PollingTier | null;
  tier_changed_at: string | null;
  tier_metadata: TierMetadata | null;
  consecutive_unchanged: number;
}

export interface SourceUpdatePayload {
  crawl_interval_minutes?: number;
  realtime_enabled?: boolean;
  name?: string;
  category?: string | null;
}

export interface SourceCreatePayload {
  name: string;
  slug: string;
  domain: string;
  type: SourceType;
  base_url: string;
  language?: string;
  country?: string;
  category?: string | null;
  crawl_interval_minutes?: number;
  config_json?: Record<string, unknown> | null;
}

export interface ComplianceChecklist {
  robots_txt_checked: boolean;
  not_paywalled: boolean;
  tos_allows_scraping: boolean;
  publicly_accessible: boolean;
  commercial_risk_assessed: boolean;
}

export interface ActivatePayload {
  checklist: ComplianceChecklist;
  note?: string;
}

export interface FeedReportPublic {
  feed_url: string;
  fetched: boolean;
  status_code: number;
  error: string | null;
  feed_title: string;
  feed_description: string;
  feed_language: string | null;
  item_count: number;
  sample_items: Array<{
    title: string;
    link: string;
    summary: string;
    author: string | null;
    published_at: string | null;
    image_url: string | null;
  }>;
}

export interface RobotsReportPublic {
  domain: string;
  robots_url: string;
  fetched: boolean;
  status_code: number;
  base_url_allowed: boolean;
  crawl_delay_sec: number;
  sitemaps: string[];
  error: string | null;
}

export interface SourceListFilters {
  is_active?: boolean;
  type?: SourceType;
  limit?: number;
  offset?: number;
}

export async function listSources(
  filters?: SourceListFilters,
): Promise<SourcePublic[]> {
  return apiFetch<SourcePublic[]>(
    `/admin/sources${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function createSource(
  payload: SourceCreatePayload,
): Promise<SourcePublic> {
  return apiFetch<SourcePublic>("/admin/sources", {
    method: "POST",
    body: payload,
  });
}

export async function getSource(id: string): Promise<SourcePublic> {
  return apiFetch<SourcePublic>(`/admin/sources/${id}`);
}

export async function activateSource(
  id: string,
  payload: ActivatePayload,
): Promise<SourcePublic> {
  return apiFetch<SourcePublic>(`/admin/sources/${id}/activate`, {
    method: "POST",
    body: payload,
  });
}

export async function updateSource(
  id: string,
  payload: SourceUpdatePayload,
): Promise<SourcePublic> {
  return apiFetch<SourcePublic>(`/admin/sources/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function testFeed(feedUrl: string): Promise<FeedReportPublic> {
  return apiFetch<FeedReportPublic>("/admin/sources/test-feed", {
    method: "POST",
    body: { feed_url: feedUrl },
  });
}

export async function robotsCheck(id: string): Promise<RobotsReportPublic> {
  return apiFetch<RobotsReportPublic>(`/admin/sources/${id}/robots-check`);
}

// ---- Selector test (#70 R-OPS-01) — Part 2/3, extracted in PR-7a-16b ------
//
// Backend endpoints:
//   - POST /admin/sources/{id}/test-listing      — testListing          (SIDE-EFFECT; outbound URL fetch + parse)
//   - GET  /admin/sources/{id}/extraction-stats  — sourceExtractionStats (read-only)

export interface SelectorMap {
  card?: string;
  title?: string;
  link?: string;
  image?: string;
  date?: string;
  // detail-only
  subtitle?: string;
  author?: string;
  published?: string;
  body?: string;
}

export interface TestListingCard {
  title: string | null;
  link: string | null;
  image_url: string | null;
  date: string | null;
}

export interface TestListingResponse {
  url: string;
  fetch_status: number;
  fetch_error: string | null;
  card_count: number;
  cards: TestListingCard[];
  warnings: string[];
}

// #904 — TestDetail* (kaynağa özel DETAY selector testi) KALDIRILDI.
// Detay extraction artık generic (Tier-0 JSON-LD → density → fallback);
// per-domain çıkarım sağlığı `sourceExtractionStats` ile izlenir.
// `testListing` (category_page keşfi) KORUNUR.

export interface SourceExtractionStats {
  avg_confidence: number; // cleaned son 7g ortalama extraction_confidence
  quarantine_rate: number; // miss / (cleaned+miss) son 7g
  cleaned_7d: number;
  miss_7d: number; // quarantine + discarded
  buckets: { day: string; avg: number; cleaned: number; miss: number }[];
}

export async function testListing(
  sourceId: string,
  url: string,
  selectors: SelectorMap,
): Promise<TestListingResponse> {
  return apiFetch<TestListingResponse>(
    `/admin/sources/${sourceId}/test-listing`,
    { method: "POST", body: { url, selectors } },
  );
}

export async function sourceExtractionStats(
  sourceId: string,
): Promise<SourceExtractionStats> {
  return apiFetch<SourceExtractionStats>(
    `/admin/sources/${sourceId}/extraction-stats`,
  );
}
