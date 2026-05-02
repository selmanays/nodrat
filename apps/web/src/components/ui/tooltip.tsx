"use client";

/**
 * Portal-based info tooltip (#194 + clipping fix #196).
 * - Hover + keyboard focus ile açılır
 * - Body'ye portal — overflow:hidden parent'lardan etkilenmez
 * - Klavye erişilebilir (tabIndex=0)
 * - Mobile: tıklanabilir (focus → görünür)
 */

import { Info } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface InfoTooltipProps {
  content: string;
  children?: React.ReactNode;
  side?: "top" | "bottom" | "right";
  className?: string;
}

interface Position {
  top: number;
  left: number;
  side: "top" | "bottom" | "right";
}

export function InfoTooltip({
  content,
  children,
  side = "top",
  className,
}: InfoTooltipProps) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = () => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const tooltipWidth = 256; // w-64
    const tooltipHeightEst = 80; // estimate
    const margin = 8;

    let actualSide = side;
    let top = 0;
    let left = 0;

    // Üst tarafa sığmazsa alta çevir
    if (side === "top" && rect.top < tooltipHeightEst + margin) {
      actualSide = "bottom";
    }

    if (actualSide === "top") {
      top = rect.top - margin;
      left = rect.left + rect.width / 2;
    } else if (actualSide === "bottom") {
      top = rect.bottom + margin;
      left = rect.left + rect.width / 2;
    } else {
      top = rect.top + rect.height / 2;
      left = rect.right + margin;
    }

    // Yan kenar guard'ı (sağa taşmayı engelle)
    const maxLeft = window.innerWidth - tooltipWidth / 2 - margin;
    const minLeft = tooltipWidth / 2 + margin;
    if (actualSide !== "right") {
      if (left > maxLeft) left = maxLeft;
      if (left < minLeft) left = minLeft;
    }

    setPosition({ top, left, side: actualSide });
  };

  const handleOpen = () => updatePosition();
  const handleClose = () => setPosition(null);

  // Scroll/resize dinleme
  useEffect(() => {
    if (!position) return;
    const update = () => updatePosition();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position]);

  const tooltipNode =
    position && mounted ? (
      <div
        role="tooltip"
        style={{
          position: "fixed",
          top: position.top,
          left: position.left,
          transform:
            position.side === "top"
              ? "translate(-50%, -100%)"
              : position.side === "bottom"
                ? "translate(-50%, 0)"
                : "translate(0, -50%)",
          zIndex: 9999,
          pointerEvents: "none",
        }}
        className="w-64 max-w-[calc(100vw-2rem)] rounded-md border bg-popover px-3 py-2 text-xs leading-relaxed text-popover-foreground shadow-lg"
      >
        {content}
      </div>
    ) : null;

  return (
    <>
      <span
        ref={triggerRef}
        className={cn("inline-flex cursor-help items-center align-middle", className)}
        tabIndex={0}
        onMouseEnter={handleOpen}
        onMouseLeave={handleClose}
        onFocus={handleOpen}
        onBlur={handleClose}
        aria-describedby={position ? "info-tooltip" : undefined}
      >
        {children ?? (
          <Info
            className="h-3.5 w-3.5 text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Bilgi"
          />
        )}
      </span>
      {mounted && tooltipNode && createPortal(tooltipNode, document.body)}
    </>
  );
}

/**
 * Term: yanına ⓘ ikonlu kısaltma. <Term label="NDCG@10" hint="..." />
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
