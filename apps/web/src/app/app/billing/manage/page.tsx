"use client";

/**
 * /app/billing/manage — LS Customer Portal redirect (#76).
 *
 * Backend GET /app/billing/portal-url → signed LS URL döner. Bu URL'e yeni
 * tab'da yönlendirilir (cancel, update card, change plan, invoice list).
 *
 * Aktif abonelik yoksa veya LS hesap konfigüre değilse uygun mesaj gösterilir.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, Loader2, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiException } from "@/lib/api";
import { getPortalUrl, isBillingNotConfigured } from "@/lib/billing-api";


type State =
  | { phase: "loading" }
  | { phase: "ready"; portalUrl: string }
  | { phase: "no_subscription" }
  | { phase: "not_configured" }
  | { phase: "error"; message: string };


export default function BillingManagePage() {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    (async () => {
      try {
        const res = await getPortalUrl();
        setState({ phase: "ready", portalUrl: res.portal_url });
      } catch (err) {
        if (isBillingNotConfigured(err)) {
          setState({ phase: "not_configured" });
        } else if (err instanceof ApiException && err.status === 404) {
          setState({ phase: "no_subscription" });
        } else {
          const msg =
            err instanceof ApiException
              ? err.message
              : "Bir hata oluştu, lütfen tekrar deneyin.";
          setState({ phase: "error", message: msg });
        }
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <Button variant="ghost" size="sm" asChild className="mb-2">
          <Link href="/app/billing">
            <ArrowLeft className="size-4" />
            Plan ve Faturalama
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">
          Aboneliği yönet
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          İptal, kart bilgisi güncelleme ve plan değişikliği Lemon Squeezy
          Customer Portal üzerinden yapılır.
        </p>
      </div>

      {state.phase === "loading" && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Lemon Squeezy portal URL hazırlanıyor…
        </div>
      )}

      {state.phase === "ready" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings2 className="size-5 text-primary" />
              Lemon Squeezy Customer Portal
            </CardTitle>
            <CardDescription>
              Yeni sekmede güvenli bir oturum açacak. Aşağıdaki işlemleri
              gerçekleştirebilirsin:
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-1.5 text-sm">
              <li>• Aboneliği iptal et (mevcut dönem sonuna kadar erişim)</li>
              <li>• Kart bilgisini güncelle</li>
              <li>• Plan değiştir (yıllık'a geçiş, upgrade/downgrade)</li>
              <li>• Geçmiş faturalarını gör + PDF indir</li>
              <li>• İade talep et (ilk 14 gün — TR Tüketici Kanunu uyumu)</li>
            </ul>
            <Button asChild className="w-full">
              <a
                href={state.portalUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="size-4" />
                Customer Portal'ı aç
              </a>
            </Button>
            <p className="text-xs text-muted-foreground">
              <strong>Güvenlik:</strong> URL'i sadece sen kullanabilirsin (signed
              link, kısa süreli geçerli). Yeni sekmeyi kapattığında oturum
              sonlanır.
            </p>
          </CardContent>
        </Card>
      )}

      {state.phase === "no_subscription" && (
        <Card>
          <CardHeader>
            <CardTitle>Aktif aboneliğin yok</CardTitle>
            <CardDescription>
              Henüz bir plan satın almadın. Plan ve Faturalama sayfasından
              başlayabilirsin.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/app/billing">Plan seç</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {state.phase === "not_configured" && (
        <Card className="border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40">
          <CardHeader>
            <CardTitle className="text-amber-900 dark:text-amber-100">
              Ödeme sistemi kurulum aşamasında
            </CardTitle>
            <CardDescription className="text-amber-800 dark:text-amber-200">
              Lemon Squeezy hesap kurulumu tamamlandığında abonelik yönetimi
              aktif olacak. Şu an mevcut hizmetin etkilenmiyor.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild>
              <Link href="/app/research">Üretime dön</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {state.phase === "error" && (
        <Card>
          <CardHeader>
            <CardTitle>Bir hata oluştu</CardTitle>
            <CardDescription>{state.message}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => window.location.reload()} variant="outline">
              Tekrar dene
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
