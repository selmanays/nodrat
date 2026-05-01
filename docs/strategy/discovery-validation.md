# Nodrat — Discovery & Validation Brief

**Doküman türü:** Product Discovery & Customer Validation
**Sürüm:** v0.1
**Bağımlılık:** `product/prd.md` v0.1, `product/information-architecture.md` v0.1
**Hedef:** "Bu ürün kim için, hangi alternatife rağmen, neden değer üretiyor?" sorusunun yapılandırılmış cevabı ve doğrulama yol haritası.

---

## 0. Yönetici Özeti

Nodrat, Türkiye odaklı politik/güncel içerik üreticilerinin **gündem→X paylaşımı** dönüşümünde yaşadığı zaman ve doğruluk sıkıntısını çözmek için pozisyonlanır.

**Çekirdek hipotez:** "30K+ takipçili bağımsız politik creator'lar ve küçük SoMe ajansları, ChatGPT'nin Türkçe gündeme geç ulaşması ve halüsinasyon riski yüzünden manuel haber takibine 60–120 dk/gün harcıyor; Nodrat bunu 5–10 dk'ya indirmeyi vaat ediyor."

**Validation durumu:** ✅ **27 görüşme tamamlandı** (2026-05-01). Bulgular `validation/research-findings.md` dosyasına entegre edildi. Bu doküman hipotezleri orijinal haliyle korur (tarihsel bağlam); doğrulama sonuçları ve revize kararlar için integration dosyasına bakın.

---

## 1. Problem Hipotezi

### 1.1 Sorun ifadesi (problem statement)

Türkiye'de gündem üzerinden içerik üreten X kullanıcıları (bağımsız creator, ajans, gazeteci, marka SoMe) günde 60–120 dakika **manuel haber okuma + tweet üretme** döngüsünde sıkışıyor. Mevcut LLM araçları (ChatGPT, Claude, Perplexity) Türkiye-spesifik gündemde:

```text
- Anlık güncel haberlere geç ulaşıyor (web search değişken, 5–30 dk gecikme)
- Hataya açık özetler veriyor (halüsinasyon: kişi/tarih/olay uydurma)
- Kaynak göstermiyor veya yanlış URL üretiyor
- Karşılaştırmalı analiz (ay/yıl bazlı) yapamıyor
- X formatına özel optimize değil (250 karakter, thread, hashtag mantığı)
```

### 1.2 Çözüm hipotezi

Admin tarafından küratörlüğü yapılan **güvenilir Türkçe haber havuzu + RAG mimarisi + zaman/karşılaştırma modları** sunulduğunda kullanıcı:

```text
- Tek doğal dil sorgusuyla 5–10 alakalı X paylaşımı alır (≤30 sn)
- Her paylaşımı kaynağa kadar doğrulayabilir
- Karşılaştırmalı içerik üretebilir (geçen ayki gündem vs bu ay)
- Halüsinasyon riski minimize edilmiştir (PRD §3.5, §12.4)
- Kendi tonunu koruyabilir (Faz 5 stil profili)
```

### 1.3 Hipotez doğrulama tablosu (research sonrası)

| ID | Varsayım | Durum (2026-05-01) | Yorum |
|---|---|---|---|
| A1 | Hedef kitle gerçekten 60–120 dk/gün harcıyor | ✅ **GÜÇLÜ** | Gerçek 75–120 dk (P1A); refine edildi |
| A2 | Türkçe gündem havuzu ChatGPT'ye karşı kazanan moat | ✅ **GÜÇLÜ** | "ChatGPT TR gündemde güven vermiyor" tutarlı |
| A3 | Kaynaklı çıktı "must-have", "nice-to-have" değil | ✅ **GÜÇLÜ** | "Güvenlik katmanı" framing'i ile core UX |
| A4 | Kullanıcı 249 TL/ay verecek kadar acı çekiyor | ✅ DOĞRULANDI | %48 "muhtemelen Starter alırım" |
| A5 | Comparison mode gerçek kullanım, imaginary değil | 🟡 **KISMEN** | Mod adı net değil → MVP-2'ye lock |
| A6 | Stil profili (Faz 5) retention hook'u | 🟡 **KISMEN** | "Değer hemen anlatmıyor" → Pro upsell A/B |
| A7 | Türk creator'ları aylık fatura ödemeye yatkın | 🟡 **KISMEN** | "Denerim" güçlü, sürdürme bilinmiyor |

Detaylı doğrulama analizi: `validation/research-findings.md` §2.

---

## 2. Hedef Kitle ve Pazar

### 2.1 TAM → SAM → SOM

```text
TAM (Total Addressable Market):
  Türkiye'de aktif X kullanıcısı (≈16M) içinde
  içerik üretip etkileşim arayan kitle
  Tahmin: 2–3M kişi

SAM (Serviceable Addressable Market):
  10K+ takipçili, gündem odaklı içerik üretenler
  Bağımsız creator + ajans + gazeteci + marka SoMe ekibi
  Tahmin: 50K–100K aktif hesap

SOM (Serviceable Obtainable Market) — Yıl 1:
  Bağımsız politik creator + küçük ajans (2–10 kişi)
  Türkiye odaklı, ödeme yatkınlığı yüksek alt küme
  Hedef: 500–2.000 paid kullanıcı
```

### 2.2 Persona haritası

```text
Birincil personalar (P1) — primer hedef:
  P1A. Mete    — Bağımsız politik içerik üreticisi (creator)
  P1B. Selin   — SoMe ajans yöneticisi (3–8 marka)

İkincil personalar (P2):
  P2A. Hasan   — Köşe yazarı / opinion-maker
  P2B. Burak   — Marka SoMe sorumlusu (kurumsal)

Üçüncül (P3):
  P3A. Deniz   — Politik kampanya/parti içerik çalışanı
  P3B. Ayça    — Akademisyen / think-tank analisti

Anti-personalar (kapsam dışı):
  AP1. Pasif haber tüketicisi (sadece okumak isteyen)
  AP2. Düşük WTP olan öğrenci/junior kullanıcı
  AP3. Spam/bot operatörü (rate limit + abuse detection target)
```

---

## 3. Birincil Persona — Mete (Politik İçerik Üreticisi)

### 3.1 Demografi

```text
Yaş:           28–42
Konum:         İstanbul, Ankara, İzmir (>%80)
Eğitim:        Lisans (sosyal bilimler, iletişim, hukuk, mühendislik)
Gelir:         Aylık 30–150K TL (X reklam + danışmanlık + podcast/kitap)
Takipçi:       30K–300K X
Paylaşım freq: Günde 5–15 tweet, haftada 1–2 thread
Aktif saat:    08:00–11:00, 18:00–23:00 (gündem zirveleri)
```

### 3.2 Hedefler (Goals)

```text
G1. Etkileşimi yüksek paylaşım üretmek
G2. Gündemi geç değil, ilk dalgada yakalamak
G3. Kaynaklı yorumla "ciddi creator" konumunu korumak
G4. Yorgunluğu azaltıp creative iş zamanına ayırmak
G5. Karşılaştırmalı/derinlikli içerikle "1K like" eşiğini aşmak
```

### 3.3 Acılar (Pain points)

```text
P1. Gündem 6–7 yerden takip ediliyor (X feed, gazete RSS, NTV bandı,
    AP/Reuters Telegram, Periscope, vb.) → bilgi parçalı
P2. "Geç kalmak" en büyük korku — 30 dk sonra trend tükeniyor
P3. ChatGPT Türkçe gündemde "bilmiyorum" diyor veya yanlış söylüyor
P4. Manuel yazınca aynı tonu tutturmak zor (özellikle yorgunken)
P5. Karşılaştırmalı analiz (geçen yıl ne diyorlardı vs şimdi) saatler alıyor
P6. Yanlış bilgi paylaşmak takipçi kaybettiriyor; her tweet 2–3 yerden
    doğrulanmaya zorlanıyor
```

### 3.4 Mevcut çözüm (workaround)

```text
- 4–5 RSS reader (Feedly, Reeder) + X advanced search
- ChatGPT Plus aboneliği ($20/ay) + Twitter Blue/Premium ($8/ay)
- Notion'da "tweet bankası" + "konu havuzu"
- Discord/WhatsApp gazeteci grupları
- Manuel "neyse bunu yarın yazayım" defteri

Toplam: 60–120 dk/gün manuel iş + ~30$/ay araç bütçesi
```

### 3.5 İdeal sonuç (success outcome)

```text
"Sabah 10 dakikada gündem brifim hazır olsun, 5 alakalı tweet seçeneği
gelsin, tıkla-doğrula-yayınla. Akşam comparison thread için yine
10 dakika. Toplam 20 dk/gün."
```

### 3.6 Willingness to pay (tahmin)

```text
Anchor: ChatGPT Plus $20 + Twitter Blue $8 = $28/ay zaten harcıyor
Tahmin: 250–750 TL/ay (Starter–Pro tier'a uyumlu)
Risk:   Free user kalıp Starter'a dönüşmemek (free-loader)
        → "Free tier yeterince acıtmalı" tasarım kuralı
```

---

## 4. İkincil Persona — Selin (SoMe Ajans Yöneticisi)

### 4.1 Profil

```text
Yaş:           26–38
Rol:           Mid-size SoMe ajansında account/strategy lead
Müşteri:       3–8 marka (kozmetik, food, retail, B2B mix)
Ekip:          2–5 kişi (kendisi + junior'lar + tasarımcı)
Ajans cirosu:  200K–1M TL/ay
Aylık araç bütçesi: 5–20K TL (Hootsuite, Canva Pro, Buzzsumo, ChatGPT)
```

### 4.2 Acılar

```text
P1. Marka başına haftalık 3–5 paylaşım × 5 marka = 15–25 paylaşım
P2. Müşteriler "gündeme uyumlu ama marka tonu korunmuş" istiyor
P3. Pazartesi sabah brief'i için Pazar gecesi kaynak tarama
P4. Junior ekibe iş atayınca tone tutmazsa müşteri şikayet ediyor
P5. Comparison report (Q3 vs Q4 gündem) müşteri sunumu için saatler
P6. Müşteriye "kaynaklı" rapor sunma zorunluluğu (PR riski)
```

### 4.3 Willingness to pay

```text
Ajans bütçesi yüksek, ROI argümanı kritik.
Pro veya Agency tier hedef: 750–2.500 TL/ay
Multi-seat ihtiyacı (3–5 kullanıcı)
Yıllık ödeme yatkınlığı yüksek (faturalama kolaylığı)
```

---

## 5. Jobs-to-be-Done Çerçevesi

### 5.1 Functional jobs

```text
J1. "Gündemi hızlıca tarayıp benim için alakalı olanları seçmek"
J2. "Aynı olayı birden fazla kaynaktan çapraz doğrulamak"
J3. "Olayı bana özel tonda X içeriğine çevirmek"
J4. "Geçmiş bir gündemi şimdiki ile karşılaştırmak"
J5. "Haftalık içerik takvimi oluşturmak"
J6. "Kaynaklı paylaşım üretip güvenilirlik kazanmak"
```

### 5.2 Emotional jobs

```text
E1. "Geç kaldım" anksiyetesini azaltmak
E2. "Yanlış bilgi paylaştım" korkusundan kurtulmak
E3. "Yine aynı şeyi yazıyorum" yaratıcı tükenmişliğine karşı
E4. "Profesyonel görünmek" — kaynaklı, derinlikli içerik
```

### 5.3 Social jobs

```text
S1. Takipçilere "ciddi/güvenilir creator" görünmek
S2. Müşteriye/patrona "verimli ekip lideri" görünmek
S3. Diğer creator'lara karşı "geçmiş analizi yapan derin yorumcu" konumu
```

### 5.4 JTBD önceliği

```text
Birincil JTBD (paying willingness yüksek): J1 + J3 + J6
İkincil JTBD (retention'ı artıran):         J2 + J4
Üçüncül JTBD (advanced/upsell):            J5 + Faz 5 stil profili
```

---

## 6. Problem-Solution Fit Hipotezi

### 6.1 Fit haritası

```text
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   PERSONA              ACI                  ÇÖZÜM                │
│                                                                  │
│   Mete (P1A)           60–120 dk/gün        Nodrat /generate    │
│   politik creator      haber tarama         RAG + kaynak         │
│                        halüsinasyon         Comparison mode      │
│                        karşılaştırma        Stil profili (F5)   │
│                        ton tutarlılığı                          │
│                                                                  │
│   Beklenen sonuç: ↓%75 zaman, ↓%90 hata riski, ↑ etkileşim       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 Fit kanıtı için gereken sinyaller

```text
S1. ≥25 persona görüşmesi (P1A: 15, P1B: 10) — acı doğrulanması
S2. ≥50 kişiyle landing page + waitlist (≥%10 conversion hedefi)
S3. ≥10 kişiyle "concierge MVP" (manual + Nodrat hibrit)
S4. ≥30 kişi prototype testi → ≥%60 "would pay 250+ TL"
S5. ≥20 paid kullanıcı, 30 gün retention ≥%50
S6. NPS ≥30 (closed beta sonrası)
```

### 6.3 Doğrulanmadığında ne yaparız?

```text
- P1A acısı onaylanmazsa → P1B (ajans) primer'a geçilir
- "ChatGPT yeter" denirse → Türkçe gündem moat'u + comparison vurgusu
- "Comparison mode imaginary" çıkarsa → Faz 1'de kesilir (MVP cut-list)
- "10$/ay max" çıkarsa → ekonomi modeli yeniden, paket küçülür
- "50K takipçi altı pay etmiyor" çıkarsa → SAM daralır, niche pivot
```

---

## 7. Doğrulama Görev Listesi

### 7.1 Pre-build validation (kod yazılmadan önce)

```text
V1. 25 persona görüşmesi (P1A: 15, P1B: 10)
    Süre: 30–45 dk her biri
    Soru bloklari: problem framing / mevcut workaround / WTP / feature ranking
    Çıktı: persona doğrulanma raporu, JTBD önceliği

V2. Landing page + waitlist
    URL: nodrat.com (veya alternatif)
    Headline A/B (problem-odaklı vs çözüm-odaklı)
    Hedef: %10+ email signup conversion
    Bütçe: 1.500 TL X Ads (15–20 gün)

V3. Smoke test reklamı
    Mock pricing page → "Coming soon, get early access"
    Hangi tier'a tıklandığı ölçümü
    Hedef: ≥%5 "Pro tier" tıklama

V4. Concierge MVP
    İlk 10 waitlist'e manuel hizmet
    Form → manuel brief hazırlama → tweet seçeneği
    NPS + "would pay 250 TL/ay?" cevabı
```

### 7.2 Post-build validation (Faz 2 sonrası)

```text
V5. Closed beta (30 davet)
V6. 30 gün retention ölçümü (D1, D7, D30)
V7. "Aha moment" tanımlama (ilk kayıtlı üretim mi, ilk thread mi?)
V8. Conversion funnel: trial → free → starter → pro
V9. NPS ≥30 hedefi
V10. Cancellation reason analizi (1-on-1 exit interview)
```

---

## 8. Karar Noktaları

### 8.1 Bu doküman üzerine alınması gereken kararlar

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Birincil persona kim? | P1A (creator) primer, P1B (ajans) secondary | Pricing, GTM, feature priority |
| D2 | Türkçe-only mi multi-language mi? | TR-only başla, EN sonra (≥1K paid sonra) | i18n yapısı kalır, kapsamı kapatır |
| D3 | Comparison mode MVP'de mi? | Hayır, MVP-2'ye al; MVP-1 sadece current | Faz 2 kapsamı küçülür |
| D4 | Beta paid mi free mi? | Closed beta free, public launch'ta paid | Conversion data kaybı vs hız |
| D5 | Self-serve mi sales-led mi? | Self-serve (consumer SaaS DNA) | GTM + onboarding tasarımı |
| D6 | X otomatik gönderme entegrasyonu? | Hayır (PRD §3.2 kapsam dışı) | Yasal + kullanıcı sorumluluğu |
| D7 | Beta'da hangi vertical? | Politik creator > ajans (acı netliği) | İlk 100 kullanıcı seçimi |

### 8.2 Bu doküman ne zaman güncellenir?

```text
- 25 görüşme tamamlandığında (persona kalibrasyonu)
- Landing waitlist sonucu (top-of-funnel sinyali)
- Beta launch sonrası (gerçek kullanım davranışı)
- Pricing tier ilk gerçek conversion verisinden sonra
```

---

## 9. Çapraz Referans

```text
Persona P1A (Mete)         → Pricing Strategy: Pro tier birincil hedef
Persona P1B (Selin)        → Pricing Strategy: Agency tier multi-seat
JTBD J1+J3+J6              → North Star: Saved Generations (değer alındı)
JTBD J4 (comparison)       → MVP Cut-List: MVP-2'ye taşındı
Anti-persona AP3 (spam)    → Risk Register: abuse vector R-OPS-04
Validation gap V1–V4       → MVP Cut-List: Faz 1 ile paralel waitlist
WTP "Mete 250–750 TL"      → Unit Economics: Pro tier margin doğrulama
```

---

**Sonuç:** Bu doküman bir **varsayım haritasıdır**. Test edilmeden ürün geliştirme her gün hipotez biriktirir; kanıt biriktirmez. Build–measure–learn döngüsünü hızlandırmak için **25 görüşme + landing waitlist + smoke test** Faz 1 ile paralel ilerlemelidir. Faz 2 sonrası geliştirmeye geçmeden V1–V4'ün tamamlanması önerilir.
