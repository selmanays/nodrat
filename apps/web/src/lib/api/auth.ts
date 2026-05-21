/**
 * Auth API client — login / register / logout.
 *
 * Extracted from `api.ts` L185-254 in T6 P7a PR-7a-3.
 *
 * Primary caller: `apps/web/src/lib/auth-context.tsx` (imports login/register/
 * logout + types).
 * Backend:
 *   - POST `/auth/login` — anonymous (skipAuth=true)
 *   - POST `/auth/register` — anonymous (skipAuth=true)
 *   - POST `/auth/logout` — silent fail if refresh missing; clearTokens always
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1173 / #1174 — Public search + Admin Disk extract patterns
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - getRefreshToken / clearTokens — token storage (used by logout)
 */

import { apiFetch, clearTokens, getRefreshToken } from "../api";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface UserPublic {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tier: string;
  locale: string;
  email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: UserPublic;
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string | null;
  locale?: string;
  // 4 KVKK checkboxes (3 zorunlu + 1 opsiyonel) + 18+ gate
  kvkk_acknowledgment: boolean;
  data_processing_consent: boolean;
  foreign_transfer_consent: boolean;
  marketing_consent?: boolean;
  age_18_plus: boolean;
}

export async function register(
  payload: RegisterPayload,
): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/register", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: { refresh_token: refresh },
        skipAuth: true,
      });
    } catch {
      // Silent fail — token revoked anyway
    }
  }
  clearTokens();
}
