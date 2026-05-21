/**
 * Shared query-string builder for the api/* modules.
 *
 * Consolidates the non-exported `buildQuery` copies introduced by the Phase 7a
 * admin extracts (PR-7a-5 admin-users, PR-7a-6 admin-audit, PR-7a-8 admin-media)
 * plus the original definition in `api.ts`. Behavior is byte-for-byte identical
 * to those copies — no API behavior change (T6 P7a PR-7a-9 housekeeping).
 *
 * Invariant: `undefined` / `null` values are SKIPPED (URLSearchParams would
 * otherwise emit the literal "undefined" / "null"). Keys and values are
 * `encodeURIComponent`-encoded. Returns "" (no leading "?") when there is
 * nothing to encode.
 *
 * Internal helper — NOT re-exported from `api.ts` (no public `@/lib/api`
 * surface change). Underscore-prefixed filename marks it as module-internal.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1178 / #1180 / #1183 — admin extracts that each copied buildQuery
 */

export function buildQuery(
  params: Record<string, unknown> | undefined,
): string {
  if (!params) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}
