/**
 * Model improvement consent API client (KVKK 5. checkbox, #564 + #566).
 *
 * Backend endpoints (PR #584 + #586 production'da):
 *   GET    /app/me/consent/model-improvement     — durum
 *   POST   /app/me/consent/model-improvement     — açık rıza grant (idempotent)
 *   DELETE /app/me/consent/model-improvement     — geri çekme (KVKK m.11)
 *
 * KVKK md.5/2-a — açık ve özgül amaç (model eğitimi). data_processing ve
 * foreign_transfer rızalarından BAĞIMSIZDIR.
 */

import { apiFetch } from "@/lib/api";

export interface ModelImprovementConsentStatus {
  is_active: boolean;
  granted_at: string | null;
  revoked_at: string | null;
  text_version: string | null;
}

export interface ModelImprovementGrantResponse {
  status: "granted";
  granted_at: string;
  text_version: string;
}

export interface ModelImprovementRevokeResponse {
  status: "revoked";
  revoked_at: string;
  generations_affected: number;
}

export const MODEL_IMPROVEMENT_TEXT_VERSION = "v0.3";

export async function getModelImprovementConsent(): Promise<ModelImprovementConsentStatus> {
  return apiFetch<ModelImprovementConsentStatus>(
    "/app/me/consent/model-improvement",
  );
}

export async function grantModelImprovementConsent(
  textVersion: string = MODEL_IMPROVEMENT_TEXT_VERSION,
  textHash?: string,
): Promise<ModelImprovementGrantResponse> {
  return apiFetch<ModelImprovementGrantResponse>(
    "/app/me/consent/model-improvement",
    {
      method: "POST",
      body: { text_version: textVersion, text_hash: textHash ?? null },
    },
  );
}

export async function revokeModelImprovementConsent(): Promise<ModelImprovementRevokeResponse> {
  return apiFetch<ModelImprovementRevokeResponse>(
    "/app/me/consent/model-improvement",
    { method: "DELETE" },
  );
}
