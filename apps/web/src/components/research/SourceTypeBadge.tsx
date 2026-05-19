"use client";

import { BookOpen, Newspaper, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ResearchMessageSource } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * SourceTypeBadge — assistant mesajının üstünde gösterilen "Kaynak: ..." chip.
 *
 * Modlar:
 *  - "news"     — sadece haber arşivi kaynaklı (default)
 *  - "wikipedia"— Wikipedia kaynaklı (2B Wikipedia fallback)
 *  - "hybrid"   — hem haber hem Wikipedia karışık (gelecek: 2D)
 *  - "none"     — kaynak yok (meta-query veya refusal)
 *
 * Mode `sources_used` array'inden derive edilir.
 *
 * Plan: #813 Faz 2 2B
 */
export interface SourceTypeBadgeProps {
  sources?: ResearchMessageSource[] | null;
  className?: string;
}

export function SourceTypeBadge({ sources, className }: SourceTypeBadgeProps) {
  const mode = deriveSourceMode(sources);

  const config = {
    news: {
      label: "Kaynak: Güncel haber arşivi",
      icon: Newspaper,
      variant: "default" as const,
    },
    wikipedia: {
      label: "Kaynak: Wikipedia",
      icon: BookOpen,
      variant: "secondary" as const,
    },
    hybrid: {
      label: "Kaynak: Haber + Wikipedia",
      icon: Sparkles,
      variant: "outline" as const,
    },
    none: {
      label: "Kaynak yok — konuşma context'inden",
      icon: Sparkles,
      variant: "outline" as const,
    },
  }[mode];

  const Icon = config.icon;

  return (
    <Badge
      variant={config.variant}
      className={cn("inline-flex items-center gap-1 text-[10px]", className)}
    >
      <Icon className="size-3" />
      {config.label}
    </Badge>
  );
}

function deriveSourceMode(
  sources?: ResearchMessageSource[] | null,
): "news" | "wikipedia" | "hybrid" | "none" {
  if (!sources || sources.length === 0) return "none";
  const types = new Set(sources.map((s) => s.source_type || "news"));
  const hasWiki = types.has("wikipedia");
  const hasNews = types.has("news");
  if (hasWiki && hasNews) return "hybrid";
  if (hasWiki) return "wikipedia";
  return "news";
}
