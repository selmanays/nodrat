/**
 * Admin Settings API client — runtime config registry (#262/#265, MVP-1.2).
 *
 * Extracted from `api.ts` L1391-1442 in T6 P7a PR-7a-14.
 *
 * Primary callers (3):
 *   - apps/web/src/app/admin/page.tsx — settings overview
 *   - apps/web/src/app/admin/settings/[group]/page.tsx — per-group settings editor
 *   - apps/web/src/app/admin/sft/page.tsx — SFT-related settings
 *
 * Backend endpoints:
 *   - GET    /admin/settings{?group=}    — adminSettingsList (read-only)
 *   - PUT    /admin/settings/{key}       — adminSettingUpdate (STATE-CHANGING; runtime config)
 *   - DELETE /admin/settings/{key}       — adminSettingReset  (STATE-CHANGING; runtime config reset)
 *
 * NOTE: `adminSettingReset` uses DELETE (resets an override to its code default),
 * NOT POST — preserved verbatim from api.ts (no method change).
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1190 (api/account.ts) — admin sub-folder + smoke-skip pattern
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 *
 * No `buildQuery` needed (single inline `?group=` query param preserved as-is).
 */

import { apiFetch } from "../../api";

export interface AdminSettingItem {
  key: string;
  value: unknown;
  default: unknown;
  type: "float" | "int" | "bool" | "string" | "json";
  group: string;
  description: string | null;
  min_value: number | null;
  max_value: number | null;
  allowed_values: unknown[] | null;
  requires_restart: boolean;
  is_overridden: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AdminSettingsListResponse {
  data: AdminSettingItem[];
  groups: string[];
}

export async function adminSettingsList(
  group?: string,
): Promise<AdminSettingsListResponse> {
  const qs = group ? `?group=${encodeURIComponent(group)}` : "";
  return apiFetch<AdminSettingsListResponse>(`/admin/settings${qs}`);
}

export async function adminSettingUpdate(
  key: string,
  value: unknown,
): Promise<AdminSettingItem> {
  return apiFetch<AdminSettingItem>(
    `/admin/settings/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: { value },
    },
  );
}

export async function adminSettingReset(
  key: string,
): Promise<AdminSettingItem> {
  return apiFetch<AdminSettingItem>(
    `/admin/settings/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}
