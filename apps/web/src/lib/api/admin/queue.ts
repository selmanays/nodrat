/**
 * Admin Queue API client — job queue overview, failed jobs, maintenance (#17).
 *
 * Extracted from `api.ts` L797-941 in T6 P7a PR-7a-15.
 *
 * Primary callers (2):
 *   - apps/web/src/app/admin/queue/page.tsx — queue overview + failed jobs + maintenance (full management)
 *   - apps/web/src/app/admin/page.tsx        — admin dashboard (queue overview)
 *
 * Backend endpoints:
 *   - GET    /admin/queue/overview                   — getQueueOverview     (read-only)
 *   - GET    /admin/queue/failed{query}              — listFailedJobs       (read-only)
 *   - GET    /admin/queue/maintenance                — listMaintenanceTasks (read-only)
 *   - POST   /admin/queue/jobs/{id}/retry            — retryFailedJob       (STATE-CHANGING; Celery re-enqueue / manual job trigger)
 *   - POST   /admin/queue/failed/bulk-retry          — bulkRetryFailedJobs  (STATE-CHANGING; bulk re-enqueue / manual job trigger)
 *   - POST   /admin/queue/failed/bulk-resolve        — bulkResolveFailedJobs (STATE-CHANGING; DB write)
 *   - POST   /admin/queue/maintenance/{name}/run-now — runMaintenanceNow    (STATE-CHANGING; MANUAL MAINTENANCE TASK TRIGGER — prod'da ASLA tetiklenmez)
 *   - DELETE /admin/queue/failed/{id}                — resolveFailedJob     (STATE-CHANGING; DB write)
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Refs:
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
 * - PR #1180 / #1183 / #1186 — admin sub-folder extract pattern
 * - PR #1184 — shared buildQuery (api/_query.ts)
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch — core HTTP helper
 * - buildQuery — shared internal query helper (api/_query.ts, PR-7a-9)
 */

import { apiFetch } from "../../api";
import { buildQuery } from "../_query";

export interface QueueStat {
  name: string;
  queued_count: number;
  running_count: number;
  succeeded_count_24h: number;
  failed_count_24h: number;
}

export interface QueueOverviewResponse {
  queues: QueueStat[];
  failed_jobs_unresolved: number;
  worker_count?: number;
}

export interface FailedJobPublic {
  id: string;
  original_job_id: string | null;
  job_type: string;
  severity?: "error" | "warning" | "permanent_info";
  source_id: string | null;
  article_url: string | null;
  error_message: string;
  stack_trace: string | null;
  retry_count: number;
  last_attempt_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  payload: Record<string, unknown>;
}

export interface FailedJobListResponse {
  data: FailedJobPublic[];
  total: number;
}

export async function getQueueOverview(): Promise<QueueOverviewResponse> {
  return apiFetch<QueueOverviewResponse>("/admin/queue/overview");
}

export async function listFailedJobs(filters?: {
  job_type?: string;
  unresolved_only?: boolean;
  source_id?: string;
  severity?: "error" | "warning" | "permanent_info" | "all";
  include_info?: boolean;
  limit?: number;
  offset?: number;
}): Promise<FailedJobListResponse> {
  return apiFetch<FailedJobListResponse>(
    `/admin/queue/failed${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function retryFailedJob(
  failedId: string,
): Promise<{ new_job_id: string; scheduled_at: string; celery_task_id?: string }> {
  return apiFetch(`/admin/queue/jobs/${failedId}/retry`, {
    method: "POST",
    body: {},
  });
}

// #462 — Bulk operations
export interface BulkResultItem {
  id: string;
  ok: boolean;
  code?: string | null;
  celery_task_id?: string | null;
}

export interface BulkResponse {
  succeeded: number;
  failed: number;
  results: BulkResultItem[];
}

export async function bulkRetryFailedJobs(
  ids: string[],
): Promise<BulkResponse> {
  return apiFetch("/admin/queue/failed/bulk-retry", {
    method: "POST",
    body: { ids },
  });
}

export async function bulkResolveFailedJobs(
  ids: string[],
  note?: string,
): Promise<BulkResponse> {
  return apiFetch("/admin/queue/failed/bulk-resolve", {
    method: "POST",
    body: { ids, note: note || null },
  });
}

// #468 — Maintenance task list + run-now
export interface MaintenanceLastRun {
  task_name: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  status: "succeeded" | "failed";
  summary: Record<string, unknown> | null;
  triggered_by: string;
  error: string | null;
}

export interface MaintenanceTaskInfo {
  task_name: string;
  label: string;
  pipeline: string;
  interval_human: string;
  queue: string;
  last_run: MaintenanceLastRun | null;
}

export interface MaintenanceListResponse {
  tasks: MaintenanceTaskInfo[];
}

export async function listMaintenanceTasks(): Promise<MaintenanceListResponse> {
  return apiFetch<MaintenanceListResponse>("/admin/queue/maintenance");
}

export async function runMaintenanceNow(
  taskName: string,
): Promise<{ task_name: string; celery_task_id: string; triggered_at: string }> {
  return apiFetch(`/admin/queue/maintenance/${encodeURIComponent(taskName)}/run-now`, {
    method: "POST",
    body: {},
  });
}

export async function resolveFailedJob(
  failedId: string,
  note?: string,
): Promise<void> {
  return apiFetch(`/admin/queue/failed/${failedId}`, {
    method: "DELETE",
    body: { note: note || null },
  });
}
