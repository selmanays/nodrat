"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

const STORAGE_KEY = "nodrat_cookie_consent_v1";

type Consent = {
  functional: boolean;
  analytics: boolean;
  marketing: boolean;
  decided_at: string;
};

function loadConsent(): Consent | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Consent;
  } catch {
    return null;
  }
}

function saveConsent(c: Consent) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(c));
}

export function CookieBanner() {
  const [hidden, setHidden] = useState(true);
  const [showDetails, setShowDetails] = useState(false);
  const [functional, setFunctional] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  useEffect(() => {
    const existing = loadConsent();
    if (existing === null) {
      setHidden(false);
    } else {
      setFunctional(existing.functional);
      setAnalytics(existing.analytics);
      setMarketing(existing.marketing);
    }
  }, []);

  function decide(c: { functional: boolean; analytics: boolean; marketing: boolean }) {
    saveConsent({
      ...c,
      decided_at: new Date().toISOString(),
    });
    setFunctional(c.functional);
    setAnalytics(c.analytics);
    setMarketing(c.marketing);
    setHidden(true);
  }

  function acceptAll() {
    decide({ functional: true, analytics: true, marketing: true });
  }

  function rejectAll() {
    decide({ functional: false, analytics: false, marketing: false });
  }

  function saveCustom() {
    decide({ functional, analytics, marketing });
  }

  if (hidden) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="cookie-banner-title"
      className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-3xl rounded-lg border border-border bg-card text-card-foreground shadow-lg md:bottom-6 md:left-6 md:right-6"
    >
      <div className="p-4 md:p-5">
        <h3 id="cookie-banner-title" className="text-sm font-semibold">
          🍪 Çerez tercihleriniz
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Hizmeti sunmak için zorunlu çerezleri kullanırız (oturum, güvenlik).
          İsteğe bağlı çerezler için tercihinizi belirtin. Detay için{" "}
          <Link href="/legal/cookies" className="text-brand-700 hover:underline">
            Çerez Politikası
          </Link>
          .
        </p>

        {showDetails && (
          <div className="mt-3 space-y-2 rounded-md bg-muted/40 p-3 text-xs">
            <div>
              <label className="flex items-center justify-between">
                <span>
                  <strong>Zorunlu</strong> · oturum, güvenlik (kapatılamaz)
                </span>
                <input type="checkbox" checked disabled className="cursor-not-allowed" />
              </label>
            </div>
            <div>
              <label className="flex items-center justify-between cursor-pointer">
                <span>
                  <strong>İşlevsel</strong> · tema, dil tercihi
                </span>
                <input
                  type="checkbox"
                  checked={functional}
                  onChange={(e) => setFunctional(e.target.checked)}
                />
              </label>
            </div>
            <div>
              <label className="flex items-center justify-between cursor-pointer">
                <span>
                  <strong>Analitik</strong> · anonim sayfa istatistikleri
                </span>
                <input
                  type="checkbox"
                  checked={analytics}
                  onChange={(e) => setAnalytics(e.target.checked)}
                />
              </label>
            </div>
            <div>
              <label className="flex items-center justify-between cursor-pointer">
                <span>
                  <strong>Pazarlama</strong> · şu an kullanılmıyor
                </span>
                <input
                  type="checkbox"
                  checked={marketing}
                  onChange={(e) => setMarketing(e.target.checked)}
                />
              </label>
            </div>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="accent" onClick={acceptAll}>
            Tümünü kabul et
          </Button>
          <Button size="sm" variant="outline" onClick={rejectAll}>
            Yalnızca zorunlu
          </Button>
          {!showDetails ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowDetails(true)}
            >
              Tercihleri özelleştir
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={saveCustom}>
              Tercihleri kaydet
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
