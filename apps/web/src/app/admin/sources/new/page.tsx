"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
} from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ApiException,
  createSource,
  testFeed,
  type FeedReportPublic,
  type SourceCreatePayload,
  type SourceType,
} from "@/lib/api";
import { formatTrDate } from "@/lib/format";

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

  // #71 — category_page selectors + pagination
  const [catSelectors, setCatSelectors] = useState({
    card: "",
    title: "",
    link: "",
    image: "",
    date: "",
  });
  const [detailSelectors, setDetailSelectors] = useState({
    title: "",
    subtitle: "",
    author: "",
    published: "",
    image: "",
    body: "",
  });
  type PaginationType = "none" | "page_param" | "next_link";
  const [paginationType, setPaginationType] = useState<PaginationType>("none");
  const [paginationCfg, setPaginationCfg] = useState({
    param_name: "page",
    start: 1,
    max_pages: 5,
    next_selector: "",
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

    // #71 — category_page için config_json build et
    let payload = { ...form };
    if (form.type === "category_page") {
      if (!catSelectors.card.trim()) {
        toast.error("Kategori sayfa kaynağı için 'card' selector zorunlu");
        return;
      }
      const listSels: Record<string, string> = {};
      for (const [k, v] of Object.entries(catSelectors)) {
        if (v.trim()) listSels[k] = v.trim();
      }
      const detailSels: Record<string, string> = {};
      for (const [k, v] of Object.entries(detailSelectors)) {
        if (v.trim()) detailSels[k] = v.trim();
      }
      const pagination: Record<string, string | number> = {
        type: paginationType,
        max_pages: Math.max(1, Math.min(20, paginationCfg.max_pages)),
      };
      if (paginationType === "page_param") {
        pagination.param_name = paginationCfg.param_name || "page";
        pagination.start = paginationCfg.start || 1;
      } else if (paginationType === "next_link") {
        if (!paginationCfg.next_selector.trim()) {
          toast.error("'next_link' için next_selector zorunlu");
          return;
        }
        pagination.next_selector = paginationCfg.next_selector.trim();
      }
      payload = {
        ...form,
        config_json: {
          list_selectors: listSels,
          detail_selectors: detailSels,
          pagination,
        },
      };
    }

    setSubmitting(true);
    try {
      const created = await createSource(payload);
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
              <Select
                value={form.type}
                onValueChange={(v) => update("type", v as SourceType)}
              >
                <SelectTrigger id="type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="rss">RSS feed</SelectItem>
                  <SelectItem value="category_page">
                    Kategori sayfa (#71)
                  </SelectItem>
                  <SelectItem value="manual" disabled>
                    Manuel (Faz 2)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="base_url">
                {form.type === "rss" ? "Feed URL *" : "Liste sayfa URL *"}
              </Label>
              <div className="flex gap-2">
                <Input
                  id="base_url"
                  type="url"
                  required
                  value={form.base_url}
                  onChange={(e) => update("base_url", e.target.value)}
                  placeholder={
                    form.type === "rss"
                      ? "https://www.bbc.com/turkce/index.xml"
                      : "https://www.evrensel.net/haber/dunya"
                  }
                />
                {form.type === "rss" && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleTestFeed}
                    disabled={testing || !form.base_url}
                  >
                    <FlaskConical className="h-4 w-4" />
                    {testing ? "Test ediliyor…" : "Feed test et"}
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {form.type === "rss"
                  ? "Test sonucunda örnek 5 başlık aşağıda gösterilir. DB'ye yazılmaz."
                  : "Kayıttan sonra 'Selector test' sayfasında selector'ları canlı doğrulayabilirsin."}
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

        {/* #71 — Category page selectors + pagination */}
        {form.type === "category_page" && (
          <Card>
            <CardHeader>
              <CardTitle>Liste sayfası selectors (#71)</CardTitle>
              <CardDescription>
                Kategori sayfasındaki haber kart yapısı. Kart container + 4 alt
                alan. Kayıttan sonra <strong>Selector test</strong> sayfasında
                doğrulayabilirsin.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                {(["card", "title", "link", "image", "date"] as const).map(
                  (k) => (
                    <div key={k} className="space-y-1">
                      <Label htmlFor={`sel-${k}`} className="text-xs">
                        {k}
                        {k === "card" ? " *" : ""}
                      </Label>
                      <Input
                        id={`sel-${k}`}
                        value={catSelectors[k]}
                        onChange={(e) =>
                          setCatSelectors((s) => ({
                            ...s,
                            [k]: e.target.value,
                          }))
                        }
                        className="font-mono text-xs"
                        placeholder={
                          k === "card"
                            ? ".kategoriHaberler span"
                            : k === "title"
                              ? ".title"
                              : k === "link"
                                ? "a"
                                : k === "image"
                                  ? "img"
                                  : ".tarih > div"
                        }
                      />
                    </div>
                  ),
                )}
              </div>

              <div className="space-y-3 pt-4 border-t">
                <div>
                  <Label className="text-sm font-medium">
                    Detay sayfa selectors (opsiyonel)
                  </Label>
                  <p className="text-xs text-muted-foreground mt-1">
                    Tek haber sayfasından çıkarılacak alanlar. Boş bırakırsan
                    trafilatura otomatik çıkarır (genel amaçlı). Doldurursan
                    daha temiz extraction.
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {(
                    [
                      "title",
                      "subtitle",
                      "author",
                      "published",
                      "image",
                      "body",
                    ] as const
                  ).map((k) => (
                    <div key={`d-${k}`} className="space-y-1">
                      <Label htmlFor={`dsel-${k}`} className="text-xs">
                        {k}
                      </Label>
                      <Input
                        id={`dsel-${k}`}
                        value={detailSelectors[k]}
                        onChange={(e) =>
                          setDetailSelectors((s) => ({
                            ...s,
                            [k]: e.target.value,
                          }))
                        }
                        className="font-mono text-xs"
                        placeholder={
                          k === "title"
                            ? "h1.article-title"
                            : k === "subtitle"
                              ? ".article-summary"
                              : k === "author"
                                ? ".author-name"
                                : k === "published"
                                  ? "time[datetime]"
                                  : k === "image"
                                    ? ".article-image img"
                                    : ".article-body"
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2 pt-2 border-t">
                <Label htmlFor="pag-type">Pagination</Label>
                <Select
                  value={paginationType}
                  onValueChange={(v) =>
                    setPaginationType(v as PaginationType)
                  }
                >
                  <SelectTrigger id="pag-type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Yok (tek sayfa)</SelectItem>
                    <SelectItem value="page_param">
                      page_param (?page=N URL)
                    </SelectItem>
                    <SelectItem value="next_link">
                      next_link (sonraki link)
                    </SelectItem>
                  </SelectContent>
                </Select>
                <div className="grid gap-3 md:grid-cols-3">
                  {paginationType !== "none" && (
                    <div className="space-y-1">
                      <Label className="text-xs">max_pages</Label>
                      <Input
                        type="number"
                        min={1}
                        max={20}
                        value={paginationCfg.max_pages}
                        onChange={(e) =>
                          setPaginationCfg((c) => ({
                            ...c,
                            max_pages: parseInt(e.target.value) || 5,
                          }))
                        }
                      />
                    </div>
                  )}
                  {paginationType === "page_param" && (
                    <>
                      <div className="space-y-1">
                        <Label className="text-xs">param_name</Label>
                        <Input
                          value={paginationCfg.param_name}
                          onChange={(e) =>
                            setPaginationCfg((c) => ({
                              ...c,
                              param_name: e.target.value,
                            }))
                          }
                          placeholder="page"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">start</Label>
                        <Input
                          type="number"
                          value={paginationCfg.start}
                          onChange={(e) =>
                            setPaginationCfg((c) => ({
                              ...c,
                              start: parseInt(e.target.value) || 1,
                            }))
                          }
                        />
                      </div>
                    </>
                  )}
                  {paginationType === "next_link" && (
                    <div className="space-y-1 md:col-span-2">
                      <Label className="text-xs">next_selector *</Label>
                      <Input
                        value={paginationCfg.next_selector}
                        onChange={(e) =>
                          setPaginationCfg((c) => ({
                            ...c,
                            next_selector: e.target.value,
                          }))
                        }
                        className="font-mono text-xs"
                        placeholder="a.next-page, .pagination .next a"
                      />
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

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
                <Alert>
                  <AlertCircle />
                  <AlertDescription>{feedReport.error}</AlertDescription>
                </Alert>
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
                          {formatTrDate(item.published_at)}
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
              <Badge variant="outline">Hatırlatma</Badge>
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
