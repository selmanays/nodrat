"use client";

import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export interface CheckboxProps {
  id?: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Minimal checkbox — Radix UI yerine plain input + custom UI.
 * Form usage: ariki gerekirse FormField sarın.
 */
export function Checkbox({
  id,
  checked,
  onCheckedChange,
  disabled,
  className,
}: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      id={id}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "peer h-4 w-4 shrink-0 rounded-sm border border-input ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        checked && "bg-brand-700 text-white border-brand-700",
        className,
      )}
    >
      {checked && (
        <Check className="h-3.5 w-3.5 text-white" strokeWidth={3} />
      )}
    </button>
  );
}
