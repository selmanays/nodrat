"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CircleX,
  MoreVertical,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { InfoTooltip } from "@/components/info-tooltip";
import { PageHeader } from "@/components/blocks/page-header";
import { formatTrDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ApiException,
  bulkResolveFailedJobs,
  bulkRetryFailedJobs,
  getQueueOverview,
  listFailedJobs,
  listMaintenanceTasks,
  resolveFailedJob,
  retryFailedJob,
  runMaintenanceNow,
  type FailedJobPublic,
  type MaintenanceTaskInfo,
  type QueueOverviewResponse,
} from "@/lib/api";
import { Play, Wrench } from "lucide-react";

// ---------------------------------------------------------------------------
// Sözlükler — #444/#445/#446 sonrası gerçek backend kuyruk + job_type isimleri
// ---------------------------------------------------------------------------

const ISTIPI_ETIKETI: Record<string, string> = {
  // Crawl pipeline
  "source.fetch_rss": "RSS çek",
  "source.fetch_category": "Kategori çek",
  "source.healthcheck": "Kaynak sağlık",
  "article.discover": "Haber keşif",
  "article.fetch_detail": "Detay indir",
  "article.extract": "Metin çıkar",
  "article.clean": "Temizle",
  "article.dedupe": "Yinele tespiti",
  // #445 — RSS re-emit (info, retry mantıksız)
  "article.duplicate_content": "Yinelenen içerik (RSS)",
  "article.discovered_timeout": "Keşif sonrası fetch yok",
  // Image VLM pipeline
  "media.download": "Görsel indir",
  "media.hash": "Görsel hash",
  "image.download": "Görsel indir",
  "image_vlm.process": "VLM görsel işleme",
  "tasks.image_vlm.process": "VLM görsel işleme",
};

function isTipiniBicimle(ham: string): string {
  if (ISTIPI_ETIKETI[ham]) return ISTIPI_ETIKETI[ham];
  // 'article.fetch_detail' → 'Article fetch detail'
  const parcalar = ham.split(/[._-]/);
  if (parcalar.length === 0) return ham;
  return parcalar
    .map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

const KUYRUK_ETIKETI: Record<string, string> = {
  // #444 — celery_app.task_routes ile birebir
  crawl_queue: "Kazıyıcı",
  embedding_queue: "Vektörleştirici",
  event_queue: "Etkinlik (cluster + agenda + raptor)",
  image_vlm_queue: "Görsel VLM",
  // Legacy / default
  media_queue: "Görsel (legacy)",
  default: "Varsayılan",
  celery: "Genel",
};

function kuyrukAdiniBicimle(ham: string): string {
  if (KUYRUK_ETIKETI[ham]) return KUYRUK_ETIKETI[ham];

  let temiz = ham
    .replace(/^worker[._-]/i, "")
    .replace(/^celery[._@-]/i, "")
    .replace(/^queue[._-]/i, "");

  if (/scrap|crawl/i.test(temiz)) return "Kazıyıcı";
  if (/clean/i.test(temiz)) return "Temizleyici";
  if (/embed|vector/i.test(temiz)) return "Vektörleştirici";
  if (/event|cluster|agenda|raptor/i.test(temiz)) return "Etkinlik";
  if (/vlm|\bimage\b|gorsel|görsel/i.test(temiz)) return "Görsel VLM";
  if (/schedul|beat/i.test(temiz)) return "Zamanlayıcı";
  if (/email|mail/i.test(temiz)) return "E-posta";

  temiz = temiz.replace(/[_-]/g, " ");
  return temiz.charAt(0).toUpperCase() + temiz.slice(1);
}

function hataAciklamasi(jobType: string, errorMessage: string): string {
  const m = errorMessage.toLowerCase();

  // #445 — duplicate_content özel mesaj (info-level)
  if (jobType === "article.duplicate_content")
    return "RSS yeniden yayım (info)";

  if (/timeout|timed out|deadlin/.test(m)) return "Zaman aşımı";
  if (/connection refused|connect.*refus|ec[onn]+reset/.test(m))
    return "Bağlantı reddedildi";
  if (/network|connection|connect|dns|resolve/.test(m))
    return "Ağ bağlantı hatası";
  if (/\b404\b|not found/.test(m)) return "Kaynak bulunamadı";
  if (/\b403\b|forbidden|access denied/.test(m)) return "Erişim reddedildi";
  if (/\b401\b|unauthor/.test(m)) return "Yetki yok";
  if (/\b429\b|rate.?limit|too many requests/.test(m)) return "Hız sınırı aşıldı";
  if (/\b5\d{2}\b|server error|bad gateway|gateway timeout/.test(m))
    return "Sunucu hatası";
  if (/robots/.test(m)) return "Robots engeli";
  if (
    /parse|parsing|invalid (?:json|xml|html)|malformed|extraction failed/.test(m)
  )
    return "Ayrıştırma başarısız";
  if (/ssl|certificate|tls/.test(m)) return "Sertifika hatası";
  if (/captcha/.test(m)) return "CAPTCHA engeli";
  if (/quota|limit exceed/.test(m)) return "Kota aşıldı";
  if (/empty|no content|no data/.test(m)) return "İçerik boş";
  if (/content_hash already exists|duplicate/.test(m))
    return "Yinelenen içerik";

  const ISTIPINE_GORE: Record<string, string> = {
    "source.fetch_rss": "RSS çekilemedi",
    "source.fetch_category": "Kategori sayfası çekilemedi",
    "article.discover": "Keşif başarısız",
    "article.fetch_detail": "Detay indirilemedi",
    "article.extract": "Metin çıkarılamadı",
    "article.clean": "Temizleme başarısız",
    "article.discovered_timeout": "RSS keşif sonrası fetch yapılamadı",
    "media.download": "Görsel indirilemedi",
    "image.download": "Görsel indirilemedi",
    "media.hash": "Görsel hash başarısız",
    "image_vlm.process": "VLM işleme başarısız",
    "tasks.image_vlm.process": "VLM işleme başarısız",
    "article.dedupe": "Yinele tespiti başarısız",
    "source.healthcheck": "Sağlık kontrolü başarısız",
  };
  return ISTIPINE_GORE[jobType] ?? "Bilinmeyen hata";
}

function DurumRozeti({ cozuldu }: { cozuldu: boolean }) {
  return (
    <Badge variant="outline" className="h-5.5">
      {cozuldu ? "Çözüldü" : "Açık"}
    </Badge>
  );
}

// #445 — severity için renk + etiket
function SeverityRozeti({ severity }: { severity?: string }) {
  const sev = severity ?? "error";
  if (sev === "permanent_info") {
    return (
      <Badge
        variant="outline"
        className="h-5.5 text-blue-600 dark:text-blue-400"
      >
        Bilgi
      </Badge>
    );
  }
  if (sev === "warning") {
    return (
      <Badge
        variant="outline"
        className="h-5.5 text-amber-600 dark:text-amber-400"
      >
        Uyarı
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="h-5.5 text-destructive">
      Hata
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Sayfa
// ---------------------------------------------------------------------------

const SAYFA_BOYUTLARI = [25, 50, 100, 200] as const;
type SayfaBoyutu = (typeof SAYFA_BOYUTLARI)[number];

export default function AdminQueuePage() {
  const [genelBakis, setGenelBakis] =
    useState<QueueOverviewResponse | null>(null);
  const [basarisizIsler, setBasarisizIsler] = useState<FailedJobPublic[]>([]);
  const [bakimGorevleri, setBakimGorevleri] = useState<MaintenanceTaskInfo[]>(
    [],
  );
  const [calisanBakim, setCalisanBakim] = useState<Set<string>>(new Set());
  const [toplam, setToplam] = useState(0);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [sadeceCozulmemis, setSadeceCozulmemis] = useState(true);
  const [bilgileriDahilEt, setBilgileriDahilEt] = useState(false);
  const [isTipiFiltresi, setIsTipiFiltresi] = useState<string>("all");
  const [siddetFiltresi, setSiddetFiltresi] = useState<string>("default");
  const [sayfa, setSayfa] = useState(1);
  const [sayfaBoyutu, setSayfaBoyutu] = useState<SayfaBoyutu>(50);
  const [otoYenile, setOtoYenile] = useState(true);
  const [secilenIds, setSecilenIds] = useState<Set<string>>(new Set());

  const isMounted = useRef(false);

  async function veriYukle() {
    setYukleniyor(true);
    try {
      const offset = (sayfa - 1) * sayfaBoyutu;
      const [genelSonuc, listeSonuc, bakimSonuc] = await Promise.all([
        getQueueOverview(),
        listFailedJobs({
          unresolved_only: sadeceCozulmemis,
          job_type: isTipiFiltresi === "all" ? undefined : isTipiFiltresi,
          severity:
            siddetFiltresi === "default"
              ? undefined
              : (siddetFiltresi as
                  | "error"
                  | "warning"
                  | "permanent_info"
                  | "all"),
          include_info: bilgileriDahilEt || siddetFiltresi !== "default",
          limit: sayfaBoyutu,
          offset,
        }),
        listMaintenanceTasks(),
      ]);
      setGenelBakis(genelSonuc);
      setBasarisizIsler(listeSonuc.data);
      setToplam(listeSonuc.total);
      setBakimGorevleri(bakimSonuc.tasks);
    } catch (hata) {
      toast.error((hata as ApiException).message || "Yüklenemedi");
    } finally {
      setYukleniyor(false);
    }
  }

  async function bakimSimdiCalistir(taskName: string) {
    setCalisanBakim((prev) => new Set(prev).add(taskName));
    try {
      const sonuc = await runMaintenanceNow(taskName);
      toast.success(
        `Çalıştırıldı: ${sonuc.celery_task_id.slice(0, 8)}…`,
      );
      // 2sn sonra yenile — task hızlı bitebilir
      setTimeout(() => void veriYukle(), 2000);
    } catch (hata) {
      toast.error((hata as ApiException).message || "Çalıştırma başarısız");
    } finally {
      setCalisanBakim((prev) => {
        const next = new Set(prev);
        next.delete(taskName);
        return next;
      });
    }
  }

  // İlk yükleme + filtre/sayfa değişince
  useEffect(() => {
    void veriYukle();
    isMounted.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sadeceCozulmemis,
    bilgileriDahilEt,
    isTipiFiltresi,
    siddetFiltresi,
    sayfa,
    sayfaBoyutu,
  ]);

  // Filter değişince sayfa 1'e dön
  useEffect(() => {
    if (isMounted.current) setSayfa(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sadeceCozulmemis, bilgileriDahilEt, isTipiFiltresi, siddetFiltresi]);

  // #446 — auto-refresh 10s, sadece sayfa görünür iken
  useEffect(() => {
    if (!otoYenile) return;
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        void veriYukle();
      }
    }, 10_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    otoYenile,
    sadeceCozulmemis,
    bilgileriDahilEt,
    isTipiFiltresi,
    siddetFiltresi,
    sayfa,
    sayfaBoyutu,
  ]);

  async function tekrarDene(id: string, severity?: string) {
    if (severity === "permanent_info") {
      toast.info("Bilgi kayıtları için tekrar deneme mantıklı değil");
      return;
    }
    if (!confirm("Bu başarısız işi tekrar denemek istediğinden emin misin?"))
      return;
    try {
      const sonuc = await retryFailedJob(id);
      const tid = sonuc.celery_task_id || sonuc.new_job_id;
      toast.success(`Celery'ye gönderildi: ${tid.slice(0, 8)}…`);
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

  // #462 — Bulk işlemler
  function secimDegistir(id: string, isChecked: boolean) {
    setSecilenIds((prev) => {
      const next = new Set(prev);
      if (isChecked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function tumSayfaSec(secili: boolean) {
    setSecilenIds((prev) => {
      const next = new Set(prev);
      if (secili) {
        for (const j of basarisizIsler) next.add(j.id);
      } else {
        for (const j of basarisizIsler) next.delete(j.id);
      }
      return next;
    });
  }

  function secimiTemizle() {
    setSecilenIds(new Set());
  }

  async function topluTekrarDene() {
    const ids = Array.from(secilenIds);
    if (ids.length === 0) return;
    if (
      !confirm(`${ids.length} işi Celery'ye yeniden göndermek istediğinden emin misin?`)
    )
      return;
    try {
      const sonuc = await bulkRetryFailedJobs(ids);
      if (sonuc.failed === 0) {
        toast.success(`${sonuc.succeeded} iş yeniden kuyruğa alındı`);
      } else {
        toast.warning(
          `${sonuc.succeeded} başarılı, ${sonuc.failed} başarısız (detaylar konsolda)`,
        );
        // Detayları konsola dök, admin debug için
        // eslint-disable-next-line no-console
        console.warn("bulk_retry partial failure", sonuc.results);
      }
      secimiTemizle();
      await veriYukle();
    } catch (hata) {
      toast.error(
        (hata as ApiException).message || "Toplu tekrar deneme başarısız",
      );
    }
  }

  async function topluKapat() {
    const ids = Array.from(secilenIds);
    if (ids.length === 0) return;
    const not = window.prompt(
      `${ids.length} iş için kapanış notu (opsiyonel):`,
    );
    if (not === null) return; // user cancelled prompt
    try {
      const sonuc = await bulkResolveFailedJobs(ids, not || undefined);
      toast.success(`${sonuc.succeeded} iş kapatıldı`);
      secimiTemizle();
      await veriYukle();
    } catch (hata) {
      toast.error(
        (hata as ApiException).message || "Toplu kapatma başarısız",
      );
    }
  }

  const cozulmemisSayisi = genelBakis?.failed_jobs_unresolved ?? 0;
  const workerCount = genelBakis?.worker_count ?? 0;
  const toplamSayfa = Math.max(1, Math.ceil(toplam / sayfaBoyutu));
  const ilkSatir = toplam === 0 ? 0 : (sayfa - 1) * sayfaBoyutu + 1;
  const sonSatir = Math.min(toplam, sayfa * sayfaBoyutu);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Kuyruk"
        description={`Worker kuyruklarının durumunu izle, başarısız işleri yeniden dene veya kapat. ${
          workerCount > 0
            ? `${workerCount} aktif worker.`
            : "Worker tespit edilemedi."
        }`}
      />

      {cozulmemisSayisi > 0 && (
        <Alert>
          <AlertTriangle />
          <AlertTitle>
            {cozulmemisSayisi} çözülmemiş başarısız iş
          </AlertTitle>
          <AlertDescription>
            DLQ&apos;da retry veya kapat bekliyor. Bilgi kayıtları (RSS yeniden
            yayım) bu sayıma dahil değildir.
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

      {/* Kuyruk özeti — pipeline-aligned 4 kart */}
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
                  {kuyrukAdiniBicimle(q.name)}
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
        <div className="flex flex-wrap items-center gap-3">
          <Select value={isTipiFiltresi} onValueChange={setIsTipiFiltresi}>
            <SelectTrigger size="sm" className="w-[200px]">
              <SelectValue placeholder="İş tipi" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm iş tipleri</SelectItem>
              {Object.entries(ISTIPI_ETIKETI).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={siddetFiltresi} onValueChange={setSiddetFiltresi}>
            <SelectTrigger size="sm" className="w-[170px]">
              <SelectValue placeholder="Şiddet" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Şiddet (varsayılan)</SelectItem>
              <SelectItem value="error">Sadece hata</SelectItem>
              <SelectItem value="warning">Sadece uyarı</SelectItem>
              <SelectItem value="permanent_info">Sadece bilgi</SelectItem>
              <SelectItem value="all">Hepsi (info dahil)</SelectItem>
            </SelectContent>
          </Select>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Switch
              checked={sadeceCozulmemis}
              onCheckedChange={setSadeceCozulmemis}
            />
            <span>Sadece çözülmemiş</span>
          </label>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Switch
              checked={bilgileriDahilEt}
              onCheckedChange={setBilgileriDahilEt}
              disabled={siddetFiltresi !== "default"}
            />
            <span>Bilgileri dahil et</span>
          </label>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Switch checked={otoYenile} onCheckedChange={setOtoYenile} />
            <span>Otomatik yenile (10s)</span>
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
      </div>

      {/* Bulk toolbar — #462 */}
      {secilenIds.size > 0 && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/30 bg-primary/5 px-4 py-3 backdrop-blur">
          <span className="text-sm">
            <span className="font-medium tabular-nums">{secilenIds.size}</span> kayıt
            seçildi
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void topluTekrarDene()}
            >
              <RotateCcw />
              Toplu tekrar dene
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void topluKapat()}
            >
              <CircleX />
              Toplu kapat
            </Button>
            <Button size="sm" variant="ghost" onClick={secimiTemizle}>
              Seçimi temizle
            </Button>
          </div>
        </div>
      )}

      {/* Başarısız işler tablosu */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/50 hover:bg-muted/50">
                  <TableHead className="px-6 w-10">
                    <Checkbox
                      aria-label="Tüm sayfayı seç"
                      checked={
                        basarisizIsler.length > 0 &&
                        basarisizIsler.every((j) => secilenIds.has(j.id))
                      }
                      onCheckedChange={(v) => tumSayfaSec(Boolean(v))}
                    />
                  </TableHead>
                  <TableHead>İş tipi</TableHead>
                  <TableHead>Şiddet</TableHead>
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
                        <Skeleton className="size-4" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-28" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-12" />
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
                      colSpan={8}
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
                        <Checkbox
                          aria-label={`${is.job_type} seç`}
                          checked={secilenIds.has(is.id)}
                          onCheckedChange={(v) =>
                            secimDegistir(is.id, Boolean(v))
                          }
                        />
                      </TableCell>
                      <TableCell className="font-medium">
                        {isTipiniBicimle(is.job_type)}
                      </TableCell>
                      <TableCell>
                        <SeverityRozeti severity={is.severity} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <span>
                            {hataAciklamasi(is.job_type, is.error_message)}
                          </span>
                          <InfoTooltip
                            content={
                              <pre className="max-w-xs whitespace-pre-wrap break-words font-mono text-xs">
                                {is.error_message}
                              </pre>
                            }
                          />
                        </div>
                      </TableCell>
                      <TableCell className="font-mono tabular-nums">
                        {is.retry_count}×
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatTrDate(is.last_attempt_at)}
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
                                  onClick={() =>
                                    void tekrarDene(is.id, is.severity)
                                  }
                                  disabled={is.severity === "permanent_info"}
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

          {/* Pagination footer — #446 */}
          <div className="flex flex-col gap-3 border-t px-6 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <span>
              {yukleniyor ? (
                <Skeleton className="inline-block h-3.5 w-32 align-middle" />
              ) : toplam === 0 ? (
                <>0 başarısız iş</>
              ) : (
                <>
                  <span className="font-medium tabular-nums text-foreground">
                    {ilkSatir}–{sonSatir}
                  </span>{" "}
                  /{" "}
                  <span className="font-medium tabular-nums text-foreground">
                    {toplam}
                  </span>{" "}
                  başarısız iş
                </>
              )}
            </span>
            <div className="flex items-center gap-2">
              <Select
                value={String(sayfaBoyutu)}
                onValueChange={(v) =>
                  setSayfaBoyutu(Number(v) as SayfaBoyutu)
                }
              >
                <SelectTrigger size="sm" className="w-[100px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SAYFA_BOYUTLARI.map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n}/sayfa
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                disabled={sayfa <= 1 || yukleniyor}
                onClick={() => setSayfa((s) => Math.max(1, s - 1))}
              >
                <ChevronLeft />
                Önceki
              </Button>
              <span className="tabular-nums">
                Sayfa {sayfa}/{toplamSayfa}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={sayfa >= toplamSayfa || yukleniyor}
                onClick={() => setSayfa((s) => Math.min(toplamSayfa, s + 1))}
              >
                Sonraki
                <ChevronRight />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Bakım görevleri — #468 */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <CardContent className="p-0">
          <div className="flex items-center gap-2 border-b px-6 py-4">
            <Wrench className="size-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Bakım görevleri</h3>
            <span className="text-xs text-muted-foreground">
              ({bakimGorevleri.length})
            </span>
            <span className="ml-auto text-xs text-muted-foreground">
              Beat schedule otomatik çalışır; admin bireysel olarak şimdi
              tetikleyebilir.
            </span>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/30 hover:bg-muted/30">
                  <TableHead className="px-6">Görev</TableHead>
                  <TableHead>Pipeline</TableHead>
                  <TableHead>Aralık</TableHead>
                  <TableHead>Son çalışma</TableHead>
                  <TableHead>Sonuç</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bakimGorevleri.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-20 text-center text-sm text-muted-foreground"
                    >
                      {yukleniyor
                        ? "Yükleniyor…"
                        : "Bakım görevi tanımlı değil."}
                    </TableCell>
                  </TableRow>
                ) : (
                  bakimGorevleri.map((g) => {
                    const lr = g.last_run;
                    const dispatched =
                      lr?.summary &&
                      typeof lr.summary === "object" &&
                      "dispatched" in lr.summary
                        ? (lr.summary as { dispatched: number }).dispatched
                        : null;
                    const calisiyor = calisanBakim.has(g.task_name);
                    return (
                      <TableRow key={g.task_name}>
                        <TableCell className="px-6">
                          <div className="font-medium">{g.label}</div>
                          <div className="font-mono text-xs text-muted-foreground">
                            {g.task_name}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {g.pipeline}
                        </TableCell>
                        <TableCell className="text-sm">
                          {g.interval_human}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {lr ? (
                            <>
                              {formatTrDate(lr.finished_at)}
                              <span className="ml-1 font-mono text-xs">
                                ({lr.duration_seconds.toFixed(1)}s,{" "}
                                {lr.triggered_by})
                              </span>
                            </>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {lr ? (
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="outline"
                                className={cn(
                                  "h-5.5",
                                  lr.status === "succeeded"
                                    ? "text-emerald-600"
                                    : "text-destructive",
                                )}
                              >
                                {lr.status === "succeeded"
                                  ? "Başarılı"
                                  : "Başarısız"}
                              </Badge>
                              {dispatched !== null && (
                                <span className="font-mono text-xs tabular-nums">
                                  {dispatched} dispatch
                                </span>
                              )}
                              {lr.summary && (
                                <InfoTooltip
                                  content={
                                    <pre className="max-w-xs whitespace-pre-wrap break-words font-mono text-xs">
                                      {JSON.stringify(lr.summary, null, 2)}
                                    </pre>
                                  }
                                />
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              Henüz çalıştırılmadı
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="px-6 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              void bakimSimdiCalistir(g.task_name)
                            }
                            disabled={calisiyor}
                          >
                            <Play className={cn(calisiyor && "animate-pulse")} />
                            {calisiyor ? "Gönderiliyor…" : "Şimdi çalıştır"}
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
