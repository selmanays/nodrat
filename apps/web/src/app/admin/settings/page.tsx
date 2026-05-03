"use client";

/**
 * Admin Settings — runtime config (#262/#267, MVP-1.2)
 *
 * Hardcoded sistem ayarları — admin paneli üzerinden tune edilebilir,
 * deploy/restart gerektirmez. Redis pub/sub ile <30s içinde tüm
 * container'lara yansır.
 */

import { useEffect, useMemo, useState } from "react";
import { Settings as SettingsIcon, RotateCcw, Save, AlertCircle, CheckCircle2 } from "lucide-react";

import {
  AdminSettingItem,
  adminSettingReset,
  adminSettingUpdate,
  adminSettingsList,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";

const GROUP_LABELS: Record<string, string> = {
  rag: "RAG / Yeniden Sıralama",
  retrieval: "Hibrit Retrieval",
  clustering: "Olay Kümeleme",
  chunker: "Chunker (Token boyutları)",
  media: "Görsel İndirme",
  quota: "Kota & Limitler",
  scraping: "Kazıma Politikası",
  llm: "LLM Modelleri",
  auth: "Auth / JWT",
  cost: "Maliyet Cap'leri",
  schedule: "Worker Beat Schedule",
  prompts: "LLM Prompts",
};

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSettingItem[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminSettingsList();
      setSettings(res.data);
      setGroups(res.groups);
      if (!activeGroup && res.groups.length > 0) {
        setActiveGroup(res.groups[0]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(
    () => settings.filter((s) => !activeGroup || s.group === activeGroup),
    [settings, activeGroup],
  );

  const handleChange = (key: string, value: unknown) => {
    setDrafts((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (item: AdminSettingItem) => {
    const newValue = drafts[item.key];
    if (newValue === undefined) return;
    setSaving((p) => ({ ...p, [item.key]: true }));
    try {
      const updated = await adminSettingUpdate(item.key, newValue);
      setSettings((prev) =>
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
        `${item.key} kaydedilemedi: ${e instanceof Error ? e.message : "bilinmeyen hata"}`,
      );
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }));
    }
  };

  const handleReset = async (item: AdminSettingItem) => {
    if (!item.is_overridden) return;
    if (!confirm(`"${item.key}" varsayılana döndürülsün mü? (${JSON.stringify(item.default)})`)) {
      return;
    }
    setSaving((p) => ({ ...p, [item.key]: true }));
    try {
      const reset = await adminSettingReset(item.key);
      setSettings((prev) =>
        prev.map((s) => (s.key === item.key ? reset : s)),
      );
      setDrafts((prev) => {
        const { [item.key]: _, ...rest } = prev;
        return rest;
      });
    } catch (e: unknown) {
      setError(
        `${item.key} sıfırlanamadı: ${e instanceof Error ? e.message : "bilinmeyen hata"}`,
      );
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="h-6 w-6 text-foreground/70" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sistem Ayarları</h1>
          <p className="text-sm text-muted-foreground">
            Çalışma zamanı parametreleri — değişiklik 30 saniye içinde tüm container'lara yansır.
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Tabs
        value={activeGroup ?? undefined}
        onValueChange={(v) => setActiveGroup(v)}
        className="w-full"
      >
        <TabsList>
          {groups.map((g) => (
            <TabsTrigger key={g} value={g}>
              {GROUP_LABELS[g] || g}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="mt-6 space-y-4">
          {loading && <p className="text-sm text-muted-foreground">Yükleniyor…</p>}
          {!loading && filtered.length === 0 && (
            <p className="text-sm text-muted-foreground">Bu grupta ayar yok.</p>
          )}
          {filtered.map((item) => {
            const draft = drafts[item.key];
            const dirty = draft !== undefined && draft !== item.value;
            return (
              <Card key={item.key}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex flex-col">
                      <CardTitle className="text-base font-mono">
                        {item.key}
                      </CardTitle>
                      {item.description && (
                        <CardDescription className="mt-1">
                          {item.description}
                        </CardDescription>
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
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-end gap-4">
                    <div className="flex-1 space-y-1.5">
                      <Label htmlFor={item.key} className="text-xs text-muted-foreground">
                        Değer{" "}
                        {item.min_value !== null || item.max_value !== null ? (
                          <span className="ml-1">
                            (aralık: {item.min_value ?? "−∞"} … {item.max_value ?? "+∞"})
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
                      <Label className="text-xs text-muted-foreground">Varsayılan</Label>
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
                      <Save className="mr-1.5 h-3.5 w-3.5" />
                      {saving[item.key] ? "Kaydediliyor…" : "Kaydet"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReset(item)}
                      disabled={!item.is_overridden || saving[item.key]}
                    >
                      <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                      Varsayılana Dön
                    </Button>
                    {savedKey === item.key && (
                      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 dark:text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Kaydedildi (≤30s'de aktif)
                      </span>
                    )}
                    {item.updated_at && (
                      <span className="ml-auto text-xs text-muted-foreground">
                        Son güncelleme: {formatTrDateTime(item.updated_at)}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </Tabs>
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
      <div className="mt-2 flex items-center gap-3">
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
      type={
        item.type === "int" || item.type === "float" ? "number" : "text"
      }
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
      className="mt-1 font-mono text-sm"
    />
  );
}
