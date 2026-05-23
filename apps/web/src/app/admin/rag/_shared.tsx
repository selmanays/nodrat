"use client";

/**
 * Admin RAG sayfası — ortak yardımcılar (PR-7b-1).
 *
 * Phase 7b mini-plan kapsamında `apps/web/src/app/admin/rag/page.tsx` 2356 LoC
 * god-file için 13 PR sırasının 2. adımı. Sembol göçü saf taşıma (byte-for-byte
 * korumalı); imza/davranış/JSX/render değişikliği YOK. Tab fonksiyonları
 * (HealthTab, BenchmarkTab, …) bu PR'da page.tsx içinde kalır; sonraki
 * PR-7b-2..7b-10'da `_tabs/*.tsx`'e taşınır ve bu modülden helper'ları
 * import eder.
 *
 * "use client" direktifi: page.tsx zaten client component; bu modül de React
 * fonksiyonel komponentler (StatCard, KV) export ettiği için defensive olarak
 * client işaretlendi (mevcut proje deseni — info-tooltip.tsx + dashboard-stat-card.tsx
 * aynı yaklaşım). `Card` shadcn komponenti universal (use client'siz) çalışsa da
 * client boundary'yi explicit tutmak Next.js App Router'da review kolaylığı sağlar.
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a precedent (api.ts split)
 */

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// ============================================================================
// Sözlük — kısaltmalar / teknik terimler için tooltip metinleri
// ============================================================================

export const HINTS = {
  ndcg10:
    "NDCG@10 (Normalize Edilmiş Kümülatif Kazanç). İlk 10 sonuçtaki sıralama kalitesini ölçer. 0–1 arası, 1 mükemmel sıralama. Doğru cevap ne kadar üstte ise puan o kadar yüksek.",
  map5:
    "MAP@5 (Ortalama Hassasiyet). İlk 5 sonuçta her doğru cevabın bulunduğu sıraya göre puan. 0–1 arası, yüksek iyi.",
  mrr10:
    "MRR@10 (Ortalama Karşılıklı Sıra). İlk doğru sonucun ortalama sırasının tersi. 1.0 = ilk sırada bulundu, 0.5 = 2. sırada, 0.33 = 3. sırada.",
  recall20:
    "Recall@20 (Geri Çağırma). İlk 20 sonuçta toplam doğru cevapların yakalanma oranı. 0–1 arası, yüksek iyi.",
  p5: "Precision@5 (Hassasiyet). İlk 5 sonucun ne kadarının doğru olduğu oranı.",
  p50: "p50 — Sorguların yarısı bu süreden hızlı tamamlandı (medyan).",
  p95: "p95 — Sorguların %95'i bu süreden hızlı tamamlandı.",
  raptor:
    "RAPTOR-Lite. Günlük gündem kartlarını embedding cosine benzerliğine göre kümeleyip DeepSeek özetiyle haftalık tema kartları üreten hiyerarşik kümeleme.",
  rrf:
    "RRF (Reciprocal Rank Fusion). Yoğun (embedding) ve sparse (trigram) arama sonuçlarını sıraya göre puanlayıp birleştirir. k=60 sabit.",
  reranker:
    "Yeniden Sıralayıcı. RRF'nin top-50 sonucunu cross-encoder ile yeniden puanlar; en alakalı 10'u öne çıkarır.",
  citation:
    "Atıf doğrulama. LLM çıktısının kaynak referanslarını embedding benzerliği ile kontrol eder; kanıtsız iddiaları işaretler.",
  candidatePool:
    "Aday havuzu. RRF füzyonuna alınan ilk N sonuç sayısı. Reranker bu havuzdan top-K'ya iner.",
  crossEncoder:
    "Cross-encoder. Sorgu + pasajı tek seferde değerlendiren model; bi-encoder'dan daha kaliteli ama yavaş.",
  importance:
    "Önem skoru. Kaynak çeşitliliği ve makale sayısına göre 0–1 arası puan; haber kümesinin gündem ağırlığını yansıtır.",
  insufficient:
    "Yeterli kaynak bulunamadı durumu. Sorgu için RAG ilgili agenda kartı bulamadığında dönen sonuç.",
  goldenSet:
    "Altın küme. Beklenen doğru cevapları (manuel hazırlanmış) içeren değerlendirme veri seti. retrieval_golden_tr.yaml içinde 50 Türkçe sorgu var.",
  daily:
    "Günlük gündem kartı. Tek bir olay kümesi için DeepSeek tarafından üretilen başlık + özet + kilit noktalar.",
  weekly:
    "Haftalık tema kartı. RAPTOR-Lite tarafından, son 7 günün benzer günlük kartlarından oluşturulan üst seviye özet.",
  unsupportedClaim:
    "Kanıtsız iddia. LLM'in ürettiği bir cümle için kaynak embedding benzerliği eşik altı kalan durumlar; halüsinasyon riski göstergesi.",
  generation: "Kullanıcı içerik üretim isteği (örn. tweet, özet).",
};

// ============================================================================
// Ortak yardımcı komponentler / fonksiyonlar
// ============================================================================

export function StatCard({
  label,
  value,
  subtitle,
}: {
  label: React.ReactNode;
  value: number | string;
  subtitle?: string;
}) {
  return (
    <Card className="rounded-2xl shadow-none ring-[var(--border)]">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">
          {value}
        </CardTitle>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardHeader>
    </Card>
  );
}

export function KV({ k, v }: { k: React.ReactNode; v: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border p-3">
      <span className="text-sm text-muted-foreground">{k}</span>
      <span className="font-mono text-xs">{v}</span>
    </div>
  );
}

export function fmt(n: number | null): string {
  if (n == null) return "—";
  return n.toFixed(4);
}
