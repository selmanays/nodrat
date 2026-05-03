"use client";

/**
 * Admin LLM Prompts — runtime prompt management (#270 PR-B, MVP-1.2)
 *
 * Hardcoded `app/prompts/*.py` modüllerinin DB-backed alternatifi.
 * Version history korunur, rollback mümkün.
 */

import { useEffect, useState } from "react";
import { FileCode, RotateCcw, Save, History, AlertCircle, CheckCircle2 } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PromptDTO {
  name: string;
  version: number;
  content: string;
  default: string;
  description: string | null;
  model_hint: string | null;
  is_overridden: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

interface PromptHistoryItem {
  id: string;
  name: string;
  version: number;
  content: string;
  updated_by: string | null;
  created_at: string;
}

const PROMPT_LABELS: Record<string, string> = {
  query_planner: "Query Planner",
  agenda_card: "Agenda Card Generator",
  content_generator: "İçerik Üretici (X Post)",
};

export default function AdminPromptsPage() {
  const [prompts, setPrompts] = useState<PromptDTO[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [history, setHistory] = useState<PromptHistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ data: PromptDTO[] }>("/admin/prompts");
      setPrompts(res.data);
      if (!activeName && res.data.length > 0) {
        setActiveName(res.data[0].name);
        setDraft(res.data[0].content);
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

  const active = prompts.find((p) => p.name === activeName) || null;
  const dirty = active !== null && draft !== active.content;

  const selectPrompt = (name: string) => {
    setActiveName(name);
    const p = prompts.find((x) => x.name === name);
    setDraft(p?.content || "");
    setShowHistory(false);
    setHistory([]);
  };

  const handleSave = async () => {
    if (!active) return;
    setSaving(true);
    try {
      const updated = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}`,
        { method: "PUT", body: { content: draft } },
      );
      setPrompts((prev) => prev.map((p) => (p.name === active.name ? updated : p)));
      setDraft(updated.content);
      setSavedAt(new Date().toISOString());
      setTimeout(() => setSavedAt(null), 4000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!active || !active.is_overridden) return;
    if (!confirm("Bu prompt'u kod-tarafı varsayılana döndürmek istiyor musun? (history korunur)")) {
      return;
    }
    setSaving(true);
    try {
      const reset = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}`,
        { method: "DELETE" },
      );
      setPrompts((prev) => prev.map((p) => (p.name === active.name ? reset : p)));
      setDraft(reset.content);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sıfırlanamadı");
    } finally {
      setSaving(false);
    }
  };

  const loadHistory = async () => {
    if (!active) return;
    try {
      const res = await apiFetch<{ data: PromptHistoryItem[] }>(
        `/admin/prompts/${encodeURIComponent(active.name)}/history`,
      );
      setHistory(res.data);
      setShowHistory(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "History alınamadı");
    }
  };

  const handleRestore = async (version: number) => {
    if (!active) return;
    if (!confirm(`Versiyon ${version}'ı current yapmak istiyor musun? (yeni versiyon üretilir)`)) {
      return;
    }
    setSaving(true);
    try {
      const restored = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}/restore/${version}`,
        { method: "POST" },
      );
      setPrompts((prev) => prev.map((p) => (p.name === active.name ? restored : p)));
      setDraft(restored.content);
      setShowHistory(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Restore hatası");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <FileCode className="h-6 w-6 text-slate-700" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">LLM Prompts</h1>
          <p className="text-sm text-slate-500">
            Sistem promptları runtime tunable. Her güncelleme yeni versiyon üretir, history korunur.
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
        <div className="col-span-12 md:col-span-3">
          <Card>
            <CardContent className="p-2">
              {loading && <p className="p-2 text-xs text-slate-500">Yükleniyor…</p>}
              {prompts.map((p) => (
                <button
                  key={p.name}
                  onClick={() => selectPrompt(p.name)}
                  className={`flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm transition ${
                    activeName === p.name ? "bg-slate-900 text-white" : "hover:bg-slate-100"
                  }`}
                >
                  <span>{PROMPT_LABELS[p.name] || p.name}</span>
                  {p.is_overridden && (
                    <Badge variant={activeName === p.name ? "outline" : "secondary"}>
                      v{p.version}
                    </Badge>
                  )}
                </button>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="col-span-12 md:col-span-9">
          {!active && !loading && (
            <p className="text-sm text-slate-500">Sol menüden bir prompt seç.</p>
          )}
          {active && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-lg">
                      {PROMPT_LABELS[active.name] || active.name}
                    </CardTitle>
                    {active.description && (
                      <p className="mt-1 text-sm text-slate-600">{active.description}</p>
                    )}
                    {active.model_hint && (
                      <p className="mt-0.5 text-xs text-slate-400">Model: {active.model_hint}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {active.is_overridden ? (
                      <Badge variant="secondary">Override v{active.version}</Badge>
                    ) : (
                      <Badge variant="outline">Varsayılan (kod)</Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={20}
                  className="font-mono text-xs"
                  spellCheck={false}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={handleSave} disabled={!dirty || saving} size="sm">
                    <Save className="mr-1.5 h-3.5 w-3.5" />
                    {saving ? "Kaydediliyor…" : "Yeni versiyonu kaydet"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleReset}
                    disabled={!active.is_overridden || saving}
                    size="sm"
                  >
                    <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                    Varsayılana Dön
                  </Button>
                  <Button variant="outline" onClick={loadHistory} size="sm">
                    <History className="mr-1.5 h-3.5 w-3.5" />
                    Versiyon Geçmişi
                  </Button>
                  {savedAt && (
                    <span className="flex items-center gap-1 text-xs text-emerald-600">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Kaydedildi (≤30s'de aktif)
                    </span>
                  )}
                  {active.updated_at && (
                    <span className="ml-auto text-xs text-slate-400">
                      Son güncelleme: {formatTrDateTime(active.updated_at)}
                    </span>
                  )}
                </div>

                {showHistory && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="mb-2 text-xs font-semibold text-slate-700">
                      Versiyon Geçmişi ({history.length})
                    </p>
                    {history.length === 0 ? (
                      <p className="text-xs text-slate-500">Henüz history kaydı yok.</p>
                    ) : (
                      <div className="space-y-2">
                        {history.map((h) => (
                          <div
                            key={h.id}
                            className="flex items-center justify-between rounded border border-slate-200 bg-white p-2 text-xs"
                          >
                            <div>
                              <span className="font-mono font-semibold">v{h.version}</span>
                              <span className="ml-2 text-slate-500">
                                {formatTrDateTime(h.created_at)}
                              </span>
                              <span className="ml-2 text-slate-400">
                                {h.content.length} chars
                              </span>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleRestore(h.version)}
                              disabled={saving}
                            >
                              Geri Yükle
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
