"use client";

import React from "react";
import { BookOpen, ChevronRight, ExternalLink, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { MessageActions } from "./MessageActions";
import { SourceTypeBadge } from "./SourceTypeBadge";
import { ThinkingPanel, type DiscoveredSource, type ThinkingStep } from "./ThinkingPanel";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type {
  ChatMessage as ChatMessageType,
  ChatMessageSource,
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
  className?: string;
}

export function ChatMessage({
  message,
  streaming,
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

  return (
    <AssistantMessageView
      messageId={message.id}
      content={message.content}
      thinkingSteps={(message.thinking_steps as ThinkingStep[] | null) || []}
      sources={(message.sources_used as ChatMessageSource[] | null) || []}
      sourcesConsidered={
        (message.sources_considered as ChatMessageSource[] | null) || []
      }
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
  sourcesConsidered = [],
  isStreaming,
  alreadyFlagged = false,
  alreadyAction = null,
  className,
}: {
  messageId: string | null;
  content: string;
  thinkingSteps: ThinkingStep[];
  sources: ChatMessageSource[] | DiscoveredSource[];
  sourcesConsidered?: ChatMessageSource[];
  isStreaming: boolean;
  alreadyFlagged?: boolean;
  alreadyAction?: string | null;
  className?: string;
}) {
  // Cast — DiscoveredSource (streaming) ChatMessageSource ile uyumlu
  const typedSources = sources as ChatMessageSource[];
  // #845 — "Kaynaklar" SADECE cevapta cite edilen (sources_used).
  // sources_considered = taranan tüm kaynaklar → collapsed. Cite edilmemiş
  // (used dışı kalan) kaynaklar collapse altında gösterilir.
  const usedKeys = new Set(
    typedSources.map((s) => s.article_id || s.url || s.title || ""),
  );
  const extraConsidered = sourcesConsidered.filter(
    (s) => !usedKeys.has(s.article_id || s.url || s.title || ""),
  );
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
          <div className="prose prose-sm max-w-none break-words text-sm leading-relaxed dark:prose-invert prose-p:my-2 prose-headings:mt-3 prose-headings:mb-1.5 prose-headings:text-sm prose-headings:font-semibold prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-strong:font-semibold">
            <MarkdownWithCitations content={content} />
          </div>
        )}

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

        {/* #845 — Cevapta cite edilmemiş ama taranan kaynaklar: collapsed */}
        {!isStreaming && extraConsidered.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer list-none text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
              <span className="inline-flex items-center gap-1">
                <ChevronRight className="size-3 transition-transform group-open:rotate-90" />
                Taranan diğer kaynaklar ({extraConsidered.length})
              </span>
            </summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {extraConsidered.map((s, i) => (
                <SourcePill
                  key={(s.article_id || s.url || "") + "c" + i}
                  source={s}
                  index={typedSources.length + i}
                />
              ))}
            </div>
          </details>
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
  // #851 — gerçek global cite token'ı göster (cevap metniyle birebir
  // eşleşsin). Eski mesajlarda cite yoksa pozisyonel fallback.
  const citationLabel = s.cite
    ? s.cite.replace(/[[\]]/g, "")
    : isWiki
      ? `W${i + 1}`
      : `${i + 1}`;
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
 * #829 — Markdown render (react-markdown + remark-gfm) + [N] citation sup.
 * Eski kod plain text + sadece [N]→sup yapıyordu; LLM markdown üretiyor
 * (bold/paragraf/liste/başlık) ama ham görünüyordu. ReactMarkdown ile
 * render, text node'larındaki [N] referansları sup'a çevrilir.
 */
function renderCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /\[([WW]?\d+)\]/g; // [1] veya [W1] (Wikipedia)
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(
      <sup
        key={`c${k++}`}
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

/** ReactMarkdown children içindeki string node'larda [N] → sup. */
function processCitations(children: React.ReactNode): React.ReactNode {
  if (typeof children === "string") return renderCitations(children);
  if (Array.isArray(children))
    return children.map((c, i) =>
      typeof c === "string" ? (
        <React.Fragment key={i}>{renderCitations(c)}</React.Fragment>
      ) : (
        c
      ),
    );
  return children;
}

function MarkdownWithCitations({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p>{processCitations(children)}</p>,
        li: ({ children }) => <li>{processCitations(children)}</li>,
        strong: ({ children }) => (
          <strong>{processCitations(children)}</strong>
        ),
        em: ({ children }) => <em>{processCitations(children)}</em>,
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2"
          >
            {children}
          </a>
        ),
        h1: ({ children }) => <h3>{processCitations(children)}</h3>,
        h2: ({ children }) => <h3>{processCitations(children)}</h3>,
        h3: ({ children }) => <h3>{processCitations(children)}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
