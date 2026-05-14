"use client";

import { AlertTriangle, BookOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * InsufficiencySignal — hybrid path (T_low <= score < T_high) için banner CTA.
 *
 * Cevap üretildi ama confidence skoru orta — kullanıcıya "Daha geniş bilgi
 * için Wikipedia'dan bakmamı ister misin?" CTA sun.
 *
 * Click → parent'a `onAskWikipedia` callback ile haber ver; parent yeni
 * chat mesajı gönderir ("Bu sorunun Wikipedia kaynaklı cevabı"). Yeni
 * mesaj planner tarafından general_knowledge olarak sınıflandırılacak ve
 * 2B Wikipedia fallback akışına girecek.
 *
 * Reddedilirse banner kaybolur, mesaj olduğu gibi kalır.
 *
 * Plan: #815 Faz 2 2D
 */
export interface InsufficiencySignalProps {
  message?: string;
  /** Kullanıcı "Wikipedia'dan bak" tıkladı — parent yeni mesaj submit eder. */
  onAskWikipedia: () => void;
  onDismiss?: () => void;
}

export function InsufficiencySignal({
  message,
  onAskWikipedia,
  onDismiss,
}: InsufficiencySignalProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const handleAccept = () => {
    setDismissed(true);
    onAskWikipedia();
  };

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-50/30 px-3 py-2 text-xs dark:bg-amber-950/20">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground">
          {message ||
            "Bu konuda kaynaklarım kısıtlı kaldı. Wikipedia'dan da bakmamı ister misin?"}
        </p>
      </div>
      <div className="flex shrink-0 gap-1.5">
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-2 text-[11px]"
          onClick={handleAccept}
        >
          <BookOpen className="size-3" />
          Wikipedia
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-[11px]"
          onClick={handleDismiss}
        >
          Hayır
        </Button>
      </div>
    </div>
  );
}
