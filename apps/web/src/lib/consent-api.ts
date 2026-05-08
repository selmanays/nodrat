/**
 * Foreign transfer consent API client (#453, KVKK m.9).
 *
 * Backend endpoints (#470 PR #492 ile production'da):
 *   GET    /app/consent/status              — mevcut durum
 *   POST   /app/consent/foreign-transfer    — açık rıza grant
 *   DELETE /app/consent/foreign-transfer    — geri çekme (KVKK m.11)
 *
 * Avukat şartlı onayı (Epic #448 §3.9 N-09 RESOLVED): TIA 5 maddelik kayıt
 * sistemi backend'de tutulur (timestamp + IP + version + text_hash + user_id).
 * Bu modül sadece UI flow için typed wrapper.
 */

import { apiFetch } from "@/lib/api";

export interface ConsentStatus {
  has_consent: boolean;
  consent_at: string | null;
  version: string | null;
  revoked_at: string | null;
  current_version: string;
  needs_re_consent: boolean;
}

export interface ConsentGrantResponse {
  consent_at: string;
  version: string;
  revoked: boolean;
}

export interface ConsentRevokeResponse {
  revoked_at: string;
  message: string;
}

export async function getConsentStatus(): Promise<ConsentStatus> {
  return apiFetch<ConsentStatus>("/app/consent/status");
}

export async function grantForeignTransferConsent(
  consentTextVersion: string,
): Promise<ConsentGrantResponse> {
  return apiFetch<ConsentGrantResponse>("/app/consent/foreign-transfer", {
    method: "POST",
    body: JSON.stringify({ consent_text_version: consentTextVersion }),
  });
}

export async function revokeForeignTransferConsent(): Promise<ConsentRevokeResponse> {
  return apiFetch<ConsentRevokeResponse>("/app/consent/foreign-transfer", {
    method: "DELETE",
  });
}
