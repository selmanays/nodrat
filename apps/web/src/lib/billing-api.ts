/**
 * Billing API client (#76, #53 backend).
 *
 * Backend endpoints (#53 PR #497):
 *   GET    /app/billing/plans              — public, USD primary
 *   POST   /app/billing/checkout           — LS hosted URL
 *   GET    /app/billing/subscription       — mevcut durum
 *   GET    /app/billing/portal-url         — LS Customer Portal redirect
 *   GET    /app/billing/invoices           — LS invoice referans listesi
 *   GET    /app/billing/seats              — Agency multi-seat listesi
 *   POST   /app/billing/seats/invite       — seat email davet
 *   DELETE /app/billing/seats/{id}         — seat çıkar
 *
 * LS hesap konfigüre değilse → 503 BILLING_NOT_CONFIGURED graceful response.
 * Frontend bu durumu "yakında aktif" olarak gösterir.
 */

import { apiFetch, ApiException } from "@/lib/api";

export interface PlanFeatures {
  allowed_models: string[];
  comparison_mode: boolean;
  style_profiles: boolean;
  style_profiles_slots: number | null;
  visual_features: boolean;
  visual_premium_vlm: boolean;
  analysis_output: boolean;
  concurrent_gen: number;
  rate_per_hour: number;
  support_sla_hours: number;
  bulk_export: boolean;
  comparison_premium_model: boolean;
}

export interface BillingPlan {
  code: string;
  name: string;
  tier: string;
  price_usd_monthly: number;
  price_usd_yearly: number;
  price_tl_display_monthly: number | null;
  price_tl_display_yearly: number | null;
  monthly_generation_limit: number;
  seat_count: number;
  features: Record<string, unknown>;
  available: boolean;
}

export interface PlansListResponse {
  plans: BillingPlan[];
  currency_primary: string;
  billing_provider: string;
  refund_policy_url: string;
  mesafeli_satis_url: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  ls_variant_id: string;
  expires_at: string | null;
}

export interface SubscriptionDetail {
  plan_code: string;
  plan_name: string;
  status: string;
  billing_cycle: string;
  trial_ends_at: string | null;
  current_period_start: string;
  current_period_end: string;
  cancelled_at: string | null;
  ends_at: string | null;
  seat_count: number;
  payment_provider: string;
  ls_subscription_id: string | null;
  next_invoice_amount_usd: number;
  next_invoice_amount_tl_display_ref: number | null;
}

export interface PortalUrlResponse {
  portal_url: string;
  expires_at: string | null;
}

export interface InvoiceItem {
  id: string;
  ls_invoice_id: string;
  ls_invoice_url: string | null;
  issued_at: string;
  amount_usd: number;
  tax_amount_usd: number | null;
  total_usd: number;
  currency: string;
}

export interface InvoicesListResponse {
  data: InvoiceItem[];
}

export type BillingStatusCheck =
  | { configured: true }
  | { configured: false; message: string };

export interface SeatItem {
  id: string;
  user_id: string | null;
  invited_email: string;
  accepted_at: string | null;
  role: "admin" | "editor";
}

export interface SeatsListResponse {
  subscription_id: string;
  plan_code: string;
  seat_count: number;
  seats: SeatItem[];
}

export interface SeatInviteResponse {
  seat_id: string;
  invite_url: string;
  invited_email: string;
}

export async function listPlans(): Promise<PlansListResponse> {
  return apiFetch<PlansListResponse>("/app/billing/plans");
}

export async function createCheckout(
  planCode: string,
  billingCycle: "monthly" | "yearly",
): Promise<CheckoutResponse> {
  return apiFetch<CheckoutResponse>("/app/billing/checkout", {
    method: "POST",
    body: JSON.stringify({
      plan_code: planCode,
      billing_cycle: billingCycle,
    }),
  });
}

export async function getSubscription(): Promise<SubscriptionDetail | null> {
  return apiFetch<SubscriptionDetail | null>("/app/billing/subscription");
}

export async function getPortalUrl(): Promise<PortalUrlResponse> {
  return apiFetch<PortalUrlResponse>("/app/billing/portal-url");
}

export async function listInvoices(): Promise<InvoicesListResponse> {
  return apiFetch<InvoicesListResponse>("/app/billing/invoices");
}

/**
 * "BILLING_NOT_CONFIGURED" 503 → graceful UX flag.
 * Diğer tüm API hataları yeniden fırlatılır.
 */
export function isBillingNotConfigured(err: unknown): boolean {
  if (!(err instanceof ApiException)) return false;
  return err.status === 503 && err.code === "BILLING_NOT_CONFIGURED";
}

/**
 * `/app/billing/seats` 404 NO_AGENCY_SUBSCRIPTION → kullanıcı Agency tier'da değil.
 * Frontend bu durumu "Agency planına geç" CTA'sı ile gösterir.
 */
export function isNoAgencySubscription(err: unknown): boolean {
  if (!(err instanceof ApiException)) return false;
  return err.status === 404 && err.code === "NO_AGENCY_SUBSCRIPTION";
}

export async function listSeats(): Promise<SeatsListResponse> {
  return apiFetch<SeatsListResponse>("/app/billing/seats");
}

export async function inviteSeat(
  email: string,
  role: "admin" | "editor" = "editor",
): Promise<SeatInviteResponse> {
  return apiFetch<SeatInviteResponse>("/app/billing/seats/invite", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function removeSeat(seatId: string): Promise<void> {
  await apiFetch<void>(
    `/app/billing/seats/${encodeURIComponent(seatId)}`,
    { method: "DELETE" },
  );
}
