"use client";

/**
 * Admin Queue sayfası — paylaşılan helper'lar (PR-7c-1).
 *
 * Phase 7b admin/queue mini-plan 2. PR. `page.tsx`'ten saf taşıma (byte-for-byte
 * korumalı); imza/davranış değişikliği YOK. AdminQueuePage tek bir component
 * olarak `page.tsx`'te kalır (shared state lift gerektireceği için section
 * split DEFERRED).
 *
 * Taşınan semboller:
 * - `ISTIPI_ETIKETI` — 28-entry job type → TR label map (#444/#445/#446)
 * - `KUYRUK_ETIKETI` — 12-entry kuyruk adı → TR label map (#444)
 * - `isTipiniBicimle(ham)` — job type formatter (fallback: split + capitalize)
 * - `kuyrukAdiniBicimle(ham)` — kuyruk adı formatter (regex tabanlı)
 * - `hataAciklamasi(jobType, errorMessage)` — hata mesajı TR'leştirme
 * - `DurumRozeti({ cozuldu })` — çözüldü/açık badge
 * - `SeverityRozeti({ severity })` — severity (permanent_info/warning/error) renkli badge
 * - `SAYFA_BOYUTLARI` — pagination boyut const (25/50/100/200)
 * - `SayfaBoyutu` — pagination type
 *
 * "use client" defensive direktif (admin/rag _shared.tsx deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-queue-mini-plan.md — Phase 7b admin/queue mini-plan
 * - apps/web/src/app/admin/queue/page.tsx — AdminQueuePage main component
 */

import { Badge } from "@/components/ui/badge";

// ---------------------------------------------------------------------------
// Sözlükler — #444/#445/#446 sonrası gerçek backend kuyruk + job_type isimleri
// ---------------------------------------------------------------------------

export const ISTIPI_ETIKETI: Record<string, string> = {
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

export function isTipiniBicimle(ham: string): string {
  if (ISTIPI_ETIKETI[ham]) return ISTIPI_ETIKETI[ham];
  // 'article.fetch_detail' → 'Article fetch detail'
  const parcalar = ham.split(/[._-]/);
  if (parcalar.length === 0) return ham;
  return parcalar
    .map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export const KUYRUK_ETIKETI: Record<string, string> = {
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

export function kuyrukAdiniBicimle(ham: string): string {
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

export function hataAciklamasi(jobType: string, errorMessage: string): string {
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

export function DurumRozeti({ cozuldu }: { cozuldu: boolean }) {
  return (
    <Badge variant="outline" className="h-5.5">
      {cozuldu ? "Çözüldü" : "Açık"}
    </Badge>
  );
}

// #445 — severity için renk + etiket
export function SeverityRozeti({ severity }: { severity?: string }) {
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

export const SAYFA_BOYUTLARI = [25, 50, 100, 200] as const;
export type SayfaBoyutu = (typeof SAYFA_BOYUTLARI)[number];
