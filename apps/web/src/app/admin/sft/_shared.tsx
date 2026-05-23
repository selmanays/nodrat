"use client";

/**
 * Admin SFT sayfası — paylaşılan helper'lar (PR-7d-1).
 *
 * Phase 7b admin/sft mini-plan 2. PR. `page.tsx`'ten saf taşıma (byte-for-byte
 * korumalı); imza/davranış değişikliği YOK. AdminSftPage tek bir component
 * olarak `page.tsx`'te kalır (shared state lift gerektireceği için section
 * split DEFERRED).
 *
 * Taşınan semboller:
 * - `EXCLUDED_LABEL` — 8-entry exclusion reason → TR label map
 * - `TASK_TYPE_OPTIONS` — 4-option task type Select array
 * - `SAMPLE_TYPE_LABEL` — 3-entry sample_type → TR label map (sft/dpo_chosen/dpo_rejected)
 * - `SPLIT_OPTIONS` — 4-option split (all/train/val/test) Select array
 * - `SFT_SETTING_KEYS` — settings key registry (4-key const)
 * - `StatCardProps` + `StatCard` — saf presentational stat kartı
 * - `NumericSettingInputProps` + `NumericSettingInput` — settings numeric input + save/reset
 *
 * "use client" defensive direktif (admin/rag _shared.tsx + admin/queue _shared.tsx deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-sft-mini-plan.md — Phase 7b admin/sft mini-plan
 * - apps/web/src/app/admin/sft/page.tsx — AdminSftPage main component
 */

import { Loader2, RotateCcw, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export const EXCLUDED_LABEL: Record<string, string> = {
  no_consent: "Onay yok",
  consent_revoked: "Onay geri çekildi",
  wrong_action: "Yanlış action",
  edit_too_large: "Edit çok büyük",
  halu_flagged: "Halü flag'li",
  review_buffer: "7g bekleme",
  pii_secondary_hit: "PII tespit edildi",
  wrong_status: "Status uygun değil",
};

export const TASK_TYPE_OPTIONS = [
  { value: "research_answer", label: "Research Answer (yeni)" },
  { value: "content_generator", label: "Content Generator (legacy)" },
  { value: "query_planner", label: "Query Planner" },
  { value: "style_analyzer", label: "Style Analyzer" },
];

export const SAMPLE_TYPE_LABEL: Record<string, string> = {
  sft: "SFT",
  dpo_chosen: "DPO Chosen",
  dpo_rejected: "DPO Rejected",
};

export const SPLIT_OPTIONS = [
  { value: "all", label: "Tüm split'ler" },
  { value: "train", label: "Train (~80%)" },
  { value: "val", label: "Val (~10%)" },
  { value: "test", label: "Test (~10%)" },
];

export const SFT_SETTING_KEYS = {
  enabled: "sft.curator.enabled",
  reviewBufferDays: "sft.curator.review_buffer_days",
  dailyMaxSamples: "sft.curator.daily_max_samples",
  minQualityScore: "sft.curator.min_quality_score",
} as const;

export interface StatCardProps {
  title: string;
  value: number | string | null;
  hint?: string;
}

export function StatCard({ title, value, hint }: StatCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">
          {value === null ? <Skeleton className="h-8 w-20" /> : value.toLocaleString("tr-TR")}
        </CardTitle>
      </CardHeader>
      {hint && (
        <CardContent>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </CardContent>
      )}
    </Card>
  );
}

export interface NumericSettingInputProps {
  id: string;
  label: string;
  hint: string;
  defaultValue: string;
  currentValue: string;
  isOverridden: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  saving: boolean;
  disabled: boolean;
  onSave: () => void;
  onReset: () => void;
}

export function NumericSettingInput({
  id,
  label,
  hint,
  defaultValue,
  currentValue,
  isOverridden,
  inputValue,
  onInputChange,
  saving,
  disabled,
  onSave,
  onReset,
}: NumericSettingInputProps) {
  const dirty = inputValue.trim() !== currentValue.trim();
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="text-sm font-medium">
          {label}
        </Label>
        {isOverridden && (
          <Badge variant="outline" className="text-[10px]">
            override
          </Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          type="text"
          inputMode="decimal"
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={disabled || saving}
          className="font-mono"
        />
        <Button
          size="sm"
          variant="default"
          onClick={onSave}
          disabled={disabled || saving || !dirty}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onReset}
          disabled={disabled || saving || !isOverridden}
          title="Default değere döndür"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground tabular-nums">
        default: {defaultValue} · mevcut: {currentValue || "—"}
      </p>
    </div>
  );
}
