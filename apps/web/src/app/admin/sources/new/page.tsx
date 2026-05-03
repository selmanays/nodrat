"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { CheckCircle2, AlertTriangle, FlaskConical } from "lucide-react";
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
import {
  ApiException,
  createSource,
  testFeed,
  type FeedReportPublic,
  type SourceCreatePayload,
  type SourceType,
} from "@/lib/api";

const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

export default function NewSourcePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [feedReport, setFeedReport] = useState<FeedReportPublic | null>(null);

  const [form, setForm] = useState<SourceCreatePayload>({
    name: "",
    slug: "",
    domain: "",
    type: "rss",
    base_url: "",
    language: "tr",
    country: "TR",
    category: null,
    crawl_interval_minutes: 30,
    config_json: null,
  });

  function update<K extends keyof SourceCreatePayload>(
    key: K,
    value: SourceCreatePayload[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleTestFeed() {
    if (!form.base_url) {
      toast.error("Önce feed URL'sini gir");
      return;
    }
    setTesting(true);
    try {
      const report = await testFeed(form.base_url);
      setFeedReport(report);
      if (report.fetched && report.item_count > 0) {
        toast.success(`Feed parse edildi — ${report.item_count} item`);
        // Auto-fill name from feed title
        if (!form.name && report.feed_title) {
          update("name", report.feed_title);
        }
      } else {
        toast.warning(report.error || "Feed parse edilemedi");
      }
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Feed test başarısız");
    } finally {
      setTesting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!SLUG_RE.test(form.slug)) {
      toast.error("Slug geçersiz: küçük harf + rakam + tire");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createSource(form);
      toast.success("Kaynak oluşturuldu (pasif). Aktivasyon için detay sayfasına geç.");
      router.push(`/admin/sources/${created.id}`);
    } catch (error) {
      const apiError = error as ApiException;
      if (apiError.code === "ROBOTS_DISALLOWED") {
        toast.error("robots.txt bu kaynağa erişimi engelliyor — kategorik red");
      } else if (apiError.code === "SLUG_EXISTS") {
        toast.error("Bu slug zaten kullanımda");
      } else {
        toast.error(apiError.message || "Oluşturulamadı");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Yeni Kaynak</h1>
        <p className="text-sm text-muted-foreground">
          robots.txt otomatik kontrol edilir. Aktivasyon ayrı adım — önce
          oluştur, sonra detay sayfasından 5 maddelik uyumluluk kontrolüyle
          aktif et.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Temel bilgiler</CardTitle>
            <CardDescription>
              Slug oluşturulduktan sonra değiştirilemez.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Görünen ad *</Label>
              <Input
                id="name"
                required
                minLength={2}
                maxLength={120}
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                placeholder="BBC Türkçe"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="slug">Slug *</Label>
              <Input
                id="slug"
                required
                pattern="[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
                value={form.slug}
                onChange={(e) =>
                  update("slug", e.target.value.toLowerCase().trim())
                }
                placeholder="bbc-turkce"
              />
              <p className="text-xs text-muted-foreground">
                Küçük harf + rakam + tire. URL'lerde geçer.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="domain">Domain *</Label>
              <Input
                id="domain"
                required
                value={form.domain}
                onChange={(e) =>
                  update("domain", e.target.value.toLowerCase().trim())
                }
                placeholder="bbc.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="type">Tür</Label>
              <select
                id="type"
                value={form.type}
                onChange={(e) =>
                  update("type", e.target.value as SourceType)
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="rss">RSS feed</option>
                <option value="category_page" disabled>
                  Kategori sayfa (Faz 2)
                </option>
                <option value="manual" disabled>
                  Manuel (Faz 2)
                </option>
              </select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="base_url">Feed URL *</Label>
              <div className="flex gap-2">
                <Input
                  id="base_url"
                  type="url"
                  required
                  value={form.base_url}
                  onChange={(e) => update("base_url", e.target.value)}
                  placeholder="https://www.bbc.com/turkce/index.xml"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTestFeed}
                  disabled={testing || !form.base_url}
                >
                  <FlaskConical className="h-4 w-4" />
                  {testing ? "Test ediliyor…" : "Feed test et"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Test sonucunda örnek 5 başlık aşağıda gösterilir. DB'ye yazılmaz.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="language">Dil</Label>
              <Input
                id="language"
                value={form.language}
                onChange={(e) => update("language", e.target.value)}
                placeholder="tr"
                maxLength={10}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="country">Ülke</Label>
              <Input
                id="country"
                value={form.country}
                onChange={(e) => update("country", e.target.value.toUpperCase())}
                placeholder="TR"
                maxLength={8}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Kategori</Label>
              <Input
                id="category"
                value={form.category ?? ""}
                onChange={(e) =>
                  update("category", e.target.value || null)
                }
                placeholder="Genel"
                maxLength={80}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="interval">Tarama aralığı (dk)</Label>
              <Input
                id="interval"
                type="number"
                min={5}
                max={1440}
                value={form.crawl_interval_minutes ?? 30}
                onChange={(e) =>
                  update(
                    "crawl_interval_minutes",
                    parseInt(e.target.value) || 30,
                  )
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Feed test sonucu */}
        {feedReport && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {feedReport.fetched && feedReport.item_count > 0 ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                    Feed önizleme
                  </>
                ) : (
                  <>
                    <AlertTriangle className="h-5 w-5 text-amber-600" />
                    Feed sorunlu
                  </>
                )}
              </CardTitle>
              <CardDescription>
                {feedReport.feed_title || "—"} · {feedReport.item_count} item ·
                HTTP {feedReport.status_code}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {feedReport.error && (
                <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {feedReport.error}
                </div>
              )}
              {feedReport.sample_items.length > 0 && (
                <div className="space-y-2">
                  {feedReport.sample_items.map((item, idx) => (
                    <div
                      key={idx}
                      className="rounded-md border bg-muted/30 px-3 py-2"
                    >
                      <div className="font-medium text-sm">{item.title}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {item.link}
                      </div>
                      {item.published_at && (
                        <div className="text-xs text-muted-foreground">
                          {new Date(item.published_at).toLocaleString("tr-TR")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Compliance reminder */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Badge variant="warning">Hatırlatma</Badge>
              5 maddelik uyumluluk kontrolü
            </CardTitle>
            <CardDescription>
              Bu form sadece kaynağı pasif olarak oluşturur. Aktivasyon ayrı
              adımdadır — detay sayfasında 5 maddelik onay vermeden taranmaz.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm text-muted-foreground">
              <li>• robots.txt otomatik kontrol</li>
              <li>• Paywall yok onayı</li>
              <li>• Kullanım Şartları scraping yasaklamıyor</li>
              <li>• Kamuya açık içerik</li>
              <li>• Ticari kullanım riski değerlendirildi</li>
            </ul>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/admin/sources")}
          >
            İptal
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Oluşturuluyor…" : "Kaynak oluştur (pasif)"}
          </Button>
        </div>
      </form>
    </div>
  );
}
