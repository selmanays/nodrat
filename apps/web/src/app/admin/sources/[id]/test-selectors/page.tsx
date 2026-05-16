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
import {
  ApiException,
  getSource,
  testListing,
  type SelectorMap,
  type SourcePublic,
  type TestListingResponse,
} from "@/lib/api";

// #904 — Detay selector testi KALDIRILDI. Detay extraction artık generic
// (Tier-0 JSON-LD → trafilatura density → fallback); kaynağa özel detay
// selector'ı yok. Bu sayfa yalnız `category_page` keşfi için LİSTE
// selector'larını test eder (R-OPS-01). Detay çıkarım sağlığı kaynak detay
// sayfasındaki per-domain extract-confidence widget'ı ile izlenir.
export default function TestSelectorsPage() {
  const params = useParams<{ id: string }>();
  const sourceId = params?.id ?? "";

  const [source, setSource] = useState<SourcePublic | null>(null);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    if (!sourceId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getSource(sourceId);
        if (!cancelled) {
          setSource(data);
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
          Liste testi — {source.name}
        </h1>
        <Badge variant="outline">{source.type}</Badge>
      </div>

      <p className="text-sm text-muted-foreground">
        R-OPS-01: <code>category_page</code> kaynakları için liste/kategori
        sayfası selector'larını canlı test et. Bu sayfa DB'ye yazmaz — sadece
        preview. Detay extraction generic (per-site selector yok); detay
        çıkarım sağlığı kaynak detay sayfasındaki çıkarım telemetrisinde.
      </p>

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

      {listingResult && <ListingResults result={listingResult} />}
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

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
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <ImageOff className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {c.title ?? (
                      <span className="text-destructive">— eksik —</span>
                    )}
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
