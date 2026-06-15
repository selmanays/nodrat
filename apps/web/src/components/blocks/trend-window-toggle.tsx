/**
 * TrendWindowToggle — trend penceresi seçici (1h/6h/24h/7d) (Faz 1, #1500).
 *
 * shadcn ToggleGroup (dashboard-area-chart-card range toggle deseni).
 */

"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { TrendWindow } from "@/lib/api";

const WINDOWS: { value: TrendWindow; label: string }[] = [
  { value: "1h", label: "1sa" },
  { value: "6h", label: "6sa" },
  { value: "24h", label: "24sa" },
  { value: "7d", label: "7g" },
];

export function TrendWindowToggle({
  value,
  onChange,
  disabled,
}: {
  value: TrendWindow;
  onChange: (w: TrendWindow) => void;
  disabled?: boolean;
}) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as TrendWindow)}
      disabled={disabled}
      variant="outline"
      size="sm"
    >
      {WINDOWS.map((w) => (
        <ToggleGroupItem key={w.value} value={w.value}>
          {w.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
