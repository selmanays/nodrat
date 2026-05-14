"use client";

import { BookOpen, Check, Loader2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  submitWikipediaConsent,
  type WikipediaFallbackResponse,
} from "@/lib/api";

/**
 * Wikipedia fallback CTA — inline kart (modal değil) assistant mesajının
 * içine render edilir. Backend stream `requires_user_consent` event'i ile
 * stub message oluşturduğunda, ChatMessage onu detect eder ve bu component
 * render edilir.
 *
 * 2 buton:
 *  - "Evet, Wikipedia'dan bak" → submitWikipediaConsent(true) → Wikipedia kaynaklı cevap
 *  - "Hayır, gerek yok"       → submitWikipediaConsent(false) → kısa refusal
 *
 * Cevap geldiğinde parent (ChatMessage / ChatThread page) message'ı refresh eder
 * (onResponse callback ile).
 *
 * Plan: #813 Faz 2 2B
 */
export interface WikipediaConsentCardProps {
  conversationId: string;
  assistantMessageId: string;
  topicQuery?: string;
  /** Cevap geldikten sonra parent'a haber ver — message refresh tetiklenir. */
  onResponse: (resp: WikipediaFallbackResponse) => void;
}

export function WikipediaConsentCard({
  conversationId,
  assistantMessageId,
  topicQuery,
  onResponse,
}: WikipediaConsentCardProps) {
  const [submitting, setSubmitting] = useState<"yes" | "no" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async (accepted: boolean) => {
    setSubmitting(accepted ? "yes" : "no");
    setError(null);
    try {
      const resp = await submitWikipediaConsent(
        conversationId,
        assistantMessageId,
        accepted,
      );
      onResponse(resp);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "İstek başarısız");
      setSubmitting(null);
    }
  };

  return (
    <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-4">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-secondary/20 text-secondary-foreground">
          <BookOpen className="size-4" />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <p className="text-sm font-medium">
              Bu konuda güncel haber arşivimde yeterli kaynak yok
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {topicQuery ? `"${topicQuery}" sorgusu için ` : ""}
              Wikipedia&apos;dan kaynaklı bakabilirim — kaynak Wikipedia (CC BY-SA),
              güncel olmayan içerik olabilir. İster misin?
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="default"
              onClick={() => handleClick(true)}
              disabled={submitting !== null}
            >
              {submitting === "yes" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              Evet, Wikipedia&apos;dan bak
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleClick(false)}
              disabled={submitting !== null}
            >
              {submitting === "no" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <X className="size-3.5" />
              )}
              Hayır, gerek yok
            </Button>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      </div>
    </div>
  );
}
