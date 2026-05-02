"use client";

/**
 * Hafif CSS-only info tooltip (#194).
 * - Hover + keyboard focus ile açılır
 * - Klavye erişilebilir (tabIndex=0)
 * - Mobile: tıklanabilir (focus → görünür)
 */

import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface InfoTooltipProps {
  /** Tooltip içeriği — kısa açıklama */
  content: string;
  /** İkon yerine sarılacak özel etiket (opsiyonel) */
  children?: React.ReactNode;
  /** Tooltip pozisyonu */
  side?: "top" | "bottom" | "right";
  className?: string;
}

export function InfoTooltip({
  content,
  children,
  side = "top",
  className,
}: InfoTooltipProps) {
  const positionClasses: Record<string, string> = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  return (
    <span
      className={cn(
        "group relative inline-flex items-center gap-1 align-middle",
        className,
      )}
      tabIndex={0}
    >
      {children ?? (
        <Info
          className="h-3.5 w-3.5 cursor-help text-muted-foreground transition-colors group-hover:text-foreground group-focus:text-foreground"
          aria-label="Bilgi"
        />
      )}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 hidden w-64 rounded-md border bg-popover px-3 py-2 text-xs leading-relaxed text-popover-foreground shadow-lg",
          "group-hover:block group-focus:block group-focus-within:block",
          positionClasses[side],
        )}
      >
        {content}
      </span>
    </span>
  );
}

/**
 * Term: yanına ⓘ ikonlu kısaltma. Örn: <Term label="NDCG@10" hint="..." />
 */
export function Term({
  label,
  hint,
  className,
}: {
  label: string;
  hint: string;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span>{label}</span>
      <InfoTooltip content={hint} />
    </span>
  );
}
