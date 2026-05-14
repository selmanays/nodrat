"use client";

import { BookOpen, ExternalLink, User } from "lucide-react";

import { InsufficiencySignal } from "./InsufficiencySignal";
import { MessageActions } from "./MessageActions";
import { SourceTypeBadge } from "./SourceTypeBadge";
import { ThinkingPanel, type DiscoveredSource, type ThinkingStep } from "./ThinkingPanel";
import { WikipediaConsentCard } from "./WikipediaConsentCard";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type {
  ChatMessage as ChatMessageType,
  ChatMessageSource,
  WikipediaFallbackResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * ChatMessage — bir mesaj (user veya assistant).
 *
 * User: sağ-aligned, primary bg
 * Assistant: sol-aligned, thinking panel + content + sources
 *
 * Streaming assistant mesajı için: thinking_steps + sources canlı güncellenir.
 */

export interface ChatMessageProps {
  message?: ChatMessageType;
  // Streaming durumu için (assistant):
  streaming?: {
    role: "assistant";
    content: string;
    thinking_steps: ThinkingStep[];
    sources_discovered: DiscoveredSource[];
    is_streaming: boolean;
  };
  // #813 Faz 2 2B — Wikipedia consent context (sadece persisted assistant mesajları için)
  conversationId?: string;
  onConsentResponse?: (resp: WikipediaFallbackResponse) => void;
  // #815 Faz 2 2D — Hybrid insufficiency banner: kullanıcı "Wikipedia'dan bak"
  // tıklarsa parent yeni chat mesajı submit eder
  onAskWikipedia?: (originalContent: string) => void;
  className?: string;
}

export function ChatMessage({
  message,
  streaming,
  conversationId,
  onConsentResponse,
  onAskWikipedia,
  className,
}: ChatMessageProps) {
  if (streaming) {
    return (
      <AssistantMessageView
        messageId={null}
        content={streaming.content}
        thinkingSteps={streaming.thinking_steps}
        sources={streaming.sources_discovered}
        isStreaming={streaming.is_streaming}
        className={className}
      />
    );
  }

  if (!message) return null;

  if (message.role === "user") {
    return <UserMessageView content={message.content} className={className} />;
  }

  // #813 Faz 2 2B — consent_pending detect (Wikipedia fallback bekliyor)
  const consentEntry = (message.thinking_steps || []).find(
    (s) => s.phase === "consent_pending" && s.type === "wikipedia_fallback",
  );
  const isPendingConsent =
    Boolean(consentEntry) && !message.content && conversationId != null;

  // #815 Faz 2 2D — Hybrid insufficiency banner (cevap üretildi ama
  // confidence orta; Wikipedia teklifi göster)
  const hybridSignal = (message.thinking_steps || []).find(
    (s) => s.phase === "hybrid_signal" && s.type === "wikipedia_offer",
  );

  return (
    <AssistantMessageView
      messageId={message.id}
      content={message.content}
      thinkingSteps={(message.thinking_steps as ThinkingStep[] | null) || []}
      sources={(message.sources_used as ChatMessageSource[] | null) || []}
      isStreaming={false}
      // Halu/action önceden bildirildiyse butonları işaretle
      // (#802 S1C — ChatMessage interface'i bu alanları taşır)
      alreadyFlagged={Boolean(
        (message as unknown as { halu_flagged_at?: string | null })
          .halu_flagged_at,
      )}
      alreadyAction={
        (message as unknown as { user_action?: string | null }).user_action ?? null
      }
      consentCard={
        isPendingConsent && conversationId ? (
          <WikipediaConsentCard
            conversationId={conversationId}
            assistantMessageId={message.id}
            topicQuery={consentEntry?.topic_query}
            onResponse={(resp) => onConsentResponse?.(resp)}
          />
        ) : null
      }
      insufficiencyCard={
        hybridSignal && onAskWikipedia ? (
          <InsufficiencySignal
            message={
              typeof (hybridSignal as { message?: unknown }).message === "string"
                ? ((hybridSignal as { message?: string }).message as string)
                : undefined
            }
            onAskWikipedia={() => onAskWikipedia(message.content)}
          />
        ) : null
      }
      className={className}
    />
  );
}

function UserMessageView({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={cn("flex justify-end gap-3", className)}>
      <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-primary px-4 py-2.5 text-primary-foreground">
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
      </div>
      <Avatar className="size-8 shrink-0">
        <AvatarFallback>
          <User className="size-4" />
        </AvatarFallback>
      </Avatar>
    </div>
  );
}

function AssistantMessageView({
  messageId,
  content,
  thinkingSteps,
  sources,
  isStreaming,
  alreadyFlagged = false,
  alreadyAction = null,
  consentCard = null,
  insufficiencyCard = null,
  className,
}: {
  messageId: string | null;
  content: string;
  thinkingSteps: ThinkingStep[];
  sources: ChatMessageSource[] | DiscoveredSource[];
  isStreaming: boolean;
  alreadyFlagged?: boolean;
  alreadyAction?: string | null;
  consentCard?: React.ReactNode;
  insufficiencyCard?: React.ReactNode;
  className?: string;
}) {
  // Cast — DiscoveredSource (streaming) ChatMessageSource ile uyumlu
  const typedSources = sources as ChatMessageSource[];
  return (
    <div className={cn("flex gap-3", className)}>
      <Avatar className="size-8 shrink-0">
        <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
          N
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 space-y-3">
        <ThinkingPanel
          steps={thinkingSteps}
          sources={sources as DiscoveredSource[]}
          isStreaming={isStreaming}
          defaultExpanded={isStreaming}
        />

        {/* #813 Faz 2 2B — Source type badge (haber / Wikipedia / hybrid) */}
        {!isStreaming && content && typedSources.length > 0 && (
          <SourceTypeBadge sources={typedSources} />
        )}

        {content && (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {renderCitations(content)}
            </p>
          </div>
        )}

        {/* #813 Faz 2 2B — Wikipedia consent CTA (content boş + consent_pending) */}
        {consentCard}

        {/* #815 Faz 2 2D — Hybrid insufficiency banner */}
        {insufficiencyCard}

        {!isStreaming && typedSources.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Kaynaklar
            </p>
            <div className="flex flex-wrap gap-2">
              {typedSources.map((s, i) => (
                <SourcePill key={(s.article_id || s.url || "") + i} source={s} index={i} />
              ))}
            </div>
          </div>
        )}

        {/* S1C: Message action toolbar — sadece persisted (non-streaming) mesajlar */}
        {!isStreaming && messageId && content && (
          <MessageActions
            messageId={messageId}
            content={content}
            alreadyFlagged={alreadyFlagged}
            alreadyAction={alreadyAction}
          />
        )}
      </div>
    </div>
  );
}

function SourcePill({
  source: s,
  index: i,
}: {
  source: ChatMessageSource;
  index: number;
}) {
  const isWiki = s.source_type === "wikipedia";
  const citationLabel = isWiki ? `W${i + 1}` : `${i + 1}`;
  return (
    <a
      href={s.url || "#"}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
        isWiki
          ? "border-secondary/40 bg-secondary/10 hover:bg-secondary/20"
          : "border-border bg-card hover:bg-muted",
      )}
    >
      {isWiki ? (
        <BookOpen className="size-3 shrink-0 text-secondary-foreground" />
      ) : null}
      <span className="shrink-0 font-mono text-muted-foreground">
        [{citationLabel}]
      </span>
      <span className="shrink-0 font-medium">{s.source_name || "Kaynak"}</span>
      {s.title && (
        <span className="truncate text-muted-foreground">— {s.title}</span>
      )}
      <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
    </a>
  );
}

/**
 * [1][3] citation referanslarını span'lara çevir (link/popover S5b'de).
 * Şu an sadece display — tıklanabilirlik gelecek sprint.
 */
function renderCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(
      <sup
        key={m.index}
        className="ml-0.5 inline-block rounded bg-primary/10 px-1 text-[10px] font-semibold text-primary"
      >
        {m[1]}
      </sup>,
    );
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
