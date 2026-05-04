"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CircleX,
  Loader,
  MoreVertical,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import type { LucideIcon } from "lucide-react";

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/blocks/page-header";
import { cn } from "@/lib/utils";
import {
  ApiException,
  getQueueOverview,
  listFailedJobs,
  resolveFailedJob,
  retryFailedJob,
  type FailedJobPublic,
  type QueueOverviewResponse,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Sözlükler
// ---------------------------------------------------------------------------

const ISTIPI_ETIKETI: Record<string, string> = {
  "source.fetch_rss": "RSS çek",
  "source.fetch_category": "Kategori çek",
  "article.discover": "Haber keşif",
  "article.fetch_detail": "Detay indir",
  "article.extract": "Metin çıkar",
  "article.clean": "Temizle",
  "media.download": "Görsel indir",
  "media.hash": "Görsel hash",
  "article.dedupe": "Yinele tespiti",
  "source.healthcheck": "Kaynak sağlık",
};

const KUYRUK_ETIKETI: Record<string, string> = {
  scraper: "Kazıyıcı",
  cleaner: "Temizleyici",
  embedding: "Embedding",
  rag: "RAG",
  worker_scraper: "Kazıyıcı",
  worker_cleaner: "Temizleyici",
  worker_embedding: "Embedding",
  worker_rag: "RAG",
  scheduler: "Zamanlayıcı",
};

// "Çözüldü" için yeşil dolu CircleCheck
function YesilDoluTik(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <circle cx="12" cy="12" r="10" />
      <path
        d="m9 11 3 3 4-4"
        stroke="white"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DurumRozeti({ cozuldu }: { cozuldu: boolean }) {
  const Ikon: LucideIcon | typeof YesilDoluTik = cozuldu
    ? YesilDoluTik
    : Loader;
  return (
    <Badge variant="outline" className="h-5.5 [&>svg]:size-3.5!">
      <Ikon
        data-icon="inline-start"
        className={cn(cozuldu ? "text-emerald-500" : "text-muted-foreground")}
      />
      {cozuldu ? "Çözüldü" : "Açık"}
    </Badge>
  );
}

function tariSaatBicimle(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Sayfa
// ---------------------------------------------------------------------------

export default function AdminQueuePage() {
  const [genelBakis, setGenelBakis] =
    useState<QueueOverviewResponse | null>(null);
  const [basarisizIsler, setBasarisizIsler] = useState<FailedJobPublic[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [sadeceCozulmemis, setSadeceCozulmemis] = useState(true);

  async function veriYukle() {
    setYukleniyor(true);
    try {
      const [genelSonuc, listeSonuc] = await Promise.all([
        getQueueOverview(),
        listFailedJobs({ unresolved_only: sadeceCozulmemis, limit: 50 }),
      ]);
      setGenelBakis(genelSonuc);
      setBasarisizIsler(listeSonuc.data);
    } catch (hata) {
      toast.error((hata as ApiException).message || "Yüklenemedi");
    } finally {
      setYukleniyor(false);
    }
  }

  useEffect(() => {
    void veriYukle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sadeceCozulmemis]);

  async function tekrarDene(id: string) {
    if (!confirm("Bu başarısız işi tekrar denemek istediğinden emin misin?"))
      return;
    try {
      const sonuc = await retryFailedJob(id);
      toast.success(
        `Yeniden kuyruğa alındı: ${sonuc.new_job_id.slice(0, 8)}…`,
      );
      await veriYukle();
    } catch (hata) {
      toast.error(
        (hata as ApiException).message || "Tekrar deneme başarısız",
      );
    }
  }

  async function olarakKapat(id: string) {
    const not = window.prompt("Kapanış notu (opsiyonel):");
    try {
      await resolveFailedJob(id, not || undefined);
      toast.success("Kapatıldı");
      await veriYukle();
    } catch (hata) {
      toast.error((hata as ApiException).message || "Kapatma başarısız");
    }
  }

  const cozulmemisSayisi = genelBakis?.failed_jobs_unresolved ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Kuyruk"
        description="Worker kuyruklarının durumunu izle, başarısız işleri yeniden dene veya kapat."
      />

      {cozulmemisSayisi > 0 && (
        <Alert>
          <AlertTriangle />
          <AlertTitle>
            {cozulmemisSayisi} çözülmemiş başarısız iş
          </AlertTitle>
          <AlertDescription>
            DLQ&apos;da retry veya kapat bekliyor. Aşağıdan inceleyebilirsin.
          </AlertDescription>
          <AlertAction>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSadeceCozulmemis(true);
                document
                  .getElementById("basarisiz-isler")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              İncele
            </Button>
          </AlertAction>
        </Alert>
      )}

      {/* Kuyruk özeti */}
      <div className="grid grid-cols-1 gap-4 pb-4 sm:grid-cols-2 lg:grid-cols-4">
        {yukleniyor && !genelBakis ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card
              key={i}
              className="rounded-2xl py-0 shadow-none ring-[var(--border)]"
            >
              <CardContent className="space-y-2 p-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-20" />
              </CardContent>
            </Card>
          ))
        ) : (genelBakis?.queues ?? []).length === 0 ? (
          <Card className="col-span-full rounded-2xl py-0 shadow-none ring-[var(--border)]">
            <CardContent className="p-6 text-center text-sm text-muted-foreground">
              Kuyruk bilgisi yok.
            </CardContent>
          </Card>
        ) : (
          (genelBakis?.queues ?? []).map((q) => (
            <Card
              key={q.name}
              className="rounded-2xl py-0 shadow-none ring-[var(--border)]"
            >
              <CardContent className="space-y-2 p-4">
                <div className="text-sm font-medium">
                  {KUYRUK_ETIKETI[q.name] ?? q.name}
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Sırada</span>
                    <span className="font-mono tabular-nums">
                      {q.queued_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Çalışıyor</span>
                    <span className="font-mono tabular-nums">
                      {q.running_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
                      24s başarılı
                    </span>
                    <span className="font-mono tabular-nums text-emerald-600">
                      {q.succeeded_count_24h}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
                      24s başarısız
                    </span>
                    <span
                      className={cn(
                        "font-mono tabular-nums",
                        q.failed_count_24h > 0 && "text-destructive",
                      )}
                    >
                      {q.failed_count_24h}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Filtre + yenile */}
      <div
        id="basarisiz-isler"
        className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Switch
            checked={sadeceCozulmemis}
            onCheckedChange={setSadeceCozulmemis}
          />
          <span>Sadece çözülmemiş</span>
        </label>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void veriYukle()}
          disabled={yukleniyor}
        >
          <RefreshCw className={cn(yukleniyor && "animate-spin")} />
          Yenile
        </Button>
      </div>

      {/* Başarısız işler tablosu */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/50 hover:bg-muted/50">
                  <TableHead className="px-6">İş tipi</TableHead>
                  <TableHead>Hata</TableHead>
                  <TableHead>Deneme</TableHead>
                  <TableHead>Son deneme</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {yukleniyor ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="px-6">
                        <Skeleton className="h-5 w-28" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-72" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-8" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-24" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16" />
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <Skeleton className="ml-auto size-8 rounded-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : basarisizIsler.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      {sadeceCozulmemis
                        ? "Çözülmemiş başarısız iş yok."
                        : "Hiç başarısız iş yok."}
                    </TableCell>
                  </TableRow>
                ) : (
                  basarisizIsler.map((is) => (
                    <TableRow key={is.id}>
                      <TableCell className="px-6">
                        <div className="font-medium">
                          {ISTIPI_ETIKETI[is.job_type] ?? is.job_type}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {is.job_type}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-[420px]">
                        <div
                          className="line-clamp-2 text-xs text-destructive"
                          title={is.error_message}
                        >
                          {is.error_message}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs tabular-nums">
                        {is.retry_count}×
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {tariSaatBicimle(is.last_attempt_at)}
                      </TableCell>
                      <TableCell>
                        <DurumRozeti cozuldu={!!is.resolved_at} />
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            aria-label={`${is.job_type} işlemleri`}
                            className="ml-auto inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:bg-muted data-[state=open]:text-foreground [&_svg]:size-4 [&_svg]:shrink-0"
                          >
                            <MoreVertical />
                            <span className="sr-only">İşlemler</span>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {!is.resolved_at && (
                              <>
                                <DropdownMenuItem
                                  onClick={() => void tekrarDene(is.id)}
                                >
                                  <RotateCcw />
                                  Tekrar dene
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => void olarakKapat(is.id)}
                                >
                                  <CircleX />
                                  Kapat
                                </DropdownMenuItem>
                              </>
                            )}
                            {is.resolved_at && (
                              <DropdownMenuItem disabled>
                                Bu iş çözülmüş
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between border-t px-6 py-3 text-sm text-muted-foreground">
            <span>
              {yukleniyor ? (
                <Skeleton className="inline-block h-3.5 w-32 align-middle" />
              ) : (
                <>
                  <span className="font-medium tabular-nums text-foreground">
                    {basarisizIsler.length}
                  </span>{" "}
                  başarısız iş listeleniyor
                </>
              )}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
