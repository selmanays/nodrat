"use client";

/**
 * /app/billing — billing hub (#76, #53 backend).
 *
 * Layout:
 *   - Mevcut subscription card (varsa) — "Aboneliği yönet" CTA
 *   - Tier matrix — her tier için fiyat (USD primary, TL display ref)
 *   - Pricing/billing 5 zorunlu microcopy (avukat şartı, Epic #448 §3.9 N-09)
 *   - Footer: refund-policy + mesafeli-satis-sozlesmesi link
 *
 * LS hesap konfigüre değilse: tier matrix render olur ama "Yakında" badge
 * + checkout disabled. Kullanıcı durumu görür ama satın alamaz.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Check,
  CreditCard,
  ExternalLink,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiException } from "@/lib/api";
import {
  createCheckout,
  getSubscription,
  isBillingNotConfigured,
  listPlans,
  type BillingPlan,
  type SubscriptionDetail,
} from "@/lib/billing-api";
import { formatTrDate } from "@/lib/format";


type Cycle = "monthly" | "yearly";

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  trialing: { label: "Deneme dönemi", color: "bg-blue-500/10 text-blue-700" },
  active: { label: "Aktif", color: "bg-green-500/10 text-green-700" },
  past_due: { label: "Ödeme gecikti", color: "bg-amber-500/10 text-amber-700" },
  cancelled: { label: "İptal edildi", color: "bg-red-500/10 text-red-700" },
  expired: { label: "Süresi doldu", color: "bg-slate-500/10 text-slate-700" },
};


export default function BillingHubPage() {
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSubscription] = useState<SubscriptionDetail | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [cycle, setCycle] = useState<Cycle>("monthly");
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [billingDisabled, setBillingDisabled] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [plansRes, subRes] = await Promise.all([
          listPlans(),
          getSubscription().catch(() => null),
        ]);
        setPlans(plansRes.plans);
        setSubscription(subRes);
      } catch (err) {
        console.error("billing load failed", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleCheckout(planCode: string) {
    setCheckoutLoading(planCode);
    try {
      const res = await createCheckout(planCode, cycle);
      window.open(res.checkout_url, "_blank", "noopener");
      toast.success("Ödeme sayfası yeni sekmede açıldı.");
    } catch (err) {
      if (isBillingNotConfigured(err)) {
        setBillingDisabled(true);
        toast.info(
          "Ücretli abonelik sistemi yakında aktif olacak. Şu an kayıt alamıyoruz.",
        );
      } else {
        const msg =
          err instanceof ApiException
            ? err.message
            : "Bir hata oluştu, lütfen tekrar deneyin.";
        toast.error(msg);
      }
    } finally {
      setCheckoutLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const paidPlans = plans.filter((p) => p.code !== "free");

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Plan ve Faturalama</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Lemon Squeezy üzerinden güvenli ödeme — KDV/VAT global olarak Lemon Squeezy
          tarafından kesilir.
        </p>
      </div>

      {/* Mevcut abonelik card */}
      {subscription ? (
        <CurrentSubscriptionCard subscription={subscription} />
      ) : (
        <Card className="border-dashed">
          <CardHeader>
            <CardDescription>
              Aktif aboneliğin yok. Aşağıdan bir plan seçerek ücretsiz denemeye
              başlayabilirsin.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Cycle toggle */}
      <div className="flex items-center justify-between gap-4">
        <Tabs value={cycle} onValueChange={(v) => setCycle(v as Cycle)}>
          <TabsList>
            <TabsTrigger value="monthly">Aylık</TabsTrigger>
            <TabsTrigger value="yearly">
              Yıllık <Badge variant="secondary" className="ml-1.5 text-[10px]">2 ay bedava</Badge>
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="text-xs text-muted-foreground">
          USD primary · TL referans · İlk 14 gün iade Lemon Squeezy üzerinden
        </div>
      </div>

      {billingDisabled && (
        <Card className="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <CardContent className="py-3 text-sm">
            <strong>Ödeme sistemi kurulum aşamasında.</strong> Yakında aktif olacak;
            hesabını şimdiden açtın diye teşekkürler.
          </CardContent>
        </Card>
      )}

      {/* Tier grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {paidPlans.map((plan) => (
          <PlanCard
            key={plan.code}
            plan={plan}
            cycle={cycle}
            onCheckout={() => handleCheckout(plan.code)}
            isCheckingOut={checkoutLoading === plan.code}
            isCurrent={subscription?.plan_code === plan.code}
            disabled={billingDisabled}
          />
        ))}
      </div>

      {/* Avukat şartı 5 microcopy */}
      <Card className="bg-muted/30">
        <CardContent className="space-y-3 py-4 text-xs text-muted-foreground">
          <p>
            <strong className="text-foreground">İlk 14 gün iade:</strong> Yıllık
            aboneliklerde tam iade. Aylık aboneliklerde kullanılmamış dönem için.
            İade işlemleri Lemon Squeezy üzerinden yürütülür.
          </p>
          <p>
            <strong className="text-foreground">Vergi:</strong> KDV/VAT/sales tax
            müşteri lokasyonuna göre Lemon Squeezy (Merchant of Record) tarafından
            kesilir ve faturada ayrı kalem olarak gösterilir.
          </p>
          <p>
            <strong className="text-foreground">İptal:</strong> Dilediğin zaman
            Lemon Squeezy Customer Portal'dan abonelik yönetebilirsin — iptal
            sonrası mevcut dönem sonuna kadar erişimin devam eder.
          </p>
          <p>
            Detaylı bilgi:{" "}
            <Link
              href="/legal/refund-policy"
              className="underline hover:text-foreground"
              target="_blank"
            >
              İade Politikası
            </Link>{" "}
            ·{" "}
            <Link
              href="/legal/mesafeli-satis-sozlesmesi"
              className="underline hover:text-foreground"
              target="_blank"
            >
              Mesafeli Satış Sözleşmesi
            </Link>{" "}
            ·{" "}
            <Link
              href="/legal/tos"
              className="underline hover:text-foreground"
              target="_blank"
            >
              Hizmet Koşulları
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}


function CurrentSubscriptionCard({
  subscription,
}: {
  subscription: SubscriptionDetail;
}) {
  const status = STATUS_LABELS[subscription.status] || {
    label: subscription.status,
    color: "bg-slate-500/10 text-slate-700",
  };
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="size-5 text-primary" />
              {subscription.plan_name}
            </CardTitle>
            <CardDescription className="mt-1">
              {subscription.billing_cycle === "yearly" ? "Yıllık" : "Aylık"} abonelik
              {" · "}
              <Badge variant="secondary" className={status.color}>
                {status.label}
              </Badge>
            </CardDescription>
          </div>
          <Button asChild variant="outline">
            <Link href="/app/billing/manage">
              <ExternalLink className="size-4" />
              Aboneliği yönet
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Sıradaki yenileme</dt>
            <dd className="mt-0.5 font-medium tabular-nums">
              {formatTrDate(subscription.current_period_end)}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Sıradaki fatura</dt>
            <dd className="mt-0.5 font-medium tabular-nums">
              ${subscription.next_invoice_amount_usd.toFixed(2)}
              {subscription.next_invoice_amount_tl_display_ref && (
                <span className="ml-1 text-xs text-muted-foreground">
                  (~{subscription.next_invoice_amount_tl_display_ref.toFixed(0)} TL)
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Koltuk</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{subscription.seat_count}</dd>
          </div>
          {subscription.trial_ends_at && (
            <div>
              <dt className="text-muted-foreground">Trial bitiş</dt>
              <dd className="mt-0.5 font-medium tabular-nums">
                {formatTrDate(subscription.trial_ends_at)}
              </dd>
            </div>
          )}
        </dl>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2 border-t pt-4 text-xs text-muted-foreground">
        <Link
          href="/app/billing/invoices"
          className="underline hover:text-foreground"
        >
          Faturalarımı gör
        </Link>
        <span>·</span>
        <span>
          İade işlemleri Lemon Squeezy üzerinden yürütülür ({subscription.payment_provider})
        </span>
      </CardFooter>
    </Card>
  );
}


function PlanCard({
  plan,
  cycle,
  onCheckout,
  isCheckingOut,
  isCurrent,
  disabled,
}: {
  plan: BillingPlan;
  cycle: Cycle;
  onCheckout: () => void;
  isCheckingOut: boolean;
  isCurrent: boolean;
  disabled: boolean;
}) {
  const priceUsd =
    cycle === "yearly" ? plan.price_usd_yearly : plan.price_usd_monthly;
  const priceTl =
    cycle === "yearly"
      ? plan.price_tl_display_yearly
      : plan.price_tl_display_monthly;
  const features = plan.features as Record<string, unknown>;

  const isPro = plan.code === "pro";

  return (
    <Card className={isPro ? "border-primary/30 shadow-md" : ""}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{plan.name}</CardTitle>
          {isPro && <Badge>En popüler</Badge>}
          {isCurrent && <Badge variant="secondary">Mevcut plan</Badge>}
        </div>
        <CardDescription>
          {plan.tier === "agency"
            ? "Ajanslar için multi-seat — marka başına stil profili"
            : plan.tier === "pro"
              ? "Her gün kullanan ciddi creator için"
              : "İlk paid tier — value entry"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums">${priceUsd}</span>
            <span className="text-sm text-muted-foreground">
              /{cycle === "yearly" ? "yıl" : "ay"}
            </span>
          </div>
          {priceTl && (
            <p className="mt-1 text-xs text-muted-foreground">
              ~{priceTl.toFixed(0)} TL
              {cycle === "yearly" && " (yıllık)"}
            </p>
          )}
          {!plan.available && (
            <p className="mt-1 text-xs font-medium text-amber-600">
              Yakında — Lemon Squeezy konfigürasyonu tamamlanıyor
            </p>
          )}
        </div>

        <ul className="space-y-1.5 text-sm">
          <Feature
            ok
            text={`${plan.monthly_generation_limit.toLocaleString("tr-TR")} üretim/ay`}
          />
          {plan.seat_count > 1 && (
            <Feature ok text={`${plan.seat_count} koltuk`} />
          )}
          {(features.allowed_models as string[] | undefined)?.length && (
            <Feature
              ok
              text={
                (features.allowed_models as string[]).length > 1
                  ? "Premium model (Claude Haiku 4.5)"
                  : "DeepSeek V3 (default)"
              }
            />
          )}
          <Feature
            ok={Boolean(features.comparison_mode)}
            text="Comparison mode (Archive vs Current)"
          />
          <Feature
            ok={Boolean(features.style_profiles)}
            text={
              features.style_profiles_slots
                ? `Stil profili (${features.style_profiles_slots} slot)`
                : "Stil profili"
            }
          />
          <Feature
            ok={Boolean(features.visual_features)}
            text="Görsel destekli içerik"
          />
          <Feature
            ok={Boolean(features.analysis_output)}
            text="Analysis + Content Calendar"
          />
        </ul>

        <p className="text-xs text-muted-foreground">
          İlk 14 gün iade · Lemon Squeezy hosted checkout
        </p>
      </CardContent>
      <CardFooter>
        <Button
          className="w-full"
          variant={isPro ? "default" : "outline"}
          onClick={onCheckout}
          disabled={disabled || !plan.available || isCheckingOut || isCurrent}
        >
          {isCheckingOut ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Yönlendiriliyor…
            </>
          ) : isCurrent ? (
            "Aktif plan"
          ) : !plan.available || disabled ? (
            "Yakında"
          ) : (
            <>
              <CreditCard className="size-4" />
              {plan.tier === "agency" ? "Hemen başla" : "3 gün ücretsiz dene"}
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}


function Feature({ ok, text }: { ok: boolean; text: string }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <Check className="mt-0.5 size-4 flex-shrink-0 text-green-600" />
      ) : (
        <X className="mt-0.5 size-4 flex-shrink-0 text-muted-foreground/50" />
      )}
      <span className={ok ? "" : "text-muted-foreground/60 line-through"}>
        {text}
      </span>
    </li>
  );
}
