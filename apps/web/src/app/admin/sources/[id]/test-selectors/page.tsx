"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, ImageOff, PlayCircle } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ApiException,
  getSource,
  testDetail,
  testListing,
  type SelectorMap,
  type SourcePublic,
  type TestDetailResponse,
  type TestListingResponse,
} from "@/lib/api";

type DetailMethod = "auto" | "admin_selectors" | "trafilatura";

export default function TestSelectorsPage() {
  const params = useParams<{ id: string }>();
  const sourceId = params?.id ?? "";

  const [source, setSource] = useState<SourcePublic | null>(null);
  const [loading, setLoading] = useState(true);

  // ---- Listing tab state ----
  const [listingUrl, setListingUrl] = useState("");
  const [listingSelectors, setListingSelectors] = useState<SelectorMap>({
    card: "",
    title: "",
    link: "",
    image: "",
    date: "",
  });
  const [listingResult, setListingResult] =
    useState<TestListingResponse | null>(null);
  const [listingBusy, setListingBusy] = useState(false);

  // ---- Detail tab state ----
  const [detailUrl, setDetailUrl] = useState("");
  const [detailMethod, setDetailMethod] = useState<DetailMethod>("auto");
  const [detailSelectors, setDetailSelectors] = useState<SelectorMap>({
    title: "",
    subtitle: "",
    author: "",
    published: "",
    image: "",
    body: "",
  });
  const [detailResult, setDetailResult] = useState<TestDetailResponse | null>(
    null,
  );
  const [detailBusy, setDetailBusy] = useState(false);

  useEffect(() => {
    if (!sourceId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getSource(sourceId);
        if (!cancelled) {
          setSource(data);
          // Listing URL prefill — base_url + category yoksa base_url
          if (data.base_url) setListingUrl(data.base_url);
        }
      } catch (e) {
        if (e instanceof ApiException) {
          toast.error(e.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  async function runListing() {
    if (!listingUrl || !listingSelectors.card) {
      toast.error("URL ve 'card' selector zorunlu");
      return;
    }
    setListingBusy(true);
    setListingResult(null);
    try {
      const cleaned = onlyNonEmpty(listingSelectors);
      const r = await testListing(sourceId, listingUrl, cleaned);
      setListingResult(r);
      if (r.fetch_status >= 400 || r.fetch_error) {
        toast.error(`Fetch hatası: ${r.fetch_error ?? r.fetch_status}`);
      } else if (r.card_count === 0) {
        toast.warning("Hiç card bulunamadı — selector'ı kontrol et");
      } else {
        toast.success(`${r.card_count} card bulundu`);
      }
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : "Test başarısız");
    } finally {
      setListingBusy(false);
    }
  }

  async function runDetail() {
    if (!detailUrl) {
      toast.error("URL zorunlu");
      return;
    }
    setDetailBusy(true);
    setDetailResult(null);
    try {
      const cleaned = onlyNonEmpty(detailSelectors);
      const useSelectors = Object.keys(cleaned).length > 0 ? cleaned : undefined;
      const r = await testDetail(sourceId, detailUrl, {
        method: detailMethod,
        selectors: useSelectors,
      });
      setDetailResult(r);
      if (r.fetch_error) {
        toast.error(`Fetch hatası: ${r.fetch_error}`);
      } else if (r.error) {
        toast.error(r.error);
      } else if (r.metrics?.successful) {
        toast.success(
          `Başarılı — confidence ${(r.metrics.extraction_confidence * 100).toFixed(0)}%`,
        );
      } else {
        toast.warning(
          `Düşük güven — confidence ${
            r.metrics
              ? (r.metrics.extraction_confidence * 100).toFixed(0)
              : 0
          }%`,
        );
      }
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : "Test başarısız");
    } finally {
      setDetailBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 md:px-6 py-10">
        <p className="text-muted-foreground">Yükleniyor…</p>
      </div>
    );
  }

  if (!source) {
    return (
      <div className="mx-auto max-w-5xl px-4 md:px-6 py-10">
        <p className="text-destructive">Kaynak bulunamadı.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 md:px-6 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/admin/sources/${sourceId}`}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Kaynak detayı
          </Link>
        </Button>
        <h1 className="text-xl font-semibold">
          Selector test — {source.name}
        </h1>
        <Badge variant="outline">{source.type}</Badge>
      </div>

      <p className="text-sm text-muted-foreground">
        R-OPS-01 mitigation: HTML kırılganlığında selector'ları canlı test et.
        Bu sayfa DB'ye yazmaz — sadece preview.
      </p>

      <Tabs defaultValue="listing" className="space-y-4">
        <TabsList>
          <TabsTrigger value="listing">Liste sayfa testi</TabsTrigger>
          <TabsTrigger value="detail">Detay sayfa testi</TabsTrigger>
        </TabsList>

        {/* ---------------- LISTING TAB ---------------- */}
        <TabsContent value="listing" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Listing/kategori sayfası test</CardTitle>
              <CardDescription>
                Card container + alan selector'larını gerçek HTML'e karşı dene.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="listing-url">Test URL'si</Label>
                <Input
                  id="listing-url"
                  value={listingUrl}
                  onChange={(e) => setListingUrl(e.target.value)}
                  placeholder="https://example.com/category"
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <SelectorInput
                  label="card (zorunlu)"
                  value={listingSelectors.card ?? ""}
                  onChange={(v) =>
                    setListingSelectors((s) => ({ ...s, card: v }))
                  }
                  placeholder=".news-card"
                />
                <SelectorInput
                  label="title"
                  value={listingSelectors.title ?? ""}
                  onChange={(v) =>
                    setListingSelectors((s) => ({ ...s, title: v }))
                  }
                  placeholder="h2.title"
                />
                <SelectorInput
                  label="link"
                  value={listingSelectors.link ?? ""}
                  onChange={(v) =>
                    setListingSelectors((s) => ({ ...s, link: v }))
                  }
                  placeholder="a"
                />
                <SelectorInput
                  label="image"
                  value={listingSelectors.image ?? ""}
                  onChange={(v) =>
                    setListingSelectors((s) => ({ ...s, image: v }))
                  }
                  placeholder="img"
                />
                <SelectorInput
                  label="date"
                  value={listingSelectors.date ?? ""}
                  onChange={(v) =>
                    setListingSelectors((s) => ({ ...s, date: v }))
                  }
                  placeholder=".pub-date, time[datetime]"
                />
              </div>
              <Button onClick={runListing} disabled={listingBusy}>
                <PlayCircle className="mr-1 h-4 w-4" />
                {listingBusy ? "Test ediliyor…" : "Test et"}
              </Button>
            </CardContent>
          </Card>

          {listingResult && (
            <ListingResults result={listingResult} />
          )}
        </TabsContent>

        {/* ---------------- DETAIL TAB ---------------- */}
        <TabsContent value="detail" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Detay/article sayfası test</CardTitle>
              <CardDescription>
                Tek article URL'sine karşı extractor'ı çalıştır.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="detail-url">Article URL'si</Label>
                <Input
                  id="detail-url"
                  value={detailUrl}
                  onChange={(e) => setDetailUrl(e.target.value)}
                  placeholder="https://example.com/news/123-baslik"
                />
              </div>
              <div>
                <Label htmlFor="detail-method">Method</Label>
                <select
                  id="detail-method"
                  value={detailMethod}
                  onChange={(e) =>
                    setDetailMethod(e.target.value as DetailMethod)
                  }
                  className="w-full h-9 rounded-md border bg-background px-3 text-sm"
                >
                  <option value="auto">auto (3-tier kademe)</option>
                  <option value="admin_selectors">
                    admin_selectors (override veya aktif config)
                  </option>
                  <option value="trafilatura">trafilatura (selector bypass)</option>
                </select>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(
                  ["title", "subtitle", "author", "published", "image", "body"] as const
                ).map((k) => (
                  <SelectorInput
                    key={k}
                    label={k}
                    value={detailSelectors[k] ?? ""}
                    onChange={(v) =>
                      setDetailSelectors((s) => ({ ...s, [k]: v }))
                    }
                    placeholder={detailPlaceholders[k]}
                  />
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Selector'ları boş bırakırsanız source'un aktif config'i (varsa)
                kullanılır. method=trafilatura'da selector ignore edilir.
              </p>
              <Button onClick={runDetail} disabled={detailBusy}>
                <PlayCircle className="mr-1 h-4 w-4" />
                {detailBusy ? "Test ediliyor…" : "Test et"}
              </Button>
            </CardContent>
          </Card>

          {detailResult && <DetailResults result={detailResult} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

const detailPlaceholders: Record<string, string> = {
  title: "h1.article-title",
  subtitle: ".article-summary",
  author: ".author-name",
  published: "time[datetime]",
  image: ".article-image img",
  body: ".article-body",
};

function onlyNonEmpty(s: SelectorMap): SelectorMap {
  const out: SelectorMap = {};
  for (const [k, v] of Object.entries(s)) {
    if (typeof v === "string" && v.trim()) {
      (out as Record<string, string>)[k] = v.trim();
    }
  }
  return out;
}

function SelectorInput(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <Label className="text-xs">{props.label}</Label>
      <Input
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        className="font-mono text-xs"
      />
    </div>
  );
}

function ListingResults({ result }: { result: TestListingResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {result.card_count} card bulundu
        </CardTitle>
        <CardDescription>
          HTTP {result.fetch_status} ·{" "}
          {result.cards.length === result.card_count
            ? "tüm sonuçlar"
            : `ilk ${result.cards.length} preview`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {result.warnings.length > 0 && (
          <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 p-2 text-xs space-y-1">
            {result.warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}
        {result.cards.length === 0 ? (
          <p className="text-sm text-muted-foreground">Card yok.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {result.cards.slice(0, 12).map((c, i) => (
              <div
                key={i}
                className="border rounded-md p-2 flex gap-2 items-start"
              >
                <div className="w-16 h-16 shrink-0 bg-muted rounded overflow-hidden flex items-center justify-center">
                  {c.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={c.image_url}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <ImageOff className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {c.title ?? <span className="text-destructive">— eksik —</span>}
                  </div>
                  {c.date && (
                    <div className="text-xs text-muted-foreground truncate">
                      {c.date}
                    </div>
                  )}
                  {c.link && (
                    <a
                      href={c.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-500 truncate flex items-center gap-1 mt-1"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {c.link}
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DetailResults({ result }: { result: TestDetailResponse }) {
  if (result.fetch_error || result.error || !result.extracted) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base text-destructive">
            Hata
          </CardTitle>
          <CardDescription>HTTP {result.http_status}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm space-y-1">
          {result.fetch_error && <div>Fetch: {result.fetch_error}</div>}
          {result.error && <div>Extract: {result.error}</div>}
        </CardContent>
      </Card>
    );
  }

  const { extracted, metrics } = result;
  const conf = metrics?.extraction_confidence ?? 0;
  const confColor =
    conf >= 0.7
      ? "bg-green-500"
      : conf >= 0.4
        ? "bg-yellow-500"
        : "bg-destructive";

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex items-center gap-3">
          <CardTitle className="text-base">Extraction sonucu</CardTitle>
          <Badge variant={metrics?.successful ? "default" : "destructive"}>
            {metrics?.successful ? "successful" : "low confidence"}
          </Badge>
          <Badge variant="outline">{metrics?.strategy_used}</Badge>
        </div>
        <CardDescription>
          HTTP {result.http_status} · {extracted.text_length} char ·{" "}
          {extracted.body_image_count} body image
        </CardDescription>
        {metrics && (
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span>extraction_confidence</span>
              <span>{(conf * 100).toFixed(0)}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${confColor}`}
                style={{ width: `${conf * 100}%` }}
              />
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Field label="Title" value={extracted.title} />
        {extracted.subtitle && (
          <Field label="Subtitle" value={extracted.subtitle} />
        )}
        {extracted.author && <Field label="Author" value={extracted.author} />}
        {extracted.published_at && (
          <Field label="Published" value={extracted.published_at} />
        )}
        {extracted.main_image_url && (
          <div>
            <div className="text-xs text-muted-foreground mb-1">
              Main image
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={extracted.main_image_url}
              alt=""
              className="max-h-40 rounded border"
            />
          </div>
        )}
        <div>
          <div className="text-xs text-muted-foreground mb-1">
            Clean text preview (ilk 800 char)
          </div>
          <pre className="whitespace-pre-wrap text-xs bg-muted p-2 rounded max-h-60 overflow-auto">
            {extracted.clean_text_preview || "— boş —"}
          </pre>
        </div>
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
