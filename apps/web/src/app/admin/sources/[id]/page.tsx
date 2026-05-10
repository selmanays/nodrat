"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
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
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiException,
  activateSource,
  getSource,
  robotsCheck,
  updateSource,
  type ComplianceChecklist,
  type RobotsReportPublic,
  type SourcePublic,
} from "@/lib/api";

const CHECKLIST_ITEMS: Array<{
  key: keyof ComplianceChecklist;
  label: string;
  detail: string;
}> = [
  {
    key: "robots_txt_checked",
    label: "robots.txt kontrol edildi",
    detail: "Otomatik fetch + güncel başarısız değil.",
  },
  {
    key: "not_paywalled",
    label: "İçerik paywall arkasında değil",
    detail: "Tüm haberler oturum açmadan okunabiliyor.",
  },
  {
    key: "tos_allows_scraping",
    label: "Kullanım Şartları scraping'i yasaklamıyor",
    detail: "ToS'a girip scraping ile ilgili kuralları kontrol ettim.",
  },
  {
    key: "publicly_accessible",
    label: "Sayfalar kamuya açık",
    detail: "Üyelik / paywall / IP-region gerektirmez.",
  },
  {
    key: "commercial_risk_assessed",
    label: "Ticari kullanım riski değerlendirildi",
    detail: "FSEK 25 kelime kuralı + ticari rekabet riski yeterince düşük.",
  },
];

export default function SourceDetailPage() {
  const params = useParams<{ id: string }>();
  const sourceId = params?.id ?? "";

  const [source, setSource] = useState<SourcePublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [robotsLoading, setRobotsLoading] = useState(false);
  const [robotsReport, setRobotsReport] = useState<RobotsReportPublic | null>(
    null,
  );

  const [checklist, setChecklist] = useState<ComplianceChecklist>({
    robots_txt_checked: false,
    not_paywalled: false,
    tos_allows_scraping: false,
    publicly_accessible: false,
    commercial_risk_assessed: false,
  });
  const [note, setNote] = useState("");
  const [activating, setActivating] = useState(false);

  // Polling ayarları edit formu (#565)
  const [intervalDraft, setIntervalDraft] = useState<number>(30);
  const [realtimeDraft, setRealtimeDraft] = useState<boolean>(false);
  const [savingPolling, setSavingPolling] = useState(false);

  async function load() {
    if (!sourceId) return;
    setLoading(true);
    try {
      const data = await getSource(sourceId);
      setSource(data);
      // robots check zaten yapıldıysa checkbox'ı işaretle
      if (data.robots_txt_compliant) {
        setChecklist((prev) => ({ ...prev, robots_txt_checked: true }));
      }
      // Polling form draft'ını mevcut değerlerle hidrate et
      setIntervalDraft(data.crawl_interval_minutes);
      setRealtimeDraft(data.realtime_enabled);
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kaynak yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId]);

  async function handleRobotsCheck() {
    setRobotsLoading(true);
    try {
      const report = await robotsCheck(sourceId);
      setRobotsReport(report);
      if (report.base_url_allowed) {
        toast.success("robots.txt erişime izin veriyor");
        setChecklist((prev) => ({ ...prev, robots_txt_checked: true }));
      } else {
        toast.error("robots.txt erişimi engelliyor — kaynak otomatik pasif yapıldı");
      }
      await load();
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kontrol başarısız");
    } finally {
      setRobotsLoading(false);
    }
  }

  function allChecked(): boolean {
    return (
      checklist.robots_txt_checked &&
      checklist.not_paywalled &&
      checklist.tos_allows_scraping &&
      checklist.publicly_accessible &&
      checklist.commercial_risk_assessed
    );
  }

  async function handleSavePolling() {
    if (!source) return;
    if (
      intervalDraft === source.crawl_interval_minutes &&
      realtimeDraft === source.realtime_enabled
    ) {
      toast.info("Değişiklik yok");
      return;
    }
    if (intervalDraft < 5 || intervalDraft > 1440) {
      toast.error("Aralık 5–1440 dakika arası olmalı");
      return;
    }
    setSavingPolling(true);
    try {
      const updated = await updateSource(sourceId, {
        crawl_interval_minutes: intervalDraft,
        realtime_enabled: realtimeDraft,
      });
      setSource(updated);
      toast.success("Polling ayarları kaydedildi");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kaydetme başarısız");
    } finally {
      setSavingPolling(false);
    }
  }

  async function handleActivate() {
    if (!allChecked()) {
      toast.error("5 madde de işaretlenmelidir");
      return;
    }
    setActivating(true);
    try {
      const updated = await activateSource(sourceId, {
        checklist,
        note: note || undefined,
      });
      setSource(updated);
      toast.success("Kaynak aktif edildi — taranmaya başlanacak");
    } catch (error) {
      const apiError = error as ApiException;
      if (apiError.code === "ROBOTS_DISALLOWED") {
        toast.error("Aktivasyon başarısız: robots.txt değişmiş");
      } else if (apiError.code === "COMPLIANCE_INCOMPLETE") {
        toast.error("5 maddenin tamamı işaretli değil");
      } else {
        toast.error(apiError.message || "Aktivasyon başarısız");
      }
    } finally {
      setActivating(false);
    }
  }

  if (loading) {
    return (
      <div className="text-sm text-muted-foreground">Yükleniyor…</div>
    );
  }

  if (!source) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/sources">
            <ArrowLeft className="h-4 w-4" />
            Kaynaklara dön
          </Link>
        </Button>
        <p>Kaynak bulunamadı.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/sources">
            <ArrowLeft className="h-4 w-4" />
            Kaynaklara dön
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          {source.is_active ? (
            <Badge variant="secondary">Aktif</Badge>
          ) : (
            <Badge variant="secondary">Pasif</Badge>
          )}
          <Badge variant="outline">{source.type}</Badge>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{source.name}</h1>
          <p className="font-mono text-sm text-muted-foreground">{source.slug}</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/admin/sources/${sourceId}/configs`}>
              Config versiyonları
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href={`/admin/sources/${sourceId}/test-selectors`}>
              Selector test
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Bilgiler</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Domain</span>
              <span className="font-mono">{source.domain}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Feed URL</span>
              <a
                href={source.base_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-primary hover:underline underline-offset-4 truncate max-w-[60%]"
              >
                {source.base_url}
              </a>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Dil / Ülke</span>
              <span>
                {source.language} / {source.country}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Kategori</span>
              <span>{source.category || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tarama aralığı</span>
              <span>{source.crawl_interval_minutes} dk</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Güvenilirlik</span>
              <span className="font-mono">
                {source.reliability_score.toFixed(2)}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {source.robots_txt_compliant === true ? (
                <ShieldCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              ) : source.robots_txt_compliant === false ? (
                <ShieldAlert className="h-5 w-5 text-red-600" />
              ) : (
                <ShieldQuestion className="h-5 w-5 text-amber-600" />
              )}
              robots.txt durumu
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              {source.robots_txt_compliant === true && (
                <p className="text-emerald-700">
                  Erişim izinli (admin override yok).
                </p>
              )}
              {source.robots_txt_compliant === false && (
                <p className="text-destructive">
                  Erişim engelli. Kaynak otomatik pasif tutulur.
                </p>
              )}
              {source.robots_txt_compliant === null && (
                <p className="text-amber-700">
                  Henüz kontrol edilmedi. Aktivasyon öncesi kontrol önerilir.
                </p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRobotsCheck}
              disabled={robotsLoading}
            >
              {robotsLoading ? "Kontrol ediliyor…" : "Şimdi kontrol et"}
            </Button>

            {robotsReport && (
              <div className="space-y-1.5 rounded-md bg-muted/40 p-3 text-xs">
                <div>HTTP {robotsReport.status_code}</div>
                <div>Crawl-delay: {robotsReport.crawl_delay_sec}s</div>
                {robotsReport.sitemaps.length > 0 && (
                  <div>Sitemap: {robotsReport.sitemaps.length}</div>
                )}
                {robotsReport.error && (
                  <div className="text-destructive">{robotsReport.error}</div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 5-item compliance checklist */}
      {!source.is_active && (
        <Card>
          <CardHeader>
            <CardTitle>Aktivasyon — 5 maddelik uyumluluk</CardTitle>
            <CardDescription>
              5'i de işaretlenmediği sürece kaynak aktif olamaz. Yasal sorumluluk
              bu adımdadır.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              {CHECKLIST_ITEMS.map((item) => (
                <div
                  key={item.key}
                  className="flex items-start gap-3 rounded-md border p-3"
                >
                  <Checkbox
                    id={item.key}
                    checked={checklist[item.key]}
                    onCheckedChange={(checked) =>
                      setChecklist((prev) => ({ ...prev, [item.key]: checked }))
                    }
                    className="mt-0.5"
                  />
                  <div className="space-y-1">
                    <Label
                      htmlFor={item.key}
                      className="font-medium cursor-pointer"
                    >
                      {item.label}
                    </Label>
                    <p className="text-xs text-muted-foreground">{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="space-y-2">
              <Label htmlFor="note">Not (opsiyonel)</Label>
              <Textarea
                id="note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Aktivasyon ile ilgili not (audit log'a yazılır)…"
                maxLength={500}
                rows={2}
              />
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleActivate}
                disabled={!allChecked() || activating}
                variant="default"
              >
                <CheckCircle2 className="h-4 w-4" />
                {activating ? "Aktif ediliyor…" : "Aktif et"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {source.is_active && (
        <Card>
          <CardHeader>
            <CardTitle>Polling ayarları</CardTitle>
            <CardDescription>
              Tarama aralığı, realtime modu ve adaptive tier telemetri.
              Değişiklikler audit log&apos;a yazılır.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="crawl-interval">Tarama aralığı (dakika)</Label>
              <Input
                id="crawl-interval"
                type="number"
                min={5}
                max={1440}
                value={intervalDraft}
                onChange={(e) =>
                  setIntervalDraft(Number(e.target.value) || 0)
                }
                className="max-w-[180px]"
              />
              <p className="text-xs text-muted-foreground">
                5–1440 dakika. Düşük değerler kaynak sunucusuna yük bindirir; bant
                tasarrufu Conditional GET (ETag) ile sağlanır.
              </p>
            </div>

            <div className="flex items-start justify-between gap-4 rounded-md border p-3">
              <div className="space-y-1">
                <Label htmlFor="realtime-enabled" className="font-medium">
                  Realtime mode
                </Label>
                <p className="text-xs text-muted-foreground">
                  Açık olduğunda kaynak <span className="font-mono">polling_tier</span>{" "}
                  hesabına dahil olur (Faz 3&apos;te devreye girer). Şu an sadece bayrak
                  kaydedilir; tarama aralığını değiştirmez.
                </p>
              </div>
              <Switch
                id="realtime-enabled"
                checked={realtimeDraft}
                onCheckedChange={setRealtimeDraft}
              />
            </div>

            {/* Adaptive tier telemetri (#578 Faz 2 shadow mode) */}
            <TierTelemetry source={source} />

            <div className="flex justify-end">
              <Button
                onClick={handleSavePolling}
                disabled={savingPolling}
                variant="default"
              >
                {savingPolling ? "Kaydediliyor…" : "Kaydet"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/**
 * Adaptive tier telemetri paneli — #578 Faz 2 shadow mode gözlem.
 *
 * compute_tier her başarılı RSS fetch sonunda çalışır; sonucu
 * source.would_be_tier + tier_metadata'ya yazar. polling_tier henüz değişmez
 * (shadow mode; Faz 3'te apply edilir).
 */
function TierTelemetry({ source }: { source: SourcePublic }) {
  const md = source.tier_metadata;
  const current = source.polling_tier;
  const wouldBe = source.would_be_tier;
  const diverged = wouldBe && wouldBe !== current;

  if (!md) {
    return (
      <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
        Henüz tier hesabı yapılmamış. Bir sonraki başarılı fetch sonrası burada
        telemetri görünecek.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium text-foreground">Adaptive tier (shadow)</span>
        {diverged ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
            divergence: {current} → {wouldBe}
          </span>
        ) : (
          <span className="text-muted-foreground">stable: {current}</span>
        )}
      </div>
      {md.cold_start ? (
        <p className="text-muted-foreground">
          Cold start (kaynak {md.source_age_hours?.toFixed(1)} saatlik) — tier
          24 saat sonra kalibre olacak.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-muted-foreground">
          <span>items_1h:</span>
          <span className="text-foreground">{md.items_1h ?? "—"}</span>
          <span>items_6h:</span>
          <span className="text-foreground">{md.items_6h ?? "—"}</span>
          <span>hours_since_new:</span>
          <span className="text-foreground">
            {md.hours_since_new !== null
              ? md.hours_since_new.toFixed(1)
              : "—"}
          </span>
          <span>consecutive_unchanged:</span>
          <span className="text-foreground">{md.consecutive_unchanged}</span>
          {md.candidate_tier && md.candidate_tier !== current && (
            <>
              <span>candidate:</span>
              <span className="text-foreground">{md.candidate_tier}</span>
            </>
          )}
          {md.dwell_remaining_sec !== undefined &&
            md.dwell_remaining_sec > 0 && (
              <>
                <span>dwell_remaining:</span>
                <span className="text-foreground">
                  {Math.ceil(md.dwell_remaining_sec)}s
                </span>
              </>
            )}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        Computed: {new Date(md.computed_at).toLocaleString("tr-TR")}
      </p>
    </div>
  );
}
