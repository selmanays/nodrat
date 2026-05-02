"use client";

import { useState } from "react";
import { AlertTriangle, Mail } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiException, requestVerifyResend } from "@/lib/api";

export function EmailVerifyBanner({ email }: { email: string }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleResend() {
    setSending(true);
    try {
      await requestVerifyResend(email);
      setSent(true);
      toast.success(
        "Doğrulama maili gönderildi (kayıtlı ise). Kutunu kontrol et.",
      );
    } catch (err) {
      toast.error((err as ApiException).message || "Gönderim başarısız");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="border-b border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40">
      <div className="container flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
          <span className="text-amber-900 dark:text-amber-100">
            <strong>{email}</strong> adresini doğrulamadın. Üretim yapmak için
            doğrulama gerekli.
          </span>
        </div>
        {sent ? (
          <span className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
            <Mail className="h-3 w-3" /> Mail gönderildi
          </span>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleResend()}
            disabled={sending}
            className="border-amber-300 text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200"
          >
            {sending ? "Gönderiliyor…" : "Doğrulama mailini tekrar gönder"}
          </Button>
        )}
      </div>
    </div>
  );
}
