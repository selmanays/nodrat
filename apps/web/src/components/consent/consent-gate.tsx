"use client";

/**
 * ConsentGate (#453) — KVKK m.9 yurt dışı transfer açık rıza gate.
 *
 * App layout'unda kullanıcı authenticated olduktan sonra render edilir.
 * Backend `/app/consent/status` çağrılır:
 *   - has_consent=false              → modal force-show (blocking)
 *   - needs_re_consent=true          → modal banner-style (dismissible)
 *   - has_consent=true && !needs_re  → render children direkt
 *
 * Backend (#470 require_foreign_transfer_consent dependency) zaten
 * server-side enforcement yapar; bu component sadece UX (5-akış 403'lerden
 * önce kullanıcıyı bilgilendirir).
 */

import { useEffect, useState } from "react";

import { ApiException } from "@/lib/api";
import {
  getConsentStatus,
  type ConsentStatus,
} from "@/lib/consent-api";
import { ForeignTransferConsentModal } from "./foreign-transfer-consent-modal";

export function ConsentGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<ConsentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    getConsentStatus()
      .then((s) => {
        setStatus(s);
        // Modal koşulları:
        //   1. has_consent = false → blocking modal
        //   2. needs_re_consent = true → banner-style modal
        if (!s.has_consent || s.needs_re_consent) {
          setModalOpen(true);
        }
      })
      .catch((err: ApiException) => {
        // Silent fail — backend down vs. consent kontrolü engellemez
        console.warn("consent status fetch failed:", err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  function handleGranted(result: { consent_at: string; version: string }) {
    if (status) {
      setStatus({
        ...status,
        has_consent: true,
        consent_at: result.consent_at,
        version: result.version,
        revoked_at: null,
        needs_re_consent: false,
      });
    }
    setModalOpen(false);
  }

  if (loading) {
    return <>{children}</>;
  }

  return (
    <>
      {children}
      {status && (
        <ForeignTransferConsentModal
          status={status}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onGranted={handleGranted}
        />
      )}
    </>
  );
}
