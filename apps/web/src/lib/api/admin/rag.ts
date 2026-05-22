/**
 * Admin RAG API client — observability dashboard read-only side (Epic #189).
 *
 * Extracted from `api.ts` (Admin RAG section) in T6 P7a PR-7a-18a (Part 1 of 2).
 * Trigger/pipeline fonksiyonları (`ragBenchmarkRun` / `ragRaptorTrigger` /
 * `ragInspectQuery`) + ilgili interface'ler PR-7a-18b ile bu dosyaya eklenecek;
 * şimdilik `api.ts`'te INLINE.
 *
 * Primary callers (1):
 *   - apps/web/src/app/admin/rag/page.tsx — RAG observability dashboard
 *
 * Backend endpoints (read-only):
 *   - GET /admin/rag/health                       — ragHealth
 *   - GET /admin/rag/benchmark/history{?limit}    — ragBenchmarkHistory
 *   - GET /admin/rag/benchmark/status             — ragBenchmarkStatus
 *   - GET /admin/rag/citation-stats{?sample}      — ragCitationStats
 *   - GET /admin/rag/rerank-stats{?hours}         — ragRerankStats
 *   - GET /admin/rag/cache-telemetry{?hours}      — ragCacheTelemetry
 *   - GET /admin/rag/raptor/clusters{?limit}      — ragRaptorClusters
 *   - GET /admin/rag/ner-stats                    — ragNerStats
 *   - GET /admin/rag/pipeline-comparison{?query}  — ragPipelineComparison (#440)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1194 / #1196 — admin sub-folder extract pattern
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 */

import { apiFetch } from "../../api";

export interface RagFeatureFlags {
  reranker_enabled: boolean;
  reranker_candidate_pool: number;
  rerank_model: string;
  // #420 — use_local_embedding kaldırıldı (embedding artık tek provider:
  // local BAAI/bge-m3, NIM bge-m3 ekosistemden çıkarıldı)
}

export interface RagHealthCounts {
  daily_cards: number;
  weekly_cards: number;
  daily_with_parent: number;
  active_clusters: number;
  last_24h_generations: number;
  last_24h_insufficient: number;
}

export interface RagLastEval {
  id: string;
  golden_set: string;
  completed_at: string | null;
  ndcg_10: number | null;
  map_5: number | null;
  mrr_10: number | null;
  recall_20: number | null;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  n_queries: number;
}

export interface RagWarmUpInfo {
  // #696 (B6)
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  embedding_ms: number | null;
  rerank_ms: number | null;
  ok: boolean;
}

export interface RagHealthResponse {
  flags: RagFeatureFlags;
  counts: RagHealthCounts;
  last_eval: RagLastEval | null;
  warm_up: RagWarmUpInfo | null;  // #696 (B6)
}

export interface BenchmarkRunSummary {
  id: string;
  golden_set: string;
  started_at: string;
  completed_at: string | null;
  n_queries: number;
  suite: string | null;  // #712 B4 — chart suite-aware filtre
  ndcg_10: number | null;
  map_5: number | null;
  mrr_10: number | null;
  recall_20: number | null;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  triggered_by: string | null;
}

export interface BenchmarkHistoryResponse {
  runs: BenchmarkRunSummary[];
}

export interface CitationStatsResponse {
  sample_size: number;
  repairs_total: number;
  repairs_avg_per_gen: number;
  unsupported_warnings: number;
  unsupported_avg_per_gen: number;
}

export interface RerankStatsResponse {
  sample_size: number;
  avg_latency_ms: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  last_call_at: string | null;
}

export interface CacheCallTypeRow {
  call_type: string;
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  miss_tokens: number;
  cache_hit_ratio: number | null;
  tools_present_rate: number | null;
}

export interface CacheSegmentAvg {
  seg_system: number | null;
  seg_tools_schema: number | null;
  seg_msg1_question: number | null;
  seg_rag_tool: number | null;
  seg_assistant_intermediate: number | null;
}

export interface CacheTelemetryResponse {
  window_hours: number;
  total_calls: number;
  overall_cache_hit_ratio: number | null;
  total_input_tokens: number;
  total_cached_tokens: number;
  total_miss_tokens: number;
  by_call_type: CacheCallTypeRow[];
  segment_avg: CacheSegmentAvg;
}

export interface WeeklyClusterRow {
  id: string;
  title: string;
  summary: string;
  importance: number | null;
  daily_children_count: number;
  children_titles: string[];
  updated_at: string;
}

export interface RaptorClustersResponse {
  weekly: WeeklyClusterRow[];
}

export async function ragHealth(): Promise<RagHealthResponse> {
  return apiFetch<RagHealthResponse>("/admin/rag/health");
}

export async function ragBenchmarkHistory(
  limit = 20,
): Promise<BenchmarkHistoryResponse> {
  return apiFetch<BenchmarkHistoryResponse>(
    `/admin/rag/benchmark/history?limit=${limit}`,
  );
}

// #700 — Background benchmark koşum durumu (polling)
export interface RagBenchmarkStatus {
  running: boolean;
  started_at: string | null;
  completed_at: string | null;  // #712 B4 — false-erken-aktifleşme önlemi
  triggered_by: string | null;
  suite: string | null;
  golden: string | null;
  error: string | null;
}

export async function ragBenchmarkStatus(): Promise<RagBenchmarkStatus> {
  return apiFetch<RagBenchmarkStatus>("/admin/rag/benchmark/status");
}

export async function ragCitationStats(
  sample = 100,
): Promise<CitationStatsResponse> {
  return apiFetch<CitationStatsResponse>(
    `/admin/rag/citation-stats?sample=${sample}`,
  );
}

export async function ragRerankStats(
  hours = 24,
): Promise<RerankStatsResponse> {
  return apiFetch<RerankStatsResponse>(
    `/admin/rag/rerank-stats?hours=${hours}`,
  );
}

export async function ragCacheTelemetry(
  hours = 24,
): Promise<CacheTelemetryResponse> {
  return apiFetch<CacheTelemetryResponse>(
    `/admin/rag/cache-telemetry?hours=${hours}`,
  );
}

export async function ragRaptorClusters(
  limit = 20,
): Promise<RaptorClustersResponse> {
  return apiFetch<RaptorClustersResponse>(
    `/admin/rag/raptor/clusters?limit=${limit}`,
  );
}

// #696 (B5) — NER pipeline mode telemetri
export interface RagNerStatsResponse {
  total: number;
  distribution: Record<string, number>;
  ratios: Record<string, number>;
  first_seen: string | null;
  last_seen: string | null;
  note: string;
}

export async function ragNerStats(): Promise<RagNerStatsResponse> {
  return apiFetch<RagNerStatsResponse>("/admin/rag/ner-stats");
}

// ---------------------------------------------------------------------------
// Pipeline Comparison (#440)
// ---------------------------------------------------------------------------

export interface PeriodMetrics {
  period_start: string;
  period_end: string;
  sample_count: number;
  avg_input_tokens: number | null;
  avg_output_tokens: number | null;
  cache_hit_ratio: number | null;
  avg_cost_usd_per_req: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  halu_flag_rate: number | null;
  insufficient_data_rate: number | null;
  completed_generation_count: number;
}

export interface PipelineComparisonResponse {
  period_a: PeriodMetrics;
  period_b: PeriodMetrics;
  delta_pct: Record<string, number | null>;
}

export interface PipelineComparisonParams {
  fromA?: string; // ISO datetime
  toA?: string;
  fromB?: string;
  toB?: string;
}

export async function ragPipelineComparison(
  params: PipelineComparisonParams = {},
): Promise<PipelineComparisonResponse> {
  const qs = new URLSearchParams();
  if (params.fromA) qs.set("from_a", params.fromA);
  if (params.toA) qs.set("to_a", params.toA);
  if (params.fromB) qs.set("from_b", params.fromB);
  if (params.toB) qs.set("to_b", params.toB);
  const queryString = qs.toString();
  const url = queryString
    ? `/admin/rag/pipeline-comparison?${queryString}`
    : "/admin/rag/pipeline-comparison";
  return apiFetch<PipelineComparisonResponse>(url);
}
