"use client";

/**
 * /app/style-profiles/[id] — detay + sample yönetimi (#52 PR-2).
 *
 * Sayfa sadece Pro+ kullanıcılarına açıktır (server-side enforced). Status
 * 'ready' olduğunda rules_json render edilir; 'failed' ise tekrar dene
 * butonu görünür. 'analyzing' / 'pending' durumda 4 saniyede bir polling.
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Plus, RefreshCw} from "lucide-react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import { ApiException } from "@/lib/api";
import {
  addStyleSample,
  getStyleProfile,
  isPaywallRequired,
  reanalyzeStyleProfile,
  type StyleProfileDetail,
} from "@/lib/style-profiles-api";
import { formatTrDate } from "@/lib/format";

const MIN_SAMPLE_LEN = 20;

export default function StyleProfileDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [profile, setProfile] = useState<StyleProfileDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [newSample, setNewSample] = useState("");
  const [newSampleUrl, setNewSampleUrl] = useState("");

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await getStyleProfile(id);
      setProfile(data);
      setError(null);
    } catch (err) {
      if (isPaywallRequired(err)) {
        setError("Bu sayfa Pro tier'a açıktır.");
      } else if (err instanceof ApiException && err.status === 404) {
        setError("Stil profili bulunamadı.");
      } else {
        setError((err as ApiException).message || "Yüklenemedi");
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Polling while in-flight
  useEffect(() => {
    if (!profile) return;
    if (profile.status !== "analyzing" && profile.status !== "pending") return;
    const t = setInterval(() => void load(true), 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.status]);

  async function handleAddSample() {
    if (newSample.trim().length < MIN_SAMPLE_LEN) {
      toast.error(`Örnek en az ${MIN_SAMPLE_LEN} karakter olmalı`);
      return;
    }
    setAdding(true);
    try {
      const resp = await addStyleSample(id, {
        text: newSample.trim(),
        source_url: newSampleUrl.trim() || null,
      });
      toast.success(
        resp.will_reanalyze
          ? "Örnek eklendi, yeniden analiz başlatıldı"
          : "Örnek eklendi",
      );
      setNewSample("");
      setNewSampleUrl("");
      await load(true);
    } catch (err) {
      toast.error((err as ApiException).message || "Eklenemedi");
    } finally {
      setAdding(false);
    }
  }

  async function handleReanalyze() {
    setReanalyzing(true);
    try {
      await reanalyzeStyleProfile(id);
      toast.success("Yeniden analiz başlatıldı");
      await load(true);
    } catch (err) {
      toast.error((err as ApiException).message || "Tetiklenemedi");
    } finally {
      setReanalyzing(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-3 mb-2">
          <Link href="/app/style-profiles">
            <ArrowLeft className="mr-1 size-4" />
            Stil profilleri
          </Link>
        </Button>
      </div>

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      )}

      {error && !loading && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle>Sorun</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {profile && !loading && (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle>{profile.name}</CardTitle>
                  <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{profile.source_type}</Badge>
                    <StatusBadge status={profile.status} />
                    <span className="text-xs">
                      {profile.sample_count} örnek
                    </span>
                    <span className="text-xs">
                      {formatTrDate(profile.created_at)}
                    </span>
                  </CardDescription>
                </div>
                {profile.status === "failed" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={reanalyzing}
                    onClick={() => void handleReanalyze()}
                  >
                    {reanalyzing ? (
                      <Loader2 className="mr-1 size-3 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-1 size-3" />
                    )}
                    Tekrar dene
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {profile.style_summary && (
                <p className="text-sm">{profile.style_summary}</p>
              )}
              {profile.error_message && (
                <p className="mt-2 text-xs text-destructive">
                  {profile.error_message}
                </p>
              )}
            </CardContent>
          </Card>

          {profile.status === "ready" && (
            <RulesView rules={profile.rules_json} />
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Örnek metinler</CardTitle>
              <CardDescription>
                Daha fazla örnek profili güçlendirir; en az 3 örnekte analiz
                başlar.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {profile.samples.map((sample, idx) => (
                <div key={sample.id} className="rounded-md border bg-card p-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="font-medium">Örnek {idx + 1}</span>
                    <span>{sample.char_count} karakter</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm">
                    {sample.text}
                  </p>
                  {sample.source_url && (
                    <a
                      href={sample.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 block text-xs text-primary underline"
                    >
                      Kaynak
                    </a>
                  )}
                </div>
              ))}

              <div className="rounded-md border border-dashed p-3">
                <Label className="text-xs text-muted-foreground">
                  Yeni örnek ekle
                </Label>
                <Textarea
                  rows={3}
                  className="mt-1 font-mono text-xs"
                  placeholder={`En az ${MIN_SAMPLE_LEN} karakter`}
                  value={newSample}
                  onChange={(e) => setNewSample(e.target.value)}
                  disabled={adding}
                  maxLength={4000}
                />
                <Input
                  type="url"
                  placeholder="Kaynak URL (opsiyonel)"
                  className="mt-2 h-8 text-xs"
                  value={newSampleUrl}
                  onChange={(e) => setNewSampleUrl(e.target.value)}
                  disabled={adding}
                  maxLength={2000}
                />
                <Button
                  size="sm"
                  className="mt-2"
                  disabled={adding || newSample.trim().length < MIN_SAMPLE_LEN}
                  onClick={() => void handleAddSample()}
                >
                  {adding ? (
                    <Loader2 className="mr-1 size-3 animate-spin" />
                  ) : (
                    <Plus className="mr-1 size-3" />
                  )}
                  Ekle
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    pending: { label: "Hazırlanıyor", cls: "bg-slate-500/10 text-slate-700" },
    analyzing: { label: "Analiz ediliyor", cls: "bg-blue-500/10 text-blue-700" },
    ready: { label: "Hazır", cls: "bg-emerald-500/10 text-emerald-700" },
    failed: { label: "Başarısız", cls: "bg-red-500/10 text-red-700" },
  };
  const m = map[status] ?? { label: status, cls: "bg-muted" };
  return (
    <Badge variant="secondary" className={`h-5 ${m.cls}`}>
      {m.label}
    </Badge>
  );
}

interface StyleRules {
  style_name?: string;
  style_summary?: string;
  sentence_length?: string;
  tone?: string[];
  rhetorical_patterns?: string[];
  avoid?: string[];
  sample_transforms?: { generic: string; styled: string }[];
}

function RulesView({ rules }: { rules: Record<string, unknown> }) {
  const r = rules as StyleRules;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Stil özeti</CardTitle>
        <CardDescription>
          Sistem bu kuralları gözeterek içerik üretir.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <RuleRow label="Adı" value={r.style_name} />
        <RuleRow label="Cümle uzunluğu" value={r.sentence_length} />
        <RuleRow
          label="Ton"
          value={r.tone?.join(", ") || "—"}
          full
        />
        <RuleRow
          label="Retorik desen"
          value={r.rhetorical_patterns?.join(" · ") || "—"}
          full
        />
        <RuleRow
          label="Kaçındığı"
          value={r.avoid?.join(" · ") || "—"}
          full
        />
        {r.sample_transforms && r.sample_transforms.length > 0 && (
          <div className="sm:col-span-2">
            <p className="mb-2 text-xs font-medium uppercase text-muted-foreground">
              Örnek dönüşüm
            </p>
            <div className="space-y-2">
              {r.sample_transforms.map((t, i) => (
                <div
                  key={i}
                  className="rounded-md border bg-muted/30 p-3 text-sm"
                >
                  <div className="text-xs text-muted-foreground">Genel:</div>
                  <div className="italic">{t.generic}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Bu stilde:
                  </div>
                  <div className="font-medium">{t.styled}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RuleRow({
  label,
  value,
  full,
}: {
  label: string;
  value: string | undefined;
  full?: boolean;
}) {
  return (
    <div className={full ? "sm:col-span-2" : undefined}>
      <p className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-sm">{value || "—"}</p>
    </div>
  );
}
