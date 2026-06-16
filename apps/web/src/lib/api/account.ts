/**
 * Account API client — user-facing app quota + /app/me KVKK self-service.
 *
 * Extracted from `api.ts`:
 *   - L525-536 in T6 P7a PR-7a-12 (getMyQuota — "App: Generation" residue)
 *   - L989-1056 in T6 P7a PR-7a-13 (Account/Me — `// ---- App: /app/me ----`)
 *
 * Primary callers:
 *   - apps/web/src/app/app/layout.tsx — quota badge in app shell (getMyQuota)
 *   - apps/web/src/app/app/me/page.tsx — KVKK self-service (getMe/updateMe/exportMe/deleteMe)
 *
 * Backend endpoints:
 *   - GET    /app/quota       — getMyQuota (read-only)
 *   - GET    /app/me          — getMe     (read-only)
 *   - PATCH  /app/me          — updateMe  (STATE-CHANGING; profile update)
 *   - GET    /app/me/export   — exportMe  (read-only but PII/KVKK data dump)
 *   - DELETE /app/me          — deleteMe  (STATE-CHANGING + DANGER; account deletion)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1189 (getMyQuota mini-extract) — initial api/account.ts module
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 */

import { apiFetch } from "../api";

export interface QuotaResponse {
  tier: string;
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
  window_seconds: number;
}

export async function getMyQuota(): Promise<QuotaResponse> {
  return apiFetch<QuotaResponse>("/app/quota");
}

export interface UserMePublic {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  kvkk_acknowledgment_at: string | null;
  data_processing_consent_at: string | null;
  foreign_transfer_consent_at: string | null;
  marketing_consent_at: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface ProfileUpdatePayload {
  full_name?: string | null;
  locale?: string | null;
  marketing_consent?: boolean | null;
}

export interface AccountDeleteResponse {
  status: string;
  deletion_at: string;
}

export interface ExportResponse {
  exported_at: string;
  user: Record<string, unknown>;
  generations: Array<Record<string, unknown>>;
  saved_generations: Array<Record<string, unknown>>;
  usage_events: Array<Record<string, unknown>>;
  sessions: Array<Record<string, unknown>>;
}

export async function getMe(): Promise<UserMePublic> {
  return apiFetch<UserMePublic>("/app/me");
}

export async function updateMe(
  payload: ProfileUpdatePayload,
): Promise<UserMePublic> {
  return apiFetch<UserMePublic>("/app/me", {
    method: "PATCH",
    body: payload,
  });
}

export async function exportMe(): Promise<ExportResponse> {
  return apiFetch<ExportResponse>("/app/me/export");
}

export async function deleteMe(
  confirmation: string,
  reason?: string,
): Promise<AccountDeleteResponse> {
  return apiFetch<AccountDeleteResponse>("/app/me", {
    method: "DELETE",
    body: { confirmation, reason: reason || null },
  });
}

// ---- İlgi alanları (#1016 + #1570 trend zenginleştirme) -------------------
// GET /app/me/research-interests — kullanıcının kümeleri (talep) + AYNI
// entity'nin canlı trend durumu (arz). user-scoped (yalnız kendi kümeleri).

export interface ResearchInterestItem {
  cluster_id: string;
  canonical_name: string;
  cluster_type: string;
  item_count: number; // kullanıcının o ilgi alanındaki sorgu sayısı
  last_at: string | null;
  parent_cluster_id: string | null;
  // #1570: canlı trend durumu (trends.enabled OFF → null)
  trend_state?: string | null; // breaking|developing|stable|fading|quiet
  relative_momentum?: number | null;
  article_count_window?: number | null;
}

export interface ResearchInterestsResponse {
  interests: ResearchInterestItem[];
  total: number;
}

export async function getMyResearchInterests(): Promise<ResearchInterestsResponse> {
  return apiFetch<ResearchInterestsResponse>("/app/me/research-interests");
}

// ---- Bildirimler (#1581 C — trend-alert) ----------------------------------

export interface NotificationItem {
  id: string;
  type: string;
  cluster_key: string | null;
  title: string;
  trend_state: string | null;
  article_count: number | null;
  created_at: string;
  read: boolean;
}

export interface NotificationsResponse {
  notifications: NotificationItem[];
  unread_count: number;
}

export async function getMyNotifications(params?: {
  limit?: number;
  unread_only?: boolean;
}): Promise<NotificationsResponse> {
  const q = new URLSearchParams();
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.unread_only) q.set("unread_only", "true");
  const qs = q.toString();
  return apiFetch<NotificationsResponse>(
    `/app/me/notifications${qs ? `?${qs}` : ""}`,
  );
}

export async function markNotificationsRead(
  ids?: string[],
): Promise<{ unread_count: number }> {
  return apiFetch<{ unread_count: number }>("/app/me/notifications/read", {
    method: "POST",
    body: { ids: ids ?? null },
  });
}
