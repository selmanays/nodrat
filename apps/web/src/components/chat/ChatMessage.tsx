"use client";

import { ExternalLink, User } from "lucide-react";

import { MessageActions } from "./MessageActions";
import { ThinkingPanel, type DiscoveredSource, type ThinkingStep } from "./ThinkingPanel";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type { ChatMessage as ChatMessageType } from "@/lib/api";
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

export function ChatMessage({ message, streaming, className }: ChatMessageProps) {
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
      sources={(message.sources_used as DiscoveredSource[] | null) || []}
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
  isStreaming,
  alreadyFlagged = false,
  alreadyAction = null,
  className,
}: {
  messageId: string | null;
  content: string;
  thinkingSteps: ThinkingStep[];
  sources: DiscoveredSource[];
  isStreaming: boolean;
  alreadyFlagged?: boolean;
  alreadyAction?: string | null;
  className?: string;
}) {
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
          sources={sources}
          isStreaming={isStreaming}
          defaultExpanded={isStreaming}
        />

        {content && (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {renderCitations(content)}
            </p>
          </div>
        )}

        {!isStreaming && sources.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Kaynaklar
            </p>
            <div className="flex flex-wrap gap-2">
              {sources.map((s, i) => (
                <a
                  key={s.article_id + i}
                  href={s.url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs hover:bg-muted"
                >
                  <span className="shrink-0 font-mono text-muted-foreground">
                    [{i + 1}]
                  </span>
                  <span className="shrink-0 font-medium">
                    {s.source_name || "Kaynak"}
                  </span>
                  {s.title && (
                    <span className="truncate text-muted-foreground">
                      — {s.title}
                    </span>
                  )}
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
                </a>
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
