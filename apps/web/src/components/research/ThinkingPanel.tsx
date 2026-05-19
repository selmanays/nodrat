"use client";

import { CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * ThinkingPanel — Perplexity-style "düşünüyor" akışı.
 *
 * SSE event'lerden gelen thinking_step + source_discovered'ları sıralı göster.
 * Default: collapsed (özet) — tık ile expand.
 * Streaming biterse "done" işareti, son adım icon değişir.
 */

export interface ThinkingStep {
  phase: string;
  detail: string;
  latency_ms?: number;
}

export interface DiscoveredSource {
  article_id: string;
  title?: string;
  source_name?: string;
  url?: string;
  chunk_id?: string;
  relevance?: number;
}

export interface ThinkingPanelProps {
  steps: ThinkingStep[];
  sources: DiscoveredSource[];
  isStreaming: boolean;
  defaultExpanded?: boolean;
  className?: string;
}

// Backend `app_research_stream.py` _log_step fazlarıyla BİREBİR. Bilinmeyen
// faz zaten ham string'e düşer (geriye uyumlu); bu harita yalnız okunur
// Türkçe etiket/ikon verir. #1059 — gözlem-only şeffaflık.
const PHASE_LABEL: Record<string, string> = {
  context_check: "Bağlam kontrolü",
  query_rewrite: "Bağlamlı sorgu",
  retrieval_forced: "Kaynak araması zorunlu",
  planner: "Sorgu planlanıyor",
  retrieve: "Kaynaklar aranıyor",
  tool_use: "Kaynak araması",
  tool_result: "Kaynak sonucu",
  grounding_retry: "Düzeltici kaynak turu",
  citation_filter: "Atıf doğrulama",
  cited_only_refused: "Kaynaksız cevap reddi",
  generating: "Yanıt yazılıyor",
};

const PHASE_ICON: Record<string, string> = {
  context_check: "🔗",
  query_rewrite: "🧭",
  retrieval_forced: "🎯",
  planner: "🧠",
  retrieve: "📚",
  tool_use: "🔍",
  tool_result: "📄",
  grounding_retry: "♻️",
  citation_filter: "✅",
  cited_only_refused: "⛔",
  generating: "✍️",
};

export function ThinkingPanel({
  steps,
  sources,
  isStreaming,
  defaultExpanded = false,
  className,
}: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (steps.length === 0 && sources.length === 0) return null;

  const lastStep = steps[steps.length - 1];
  const summary = isStreaming
    ? lastStep
      ? `${PHASE_ICON[lastStep.phase] || "•"} ${PHASE_LABEL[lastStep.phase] || lastStep.phase}...`
      : "Düşünüyor..."
    : `Tamamlandı (${steps.length} adım, ${sources.length} kaynak)`;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-muted/30 px-3 py-2 text-sm",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
      >
        {isStreaming ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
        ) : (
          <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />
        )}
        <span className="flex-1 text-sm">{summary}</span>
        {expanded ? (
          <ChevronDown className="size-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="mt-3 space-y-2 border-t border-border/50 pt-3">
          {steps.map((step, i) => {
            const isLast = i === steps.length - 1 && isStreaming;
            const icon = PHASE_ICON[step.phase] || "•";
            const label = PHASE_LABEL[step.phase] || step.phase;
            return (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="mt-0.5 shrink-0">{icon}</span>
                <div className="flex-1 leading-relaxed">
                  <span className="font-medium">{label}</span>
                  {step.detail && (
                    <span className="text-muted-foreground"> — {step.detail}</span>
                  )}
                  {step.latency_ms != null && step.latency_ms > 0 && (
                    <span className="ml-1.5 text-muted-foreground/70">
                      ({step.latency_ms}ms)
                    </span>
                  )}
                </div>
                {isLast && <Loader2 className="size-3 animate-spin" />}
              </div>
            );
          })}

          {sources.length > 0 && (
            <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Bulunan kaynaklar
              </p>
              {sources.map((s, i) => (
                <div key={s.article_id + i} className="text-xs">
                  <span className="font-mono text-muted-foreground">[{i + 1}]</span>{" "}
                  <span className="font-medium">{s.source_name || "Kaynak"}</span>
                  {s.title && (
                    <span className="text-muted-foreground"> — {s.title}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
