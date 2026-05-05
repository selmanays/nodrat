"use client";

/**
 * Admin Settings — grup-bazlı dynamic route (#262/#267).
 *
 * Tüm ayarlar tek bir kapsayıcı kart içinde, her satır divider ile ayrılmış.
 */

import { useEffect, useState } from "react";
import { notFound, useParams } from "next/navigation";
import { AlertCircle, CheckCircle2, RotateCcw, Save } from "lucide-react";

import {
  AdminSettingItem,
  adminSettingReset,
  adminSettingUpdate,
  adminSettingsList,
} from "@/lib/api";
import {
  SETTINGS_GROUPS,
  getSettingsGroupLabel,
} from "@/lib/settings-groups";
import { formatTrDateTime } from "@/lib/format";
import { PageHeader } from "@/components/blocks/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

const VALID_SLUGS = new Set(SETTINGS_GROUPS.map((g) => g.slug as string));

export default function GroupSettingsPage() {
  const params = useParams<{ group: string }>();
  const group = params?.group ?? "";

  if (!VALID_SLUGS.has(group)) {
    notFound();
  }

  const [items, setItems] = useState<AdminSettingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [savedKey, setSavedKey] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    adminSettingsList(group)
      .then((res) => {
        if (!mounted) return;
        setItems(res.data);
      })
      .catch((e: unknown) => {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : "Yükleme hatası");
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [group]);

  const handleChange = (key: string, value: unknown) => {
    setDrafts((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (item: AdminSettingItem) => {
    const newValue = drafts[item.key];
    if (newValue === undefined) return;
    setSaving((p) => ({ ...p, [item.key]: true }));
    try {
      const updated = await adminSettingUpdate(item.key, newValue);
      setItems((prev) =>
        prev.map((s) => (s.key === item.key ? updated : s)),
      );
      setDrafts((prev) => {
        const { [item.key]: _, ...rest } = prev;
        return rest;
      });
      setSavedKey(item.key);
      setTimeout(() => setSavedKey(null), 3000);
    } catch (e: unknown) {
      setError(
        `${item.key} kaydedilemedi: ${
          e instanceof Error ? e.message : "bilinmeyen hata"
        }`,
      );
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }));
    }
  };

  const handleReset = async (item: AdminSettingItem) => {
    if (!item.is_overridden) return;
    if (
      !confirm(
        `"${item.key}" varsayılana döndürülsün mü? (${JSON.stringify(item.default)})`,
      )
    ) {
      return;
    }
    setSaving((p) => ({ ...p, [item.key]: true }));
    try {
      const reset = await adminSettingReset(item.key);
      setItems((prev) => prev.map((s) => (s.key === item.key ? reset : s)));
      setDrafts((prev) => {
        const { [item.key]: _, ...rest } = prev;
        return rest;
      });
    } catch (e: unknown) {
      setError(
        `${item.key} sıfırlanamadı: ${
          e instanceof Error ? e.message : "bilinmeyen hata"
        }`,
      );
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={getSettingsGroupLabel(group)}
        description="Çalışma zamanı parametreleri — değişiklik 30 saniye içinde tüm container'lara yansır."
      />

      {error && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <div className="divide-y">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={`skel-${i}`} className="space-y-3 p-6">
                <Skeleton className="h-5 w-64" />
                <Skeleton className="h-4 w-full max-w-md" />
                <Skeleton className="h-9 w-full max-w-sm" />
              </div>
            ))
          ) : items.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              Bu grupta ayar bulunamadı.
            </div>
          ) : (
            items.map((item) => {
              const draft = drafts[item.key];
              const dirty = draft !== undefined && draft !== item.value;
              return (
                <div key={item.key} className="space-y-4 p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-1">
                      <p className="font-mono text-sm font-medium break-all">
                        {item.key}
                      </p>
                      {item.description && (
                        <p className="text-sm text-muted-foreground">
                          {item.description}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {item.is_overridden ? (
                        <Badge variant="secondary">Override</Badge>
                      ) : (
                        <Badge variant="outline">Varsayılan</Badge>
                      )}
                      {item.requires_restart && (
                        <Badge variant="destructive">Restart</Badge>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-end gap-4">
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <Label
                        htmlFor={item.key}
                        className="text-xs text-muted-foreground"
                      >
                        Değer
                        {item.min_value !== null || item.max_value !== null ? (
                          <span className="ml-1 font-normal">
                            (aralık: {item.min_value ?? "−∞"} …{" "}
                            {item.max_value ?? "+∞"})
                          </span>
                        ) : null}
                      </Label>
                      <SettingInput
                        item={item}
                        value={(draft ?? item.value) as unknown}
                        onChange={(v) => handleChange(item.key, v)}
                      />
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Label className="text-xs text-muted-foreground">
                        Varsayılan
                      </Label>
                      <code className="rounded bg-muted px-2 py-1 font-mono text-xs">
                        {JSON.stringify(item.default)}
                      </code>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      onClick={() => handleSave(item)}
                      disabled={!dirty || saving[item.key]}
                    >
                      <Save />
                      {saving[item.key] ? "Kaydediliyor…" : "Kaydet"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReset(item)}
                      disabled={!item.is_overridden || saving[item.key]}
                    >
                      <RotateCcw />
                      Varsayılana Dön
                    </Button>
                    {savedKey === item.key && (
                      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" />
                        Kaydedildi (≤30s'de aktif)
                      </span>
                    )}
                    {item.updated_at && (
                      <span className="ml-auto text-xs text-muted-foreground">
                        Son güncelleme: {formatTrDateTime(item.updated_at)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>
    </div>
  );
}

function SettingInput({
  item,
  value,
  onChange,
}: {
  item: AdminSettingItem;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (item.type === "bool") {
    const b = value === true || value === "true";
    return (
      <div className="flex items-center gap-3">
        <Switch checked={b} onCheckedChange={onChange} />
        <span className="text-sm text-muted-foreground">
          {b ? "Aktif" : "Pasif"}
        </span>
      </div>
    );
  }

  return (
    <Input
      id={item.key}
      type={item.type === "int" || item.type === "float" ? "number" : "text"}
      step={item.type === "float" ? "0.01" : "1"}
      min={item.min_value ?? undefined}
      max={item.max_value ?? undefined}
      value={
        value === null || value === undefined
          ? ""
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value)
      }
      onChange={(e) => {
        const raw = e.target.value;
        if (item.type === "int") onChange(raw === "" ? "" : Number(raw));
        else if (item.type === "float") onChange(raw === "" ? "" : Number(raw));
        else onChange(raw);
      }}
      className="font-mono"
    />
  );
}
