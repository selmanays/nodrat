/**
 * Admin System Health API client — read-only system observability dashboard.
 *
 * Extracted from `api.ts` L1749-1825 in T6 P7a PR-7a-7.
 *
 * Primary caller (1):
 *   - apps/web/src/app/admin/observability/page.tsx — system health dashboard
 *     (mapped to `/admin/observability` route; `/admin/system` parent has no
 *     direct page, only `/admin/system/disk` subroute via PR-7a-2).
 *
 * Backend endpoint:
 *   - GET /admin/system/health — adminSystemHealth (read-only; no state-changing)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1174 (api/admin/disk.ts) — admin sub-folder + read-only pattern
 * - PR #1178 (api/admin/users.ts), PR #1180 (api/admin/audit.ts) — admin extracts
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 *
 * No `buildQuery` needed (no query parameters).
 */

import { apiFetch } from "../../api";

export interface CpuInfo {
  cores: number;
  load_1m: number;
  load_5m: number;
  load_15m: number;
  usage_pct: number;
}

export interface RamInfo {
  total_mb: number;
  used_mb: number;
  free_mb: number;
  used_pct: number;
}

export interface DiskInfo {
  total_gb: number;
  used_gb: number;
  free_gb: number;
  used_pct: number;
}

export interface VpsInfo {
  hostname: string;
  cpu: CpuInfo;
  ram: RamInfo;
  disk: DiskInfo;
}

export interface TableSize {
  name: string;
  size_mb: number;
  row_count: number;
  index_size_mb: number;
}

export interface PostgresInfo {
  db_size_gb: number;
  tables: TableSize[];
}

export interface BucketInfo {
  name: string;
  size_gb: number;
  object_count: number;
}

export interface MinioInfo {
  endpoint: string;
  buckets: BucketInfo[];
}

export interface ContaboInfo {
  endpoint: string;
  bucket: string;
  size_gb: number;
  object_count: number;
  by_prefix: Record<string, BucketInfo>;
}

export interface BackupInfo {
  last_snapshot_at: string | null;
  last_snapshot_age_h: number | null;
  snapshot_count: number;
  total_size_gb: number;
  last_check_status: string;
}

export interface SystemHealthResponse {
  vps: VpsInfo;
  postgres: PostgresInfo;
  minio: MinioInfo;
  contabo_os: ContaboInfo;
  backups: BackupInfo;
  timestamp: string;
  cache_age_seconds: number;
}

export async function adminSystemHealth(): Promise<SystemHealthResponse> {
  return apiFetch<SystemHealthResponse>("/admin/system/health");
}
