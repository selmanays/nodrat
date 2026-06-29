/**
 * Otomasyon Stüdyosu API client — Faz 5.3b frontend.
 *
 * Backend: app/api/app_automation.py (/app/me/automation/*). Çift flag-gate
 * (automation.enabled + automation.studio.enabled) → flag OFF iken endpoint'ler 403
 * (ApiException.status === 403) → UI "henüz aktif değil" durumunu gösterir.
 * apiFetch body'yi kendisi JSON.stringify eder → ham object geç (string DEĞİL).
 */

import { apiFetch } from "@/lib/api";

// ---- Kurallar --------------------------------------------------------------

export interface AutomationRule {
  rule_id: string;
  cluster_id: string;
  cluster_name: string | null;
  enabled: boolean;
  /** active | paused */
  status: string;
  /** approval_queue | full_auto */
  mode: string;
  /** breaking | developing */
  states: string[];
  last_triggered_at: string | null;
  created_at: string;
}

export interface RuleListResponse {
  rules: AutomationRule[];
  total: number;
}

export interface RuleCreatePayload {
  cluster_id: string;
  states?: string[];
  window_seconds?: number;
  artifact_type?: string;
  mode?: string;
}

export interface RuleUpdatePayload {
  enabled?: boolean;
  status?: string;
  states?: string[];
  mode?: string;
}

export async function listAutomationRules(): Promise<RuleListResponse> {
  return apiFetch<RuleListResponse>("/app/me/automation/rules");
}

export async function createAutomationRule(payload: RuleCreatePayload): Promise<AutomationRule> {
  return apiFetch<AutomationRule>("/app/me/automation/rules", {
    method: "POST",
    body: payload,
  });
}

export async function updateAutomationRule(
  ruleId: string,
  payload: RuleUpdatePayload,
): Promise<{ updated: boolean }> {
  return apiFetch(`/app/me/automation/rules/${ruleId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function deleteAutomationRule(ruleId: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/app/me/automation/rules/${ruleId}`, { method: "DELETE" });
}

// ---- Onay kuyruğu ----------------------------------------------------------

export interface AutomationRun {
  run_id: string;
  cluster_id: string;
  cluster_name: string | null;
  status: string;
  artifact_id: string | null;
  artifact_preview: string | null;
  triggered_at: string;
}

export interface RunListResponse {
  runs: AutomationRun[];
  total: number;
}

export async function listAutomationRuns(statusFilter = "pending"): Promise<RunListResponse> {
  return apiFetch<RunListResponse>(
    `/app/me/automation/runs?status_filter=${encodeURIComponent(statusFilter)}`,
  );
}

export async function approveAutomationRun(runId: string): Promise<{ status: string }> {
  return apiFetch(`/app/me/automation/runs/${runId}/approve`, { method: "POST" });
}

export async function rejectAutomationRun(runId: string): Promise<{ status: string }> {
  return apiFetch(`/app/me/automation/runs/${runId}/reject`, { method: "POST" });
}
