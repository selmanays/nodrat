"use client";

import { ArrowUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/**
 * ChatInput — Perplexity-style centered input.
 *
 * Auto-resize textarea (1-6 satır), Cmd/Ctrl+Enter veya Enter (shift YOK) → submit.
 * Loading state disable + spinner.
 */
export interface ChatInputProps {
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  onSubmit: (text: string) => void;
  autoFocus?: boolean;
  className?: string;
}

export function ChatInput({
  placeholder = "Bir soru sor...",
  disabled = false,
  loading = false,
  onSubmit,
  autoFocus = false,
  className,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize (1-6 satır)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = 24 * 6 + 24; // 6 satır + padding
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value]);

  // AutoFocus
  useEffect(() => {
    if (autoFocus && textareaRef.current && !disabled) {
      textareaRef.current.focus();
    }
  }, [autoFocus, disabled]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || loading) return;
    onSubmit(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      className={cn(
        "relative flex w-full items-end gap-2 rounded-2xl border border-border bg-card/60 px-4 py-3 shadow-sm backdrop-blur transition-all focus-within:border-primary/40 focus-within:shadow-md",
        disabled && "opacity-60",
        className,
      )}
    >
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || loading}
        rows={1}
        className="min-h-[24px] flex-1 resize-none border-0 bg-transparent p-0 text-base shadow-none focus-visible:ring-0"
      />
      <Button
        type="button"
        size="icon"
        onClick={handleSubmit}
        disabled={!value.trim() || disabled || loading}
        className="size-9 shrink-0 rounded-full"
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <ArrowUp className="size-4" />
        )}
        <span className="sr-only">Gönder</span>
      </Button>
    </div>
  );
}
