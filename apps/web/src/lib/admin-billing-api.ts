/**
 * Admin Billing API client (#77).
 *
 * Backend endpoints (#77):
 *   GET   /admin/plans                — tüm plan'lar (private fields)
 *   PATCH /admin/plans/{plan_code}    — variant_id_* + active toggle
 *
 * Sadece super_admin erişebilir (require_admin guard).
 */

import { apiFetch } from "@/lib/api";

export interface AdminPlanItem {
  code: string;
  name: string;
  tier: string;
  price_usd_monthly: number;
  price_usd_yearly: number;
  price_tl_display_monthly: number | null;
  price_tl_display_yearly: number | null;
  monthly_generation_limit: number;
  seat_count: number;
  max_context_cards: number;
  features: Record<string, unknown>;
  ls_variant_id_monthly: string | null;
  ls_variant_id_yearly: string | null;
  active: boolean;
  display_order: number;
  available: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminPlansListResponse {
  plans: AdminPlanItem[];
}

export interface PlanUpdateRequest {
  ls_variant_id_monthly?: string | null;
  ls_variant_id_yearly?: string | null;
  active?: boolean;
}

export async function listAdminPlans(): Promise<AdminPlansListResponse> {
  return apiFetch<AdminPlansListResponse>("/admin/plans");
}

export async function updateAdminPlan(
  planCode: string,
  payload: PlanUpdateRequest,
): Promise<AdminPlanItem> {
  return apiFetch<AdminPlanItem>(`/admin/plans/${encodeURIComponent(planCode)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
