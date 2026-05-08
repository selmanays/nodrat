/**
 * Style Profiles API client (#52, Faz 5).
 *
 * Backend (#52 PR-1):
 *   POST   /app/style-profiles               — yarat (Pro+ paywall + slot quota)
 *   GET    /app/style-profiles               — kullanıcı profilleri + quota
 *   GET    /app/style-profiles/{id}          — detay (samples dahil)
 *   DELETE /app/style-profiles/{id}          — sil
 *   POST   /app/style-profiles/{id}/samples  — örnek ekle
 *   POST   /app/style-profiles/{id}/reanalyze — manuel retry
 *
 * Pro paywall: features.style_profiles=true gerek. Free/Starter user'a 402.
 */

import { apiFetch, ApiException } from "@/lib/api";

export type StyleProfileStatus = "pending" | "analyzing" | "ready" | "failed";
export type StyleProfileSource =
  | "manual"
  | "csv_import"
  | "public_account"
  | "x_personal";

export interface StyleProfileItem {
  id: string;
  name: string;
  source_type: StyleProfileSource;
  status: StyleProfileStatus;
  style_summary: string | null;
  rules_json: Record<string, unknown>;
  sample_count: number;
  error_message: string | null;
  analyzed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StyleProfileQuota {
  style_profiles_enabled: boolean;
  used: number;
  limit: number;
  plan_code: string;
}

export interface StyleProfilesListResponse {
  data: StyleProfileItem[];
  quota: StyleProfileQuota;
}

export interface SampleResponse {
  id: string;
  text: string;
  source_url: string | null;
  char_count: number;
  created_at: string;
}

export interface StyleProfileDetail extends StyleProfileItem {
  samples: SampleResponse[];
}

export interface SampleInput {
  text: string;
  source_url?: string | null;
}

export interface ProfileCreateRequest {
  name: string;
  source_type: Exclude<StyleProfileSource, "x_personal">;
  samples?: SampleInput[];
}

export interface SampleCreateResponse {
  sample: SampleResponse;
  sample_count: number;
  will_reanalyze: boolean;
}

export async function listStyleProfiles(): Promise<StyleProfilesListResponse> {
  return apiFetch<StyleProfilesListResponse>("/app/style-profiles");
}

export async function getStyleProfile(id: string): Promise<StyleProfileDetail> {
  return apiFetch<StyleProfileDetail>(
    `/app/style-profiles/${encodeURIComponent(id)}`,
  );
}

export async function createStyleProfile(
  payload: ProfileCreateRequest,
): Promise<StyleProfileItem> {
  return apiFetch<StyleProfileItem>("/app/style-profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteStyleProfile(id: string): Promise<void> {
  await apiFetch<void>(`/app/style-profiles/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function addStyleSample(
  profileId: string,
  payload: SampleInput,
): Promise<SampleCreateResponse> {
  return apiFetch<SampleCreateResponse>(
    `/app/style-profiles/${encodeURIComponent(profileId)}/samples`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function reanalyzeStyleProfile(
  profileId: string,
): Promise<StyleProfileItem> {
  return apiFetch<StyleProfileItem>(
    `/app/style-profiles/${encodeURIComponent(profileId)}/reanalyze`,
    { method: "POST" },
  );
}

/** 402 STYLE_PROFILES_REQUIRES_PRO → graceful Pro upsell modal. */
export function isPaywallRequired(err: unknown): boolean {
  if (!(err instanceof ApiException)) return false;
  return err.status === 402 && err.code === "STYLE_PROFILES_REQUIRES_PRO";
}

/** 409 STYLE_PROFILES_SLOT_FULL → kullanıcıya quota dolu mesajı. */
export function isSlotFull(err: unknown): boolean {
  if (!(err instanceof ApiException)) return false;
  return err.status === 409 && err.code === "STYLE_PROFILES_SLOT_FULL";
}
