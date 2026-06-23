/**
 * Küme-merkezli abonelik API client — Faz 4 frontend.
 *
 * Backend: app/api/app_me.py (/app/me/clusters, /app/me/artifacts).
 * apiFetch body'yi kendisi JSON.stringify eder → ham object geç (string DEĞİL).
 */

import { apiFetch } from "@/lib/api";

// ---- Kümeler ---------------------------------------------------------------

export interface SubscribedCluster {
  cluster_id: string;
  canonical_name: string;
  cluster_type: string;
  subscribed_at: string;
  source: string;
  parent_cluster_id: string | null;
  /** breaking | developing | stable | fading | quiet (trends.enabled OFF → null) */
  trend_state: string | null;
  relative_momentum: number | null;
  article_count_window: number | null;
  /** Son 24s bucket-başına haber hacmi (sparkline; trends.enabled OFF → []) */
  spark?: number[];
}

export interface MyClustersResponse {
  clusters: SubscribedCluster[];
  total: number;
}

export async function listMyClusters(): Promise<MyClustersResponse> {
  return apiFetch<MyClustersResponse>("/app/me/clusters");
}

export async function unsubscribeCluster(clusterId: string): Promise<{ unsubscribed: boolean }> {
  return apiFetch(`/app/me/clusters/${clusterId}/unsubscribe`, { method: "POST" });
}

// ---- Keşif radarı (#1745) — takip edilmeyen yükselenler --------------------

export interface DiscoverRisingItem {
  cluster_key: string;
  entity_name: string;
  entity_type: string;
  /** breaking | developing */
  trend_state: string;
  relative_momentum: number | null;
  article_count: number;
  /** Küme mintlenmişse abone olunabilir; null → "ara" (sorgu başlat) */
  cluster_id: string | null;
}

export interface DiscoverRisingResponse {
  data: DiscoverRisingItem[];
  generated_at: string;
}

export async function discoverRising(limit = 15): Promise<DiscoverRisingResponse> {
  return apiFetch<DiscoverRisingResponse>(`/app/me/discover/rising?limit=${limit}`);
}

// ---- Artefaktlar -----------------------------------------------------------

export interface ArtifactListItem {
  artifact_id: string;
  artifact_type: string;
  created_at: string;
  revision_count: number;
  head_preview: string | null;
  /** Bu kartı üreten araştırma sorusu (initial revizyon effective_query) — #1699 */
  question: string | null;
}

export interface ClusterArtifactsResponse {
  cluster_id: string;
  artifacts: ArtifactListItem[];
  total: number;
}

export async function getClusterArtifacts(clusterId: string): Promise<ClusterArtifactsResponse> {
  return apiFetch<ClusterArtifactsResponse>(`/app/me/clusters/${clusterId}/artifacts`);
}

export interface ArtifactRevisionItem {
  revision_seq: number;
  revision_intent: string;
  content: string;
  created_at: string;
  accepted_at: string | null;
}

export interface ArtifactDetail {
  artifact_id: string;
  artifact_type: string;
  cluster_id: string;
  head_revision_seq: number | null;
  /** Bu kartı üreten araştırma sorusu (initial revizyon effective_query) — #1699 */
  question: string | null;
  revisions: ArtifactRevisionItem[];
}

export async function getArtifact(artifactId: string): Promise<ArtifactDetail> {
  return apiFetch<ArtifactDetail>(`/app/me/artifacts/${artifactId}`);
}

/** Canvas direkt-edit / serbest-metin → yeni revizyon (LLM'siz, 3b-1). */
export async function reviseArtifact(
  artifactId: string,
  content: string,
  intent = "edit",
): Promise<{ revision_seq: number }> {
  return apiFetch(`/app/me/artifacts/${artifactId}/revise`, {
    method: "POST",
    body: { content, intent },
  });
}

export type QuickActionIntent =
  | "quick_shorter"
  | "quick_rewrite"
  | "quick_longer"
  | "multi_share";

/** LLM quick-action revizyonu (3b-2; flag artifacts.revisions.llm.enabled). */
export async function quickActionArtifact(
  artifactId: string,
  intent: QuickActionIntent,
): Promise<{ revision_seq: number; content: string }> {
  return apiFetch(`/app/me/artifacts/${artifactId}/quick-action`, {
    method: "POST",
    body: { intent },
  });
}
