"use client";

/**
 * Admin LLM Prompts — runtime prompt management (#270 PR-B, MVP-1.2)
 *
 * Hardcoded `app/prompts/*.py` modüllerinin DB-backed alternatifi.
 * Version history korunur, rollback mümkün.
 */

import { useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  History,
  RotateCcw,
  Save,
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { PageHeader } from "@/components/blocks/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

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
  const [copied, setCopied] = useState(false);

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
    setCopied(false);
  };

  const handleCopy = async () => {
    if (!active) return;
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Kopyalanamadı");
    }
  };

  const handleSave = async () => {
    if (!active) return;
    setSaving(true);
    try {
      const updated = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}`,
        { method: "PUT", body: { content: draft } },
      );
      setPrompts((prev) =>
        prev.map((p) => (p.name === active.name ? updated : p)),
      );
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
    if (
      !confirm(
        "Bu prompt'u kod-tarafı varsayılana döndürmek istiyor musun? (history korunur)",
      )
    ) {
      return;
    }
    setSaving(true);
    try {
      const reset = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}`,
        { method: "DELETE" },
      );
      setPrompts((prev) =>
        prev.map((p) => (p.name === active.name ? reset : p)),
      );
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
    if (
      !confirm(
        `Versiyon ${version}'ı current yapmak istiyor musun? (yeni versiyon üretilir)`,
      )
    ) {
      return;
    }
    setSaving(true);
    try {
      const restored = await apiFetch<PromptDTO>(
        `/admin/prompts/${encodeURIComponent(active.name)}/restore/${version}`,
        { method: "POST" },
      );
      setPrompts((prev) =>
        prev.map((p) => (p.name === active.name ? restored : p)),
      );
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
      <PageHeader
        title="İstemler"
        description="Sistem promptları runtime tunable. Her güncelleme yeni versiyon üretir, geçmiş korunur."
      />

      {error && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading ? (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardContent className="space-y-3 p-6">
            <Skeleton className="h-9 w-64" />
            <Skeleton className="h-4 w-full max-w-md" />
            <Skeleton className="h-80 w-full" />
          </CardContent>
        </Card>
      ) : prompts.length === 0 ? (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardContent className="p-10 text-center text-sm text-muted-foreground">
            Hiç prompt bulunamadı.
          </CardContent>
        </Card>
      ) : (
        <Tabs
          value={activeName ?? prompts[0].name}
          onValueChange={selectPrompt}
        >
          <TabsList>
            {prompts.map((p) => (
              <TabsTrigger key={p.name} value={p.name}>
                {PROMPT_LABELS[p.name] || p.name}
              </TabsTrigger>
            ))}
          </TabsList>

          {prompts.map((p) => (
            <TabsContent key={p.name} value={p.name} className="mt-4">
              <Card className="rounded-2xl shadow-none ring-[var(--border)]">
                <CardContent className="space-y-4 p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-1">
                      <h2 className="text-lg font-semibold tracking-tight">
                        {PROMPT_LABELS[p.name] || p.name}
                      </h2>
                      {p.description && (
                        <p className="text-sm text-muted-foreground">
                          {p.description}
                        </p>
                      )}
                      {p.model_hint && (
                        <p className="text-xs text-muted-foreground">
                          Model: {p.model_hint}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {p.is_overridden ? (
                        <Badge variant="secondary">
                          Override v{p.version}
                        </Badge>
                      ) : (
                        <Badge variant="outline">Varsayılan (kod)</Badge>
                      )}
                    </div>
                  </div>

                  <div className="relative">
                    <Textarea
                      value={p.name === activeName ? draft : p.content}
                      onChange={(e) => {
                        if (p.name === activeName) setDraft(e.target.value);
                      }}
                      rows={20}
                      spellCheck={false}
                      className="resize-none pr-12 font-mono text-xs"
                    />
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      onClick={handleCopy}
                      aria-label="Kopyala"
                      className="absolute top-2 right-2"
                    >
                      {copied && p.name === activeName ? (
                        <Check className="text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <Copy />
                      )}
                    </Button>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      onClick={handleSave}
                      disabled={!dirty || saving || p.name !== activeName}
                      size="sm"
                    >
                      <Save />
                      {saving ? "Kaydediliyor…" : "Yeni versiyonu kaydet"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleReset}
                      disabled={!p.is_overridden || saving}
                      size="sm"
                    >
                      <RotateCcw />
                      Varsayılana Dön
                    </Button>
                    <Button
                      variant="outline"
                      onClick={loadHistory}
                      size="sm"
                    >
                      <History />
                      Versiyon Geçmişi
                    </Button>
                    {savedAt && p.name === activeName && (
                      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" />
                        Kaydedildi (≤30s'de aktif)
                      </span>
                    )}
                    {p.updated_at && (
                      <span className="ml-auto text-xs text-muted-foreground">
                        Son güncelleme: {formatTrDateTime(p.updated_at)}
                      </span>
                    )}
                  </div>

                  {showHistory && p.name === activeName && (
                    <div className="rounded-xl bg-muted/40 p-4">
                      <p className="mb-2 text-xs font-medium text-muted-foreground">
                        Versiyon Geçmişi ({history.length})
                      </p>
                      {history.length === 0 ? (
                        <p className="text-xs text-muted-foreground">
                          Henüz geçmiş kaydı yok.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {history.map((h) => (
                            <div
                              key={h.id}
                              className="flex items-center justify-between rounded-lg border bg-background p-2 text-xs"
                            >
                              <div className="flex items-center gap-2">
                                <span className="font-mono font-medium">
                                  v{h.version}
                                </span>
                                <span className="text-muted-foreground">
                                  {formatTrDateTime(h.created_at)}
                                </span>
                                <span className="text-muted-foreground">
                                  · {h.content.length} karakter
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
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
