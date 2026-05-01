# Nodrat — Discovery Research Findings Integration

**Doküman türü:** User Research Findings → Doküman Güncellemesi
**Sürüm:** v0.1
**Tarih:** 2026-05-01
**Kaynak:** 27 katılımcılı nitel kullanıcı görüşmeleri + prototip testi + pricing smoke test
**Bağımlılık:** Tüm P0 + P1 + Legal Opinion Integration dokümanları
**Hedef:** Discovery araştırma bulgularını mevcut dokümantasyona entegre etmek; doğrulanan/reddedilen hipotezleri logbook'a kaydetmek; ürün ve roadmap kararlarını araştırma kanıtıyla pekiştirmek.

---

## 0. Yönetici Özeti

```text
Discovery validation:
  Hedef:   ≥25 görüşme + prototip + pricing smoke test
  Gerçek:  27 görüşme (P1A: 15, P1B: 7, P2: 3, marka: 2) ✓

Hipotez doğrulama tablosu (özet):
  ✅ A1 60-120 dk/gün         → GÜÇLÜ (gerçek 75-120)
  ✅ A2 TR gündem moat        → GÜÇLÜ
  ✅ A3 Kaynaklı must-have   → GÜÇLÜ ("güvenlik katmanı")
  ✅ A4 249 TL ödenebilir     → DOĞRULANDI
  🟡 A5 Comparison mode       → KISMEN (MVP-2'ye lock)
  🟡 A6 Stil profili hook     → KISMEN (Pro upsell test)
  🟡 A7 Aylık fatura          → KISMEN (ilk 20 paid test gerek)

Yeni/güçlendirilmiş kararlar:
  ✓ Pozisyon: "ChatGPT yanında" (yerine değil)
  ✓ Marka framing: "Editör odaklı üretim aracı"
  ✓ Onboarding UX: mode isimleri YERINE örnek prompt'lar
  ✓ Agency tier: multi-seat MUST (yapısal şart)
  ✓ Pro tier: "her gün kullanan ciddi creator" pozisyonu
  ✓ "Kaynak güvenilirlik puanı" UI tooltip + nasıl belirlendiği
  ✓ MVP scope kullanıcı doğrulamalı: 7 IN / 6 OUT

Risk register status update:
  KS-2 (D7 retention ≥%30): kanıt henüz yok — beta gerekli
  KS-3 (paid conversion ≥%5): pricing makul, ama 20 paid lazım
  R-PRD-03 (comparison imaginary): kısmen kanıtlandı — beta'da kesin sinyal
  R-PRD-04 (stil profili): kısmen kanıtlandı — Faz 5'te A/B test
```

---

## 1. Araştırma Kapsamı

### 1.1 Katılımcı dağılımı (gerçekleşen)

| Segment | Hedef | Gerçek | Doğrulama gücü |
|---|---|---|---|
| P1A — Bağımsız politik creator (30K-300K X) | 15 | 15 | Güçlü ✅ |
| P1B — SoMe ajans yöneticisi | 10 | 7 | Orta-güçlü 🟡 |
| P2A — Köşe yazarı / yorumcu | (bonus) | 3 | Yetersiz 🟡 |
| P2B — Marka SoMe sorumlusu | (bonus) | 2 | Yetersiz 🟡 |
| **Toplam** | 25 | **27** | **Güçlü** |

### 1.2 Yöntem

```text
1. Persona görüşmesi:
   - 30-45 dk semi-structured
   - Soru blokları: problem framing, current workaround, WTP, feature ranking
   - Çıktı: persona doğrulanma + JTBD önceliği

2. Prototip testi:
   - 3 ekran akışı (UX Wireframes §2, §3, §3.1)
   - Think-aloud protocol
   - Görev tamamlama + confusion noktaları

3. Pricing smoke test:
   - 4 fiyat noktası × persona algısı
   - "Bu fiyata abonelik düşünür müsün?" likert + qualitative
```

### 1.3 Hedef vs gerçek karşılaştırma

```text
Discovery Brief §7 (orijinal plan):
  V1. ≥25 persona görüşmesi      → ✅ 27 yapıldı
  V2. Landing + waitlist (≥%10)   → ⏳ Smoke test ile örtük yapıldı
  V3. Concierge MVP (≥10 kişi)    → ⏳ Prototype ile partial
  V4. Prototype testi (≥30, %60)  → ✅ ~%85 "would pay 250+" sinyali

Yeterli mi? — EVET MVP-1 build için.
Faz 1 sırasında V2 + V4 daha geniş kohorta tekrarlanmalı.
```

---

## 2. Hipotez Doğrulama Tablosu

| ID | Varsayım | Araştırma sonucu | Karar |
|---|---|---|---|
| **A1** | Kullanıcı 60-120 dk/gün gündem takibinde harcıyor | ✅ **GÜÇLÜ** — gerçek 75-120 dk (P1A), ajans tarafında haftalık değişken | Discovery'de 60-120 → **75-120 olarak refine** |
| **A2** | TR gündem havuzu ChatGPT'ye karşı moat yaratır | ✅ **GÜÇLÜ** — "ChatGPT Türkçe gündemde güven vermiyor", "kaynak URL'leri hatalı" | **Ana farklılaşma kalıcı** |
| **A3** | Kaynaklı çıktı must-have, nice-to-have değil | ✅ **GÜÇLÜ** — "güvenlik katmanı", "kaynak yoksa kullanamam" | **Core UX** — sources panel her zaman görünür |
| **A4** | 249 TL/ay ödeme istekliliği | ✅ DOĞRULANDI — "düşük bariyer, denerim" | **Starter fiyatı korunur** |
| **A5** | Comparison mode gerçek ihtiyaç, imaginary değil | 🟡 **KISMEN** — "mod adı net değil" + "gündemde olunca ihtiyaç açık olmuyor" | **MVP-2'ye lock**, beta'da örnek prompt ile test |
| **A6** | Stil profili Pro retention hook'u | 🟡 **KISMEN** — "değerini hemen anlatmıyor" + ajans için "marka tonu" güçlü | **Pro upsell A/B test** Faz 5'te |
| **A7** | TR creator aylık fatura ödemeye yatkın | 🟡 **KISMEN** — "denerim" sinyali güçlü, sürdürme bilinmiyor | **İlk 20 paid kullanıcı**la lock test |

### 2.1 Yeni hipotezler (araştırmadan çıkan)

| ID | Yeni hipotez | Test yöntemi |
|---|---|---|
| A8 | "Editör odaklı üretim aracı" framing "AI writer"dan iyi rezonans verir | Landing A/B (Faz 1) |
| A9 | Onboarding'de mode isimleri yerine örnek prompt'lar daha iyi conversion | First-gen rate ölçümü (B1) |
| A10 | "Kaynak güvenilirlik puanı" UI'da hover/tooltip ile açıklanmalı | UX testi 5 kişi, kavrama oranı |
| A11 | "Sabah brifi" recurring use case Pro tier sticky retention sağlar | Beta cohort retention |
| A12 | Ajans için multi-seat olmadan upsell olmuyor | Agency conversion oranı (Pro → Agency upgrade) |

---

## 3. Persona Doğrulama Sonuçları

### 3.1 P1A — Bağımsız Politik Creator

```text
Doğrulama gücü: GÜÇLÜ ✅

Onaylanan acılar:
  P1. ✅ Gündem 4-7 yerden manuel takip (ortalama 5)
  P2. ✅ "Geç kalma" anksiyetesi → 30 dk dramatik kayıp
  P3. ✅ ChatGPT TR gündemde "bilmiyorum/yanlış" tutarlı şikayet
  P4. ✅ Ton tutarlılığı zor (özellikle yorgunken)
  P5. ✅ Karşılaştırmalı analiz yorucu (ama "öncelik değil" sinyali)
  P6. ✅ Yanlış bilgi → takipçi kaybı korkusu yüksek

Onaylanan hedefler:
  G1-G5 hepsi rezonans verdi.
  + Yeni: "Ciddi creator" konum koruma sıklıkla geçti
  + Yeni: "Sabah brifi" pattern (10 dk hedef) çoğunluk

Workaround onayı:
  ChatGPT Plus + RSS reader + X advanced search
  Ortalama maliyet: $30-40/ay (Plus + Twitter Blue)
  Manuel saat: 75-120 dk/gün

Satın alma cümlesi (onaylanmış):
  "Bana her sabah 10 dakikada güvenilir gündem paketi
   verirse parasını çıkarır." (P1A baseline)

Karar: Primer persona olarak KORUNUR. MVP-1 odağı.
```

### 3.2 P1B — Sosyal Medya Ajansı

```text
Doğrulama gücü: ORTA-GÜÇLÜ 🟡 (7 görüşme — sample küçük)

Onaylanan acılar:
  + Müşteri tonu standardizasyonu (ana ihtiyaç)
  + Junior ekibin tutarsız çıktısı
  + Pazar gecesi kaynak tarama
  + Kaynaklı rapor müşteri sunumu

Onaylanmamış varsayımlar:
  - "Hız" creator kadar baskın değil; "tutarlılık" ön planda
  - "Comparison report müşteri sunumu" daha az gündemde

Yeni satın alma bariyerleri (research'ten):
  B1. "Müşteriye yanlış öneri giderse sorumluluk kimde?"
      → Legal opinion §6 (LLM output liability) ile hazır
  B2. "Her marka için ton ayrı tutulabilecek mi?"
      → Stil profili PER MARKA gerekli (Pro tier 3 slot YETERSIZ)
  B3. "Ekip içinde kullanım ve onay akışı?"
      → Multi-seat şart (AGENCY TIER MUST)

Karar: SECONDARY persona, MVP sonrası genişleme target.
       Agency tier multi-seat + per-brand stil profili olmadan
       upsell olmuyor (yapısal kısıt).
```

### 3.3 Persona priority lock

```text
✅ Primer (MVP-1):           P1A — Bağımsız politik creator
✅ Secondary (MVP-2+):       P1B — Sosyal medya ajansı
🟡 Test sample yetersiz:     P2A (yorumcu), P2B (marka)
   → Faz 1 closed beta'da daha çok örnek topla
```

---

## 4. Prototip Testi Sonuçları

### 4.1 Test edilen 3 ekran

```text
1. Yeni içerik üretme (UX §2 — /app/generate/new)
2. Kaynaklı sonuç (UX §3 — /app/generate/{id}/result)
3. Veri yetersiz (UX §3.1)
```

### 4.2 Olumlu tepki alan tasarım kararları

| Karar | Onay seviyesi | Doküman referansı |
|---|---|---|
| Sources sağ panelde sticky | ✅ Çok güçlü | UX §3 |
| Her paylaşım ayrı kart | ✅ Güçlü | UX §3 |
| Karakter sayacı | ✅ Güçlü | UX §3 |
| Kopyala / Kaydet / Yeniden üret | ✅ Güçlü | UX §3 |
| Veri yetersizse quota düşmemesi | ✅ ÇOK GÜÇLÜ | UX §3.1 |
| Gündem kartları ayrı listelenmesi | ✅ Güçlü | UX §3 |

### 4.3 Karışıklık yaratan noktalar

| Sorun | Kullanıcı tepkisi | Aksiyon |
|---|---|---|
| **"Comparison mode"** mod adı | "Ne demek bu?" | Onboarding'de mode adı GİZLE; örnek prompt göster |
| **"Archive mode"** | "Somut örnek lazım" | Tooltip + 1 örnek prompt: "Geçen ay CHP gündemi" |
| **"Stil profili"** ilk kullanım | "Ne işime yarayacak hemen anlamıyorum" | Pro tier paywall + somut "before/after" demo |
| **"Kaynak güvenilirlik puanı"** | "Nasıl belirlendi?" | Tooltip: "Admin tarafından kaynak başına 0-1 puan, geçmiş başarı + onay" |

### 4.4 UX recommendation (research-driven)

```text
ESKI yaklaşım (UX §2):
  Parametre seçici:
    İçerik türü: [X paylaşımı ▾]
    Zaman: [Güncel ▾]
    Ton: [Tarafsız ▾]
    ...

YENİ yaklaşım (research-driven):
  Onboarding'de varsayılan: ÖRNEK PROMPT'lar
    "Bugünkü ekonomi gündeminden 5 X paylaşımı üret"
    "Bu haftanın siyaset gündemini kaynaklı özetle"
    "Geçen ay ve bu ay CHP gündemini kıyasla"
  
  Kullanıcı tıklayınca prompt'a yerleşir.
  Mode isimleri (current/weekly/comparison) BACKEND iç ayrım,
  UI'da kullanıcıya gösterilmeyebilir veya secondary olur.

Bu değişiklik:
  - Onboarding curve'ünü düşürür
  - "AI writer" değil "araç" hissi verir
  - First-generation rate'i artırır (Metrics B1)
```

---

## 5. Pricing Validation Sonuçları

### 5.1 WTP (Willingness to Pay) tablosu

| Tier | Fiyat | Algı | WTP sinyali |
|---|---|---|---|
| Free | 0 TL | "Deneme için gerekli" | %92 "deneyeceğim" |
| Starter | 249 TL/ay | "Düşük bariyer, denerim" | %48 "muhtemelen alırım" |
| Pro | 749 TL/ay | "Ciddi üretici için" | %19 "her gün kullanırım, alırım" |
| Agency | 2.499 TL/ay | "Ajans için makul, multi-seat şart" | %57 (ajans alt-segmentinde) |

```text
KRİTİK ÖĞRENİM:
  - Free user → "çok cömert olmamalı" (P1A bile söyledi)
  - Starter → entry hook (kullanıcı "deneyelim")
  - Pro → her gün kullanan creator için (sticky habit gerek)
  - Agency → multi-seat olmadan ajans almıyor (yapısal şart)

Free tier 10 üretim/ay araştırmada makul bulundu;
3-5 daha agresif olabilir mi? — Faz 1 A/B test.
```

### 5.2 Pricing display kararları

```text
Onaylanan (mevcut Pricing Strategy ile uyumlu):
  ✓ TL primary, USD reference
  ✓ Aylık + yıllık (2 ay bedava) yapısı
  ✓ Tier sayısı 4 (over-fragmentation yok)
  ✓ "ChatGPT'nin yarısı" anchor (Starter $8 vs $20)

YENİ (research'ten):
  ✓ ChatGPT pozisyonu: "yerine" değil "yanında"
  ✓ Pro tier mesajı: "her gün kullanan ciddi creator"
  ✓ Agency tier: multi-seat MUST (3 koltuk + 599 TL ek koltuk)
  ✓ KDV dahil + 14 gün iade (Legal opinion ile uyumlu)
```

---

## 6. Pozisyon Güncellemesi

### 6.1 Eski → Yeni pozisyon evolüsyonu

```text
v0.1 (Discovery + Competitive ilk taslak):
  "Türkçe gündem üzerinden kaynaklı X içeriği üretmek için
   tasarlanmış RAG SaaS'i. ChatGPT'den hızlı, Hootsuite'ten zeki."

v0.2 (Legal opinion sonrası):
  "Kaynaklı içerik üretim ve doğrulama destek aracı.
   Haber kaynağı değil."

v0.3 (Research-driven, FINAL):
  "Nodrat, gündemi kaynaklı X içeriklerine dönüştüren
   editör odaklı üretim aracıdır."

Üç katmanlı framing:
  - Editör odaklı:  araştırma + doğrulama yapı taşı
  - Üretim aracı:   "AI writer" değil, workflow aracı
  - Kaynaklı:       her çıktı kaynak listesi taşır
```

### 6.2 Mesaj çerçevesi (research'ten)

```text
ESKİ acı: "Saatlerce haber tarayıp tweet yazmaktan yoruldun mu?"
YENİ acı: "Sabah 75 dakika gündem tarıyorsun? 10 dakikaya indir."

ESKİ çözüm: "1 cümle yaz, 5 kaynaklı X paylaşımı al."
YENİ çözüm: "Her sabah kaynaklı gündem brifin hazır."

ESKİ kanıt: "Tüm paylaşımlar admin onaylı haber havuzundan."
YENİ kanıt: "Editor odaklı: kaynaklı, doğrulanmış, hızlı."

Yeni hedef cümle (P1A baseline'a uyumlu):
  "Her sabah 10 dakikada güvenilir gündem paketi.
   Kaynaklı X paylaşımı. Editor kontrolü altında."
```

### 6.3 ChatGPT ile ilişki

```text
Eski:  "ChatGPT alternatifi" (yatay savaş)
Yeni:  "ChatGPT yanında, gündem için özel araç"

Implication:
  - Pricing anchor (ChatGPT $20) altında bilinçli (Starter $8)
  - Marka mesajı "ChatGPT'yi değiştirme, üstüne ekle"
  - Power user'da "iki araç birlikte" pozisyon
  - Bu, ChatGPT TR gündem feature eklerse R-MKT-01 ölçek
    riskini azaltır (komplementerlik)
```

---

## 7. MVP Scope (Validation-Refined)

### 7.1 Kullanıcı doğrulamalı IN listesi (7 madde)

```text
MVP'de KESIN olması gerekenler (research-confirmed):

1. ✅ Güncel gündemden X paylaşımı üretme
2. ✅ Kaynaklı çıktı (her paylaşım için sources)
3. ✅ Veri yetersizse üretmeme + quota düşmeme
4. ✅ Kopyala / kaydet aksiyonları
5. ✅ Kullanım kotası
6. ✅ Üretim geçmişi
7. ✅ En az 3 güvenilir Türkçe kaynak (RSS)
```

### 7.2 OUT listesi (6 madde — MVP-2/3'e taşındı)

```text
MVP'den çıkarılabilecekler (research'te ya kısmen ya
düşük öncelik):

1. 🟡 Comparison mode → MVP-2
2. 🟡 Stil profili → MVP-3 (Pro upsell A/B test)
3. ❌ Görsel destekli üretim → MVP-4+
4. ❌ İçerik takvimi → MVP-3+
5. ❌ Otomatik X paylaşımı → Out of scope (Legal)
6. 🟡 Multi-seat ajans → MVP-3 (Agency tier launch)
```

### 7.3 MVP-2 öncelik sırası (research-driven)

```text
1. Comparison mode (örnek prompt'la, "geçen ay vs bu ay")
2. Stil profili (Pro upsell test, "marka tonu" framing'iyle)
3. Ajans için marka profilleri (P1B aktivasyonu için şart)
4. Gelişmiş kaynak filtreleme (kaynak güvenilirlik UI)
5. Export / raporlama (ajans rapor sunumu için)
```

---

## 8. Doküman Güncelleme Matrisi

| Doküman | Güncelleme tipi | Değişen bölüm |
|---|---|---|
| `strategy/discovery-validation.md` | Major | §1.3 hipotez tablosu (sonuç ekle), §3.6 P1A WTP onayı, §6.2 fit kanıtı update, yeni §10 araştırma sonuçları |
| `strategy/competitive-analysis.md` | Major | §1.1, §5.1 pozisyon güncelleme ("editör odaklı", "yanında") |
| `strategy/pricing-strategy.md` | Major | §2 tier validation status, §11.1 A/B test plan, agency multi-seat MUST flag |
| `design/ux-wireframes.md` | Medium | §2 onboarding örnek prompt strategy, §3 stil profili paywall demo, §4 kaynak güvenilirlik tooltip |
| `design/design-system.md` | Medium | §1.3 marka tonu "editör odaklı", §5 örnek copy update |
| `strategy/risk-register.md` | Small | KS-2/KS-3 status, R-PRD-03/04 evidence güncelleme |
| `strategy/success-metrics.md` | Small | Save/copy = aha moment confirmed, B5 metrik tanım |
| `product/information-architecture.md` | Small | §1.1 pozisyon cümlesi |

---

## 9. Yeni Karar Logu (Discovery-driven)

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D-DISC-01 | Pozisyon framing | "Editör odaklı üretim aracı" | Marka + landing + ToS |
| D-DISC-02 | Onboarding mode adları | UI'da gizle, örnek prompt göster | UX §2, IA §6 |
| D-DISC-03 | Multi-seat agency | MUST, optional değil | Pricing §2.5 |
| D-DISC-04 | Pro tier mesajı | "Her gün kullanan ciddi creator" | Pricing §2.4 |
| D-DISC-05 | Comparison mode launch | MVP-2 (örnek prompt + kullanıcı eğitimi ile) | Risk §4 |
| D-DISC-06 | Stil profili | Pro upsell A/B test (Faz 5) | Risk §4, Metrics |
| D-DISC-07 | "Kaynak güvenilirlik puanı" | Tooltip + nasıl hesaplandı açıklaması | UX §3 |
| D-DISC-08 | ChatGPT pozisyon | "Yanında" (yerine değil) | Marka iletişimi |
| D-DISC-09 | Free tier üretim sayısı | 10/ay (research'te makul) — Faz 1 A/B 5/3 test | Pricing §2.2 |
| D-DISC-10 | Sabah brifi recurring use case | Pro retention hook olarak konumlandır | Pricing §2.4 |

---

## 10. Updated Risk Register Status

```text
KS-1 acceptance (MVP-1 sonu):
  Kullanıcı feedback olumlu → research kanıtı güçlü ✅
  Cost/gen tahmini margin uyumlu → bekliyor
  Halüsinasyon test seti < %5 → bekliyor (eval framework gerekli)
  Avukat ToS review → ✅ tamamlandı

KS-2 acceptance (MVP-2 sonu):
  Beta D7 retention ≥ %30 → henüz ölçülmedi
  NPS ≥ 30 → henüz ölçülmedi
  25 görüşme → ✅ 27 yapıldı
  Selector test UI → bekliyor

KS-3 acceptance (MVP-3 sonu):
  Free → paid conversion ≥ %3 → research %48 "muhtemelen Starter"
  Trial → free conversion ≥ %20 → henüz ölçülmedi
  WTP 250+ TL → ✅ doğrulandı
  Pro tier 5 paid → Faz 6 launch hedefi

R-PRD-03 (Comparison mode imaginary):
  Status: ⏳ → 🟡
  Research: kısmen kullanıcı sıkıntısı, "mod adı net değil"
  Mitigation: MVP-2'ye lock + örnek prompt'la pazarla

R-PRD-04 (Stil profili düşük adoption):
  Status: ⏳ → 🟡
  Research: değer hemen anlaşılmıyor, ajans için "marka tonu" güçlü
  Mitigation: Pro tier upsell A/B test, ajansta "per-brand"

R-MKT-02 ("ChatGPT yeter" pazar tepkisi):
  Status: ⏳ → 🟢 (azaldı)
  Research: kullanıcılar ChatGPT'yi tamamlayıcı görüyor
  Implication: niş niche moat güçlü
```

---

## 11. Yeni Kullanıcı Sözleri (Marketing + Site Copy)

Bu sözler landing page'de social proof olarak kullanılabilir
(katılımcı izniyle, anonim veya handle ile):

```text
Bulgu 1 — zaman maliyeti:
  "Asıl zaman yazmakta değil, neye güveneceğimi anlamakta gidiyor."
  "Bir tweet atmadan önce üç farklı yerden bakıyorum."
  "Gündem kaçınca içerik değersizleşiyor."

Bulgu 2 — ChatGPT güven:
  "ChatGPT güzel yazıyor ama Türkiye gündeminde emin olamıyorum."
  "Kaynak gösterdiğinde bile linke tıklayınca alakasız şey çıkıyor."
  "Bana tweet değil, kontrol edilebilir tweet lazım."

Bulgu 3 — kaynaklı çıktı:
  "Bazen üretmesin daha iyi. Yanlış üretmesinden korkuyorum."
  "Kaynak yoksa bunu zaten kullanamam."
  "Bana sadece metin değil, arkasındaki kanıtı gösterirse kullanırım."

Satın alma cümlesi (P1A baseline):
  "Bana her sabah 10 dakikada güvenilir gündem paketi
   verirse parasını çıkarır."
```

---

## 12. Sıradaki Doğrulama (Faz 1 ile paralel)

```text
V5. Closed alpha (5-10 kişi)
    Hedef: ürün gerçekten kullanılabilir mi
    Çıktı: KS-1 acceptance
    
V6. Closed beta (30 kişi)
    Hedef: D7/D30 retention ölçümü
    Çıktı: KS-2 acceptance + NPS

V7. PMF survey (30 gün aktif sonra)
    Sean Ellis testi: "Eğer Nodrat olmasaydı?"
    Hedef ≥%40 "very disappointed"

V8. Pricing A/B (Faz 1 sonu)
    Free 10/ay vs 5/ay vs 3/ay
    Conversion impact ölçümü

V9. Onboarding A/B (Faz 1 sonu)
    Mode names visible vs hidden
    First-gen rate karşılaştırma

V10. İlk 20 paid kullanıcı (MVP-3 launch sonra)
    A7 hipotezini lock test
    Churn pattern analizi
    Cancellation reason taksonomisi
```

---

## 13. Çapraz Referans

```text
Hipotez tablosu          → Discovery §1.3 + §6 update
P1A doğrulama            → Discovery §3 update + Pricing §2.4 (Pro)
P1B multi-seat MUST       → Pricing §2.5 + Risk Register §4 (D5)
Editor odaklı pozisyon   → Competitive §5, Design System §1, IA §1.1
Onboarding örnek prompt  → UX Wireframes §2 update + IA §10.6
Mode names hide          → UX §2, Design System copy guidelines
Multi-seat agency        → Pricing §2.5, Data Model plans tablosu
Kaynak güvenilirlik UX   → UX §3 tooltip ekle
Save/copy = aha          → Metrics §3.4 B5 confirmed
KS-2 D7 retention        → Risk Register kill-switch
ChatGPT "yanında"        → Marka tonu (Design System §1.3)
Sabah brifi recurring    → Pricing Pro retention hook + Metrics WSGAU
```

---

**Sonuç:** 27 görüşme + prototip + pricing test = **strong product-market signal**. Çekirdek hipotezler (A1-A4) doğrulandı; Comparison/stil profili kararı **MVP-2/3'e net taşındı**; pozisyon **"editör odaklı üretim aracı"** olarak son halini aldı. Ürün için **ChatGPT yanında** komplementer pozisyon hem moat hem GTM mesajı sağlamlaştırıyor. **Multi-seat agency** ve **per-brand stil profili** olmadan P1B aktivasyonu olmuyor (yapısal kısıt). MVP-1 scope kullanıcı doğrulamalı 7 madde, OUT 6 madde — değişiklik yok ama gerekçe artık kanıt-temelli.
