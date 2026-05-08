# Nodrat — UX Wireframes ve Journey Maps

**Doküman türü:** UX Wireframes & User Journey Maps
**Sürüm:** v0.2 (2026-05-08 — Faz 6 LS hosted checkout/portal flow notu eklendi, USD primary fiyat display)
**Bağımlılık:** PRD §3 (kullanıcı dashboard), IA §5 (sayfa hiyerarşisi), §10 (kullanıcı akışları), Discovery (P1A persona), Pricing §4 (funnel triggers), Design System (sıradaki — copy guideline'lar buradan)

> **v0.2 Faz 6 notu (Epic [#448](https://github.com/selmanays/nodrat/issues/448)):** Iyzico custom checkout wireframe'i kaldırıldı. Lemon Squeezy MoR ile **çoğu billing UI hosted**: /app/billing/plans Nodrat'ta (compare + CTA), CTA tıklayınca LS hosted checkout yeni tab'da açılır; /app/billing/manage button → LS hosted Customer Portal redirect (cancel, update card, invoice list). Nodrat custom payment form veya invoice generator yapmaz. Detaylı wireframe Faz 6 PR ile gelecek.
**Hedef:** Kritik akışların low-fidelity wireframe'leri ve aşamalı kullanıcı yolculuk haritaları.

⚠️ **Notasyon:** Wireframe'ler ASCII art (low-fidelity). Visual design Figma'da yapılır; bu doküman **layout + interaction + copy** için ana kaynaktır.

---

## 0. Yönetici Özeti

```text
Doküman kapsamı:
  - 8 ana wireframe (kritik ekranlar)
  - 4 journey map (en yüksek değerli akışlar)
  - 6 kritik state catalog (loading, empty, error, vb.)
  - Aha moment + activation funnel detayı

Tasarım prensipleri:
  P1. Generate → Result tek nefeste, distract YOK
  P2. Sources hep görünür (güven yapı taşı)
  P3. Insufficient data açık + actionable (PRD §2.10)
  P4. Quota her zaman görünür (sürpriz fatura yok)
  P5. Admin selector tester pixel-precise
  P6. Mobile-first değil, desktop-first (creator workflow)

Kritik ekranlar (hassasiyet sırası):
  1. /app/generate/new          — Core loop
  2. /app/generate/{id}/result  — Aha moment
  3. /admin/sources/{id}/test-listing — Admin operasyonu
  4. /app/dashboard             — Hero metrics
  5. /trial/new                 — TOFU
  6. /register                  — Conversion
  7. /admin/sources/new         — Admin onboarding
  8. /app/billing/plans         — Pricing
```

---

## 1. Tasarım Felsefesi

### 1.1 Layout grid

```text
- 12-col grid (desktop, ≥1280px)
- 6-col grid (tablet, 768-1279px)
- 4-col grid (mobile, <768px)
- Sidebar: 240px (collapsed: 64px)
- Topbar: 56px sabit
- Content padding: 24px
- Card spacing: 16px
- Form spacing: 16-24px
```

### 1.2 Bilgi mimarisi prensipleri

```text
- F-pattern reading (sol-üstten sağa-aşağı)
- Primary action sağ üst (CTA) veya merkezi
- Sources sağ panelde (sticky), output solda
- Quota her sayfada üstte (passive awareness)
- Empty state'lerde net "next action"
```

### 1.3 Microinteraction prensipleri

```text
- Loading: skeleton placeholder (UX süresi algısı)
- Optimistic UI: kayıt anında save işareti
- Toast: success 3sn, error sticky (dismiss gerekir)
- Modal sadece destructive action veya form için
- Keyboard shortcut: Cmd+Enter (generate), Cmd+S (save)
```

---

## 2. Wireframe #1 — `/app/generate/new` (CORE LOOP)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Nodrat ▾                            Quota: 45/500 ▕▏ 91%      Mete ▾ │
├──────────────────────────────────────────────────────────────────────┤
│  Sidebar          │  ⌘ Yeni İçerik Üret                                │
│  ─────────────    │                                                    │
│  📊 Dashboard     │  ┌──────────────────────────────────────────────┐ │
│  ✦ Yeni Üret      │  │ Hangi gündemle ilgili içerik üretmek         │ │
│  📋 Geçmiş        │  │ istiyorsun?                                  │ │
│  ⭐ Kaydedilenler │  │                                              │ │
│  ─────────────    │  │ ┌──────────────────────────────────────────┐ │ │
│  🎨 Stil Profili  │  │ │ [textarea, 4 satır]                      │ │ │
│  ⚙️ Ayarlar       │  │ │                                          │ │ │
│  ─────────────    │  │ │                                          │ │ │
│  💳 Faturalama    │  │ └──────────────────────────────────────────┘ │ │
│  ❓ Yardım        │  │ Örn: "Bu hafta yapay zeka regülasyonlarıyla  │ │
│                   │  │ ilgili 5 X paylaşımı üret"                   │ │
│                   │  └──────────────────────────────────────────────┘ │
│                   │                                                    │
│                   │  Parametreler                          ▾ Daha az   │
│                   │  ┌──────────────────────────────────────────────┐ │
│                   │  │ İçerik türü: [X paylaşımı ▾]                 │ │
│                   │  │ Zaman:       [Güncel ▾]                      │ │
│                   │  │ Ton:         [Tarafsız ▾]                    │ │
│                   │  │ Uzunluk:     [Kısa ▾]                        │ │
│                   │  │ Kaynak göster: ☑                              │ │
│                   │  │ Stil profili: [Yok ▾]            🔒 Pro      │ │
│                   │  └──────────────────────────────────────────────┘ │
│                   │                                                    │
│                   │           [    Üret  (⌘ + Enter)    ]              │
│                   │                                                    │
│                   │  Tahmini süre: ~6 sn                               │
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Textarea autosize, max 1000 char
- "Üret" disabled iff textarea boş
- ⌘+Enter shortcut
- Stil profili kilitli (Pro tier değilse) → tıklayınca paywall modal
- Quota 90%+ ise sarı uyarı banner
- Quota 100% → "Üret" disabled + "Pro'ya geç" CTA

EMPTY STATE (research-driven, 2026-05-01):
Onboarding'de mode isimleri (Comparison/Archive/Weekly) UI'da gizlenir.
Yerine 3 örnek prompt clickable kart olarak gösterilir:
- "Bugünkü ekonomi gündeminden 5 X paylaşımı üret"
- "Bu haftanın siyaset gündemini kaynaklı özetle"
- "Geçen ay ve bu ay CHP gündemini kıyasla"

Tıklayınca textarea'ya yerleşir + parametreler otomatik set olur.
Mode isimleri backend'te kalır, kullanıcı UI'da görmek zorunda değil.

GEREKÇE:
Prototype testinde "Comparison/Archive mode" net bulunmadı.
Örnek prompt yaklaşımı first-generation rate'i artırır (B1 metric).
```

---

## 3. Wireframe #2 — `/app/generate/{id}/result` ⭐ AHA MOMENT

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Nodrat ▾                            Quota: 46/500              Mete ▾ │
├──────────────────────────────────────────────────────────────────────┤
│  ← Yeni Üret                                                          │
│                                                                       │
│  ┌────────────────────────────────────┐  ┌──────────────────────────┐│
│  │ "Bu hafta yapay zeka regülas..."   │  │ Kaynaklar                 ││
│  │ Mode: Weekly · 25-30 Nis · 8 kayn. │  │                           ││
│  │                                    │  │ 🟢 BBC Türkçe             ││
│  │ ─────────────────────────────────  │  │ AI Act Türkiye'ye uyum    ││
│  │                                    │  │ 28 Nis · ↗                ││
│  │ ┌──────────────────────────────┐   │  │                           ││
│  │ │ #1                            │   │  │ 🟢 NTV                    ││
│  │ │ Türkiye yeni AI regülasyon... │   │  │ Resmi Gazete açıklaması   ││
│  │ │                                │   │  │ 27 Nis · ↗                ││
│  │ │ Vurgu: regülasyon karşılaş.  │   │  │                           ││
│  │ │ 234/280 ████████░░             │   │  │ 🟡 Anadolu Ajansı         ││
│  │ │                                │   │  │ AB ile uyum çalışmaları   ││
│  │ │ [Kopyala]  [Düzenle]  [Beğendim│   │  │ 26 Nis · ↗                ││
│  │ │  ❤️]   [✗ Halüsinasyon]        │   │  │                           ││
│  │ └──────────────────────────────┘   │  │ + 5 kaynak daha ▾        ││
│  │                                    │  │                           ││
│  │ ┌──────────────────────────────┐   │  └──────────────────────────┘│
│  │ │ #2                            │   │                              │
│  │ │ Genel Başkan Pazartesi...     │   │  Gündem Kartları             │
│  │ │ ...                            │   │  • AI regülasyonu Türkiye    │
│  │ └──────────────────────────────┘   │  • EU AI Act etkisi          │
│  │                                    │                              │
│  │ ┌──────────────────────────────┐   │  Kullanılan model            │
│  │ │ #3, #4, #5 ...                │   │  DeepSeek V3 · ~$0.0024      │
│  │ └──────────────────────────────┘   │                              │
│  │                                    │  Aksiyonlar                  │
│  │ ─────────────────────────────────  │  💾 Hepsini Kaydet            │
│  │ [Yeniden üret]                     │  📋 JSON İndir                │
│  │ [Tonu değiştir]                    │  🔄 Stil değiştir → Pro 🔒    │
│  └────────────────────────────────────┘                              │
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Her post bir card, hover'da actions belirir
- "Kopyala" → clipboard + toast + analytics event
- "Beğendim ❤️" → save + activation tracking
- "✗ Halüsinasyon" → flag modal (Risk R-PRD-01)
- Sources sticky sağda, kart tıklanınca yeni tab açılır
- "Hepsini Kaydet" → bulk save, success toast
- Sol-tıklama text üzerinde → inline edit (Faz 7+)

KEY METRICS (Metrics §3.4 activation):
- B3 first save rate: bu ekranda ölçülür
- B5 aha moment: ilk "kaydet" tıklaması
- E1 halu flag rate: "✗ Halüsinasyon" tıklaması
```

### 3.1 Result variant — Insufficient data (PRD §2.10)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  ← Yeni Üret                                                          │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ⚠️  Veri yetersiz                                              │  │
│  │                                                                 │  │
│  │  Bu konu için seçilen dönemde yeterli güvenilir haber           │  │
│  │  verisi bulunamadı.                                             │  │
│  │                                                                 │  │
│  │  Bulduğumuz: 1 gündem kartı, 2 haber                            │  │
│  │  Gereken:    En az 2 gündem kartı VEYA 3 haber                  │  │
│  │                                                                 │  │
│  │  Şunları deneyebilirsin:                                        │  │
│  │                                                                 │  │
│  │  ⏱️  [Zaman aralığını genişlet — son 14 gün]                    │  │
│  │  🔍 [Konuyu daha geniş yaz: "yapay zeka" yerine "teknoloji"]    │  │
│  │  🔄 [Yeni bir konu dene]                                         │  │
│  │                                                                 │  │
│  │  Bu üretim quota'ndan DÜŞÜLMEDİ.                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

KEY POINTS:
- Net + actionable (Risk R-PRD-01 mitigation UI'ı)
- Quota sayılmaz (kullanıcı dostu)
- Suggested next action 3 farklı yön
```

---

## 4. Wireframe #3 — `/admin/sources/{id}/test-listing` (ADMIN OPERASYONU)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Admin · BBC Türkçe · Liste Sayfası Test                              │
├──────────────────────────────────────────────────────────────────────┤
│  ← BBC Türkçe                                                         │
│                                                                       │
│  ┌─────────────────────────────────────┐  ┌───────────────────────┐  │
│  │ Selectors                            │  │ Önizleme              │  │
│  │                                      │  │                       │  │
│  │ URL                                  │  │ Status: 200 OK        │  │
│  │ [https://bbc.com/turkce/haberler  ]  │  │ Cards bulundu: 12     │  │
│  │                                      │  │                       │  │
│  │ Card                                 │  │ ┌───────────────────┐ │  │
│  │ [.news-card                       ]  │  │ │ #1                │ │  │
│  │                                      │  │ │ "Türkiye AI Act'i  │ │  │
│  │ Title                                │  │ │  uygulayacak"     │ │  │
│  │ [.news-card h2                    ]  │  │ │ → /turkce/123     │ │  │
│  │                                      │  │ │ 🖼️ image found    │ │  │
│  │ Link                                 │  │ │ 28 Nis 14:30      │ │  │
│  │ [.news-card a                     ]  │  │ └───────────────────┘ │  │
│  │                                      │  │ ┌───────────────────┐ │  │
│  │ Image                                │  │ │ #2 ...            │ │  │
│  │ [.news-card img                   ]  │  │ └───────────────────┘ │  │
│  │                                      │  │                       │  │
│  │ Date                                 │  │ + 10 daha ▾           │  │
│  │ [time datetime                    ]  │  │                       │  │
│  │                                      │  │ Uyarılar:             │  │
│  │ Pagination                           │  │ ⚠️ 3 kart resimsiz    │  │
│  │ [○ Yok ◉ Next link ○ Page param]    │  │                       │  │
│  │                                      │  │ Hatalar:              │  │
│  │ [   🔍 Test Et   ]                  │  │ (yok)                 │  │
│  │                                      │  │                       │  │
│  │ ─────────────────────                │  └───────────────────────┘  │
│  │ Önceki versiyonlar                   │                              │
│  │ • v3 · 2 gün önce · aktif            │                              │
│  │ • v2 · 14 gün önce                   │                              │
│  │ • v1 · 30 gün önce                   │                              │
│  └──────────────────────────────────────┘                              │
│                                                                       │
│  [Kaydet ve Aktifleştir] [Sadece test, aktif etme]                   │
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Selectors değişince "Test Et" tıklanır → API call /test-listing
- Preview canlı dolar (cards + warnings + errors)
- Kart tıklanınca detay test ekranına git
- Pagination radyo seçimi → ilgili input açılır (next selector / page param)
- Kaydet → yeni source_configs version oluşur, eskisi pasifleşir
- Önceki versiyonlar tıklanınca config geri yüklenir (rollback hazırlığı)

KEY ROLE:
- R-OPS-01 (HTML kırılganlığı) mitigation: admin hızlı düzeltir
- Confidence skor görünür (extraction kalite)
```

---

## 4.5 Wireframe — `/admin/media` (#304 MVP-1.4 PR-4)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Görseller                                                            │
│  NIM Llama 4 Maverick (VLM) ile işlenen haber görselleri.             │
│  Bytes saklanmaz; sadece vlm_caption + ocr_text + depicts kalır       │
│  (process & discard).                                                 │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ Toplam   │ │ İşlenen  │ │ Bekleyen │ │ Başarısız │                │
│  │  1.842   │ │  1.756 ✓ │ │     38   │ │      48 ✗│                │
│  │          │ │ Son 24s: │ │          │ │ Atlanan: │                │
│  │          │ │   124    │ │          │ │     22   │                │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                │
├──────────────────────────────────────────────────────────────────────┤
│  [Durum ▾] [Kaynak ▾] [📅 Tarih aralığı]            [⟳ Yenile]      │
├──────────────────────────────────────────────────────────────────────┤
│ Önizleme │ Durum    │ VLM açıklama          │ Konular  │ Haber    │ ⋮│
├─────────┼──────────┼────────────────────────┼──────────┼──────────┼──┤
│ [thumb] │ İşlendi  │ "İki erkek el sıkışıyor"│ Erdoğan  │ AI Act…  │ ⋮│
│ 56×56   │          │ alt: "..."              │ Kılıç…   │ BBC      │  │
│         │          │ OCR: ""                 │          │          │  │
├─────────┼──────────┼────────────────────────┼──────────┼──────────┼──┤
│ [thumb] │ Bekliyor │ —                       │ —        │ ...      │ ⋮│
└─────────┴──────────┴────────────────────────┴──────────┴──────────┴──┘
                                       1–50 / 1.842 görsel  [50/sayfa▾]

Etkileşim:
- thumbnail tıkla → orijinal URL aç (yeni tab, `target=_blank`)
- haber linki → /admin/articles/{id}
- ⋮ kebab → "Yeniden işle" / "Orijinali aç"
- "Yeniden işle" sonrası status='pending' + image_vlm_queue dispatch
- Skeleton loading state, empty state ("Filtreye uyan görsel yok")

Filtreler (querystring):
  ?status=processed&source_id=...&date_from=2026-04-01&date_to=2026-05-01

KVKK / FSEK uyum:
- depicts'te politik figür → admin /legal'da ek attribution kuralı
- thumbnail kaynak haber sitesinden lazy-load (kendi sitemize bytes
  hiç indirilmez — process & discard mimarisi gereği)
```

---

## 5. Wireframe #4 — `/app/dashboard`

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Nodrat ▾                            Quota: 45/500              Mete ▾ │
├──────────────────────────────────────────────────────────────────────┤
│  Hoş geldin, Mete                                                     │
│                                                                       │
│  ┌─────────────────────────────────┐  ┌────────────────────────────┐ │
│  │ ✦ Yeni Üret                     │  │ Bu hafta                   │ │
│  │                                  │  │                            │ │
│  │ [Yeni gündem talebi...        ]  │  │ Üretim:        12          │ │
│  │ [Üret →                       ]  │  │ Kaydedilen:    7           │ │
│  │                                  │  │ Kullanım:     %42          │ │
│  │ Hızlı şablonlar:                 │  │ Yenileme:    19 gün sonra  │ │
│  │ • Bugünkü ekonomi               │  │                            │ │
│  │ • Bu hafta siyaset thread'i      │  └────────────────────────────┘ │
│  │ • Karşılaştırma analizi          │                                  │
│  └─────────────────────────────────┘  ┌────────────────────────────┐ │
│                                        │ Pro'ya Yükselt 🔒          │ │
│  Son üretimler              Hepsi →   │                            │ │
│  ┌──────────────────────────────────┐ │ Comparison mode             │ │
│  │ "Bu hafta AI regülasyon..."      │ │ Stil profili                │ │
│  │ X paylaşımı · Bugün · 5 post     │ │ Görsel destekli içerik      │ │
│  │ ⭐ Kaydedildi                     │ │                            │ │
│  ├──────────────────────────────────┤ │ [Pro'ya Geç →]              │ │
│  │ "Geçen ayki gündem..."           │ │                            │ │
│  │ Karşılaştırma · 3 gün · 2 post   │ │ 749 TL/ay · 2 ay bedava    │ │
│  └──────────────────────────────────┘ └────────────────────────────┘ │
│                                                                       │
│  💡 Bilgi: Kayıtlı kaynaklarda 12 yeni gündem kartı eklendi           │
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Hızlı şablonlar tıklanınca /generate/new açılır, prefill
- Son üretimler liste, tıklayınca result açılır
- Pro CTA dinamik: tier'a göre gizli (zaten Pro ise)
- "Bilgi" notification tipi (yeni kart, upcoming feature, vb.)

KEY METRICS:
- Time-to-first-generation (sayfada kalış süresi)
- Reactivation: dashboard'a geri dönen kullanıcı
- Pro CTA tıklama oranı
```

---

## 6. Wireframe #5 — `/trial/new` (TOFU)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Nodrat                                          [Giriş Yap] [Üye Ol] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│        Türkçe gündem üzerinden kaynaklı X içeriği üret                │
│                                                                       │
│        Halüsinasyon yok. ChatGPT'den hızlı. Gerçek kaynak.            │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │  Hangi gündemle ilgili içerik üretmek istiyorsun?                ││
│  │                                                                  ││
│  │  ┌────────────────────────────────────────────────────────────┐ ││
│  │  │ [textarea]                                                  │ ││
│  │  │ Örn: Bugünkü ekonomi gündemiyle 3 X paylaşımı üret.         │ ││
│  │  │                                                             │ ││
│  │  └────────────────────────────────────────────────────────────┘ ││
│  │                                                                  ││
│  │           [    Üret  →  Ücretsiz   ]                             ││
│  │                                                                  ││
│  │  Bugün için 1 deneme hakkın var · Üye olunca 10/ay              ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                       │
│  Nasıl çalışıyor?                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                               │
│  │ 1. Yaz   │→ │ 2. Üret  │→ │ 3. Pay.  │                              │
│  │ Talep    │  │ Kaynaklı │  │ Kopyala  │                              │
│  └─────────┘  └─────────┘  └─────────┘                               │
│                                                                       │
│  Gerçek kullanıcılar:                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │  "Sabah 10 dakikada gündemle ilgili thread hazırlıyorum.         ││
│  │   ChatGPT bunu yapamıyordu." — @_metexyz                          ││
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Textarea autofocus
- "Üret" → loading + result inline (ekran kaymaz)
- Success → result + "Kayıt ol → 10 üretim/ay" CTA
- Rate limit hit → modal "Üye ol → günde 1 değil 10/ay"

KEY METRICS:
- A1 landing CTR (visitor → trial start)
- A4 trial → free conversion
```

---

## 7. Wireframe #6 — `/register`

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Nodrat                                                  [Giriş Yap]  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│              Ücretsiz hesap oluştur                                    │
│              Aylık 10 üretim · Comparison mode 🔒 Pro                  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │  Email                                                            ││
│  │  [_______________________________]                                ││
│  │                                                                   ││
│  │  Şifre  (en az 12 karakter)                                       ││
│  │  [_______________________________]                                ││
│  │                                                                   ││
│  │  Ad Soyad (opsiyonel)                                             ││
│  │  [_______________________________]                                ││
│  │                                                                   ││
│  │  ☑ Üyelik koşullarını ve gizlilik politikasını kabul ediyorum.    ││
│  │     [Hizmet Koşulları] · [Gizlilik] · [KVKK Aydınlatma]           ││
│  │                                                                   ││
│  │  ☑ İçeriğimin AI provider'larına gönderilmesini onaylıyorum       ││
│  │     (yurt dışı veri transferi için açık rıza)                     ││
│  │                                                                   ││
│  │  ☐ Ürün haberleri ve ipuçları gönder (opsiyonel)                  ││
│  │                                                                   ││
│  │  [   Hesap Oluştur   ]                                            ││
│  │                                                                   ││
│  │  Zaten hesabın var mı? [Giriş yap]                                ││
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- Şifre strength meter (live)
- KVKK checkbox ZORUNLU (Legal §2.3)
- Foreign transfer ZORUNLU (Legal §7.6)
- Marketing OPSIYONEL
- Submit → email verification ekranı

KEY POINTS:
- Tüm legal consent açık ve net
- "Ücretsiz" anchor öne çıkar
- Pro feature paywall hint görünür ("Comparison mode 🔒 Pro")
```

---

## 8. Wireframe #7 — `/admin/sources/new` (Admin Onboarding)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Admin · Yeni Kaynak                                                  │
├──────────────────────────────────────────────────────────────────────┤
│  ← Kaynaklar                                                          │
│                                                                       │
│  Kaynak türü                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ ◉ RSS         │  │ ○ Kategori    │  │ ○ Manuel URL │                │
│  │ Önerilen      │  │ HTML kazıma   │  │ Tek haber    │                │
│  └──────────────┘  └──────────────┘  └──────────────┘                │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ Adım 1/4 — Temel Bilgiler                                          ││
│  │                                                                    ││
│  │ Kaynak adı                                                         ││
│  │ [BBC Türkçe                                                ]      ││
│  │                                                                    ││
│  │ Domain                                                             ││
│  │ [bbc.com                                                   ]      ││
│  │                                                                    ││
│  │ RSS URL                                                            ││
│  │ [https://feeds.bbci.co.uk/turkce/rss.xml                  ]      ││
│  │                                                                    ││
│  │ Dil  [Türkçe ▾]      Kategori  [Genel haber ▾]                    ││
│  │                                                                    ││
│  │ Tarama sıklığı  [30 dakika ▾]                                     ││
│  │                                                                    ││
│  │ Güvenilirlik puanı  [████████░░] 0.85                             ││
│  │                                                                    ││
│  │ ⚠️  Robots.txt kontrol edildi: ✓ Uygun                             ││
│  │ ☑ Site kullanım koşullarını okudum, scraping uygun.                ││
│  │                                                                    ││
│  │                                                  [İleri →]        ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                       │
│  Sonraki adımlar:                                                     │
│  • Adım 2: RSS field eşlemesi                                          │
│  • Adım 3: Detail page extraction                                      │
│  • Adım 4: Test + aktivasyon                                           │
└──────────────────────────────────────────────────────────────────────┘

INTERACTION:
- 4 adımlı wizard (RSS için)
- Robots.txt kontrol otomatik (Legal §4)
- ToS checkbox zorunlu
- Her adımda preview varsa göster
- Son adımda test detail + canlı önizleme
- Aktif et → scheduler kuyruğa alır
```

---

## 9. Journey Map #1 — Trial → Free Conversion

```text
ASAMA          DURUMU              AKSİYON                   DUYGU
───────────────────────────────────────────────────────────────────────
1. Discovery   X'te tweet gördü     "nodrat.com" yazdı       Meraklı
2. Landing     /trial/new             Headline okudu           İlgilenir
3. Trial-1     Talep yazdı            Üret tıkladı             Heyecanlı
4. Result-1    İlk üretim             5 post + sources         Şaşırmış (aha?)
5. Use         Tweet'i kopyaladı      Manuel paylaştı          Tatmin
6. Trial-2     Yeni talep             Rate limit modal          Hayal kırık
7. CTA         "Üye ol → 10/ay"      Email girer               Karar
8. Register    Form doldur            Submit                    Dikkatli
9. Verify      Email click            Verified                  Memnun
10. /app/dash  İlk dashboard          Yeni Üret tıklar         Aktif

PAINS / GAINS:
+ Aha moment Adım 4'te (kaynaklı ilk paylaşım)
- Adım 6 friction noktası (rate limit)
- Adım 7-9 conversion funnel kayıp riski
+ Adım 10 ikinci aha (saved generations başlar)

KEY METRICS:
- A1 landing CTR
- B1 trial → first gen rate
- A4 trial → register conversion (%25 hedef)
- B2 time-to-first-generation < 60 sn

OPTIMIZATION:
- Headline A/B test (problem-odaklı vs çözüm-odaklı)
- Trial 1 hak yetersiz mi? (3'e çıkarılabilir test)
- Verify email zorunlu mu yoksa magic link?
```

---

## 10. Journey Map #2 — Free → Starter Upgrade

```text
ASAMA              DURUMU                AKSİYON                    DUYGU
─────────────────────────────────────────────────────────────────────────
1. Active week 1   /app/generate          Günde 1 üretim             Aktif
2. Quota use       Quota %50              Üst banner görür           Farkındalık
3. Save habit     Saved generations 5     "İşe yarıyor" hissi        Bağlanma
4. Quota %80      Banner sarı             "10 üretim kaldı"          Kaygı
5. Comparison hit  /app/generate'de       Comparison kilitli          Frustration
                   tıklar                  Pro 🔒 modal
6. Pro modal       Feature listesi        "+5x üretim"               Düşünüyor
7. Pricing         /app/billing/plans     Tier karşılaştır           Compare
8. Trial offer     "7 gün ücretsiz Pro"   Tıklar                     İlgi
9. Checkout        Iyzico                  Kart bilgisi              Friction
10. Success        Pro tier active         Comparison çalışır        Excited
11. Habit          Aylık alışkanlık       Renewals                   Müşteri

KEY MOMENTS:
- Adım 5: feature paywall trigger (en güçlü conversion sinyali)
- Adım 7: pricing transparency kritik
- Adım 9: Iyzico friction noktası

OPTIMIZATION:
- Adım 4'te email kampanyası
- Adım 5'te 1-tıklama "30 dk Pro deneme"
- Adım 8 yıllık iskonto öne çıkar
- Adım 9 Apple Pay / Google Pay
```

---

## 11. Journey Map #3 — Admin Source Onboarding

```text
ASAMA              DURUMU                AKSİYON                   SÜRE
─────────────────────────────────────────────────────────────────────────
1. Discovery       Yeni kaynak ihtiyaç   "Sözcü ekleyelim"          —
2. /admin/srcs/new RSS sekme              Type: RSS                  10 sn
3. Step 1          URL + meta             Form doldur                2 dk
4. Robots check    Otomatik               ✓ Uygun                   3 sn
5. Step 2          RSS field map          Auto-detect                30 sn
6. Step 3          Detail extraction      Method seç (readability)   30 sn
7. Step 4          Test detail            1 article ile test         15 sn
8. Confidence      0.92 görür              "Yüksek, OK"              5 sn
9. Activate        Aktifleştir             Scheduler queue            5 sn
10. Wait           5-15 dk                 İlk haberler gelir        15 dk
11. Verify         /admin/articles        Sözcü filter               2 dk

TOTAL: ~20 dk admin operasyonu

PAINS:
- Adım 3-6: doğru config bulmak (yeni admin için zor)
- Adım 7: confidence düşük çıkarsa selector tweak gerek
- Adım 10: bekleme (UX'te progress indicator)

OPTIMIZATION:
- Pre-built templates (Sabah, Sözcü, vb. için hazır config)
- Confidence < 0.7 → selector test ekranına yönlendir
- Real-time activity feed (Adım 10-11)

KEY METRICS:
- Time-to-first-article < 30 dk hedef
- Source success rate ilk gün > %70 (KS-1 acceptance)
```

---

## 12. Journey Map #4 — Pro User Power Loop (haftalık)

```text
ZAMAN          AKSİYON                    Nodrat ekranı              SONUC
─────────────────────────────────────────────────────────────────────────
Pazartesi 09:00 Sabah brief'i              Dashboard                  10 dk
                Hızlı şablon: "Bu hafta"   /generate/new pre-filled
                Üret                       /result
                3 post copy → X            Manual paylaş

Pazartesi 09:30 Müşteri brief              Comparison: Q1 vs Q2       15 dk
                Marka 1 stil profili        Saved 5 post → not        
                Export JSON                 → Slack #marka1

Salı 10:00      Reaktif: gündem değişti    /generate/new               5 dk
                "ekonomi açıklaması"
                3 post seçti               Saved + Tweet

Çarşamba+      Tekrar (her gün ~5-10 üretim, ~50/hafta)

Cuma 17:00     Haftalık report            /usage                      3 dk
                65 üretim, 30 saved        WSGAU 6.0 → Pro tier
                Aylık ortalama %85         hedefini geçti

WSGAU = 30/1 = 30 (Pro power user için yüksek)
Bu pattern → Pro tier sticky habits
```

---

## 13. State Catalog

### 13.1 Loading states

```text
Generation in progress (~6 sn):
  [✦ Üretiliyor...]
  ▕████░░░░░░░░░▏ %33
  Bekleniyor: kaynaklar bulundu (8) → içerik üretiliyor

Skeleton placeholder:
  ░░░░░░░░░░░░░░░░░ — title
  ░░░░░░░░░░░░ — subtitle
  ░░░░░░░░░░░░░░░░░░░░░░░░░ — paragraph

Long task progress:
  Adım 1/4: Talebin yapılandırılıyor    ✓
  Adım 2/4: Kaynaklar getiriliyor       ✓
  Adım 3/4: İçerik üretiliyor           ⏳
  Adım 4/4: Kalite kontrolü             ○
```

### 13.2 Empty states

```text
İlk kullanım (/app/generations):
  ┌─────────────────────────────────────┐
  │  ✦                                  │
  │                                     │
  │  Henüz üretim yok                   │
  │  İlk gündem talebini yaz, başla     │
  │                                     │
  │  [Yeni Üret →]                      │
  └─────────────────────────────────────┘

Saved boş (/app/saved):
  "İçeriğini ❤️ ile beğenince burada toplanır"

Source henüz haberi yok (/admin/sources/{id}/articles):
  "Henüz bu kaynaktan haber çekilmedi.
   Tarama 30 dakikada bir, ilk crawl ~5 dk."
```

### 13.3 Error states

```text
Provider error:
  ┌─────────────────────────────────────┐
  │  ⚠️ Geçici bir sorun                 │
  │  AI provider yanıt vermedi.         │
  │  Tekrar dene? Quota'dan düşmedi.    │
  │  [Tekrar Dene]                      │
  └─────────────────────────────────────┘

Quota exceeded:
  ┌─────────────────────────────────────┐
  │  📊 Bu ayın quota'sı doldu          │
  │  Yenileme: 19 gün sonra             │
  │  Pro tier: 5x daha fazla üretim    │
  │  [Pro'ya Geç] [Yenileme bekle]      │
  └─────────────────────────────────────┘

Network error:
  "Bağlantı sorunu. Internet'i kontrol et."
  [Tekrar Dene]
```

### 13.4 Success states

```text
After save:
  Toast (3sn): "✓ Kaydedildi"
  + İcon değişimi (♡ → ❤️)
  + Optimistic UI (server'dan önce)

After upgrade:
  /app/billing/success
  ┌─────────────────────────────────────┐
  │  🎉 Pro tier aktif!                  │
  │  Comparison mode kullanılabilir.    │
  │  Stil profili oluşturabilirsin.     │
  │  [Hemen Dene →]                     │
  └─────────────────────────────────────┘
```

### 13.5 Confirmation modals

```text
Destructive action (cancel subscription):
  ┌─────────────────────────────────────┐
  │  Aboneliği iptal etmek istediğine    │
  │  emin misin?                         │
  │                                     │
  │  Pro avantajları 2026-05-31 sonuna  │
  │  kadar geçerli kalacak.             │
  │                                     │
  │  Neden ayrılıyorsun?                │
  │  ○ Çok pahalı                       │
  │  ○ Yeterince kullanmıyorum          │
  │  ○ Eksik özellik                    │
  │  ○ Diğer                             │
  │                                     │
  │  [İptal Et]  [Vazgeç]               │
  └─────────────────────────────────────┘
```

---

## 14. Mobile Adaptation (MVP-1: desktop-first)

```text
Yaklaşım:
  - Generate akışı responsive (mobile-friendly)
  - Admin panel desktop-only (sınırlama OK)
  - Stack layout mobile (sidebar collapse → hamburger)
  - Result ekranı: vertical stack (posts → sources)
  - Touch targets ≥ 44px
  - Mobile-specific: copy → native share sheet (Faz 7+)

MVP-1'de mobile native değil, web responsive yeterli.
```

---

## 15. Accessibility (WCAG AA hedef)

```text
- Tüm form input'larda label
- Color contrast ≥ 4.5:1 (text), 3:1 (UI)
- Focus indicator görünür (outline)
- Keyboard navigation full (Tab order)
- ARIA labels (icon buttons)
- Skip-to-content link
- Screen reader friendly headings (h1 → h6 hiyerarşi)
- Loading state aria-live
- Error message aria-describedby

⚠️ Faz 6 öncesi WCAG audit (~5 saat)
```

---

## 16. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Generate akışı sync vs async UI | MVP-1 sync (~6sn OK) | Latency budget |
| D2 | Result ekran layout | Sol post, sağ sources sticky | Güven inşası |
| D3 | Sidebar default | Açık (240px) | Discovery |
| D4 | Mobile priority | Desktop-first MVP, responsive | Persona P1A masa başı |
| D5 | Onboarding tour | Yok MVP-1, Faz 3+ değerlendir | Friction |
| D6 | Empty state copy tonu | Encouraging, actionable | Activation |
| D7 | Insufficient data UX | 3 actionable suggestion | Risk R-PRD-01 mitigation |
| D8 | Selector test ekranı | Real-time preview | Admin operasyonu |
| D9 | Pricing display lokasyon | Pricing page + in-app banner | Conversion |
| D10 | Aha moment metrik | İlk save | Activation |

---

## 17. Çapraz Referans

```text
/app/generate/new             → API §11.1, Prompt Contracts §4
/app/generate/{id}/result     → Aha moment, Metrics §3.4 B5
/admin/sources test-listing   → Risk R-OPS-01, API §4.5
Insufficient data ekranı      → PRD §2.10, Prompt Contracts §3.3
Pro upgrade triggers          → Pricing §4.4
KVKK consent register'da      → Legal §2.3, API §3.1
Robots.txt check admin'de     → Legal §4.2, API §4.1
WSGAU power user              → Metrics §2 (north star)
Brand tone copy               → Design System (sıradaki doc)
Mobile responsive             → Architecture (sonradan)
```

---

**Sonuç:** **8 ana wireframe + 4 journey map + 5 state catalog**. **Generate → Result tek nefeste** (P1A creator iş akışı). **Sources sağ sticky** (güven yapı taşı). **Insufficient data 3 actionable suggestion** (R-PRD-01 mitigation UI). **Selector test ekranı admin operasyonel** (R-OPS-01 mitigation). **MVP-1 desktop-first**, mobile responsive yeterli; admin panel desktop-only kabul. **WCAG AA hedef** Faz 6 öncesi audit zorunlu.
