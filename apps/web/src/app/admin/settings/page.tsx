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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const GROUP_LABELS: Record<string, string> = {
  rag: "RAG / Yeniden Sıralama",
  clustering: "Olay Kümeleme",
  retrieval: "Hibrit Retrieval",
  quota: "Kota & Limitler",
  scraping: "Kazıma Politikası",
  llm: "LLM Modelleri",
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
        <SettingsIcon className="h-6 w-6 text-slate-700" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sistem Ayarları</h1>
          <p className="text-sm text-slate-500">
            Çalışma zamanı parametreleri — değişiklik 30 saniye içinde tüm container'lara yansır.
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Sol nav: gruplar */}
        <div className="col-span-12 md:col-span-3">
          <Card>
            <CardContent className="p-2">
              {groups.length === 0 && !loading && (
                <p className="p-2 text-xs text-slate-500">Grup bulunamadı.</p>
              )}
              {groups.map((g) => (
                <button
                  key={g}
                  onClick={() => setActiveGroup(g)}
                  className={`w-full rounded px-3 py-2 text-left text-sm transition ${
                    activeGroup === g
                      ? "bg-slate-900 text-white"
                      : "hover:bg-slate-100"
                  }`}
                >
                  {GROUP_LABELS[g] || g}
                </button>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Sağ panel: settings */}
        <div className="col-span-12 md:col-span-9 space-y-4">
          {loading && (
            <p className="text-sm text-slate-500">Yükleniyor…</p>
          )}
          {!loading && filtered.length === 0 && (
            <p className="text-sm text-slate-500">Bu grupta ayar yok.</p>
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
                        <p className="mt-1 text-sm text-slate-600">
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
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <Label htmlFor={item.key} className="text-xs text-slate-500">
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
                      <Label className="text-xs text-slate-400">Varsayılan</Label>
                      <code className="rounded bg-slate-50 px-2 py-1 text-xs">
                        {JSON.stringify(item.default)}
                      </code>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
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
                      <span className="flex items-center gap-1 text-xs text-emerald-600">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Kaydedildi (≤30s'de aktif)
                      </span>
                    )}
                    {item.updated_at && (
                      <span className="ml-auto text-xs text-slate-400">
                        Son güncelleme: {formatTrDateTime(item.updated_at)}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
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
      <div className="mt-1 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(!b)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
            b ? "bg-emerald-500" : "bg-slate-300"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
              b ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <span className="text-sm">{b ? "Aktif" : "Pasif"}</span>
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
