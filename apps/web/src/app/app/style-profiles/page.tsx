"use client";

/**
 * /app/style-profiles — Faz 5 stil profili listesi (#52 PR-2).
 *
 * Pro+ tier zorunlu (server-side enforced). Free/Starter user 402 alır →
 * "Pro'ya yükselt" CTA. Profil sayısı slot quota'sını aşarsa 409.
 *
 * Status workflow: pending → analyzing → ready / failed
 *   - 5+ örnek → otomatik analyze tetiklenir
 *   - failed durumunda manuel "Yeniden analiz" butonu
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ApiException } from "@/lib/api";
import {
  deleteStyleProfile,
  isPaywallRequired,
  listStyleProfiles,
  reanalyzeStyleProfile,
  type StyleProfileItem,
  type StyleProfileQuota,
  type StyleProfileStatus,
} from "@/lib/style-profiles-api";
import { formatTrDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CreateProfileDialog } from "./_components/create-dialog";
import { ProAccessGate } from "./_components/pro-gate";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: StyleProfileItem[]; quota: StyleProfileQuota }
  | { kind: "paywall"; message: string }
  | { kind: "error"; message: string };

const STATUS_LABEL: Record<StyleProfileStatus, { label: string; cls: string }> =
  {
    pending: { label: "Hazırlanıyor", cls: "bg-slate-500/10 text-slate-700" },
    analyzing: {
      label: "Analiz ediliyor",
      cls: "bg-blue-500/10 text-blue-700",
    },
    ready: { label: "Hazır", cls: "bg-emerald-500/10 text-emerald-700" },
    failed: { label: "Başarısız", cls: "bg-red-500/10 text-red-700" },
  };

export default function StyleProfilesPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reanalyzingId, setReanalyzingId] = useState<string | null>(null);

  async function load() {
    setState({ kind: "loading" });
    try {
      const resp = await listStyleProfiles();
      setState({ kind: "ready", data: resp.data, quota: resp.quota });
    } catch (err) {
      if (isPaywallRequired(err)) {
        setState({
          kind: "paywall",
          message:
            (err as ApiException).message ||
            "Stil profilleri Pro tier'da kullanıma açıktır.",
        });
        return;
      }
      setState({
        kind: "error",
        message: (err as ApiException).message || "Yüklenemedi",
      });
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // Auto-refresh while any profile is in-flight
  useEffect(() => {
    if (state.kind !== "ready") return;
    const inFlight = state.data.some(
      (p) => p.status === "analyzing" || p.status === "pending",
    );
    if (!inFlight) return;
    const t = setInterval(() => {
      void load();
    }, 4000);
    return () => clearInterval(t);
  }, [state]);

  async function handleDelete(profile: StyleProfileItem) {
    const ok = window.confirm(
      `"${profile.name}" stil profili silinsin mi? Bu işlem geri alınamaz.`,
    );
    if (!ok) return;
    setDeletingId(profile.id);
    try {
      await deleteStyleProfile(profile.id);
      toast.success(`${profile.name} silindi`);
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Silinemedi");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleReanalyze(profile: StyleProfileItem) {
    setReanalyzingId(profile.id);
    try {
      await reanalyzeStyleProfile(profile.id);
      toast.success("Yeniden analiz başlatıldı");
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Tetiklenemedi");
    } finally {
      setReanalyzingId(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Stil profilleri
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Beğendiğiniz yazı stilini sisteme öğretin; üretirken seçtiğiniz
            stilde içerik dönsün. (Pro+ tier)
          </p>
        </div>
        {state.kind === "ready" && (
          <Button
            onClick={() => setCreating(true)}
            disabled={state.quota.used >= state.quota.limit}
          >
            <Plus className="mr-1 size-4" />
            Yeni profil
          </Button>
        )}
      </div>

      {state.kind === "loading" && (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {state.kind === "paywall" && <ProAccessGate message={state.message} />}

      {state.kind === "error" && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle>Hata</CardTitle>
            <CardDescription>{state.message}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => void load()}>Tekrar dene</Button>
          </CardContent>
        </Card>
      )}

      {state.kind === "ready" && (
        <>
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <Sparkles className="size-5 text-primary" />
              <div className="flex-1 text-sm">
                <span className="font-medium">{state.quota.plan_code}</span>{" "}
                planı — <span>{state.quota.used}</span> /{" "}
                <span>{state.quota.limit}</span> profil kullanılıyor
              </div>
              {state.quota.used >= state.quota.limit && (
                <Badge variant="outline" className="text-amber-700">
                  Kota dolu
                </Badge>
              )}
            </CardContent>
          </Card>

          {state.data.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
                <Sparkles className="size-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Henüz stil profili oluşturmadınız. İlk profili oluşturarak
                  yazılarınıza özgü ses tonunu sisteme öğretin.
                </p>
                <Button onClick={() => setCreating(true)}>
                  <Plus className="mr-1 size-4" />
                  İlk profili oluştur
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {state.data.map((profile) => {
                const status = STATUS_LABEL[profile.status];
                const isDeleting = deletingId === profile.id;
                const isReanalyzing = reanalyzingId === profile.id;
                return (
                  <Card key={profile.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <CardTitle className="text-base">
                            {profile.name}
                          </CardTitle>
                          <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                            <Badge
                              variant="secondary"
                              className={cn("h-5", status.cls)}
                            >
                              {status.label}
                            </Badge>
                            <span className="text-xs">
                              {profile.sample_count} örnek
                            </span>
                            <span className="text-xs">
                              {formatTrDate(profile.created_at)}
                            </span>
                          </CardDescription>
                          {profile.style_summary && (
                            <p className="mt-2 line-clamp-2 text-sm">
                              {profile.style_summary}
                            </p>
                          )}
                          {profile.error_message && (
                            <p className="mt-2 flex items-start gap-1 text-xs text-destructive">
                              <AlertCircle className="mt-0.5 size-3 shrink-0" />
                              {profile.error_message}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          {profile.status === "failed" && (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={isReanalyzing}
                              onClick={() => void handleReanalyze(profile)}
                            >
                              {isReanalyzing ? (
                                <Loader2 className="mr-1 size-3 animate-spin" />
                              ) : null}
                              Tekrar
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            asChild
                            disabled={isDeleting}
                          >
                            <Link
                              href={`/app/style-profiles/${profile.id}`}
                              aria-label="Detay"
                            >
                              <ArrowRight className="size-4" />
                            </Link>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={isDeleting}
                            onClick={() => void handleDelete(profile)}
                          >
                            {isDeleting ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <Trash2 className="size-4 text-destructive" />
                            )}
                          </Button>
                        </div>
                      </div>
                    </CardHeader>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}

      <CreateProfileDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false);
          void load();
        }}
      />
    </div>
  );
}
