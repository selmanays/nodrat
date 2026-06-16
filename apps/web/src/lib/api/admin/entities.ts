/**
 * Admin Canonical Entities API client — merge/split/manuel alias (#1554).
 *
 * Deterministik builder'ın çözemediği belirsiz vakaları (örn. "2026 Dünya
 * Kupası" → FIFA) admin elle yönetir. Mutation → backend audit + alias
 * `source='admin'` (builder bunları EZMEZ). `entities` tablosu dokunulmaz.
 *
 * Backend: GET /admin/entities/canonical{query}, GET /canonical/{id},
 *   POST /canonical, POST /canonical/{id}/aliases, DELETE /canonical/{id}/aliases/{alias},
 *   POST /canonical/{id}/merge.
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export type CanonicalEntityType = "person" | "org" | "place" | "event";

export interface CanonicalRow {
  id: string;
  canonical_name: string;
  entity_type: string;
  canonical_normalized: string;
  alias_count: number;
  source: string;
  status: string;
}

export interface AliasRow {
  alias_normalized: string;
  entity_type: string;
  source: string;
  confidence: number;
}

export interface CanonicalListResponse {
  data: CanonicalRow[];
  total: number;
}

export interface CanonicalDetailResponse {
  canonical: CanonicalRow;
  aliases: AliasRow[];
}

export async function listCanonical(params?: {
  search?: string;
  entity_type?: CanonicalEntityType;
  limit?: number;
  offset?: number;
}): Promise<CanonicalListResponse> {
  return apiFetch<CanonicalListResponse>(
    `/admin/entities/canonical${buildQuery(params as Record<string, unknown>)}`,
  );
}

export async function getCanonical(id: string): Promise<CanonicalDetailResponse> {
  return apiFetch<CanonicalDetailResponse>(
    `/admin/entities/canonical/${encodeURIComponent(id)}`,
  );
}

export async function createCanonical(body: {
  canonical_name: string;
  entity_type: CanonicalEntityType;
  aliases?: string[];
}): Promise<CanonicalDetailResponse> {
  return apiFetch<CanonicalDetailResponse>("/admin/entities/canonical", {
    method: "POST",
    body,
  });
}

export async function addAliases(
  id: string,
  aliases: string[],
): Promise<CanonicalDetailResponse> {
  return apiFetch<CanonicalDetailResponse>(
    `/admin/entities/canonical/${encodeURIComponent(id)}/aliases`,
    { method: "POST", body: { aliases } },
  );
}

export async function removeAlias(id: string, alias: string): Promise<void> {
  await apiFetch<void>(
    `/admin/entities/canonical/${encodeURIComponent(id)}/aliases/${encodeURIComponent(alias)}`,
    { method: "DELETE" },
  );
}

export async function mergeCanonical(
  targetId: string,
  sourceId: string,
): Promise<CanonicalDetailResponse> {
  return apiFetch<CanonicalDetailResponse>(
    `/admin/entities/canonical/${encodeURIComponent(targetId)}/merge`,
    { method: "POST", body: { source_id: sourceId } },
  );
}
