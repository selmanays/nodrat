/**
 * TrendStatusBadge — trend_state → Türkçe etiket + renk (Faz 1, #1500).
 *
 * shadcn Badge `outline` tabanı + call-site className renklendirme (ui/badge.tsx
 * dokunulmaz — shadcn customization policy). trend_state velocity-driven:
 * breaking/developing/stable/fading.
 */

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TrendState } from "@/lib/api";

const STATE_META: Record<TrendState, { label: string; className: string }> = {
  breaking: {
    label: "Patlıyor",
    className: "border-transparent bg-red-500/15 text-red-600 dark:text-red-400",
  },
  developing: {
    label: "Gelişiyor",
    className:
      "border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400",
  },
  stable: {
    label: "Sabit",
    className: "border-transparent bg-muted text-muted-foreground",
  },
  fading: {
    label: "Sönüyor",
    className: "border-transparent bg-slate-500/15 text-slate-500",
  },
};

export function TrendStatusBadge({ state }: { state: TrendState }) {
  const meta = STATE_META[state] ?? STATE_META.stable;
  return (
    <Badge variant="outline" className={cn(meta.className)}>
      {meta.label}
    </Badge>
  );
}
