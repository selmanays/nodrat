# Nodrat — Tasarım Sistemi ve Marka Tonu

**Doküman türü:** Design System & Brand Voice Guide
**Sürüm:** v0.1
**Bağımlılık:** PRD §6 (shadcn/ui), IA §11 (komponent hiyerarşisi), Discovery (P1A persona), Competitive §5.3 (marka tonu), UX Wireframes (state catalog), Pricing (in-app messages)
**Hedef:** Görsel kimlik, voice & tone, copy guidelines, komponent token'ları ve "veri yetersiz" gibi negatif mesajların standart formülü.

⚠️ **Notasyon:** Bu doküman Figma/Storybook için **kanonik kaynak**. Komponent implementasyonu shadcn/ui üzerinden, token'lar Tailwind config'inde.

---

## 0. Yönetici Özeti

```text
Marka kimliği özet:
  Persona:      "Sakin, kaynaklı, profesyonel araç"
  Mood:         Editor odaklı, AI hype'sız, veri-merkezli
  Renk:         Mat lacivert + sıcak amber (vurgu)
  Tipografi:    Inter (UI) + Source Serif 4 (uzun metin)
  Voice:        Mütevazı uzman; data-driven; Türkçe doğal

Voice & tone (3 kelime):
  Sade · Kaynaklı · Sakin

Copy yapı kuralları:
  - Üretici cümleler ("Üret", "Kaydet"), buyurgan değil
  - "AI" kelimesi sınırlı (overuse anti-pattern)
  - Hata mesajları kullanıcıyı suçlamaz
  - Negatif durumlar (yetersiz veri, kota dolu) actionable

Komponent kütüphanesi:
  - shadcn/ui (Radix primitives) — temel layer
  - 12 atom + 18 molecule + 9 organism (IA §11.1)
  - Tailwind tokens dinamik (light/dark)
  - Storybook her komponent için story
```

---

## 1. Marka Kimliği

### 1.1 Marka kişiliği (persona)

```text
Nodrat'ın bir kişiliği olsa: 
  35 yaşlarında, yorgun olmayan, kaynaklarını bilen,
  okumuş, sakin tonlu, gereksiz hype yapmayan, 
  hızlı düşünen ama acele etmeyen bir EDİTÖR.

Marka framing (research-driven, 2026-05-01):
  "Editör odaklı üretim aracı"
  Nodrat AI writer DEĞİL — workflow aracı.
  Kaynak + doğrulama + hız üçlüsü editör hassasiyeti taşır.

NE DEĞİL:
  - Genç tech-bro AI evangelist DEĞİL ("revolutionary!", "10x!")
  - Soğuk kurumsal DEĞİL (Bloomberg gibi sterilize değil)
  - Influencer hype'lı DEĞİL (rocket emoji yok)
  - Aşırı resmi DEĞİL (siz/efendim formatı yok)
  - "AI writer" / "tweet generator" DEĞİL (research'te kaçınıldı)
```

### 1.2 Marka değerleri

```text
V1. Doğruluk öncelikli
    "Halüsinasyonsuz, kaynaklı çıktı verir."

V2. Mütevazı uzmanlık
    "Yapabildiğini söyler, yapamadığını gizlemez."

V3. Editör hassasiyeti
    "Kaynağı, tarihi, ifadeyi kontrol eder."

V4. Yaratıcıya hizmet
    "Creator'ın işine engel değil, yardımcı."

V5. Yerel + güncel
    "Türkçe gündem hızlı ve doğru."
```

### 1.3 Marka cümleleri (örnekler)

```text
✓ İYİ:
  "Bu paylaşım için 3 kaynak kullanıldı."
  "Veri yetersiz. Zaman aralığını genişletmek ister misin?"
  "Pro tier ile comparison mode'a geç."
  "Kaynaklı içerik, hızlı üretim."

✗ KÖTÜ:
  "AI-powered Türkiye'nin ilk akıllı içerik üretim platformu! 🚀"
  "Revolutionary RAG technology unlocks creator productivity"
  "Hata oluştu. Lütfen tekrar deneyiniz."
  "Üyeliğiniz için teşekkürler!" (mesafeli)
```

---

## 2. Görsel Kimlik

### 2.1 Renk paleti

```text
PRIMARY — Mat Lacivert (Kuzey Yıldızı)
  Brand-50:   #F0F4F8     (en açık, background)
  Brand-100:  #D9E2EC
  Brand-300:  #829AB1
  Brand-500:  #486581    (orta, secondary text)
  Brand-700:  #243B53    (button, link)
  Brand-900:  #102A43    (headings, dark text) ← marka rengi
  Brand-950:  #0A1F33    (dark mode bg)

ACCENT — Sıcak Amber (vurgu, CTA)
  Accent-50:  #FFF8E1
  Accent-100: #FFECB3
  Accent-300: #FFD54F
  Accent-500: #FFA000    ← marka vurgu (sınırlı kullanım)
  Accent-700: #FF6F00
  Accent-900: #E65100

NEUTRAL — Soğuk Gri (yapısal)
  Neutral-50:  #FAFAFA
  Neutral-100: #F5F5F5
  Neutral-300: #D4D4D4
  Neutral-500: #737373
  Neutral-700: #404040
  Neutral-900: #171717

SEMANTIC
  Success:  #10B981      (yeşil, kayıt + başarı)
  Warning:  #F59E0B      (sarı, kota uyarı)
  Error:    #EF4444      (kırmızı, error)
  Info:     #3B82F6      (mavi, bilgilendirme)

Kullanım yüzdesi (heuristic):
  Brand:    ≈%70 (yapısal)
  Neutral:  ≈%20 (text, border)
  Accent:   ≈%5  (sadece CTA + brand moment)
  Semantic: ≈%5  (state göstergesi)
```

### 2.2 Tipografi

```text
UI font (sans-serif):
  Inter (variable, OFL lisans)
  Türkçe karakter desteği tam
  Weights: 400, 500, 600, 700

Long-form font (serif, opsiyonel):
  Source Serif 4 (sadece result panel'de uzun summary için)
  Weights: 400, 600

Monospace (kod, ID):
  JetBrains Mono
  Weights: 400, 500

Type scale (Tailwind ölçüleri):
  text-xs:    12px / 16px line-height   (caption, meta)
  text-sm:    14px / 20px               (body)
  text-base:  16px / 24px               (default body)
  text-lg:    18px / 28px               (subhead)
  text-xl:    20px / 28px               (h4)
  text-2xl:   24px / 32px               (h3)
  text-3xl:   30px / 36px               (h2)
  text-4xl:   36px / 40px               (h1)
  text-5xl:   48px / 1                  (hero, pricing)

Heading hiyerarşisi:
  h1 — text-4xl, brand-900, font-semibold (sayfa başlığı, tek)
  h2 — text-3xl, brand-900, font-semibold (section)
  h3 — text-2xl, brand-700, font-medium  (subsection)
  h4 — text-xl,  brand-700, font-medium  (card başlık)

Body text:
  Default: text-base, neutral-900 (light) / neutral-100 (dark)
  Secondary: text-sm, neutral-500
  Caption: text-xs, neutral-500

Türkçe-spesifik:
  - "I" ve "İ" ayrımı font'ta korunur (Inter destekler)
  - Tireleme: text-balance (heading), text-pretty (paragraph)
  - Punctuation TR style ("...", «...», prefer)
```

### 2.3 Spacing & layout

```text
Tailwind defaults kullanılır:
  px-2:  8px    (sıkı içerik)
  px-3:  12px   (form)
  px-4:  16px   (default)
  px-6:  24px   (card padding)
  px-8:  32px   (section)

Border radius:
  rounded-md:  6px    (input, button)
  rounded-lg:  8px    (card)
  rounded-xl:  12px   (modal)
  rounded-2xl: 16px   (hero card)
  rounded-full      (avatar, badge)

Shadow:
  shadow-sm:    subtle (sticky)
  shadow-md:    card
  shadow-lg:    modal
  shadow-2xl:   hero / focused

Border:
  border-neutral-200 (light), neutral-800 (dark)
  border-1 default
  border-2 only for focus / active
```

### 2.4 Iconography

```text
Library: lucide-react (open-source, tutarlı stil)
Stroke width: 1.5 (default Lucide), tüm iconlarda eşit

İcon boyutları:
  size-4:  16px (inline, badge içinde)
  size-5:  20px (button içinde)
  size-6:  24px (default)
  size-8:  32px (hero, empty state)

İcon kullanım kuralları:
  - Decorative ikon yok (her ikon anlam taşır)
  - Aksiyon ikonu yanında label (icon-only sadece toolbar'da)
  - Status ikon: ● yeşil (ok), ▲ sarı (warn), ✕ kırmızı (error)

Marka ikonu:
  Logomark: stilize "n" + nokta (•) — minimal
  Wordmark: "Nodrat" Inter Bold lacivert
  Favicon: 32x32, 16x16, sadece logomark
```

### 2.5 Dark mode

```text
Default: System preference
Toggle: User settings'de override
Strategy: CSS variables + Tailwind dark: prefix

Light mode:
  bg:    neutral-50 / white
  text:  neutral-900
  card:  white + shadow

Dark mode:
  bg:    brand-950 / neutral-900
  text:  neutral-100
  card:  brand-900 + subtle border

Renk semantik dark mode'da:
  - Accent (amber) parlaklık aynı (kontrast korunur)
  - Brand renkleri %20-30 daha açık variant
  - Semantic renkler %15 desat (göz yorgunluğu)
```

---

## 3. Voice & Tone

### 3.1 Voice prensipleri (her zaman aynı)

```text
P1. Sade
    Cümle kısa. 15 kelimeyi geçme.
    "Veri yetersiz" — "Veri yetersizliği nedeniyle üretim yapılamamıştır" değil.

P2. Kaynaklı
    Sayı, kaynak, belge varsa belirt.
    "5 kaynaktan üretildi" > "Kapsamlı şekilde üretildi"

P3. Sakin
    Acele yok. Heyecan yok. Sürpriz yok.
    "Yenileme 19 gün sonra" > "Acele et!"

P4. Mütevazı uzman
    Bilmediğini saklama.
    "Bu konu için yeterli kaynak yok." (eksik veri açık)

P5. Aksiyon-odaklı
    Her negatif durumda 1-3 öneri.
    "Yetersiz" + [Genişlet] [Yeni dene] [Pro'ya geç]
```

### 3.2 Tone (bağlama göre değişir)

```text
Bağlam              Tone                Örnek
──────────────────────────────────────────────────────────────────────
Onboarding/welcome  Sıcak, mütevazı     "Hoş geldin, Mete."
Generation result   Profesyonel, açık   "Bu üretim 5 kaynak kullandı."
Veri yetersiz       Bilgilendirici      "Veri yetersiz. Şunları dene:"
Hata (bizim)        Sorumlu, çözüm-odaklı "Geçici bir sorun. Tekrar dene."
Hata (kullanıcı)    Yumuşak, açıklayıcı "Bu istek için yeterli karakter yok."
Quota dolu          Sakin, bilgilendirici "Bu ayın quota'sı doldu."
Upgrade CTA         Direkt, faydaya dayalı "Pro: 5x daha fazla üretim"
Cancellation        Saygılı, geri kazanma yok  "Aboneliği iptal edildi."
Legal               Resmi ama anlaşılır "KVKK kapsamında bilgilendiririz."
```

### 3.3 Yapılması ve yapılmaması gerekenler

```text
✓ YAP:
  - Kullanıcıyı sen-sen kullan ("Bu üretimi kaydet")
  - Action verb'le başla ("Üret", "Kaydet", "Kontrol et")
  - Sayı + kaynak göster ("5 kaynak", "47 üretim")
  - Empati durumunda göster ("Veri yok" değil, "yeterli veri yok")
  - Türkçe pronoun (sen) — siz değil (B2C ürün, samimi)

✗ YAPMA:
  - Aşırı emoji ("Üret 🚀✨🎉" değil)
  - Cesur claim ("dünyanın en iyi" yok)
  - Kullanıcıyı suçlama ("Geçersiz girdi" değil "Bu istek anlaşılmadı")
  - Ünlem fazla (max 1 / paragraf)
  - "AI" overuse (her cümle değil)
  - Hashtag suggestion'da AI hype kelimeler (#yapayzeka değil)
```

### 3.4 Türkçe doğallık kuralları

```text
- "Üye ol" > "Kayıt ol" (samimi)
- "Üretim" > "İçerik üretimi" (gereksiz uzunluk yok)
- "Tekrar dene" > "Yeniden deneyiniz" (formal değil)
- "Ödeme" > "Tahsilat" (KVKK ödeme demese de, B2C)
- "Kaynaklar" > "Referanslar" (akademik değil)
- "Yenileme" > "Tahsilat dönemi" (yumuşak)
- Slang yok ("acayip", "bayağı" değil)
- İngilizce karışım minimum ("dashboard" → "ana panel" gerekirse)
- Marka adı her zaman büyük: Nodrat
```

### 3.5 Dil seviyesi (CEFR)

```text
Hedef: B1-B2 (orta seviye Türkçe okuyucu)
Cümle: 12-15 kelime ortalama
Paragraf: 3 cümle max
Avoid: jargon, akademik dil, hukuki terim

Yasal sayfalarda B2-C1 (zorunlu yasal dil):
  - /legal/* sayfalarında resmi dil OK
  - Ama özet/highlight'lar B1 dilinde
```

---

## 6. Komponent Sistemi

### 6.1 Atom seviyesi (12 komponent)

```text
Button
  Variants: default, primary (accent), secondary, ghost, destructive, link
  Sizes: sm, default, lg, icon-only
  States: default, hover, active, disabled, loading

Input
  Variants: default, error
  Types: text, email, password, number, search
  States: default, focus, error, disabled, readonly
  
Textarea
  autoResize, maxLength, char counter

Select (Radix)
  Native + custom (search, multi)

Checkbox / Radio
  Default + indeterminate

Switch
  Default + with label position

Badge
  Variants: default, success, warning, error, info
  Sizes: sm, default

Avatar
  Image / Initials fallback
  Sizes: sm (24), default (32), lg (48), xl (64)

Spinner
  Sizes: sm, default, lg
  Inline + standalone

Tooltip (Radix)
  Side: top, right, bottom, left
  Delay: 500ms default

Toast (sonner)
  Variants: success, error, info, warning
  Duration: 3s default, 5s error

Tag / Chip
  Closable opsiyonel
  Color variants
```

### 6.2 Molecule seviyesi (18 komponent)

```text
SearchBar           — input + icon + clear
FormField           — label + input + helper text + error
StatCard            — value + delta + icon + label (dashboard)
SourceRow           — admin source list item
JobRow              — admin queue item with status
GenerationCard      — geçmiş üretim kartı
CitationLink        — kaynak link (title + source + date)
FreshnessBadge      — taze/orta/eski göstergesi (renk kodlu)
ConfidenceMeter     — extraction confidence görsel meter
TimeModeSelector    — current/weekly/archive/comparison segmented
ToneSelector        — dropdown (8 ton)
QuotaBar            — kullanım progress bar (header'da)
EmptyState          — icon + title + description + CTA
ErrorBoundary       — fallback UI
LoadingState        — skeleton + spinner + progress
PaywallModal        — feature kilitli + upgrade CTA
ConfirmModal        — destructive action confirmation
NotificationToast   — sonner wrapper, brand styled
```

### 6.3 Organism seviyesi (9 komponent)

```text
Sidebar             — collapsible nav (user + admin variants)
Topbar              — logo + search + quota + user menu
DataTable           — sortable, filterable, paginated
FilterPanel         — admin source/article filter
KanbanQueue         — admin queue overview (visual)
SelectorTester      — admin selector test ekranı (UX §4)
AgendaCardPreview   — RAG ekranlarında agenda card görsel
GenerationResultPanel — wireframe §3'teki output paneli
ImageLabelEditor    — Faz 4 image labeling UI
```

### 6.4 Template seviyesi

```text
AdminListLayout     — sidebar + filter + list (sources, articles)
AdminDetailLayout   — sidebar + breadcrumb + tabs + content
UserDashboardLayout — sidebar + topbar + content
GenerationLayout    — split: input (sol) | result (sağ)
PublicLayout        — minimal nav + content + footer
AuthLayout          — center card + branding
```

---

## 5. Copy Library

### 5.1 Standart microcopy

```text
Buttons (action verbs):
  ✓ "Üret"            "Kaydet"            "İptal Et"
  ✓ "Devam Et"         "Geri"              "Tekrar Dene"
  ✓ "Onayla"           "Sil"               "Reddet"
  ✓ "Hesabı Aç"       "Giriş Yap"         "Çıkış Yap"

Loading states:
  "Üretiliyor..."           (generation)
  "Yükleniyor..."           (page load)
  "Kaydediliyor..."         (form submit)
  "Kaynaklar getiriliyor..."(retrieval)

Success:
  "✓ Kaydedildi"
  "✓ Üretildi"
  "✓ Hesap oluşturuldu"
  "✓ Email gönderildi"

Confirmation:
  "Emin misin?"
  "Bu işlem geri alınamaz."
  "[Sil]  [Vazgeç]"
```

### 5.2 Hata mesaj formülü

```text
Şablon (3 parça):
  1. NE OLDU (kısa, sebep)
  2. ETKİSİ (kullanıcı için ne demek)
  3. NE YAPILABILİR (1-3 aksiyon)

✓ İYİ:
  "Veri yetersiz.
   Bu konu için seçilen dönemde yeterli kaynak yok.
   [Zaman aralığını genişlet] [Yeni konu dene] [Tekrar dene]"

✓ İYİ:
  "Bağlantı sorunu.
   Internet bağlantını kontrol et.
   [Tekrar Dene]"

✗ KÖTÜ:
  "Hata oluştu. Tekrar deneyiniz."
  "Geçersiz girdi"
  "ERROR_CODE_5XX"
```

### 5.3 Insufficient data — STANDART MESAJ

```text
PRD §2.10 + Risk Register R-PRD-01 mitigation UX:

┌───────────────────────────────────────────────────┐
│  ⚠️ Veri yetersiz                                  │
│                                                   │
│  Bu konu için seçilen dönemde yeterli güvenilir   │
│  haber verisi bulunamadı.                          │
│                                                   │
│  Bulduğumuz: [N] kaynak, [M] gündem kartı          │
│  Gereken: en az 2 gündem kartı VEYA 3 haber        │
│                                                   │
│  Şunları deneyebilirsin:                          │
│  ⏱️  [Zaman aralığını genişlet]                    │
│  🔍 [Konuyu daha geniş yaz]                        │
│  🔄 [Yeni bir konu dene]                           │
│                                                   │
│  Bu üretim quota'ndan DÜŞÜLMEDİ.                  │
└───────────────────────────────────────────────────┘

KEY POINTS:
- "Hata" değil "yetersiz" (kullanıcıyı suçlamıyor)
- Sayı transparent (kaç bulduk, kaç gerekli)
- 3 actionable suggestion
- "Quota'ndan düşmedi" güven cümlesi
```

### 5.4 Quota uyarıları

```text
%50 (sessiz):
  Quota: 50/100 (header'da gösterilir, ek mesaj yok)

%70 (soft):
  "Bu ay 30 üretim hakkın kaldı."
  (Banner, dismiss edilebilir)

%90 (medium):
  "Bu ay 10 üretim kaldı.
   Pro tier ile 5x daha fazla."
  [Pro'ya Geç] [Anladım]

%100 (block):
  "Bu ay quota'sı doldu.
   Yenileme: 19 gün sonra.
   Pro tier 500/ay sunar."
  [Pro'ya Geç] [Yenileme bekle]
```

### 5.5 Upgrade CTA mesajları

```text
Free → Starter:
  "Daha çok üretim için Starter tier (249 TL/ay)
   100 üretim/ay, archive mode, X thread"

Starter → Pro:
  "Pro ile comparison mode + stil profili (749 TL/ay)
   500 üretim/ay, görsel destekli içerik"

Pro → Agency:
  "Ekipler için Agency tier (2.499 TL/ay, 3 koltuk)
   2.500 üretim/ay, premium model"

Yıllık iskonto vurgusu:
  "Yıllık öde, 2 ay bedava al."
  ✗ Yapma: "%16.7 iskonto" (matematik soğuk)
```

### 5.6 KVKK ve legal copy

```text
Register form:
  "Üyelik koşullarını ve gizlilik politikasını kabul ediyorum."
  
  "İçeriğimin AI provider'larına gönderilmesini onaylıyorum
   (yurt dışı veri transferi için açık rıza)."

Cookie banner:
  "Nodrat zorunlu çerezleri kullanır. Analytics ve pazarlama
   çerezleri opsiyoneldir."
  [Sadece zorunlu] [Hepsini kabul et] [Detaylar]

Data export:
  "Tüm verilerini JSON olarak indirebilirsin.
   Hazırlama 1-2 saat sürebilir, email ile bildirilecek."

Account delete:
  "Hesabını siliyorsun. 30 gün boyunca soft-delete'te kalır,
   sonra kalıcı silinir. Kayıtlı üretimler de silinir."
  [Sil]  [Vazgeç]
```

---

## 7. Komponent Tokens (CSS variables)

```css
/* Tailwind config'inde tanımlanır */

:root {
  /* Color tokens */
  --color-bg:           oklch(0.98 0.005 250);   /* neutral-50 */
  --color-bg-elevated:  oklch(1.00 0 0);          /* white */
  --color-text:         oklch(0.25 0.02 250);    /* brand-900 */
  --color-text-muted:   oklch(0.50 0.03 250);    /* neutral-500 */
  --color-border:       oklch(0.92 0.01 250);    /* neutral-200 */
  
  --color-brand:        oklch(0.30 0.04 250);    /* brand-700 */
  --color-accent:       oklch(0.75 0.15 70);     /* amber-500 */
  --color-success:      oklch(0.65 0.15 150);
  --color-warning:      oklch(0.75 0.15 75);
  --color-error:        oklch(0.65 0.20 25);
  
  /* Spacing */
  --radius-sm:          6px;
  --radius-md:          8px;
  --radius-lg:          12px;
  
  /* Shadow */
  --shadow-sm:  0 1px 2px rgba(0,0,0,0.05);
  --shadow-md:  0 4px 6px -1px rgba(0,0,0,0.1);
  --shadow-lg:  0 10px 15px -3px rgba(0,0,0,0.1);
  
  /* Typography */
  --font-sans:  'Inter', system-ui, sans-serif;
  --font-serif: 'Source Serif 4', serif;
  --font-mono:  'JetBrains Mono', monospace;
}

[data-theme="dark"] {
  --color-bg:           oklch(0.18 0.02 250);    /* brand-950 */
  --color-bg-elevated:  oklch(0.25 0.02 250);    /* brand-900 */
  --color-text:         oklch(0.95 0.01 250);    /* neutral-100 */
  --color-text-muted:   oklch(0.65 0.02 250);    /* neutral-400 */
  --color-border:       oklch(0.30 0.02 250);
  /* Diğer renkler accent dahil aynı (kontrast koruması) */
}
```

---

## 8. Animation & Motion

```text
Prensip: az ama anlamlı
Süre default: 150-250ms (UI feedback)
Easing: cubic-bezier(0.4, 0, 0.2, 1) (Tailwind ease-in-out)

Geçişler:
  - Hover: 150ms color/bg
  - Modal open: 200ms scale + fade
  - Toast slide: 250ms slide-in
  - Skeleton pulse: 1500ms infinite
  - Loading spinner: continuous

Reduced motion:
  prefers-reduced-motion: reduce → tüm geçişler 0ms
  Skeleton pulse → static
  Spinner → minimal hareket

Page transitions:
  Yumuşak fade-in (150ms)
  Sticky header parallax YOK (gereksiz)
```

---

## 9. Accessibility (WCAG AA)

```text
Min standartlar:
  - Color contrast 4.5:1 (text), 3:1 (UI)
  - Tüm interactive element keyboard erişilebilir
  - Focus indicator görünür (outline, 2px)
  - ARIA labels icon-only buttons
  - Form input → label association
  - Error message → aria-describedby
  - Loading state → aria-live="polite"
  - Modal → focus trap, ESC kapatır

Renk-bağımsız iletişim:
  Status badges renk + icon + text
  Form error: ikon + renk + mesaj

Türkçe screen reader:
  Test: NVDA + Türkçe SAPI
  HTML lang="tr" zorunlu
  Heading hierarchy düzgün (h1→h6)

Keyboard shortcuts (öğrenmesi kolay):
  ⌘+Enter   — Generate (form'da)
  ⌘+S       — Kaydet
  ⌘+/       — Search
  ESC       — Modal/dropdown kapat
  Tab/Shift+Tab — Form navigasyon

⚠️ Faz 6 öncesi formal WCAG audit (Wireframes §15 ile uyumlu).
```

---

## 10. Storybook Strateji

```text
Her atomik komponent için:
  - Default story
  - Variant stories (size, color, state)
  - Interactive story (state değişimi)
  - Accessibility addon (a11y check)

Her organism için:
  - Default + edge case stories
  - Empty state
  - Loading state
  - Error state
  - With long content (overflow test)

Documentation:
  - Description
  - Props table
  - Usage do/don't örnekleri
  - Code snippet
  - Accessibility notes

Storybook deploy:
  - Staging environment
  - Designer + dev paylaşır
  - Visual regression (Chromatic opsiyonel)
```

---

## 11. Brand Asset Library

```text
Logo varyantları:
  /assets/logo/
    nodrat-mark.svg          (icon-only, square)
    nodrat-wordmark.svg      (text)
    nodrat-full.svg          (mark + wordmark, horizontal)
    nodrat-stack.svg         (mark + wordmark, vertical)
    nodrat-mono-light.svg    (white version)
    nodrat-mono-dark.svg     (dark version)

Favicon:
  favicon.ico (32x32 + 16x16)
  apple-touch-icon.png (180x180)
  manifest.json (PWA hazır)

Open Graph + Twitter:
  /assets/og/
    og-default.png  (1200x630)
    og-pricing.png  (pricing sayfası özel)
    og-result.png   (paylaşım için template)

İllüstrasyon:
  Stil: minimal, line-based, brand renk paleti
  Library: undraw.co (free) + custom (Faz 6+)
  Empty state'lerde tutarlı kullanım

Photography:
  Stock yok (jenerik AI/laptop görselleri kaçın)
  Custom screenshot'lar product page'de
```

---

## 12. Marketing Channel Tonları

```text
Twitter/X (kendi hesabımız):
  Tone: Profesyonel + ara sıra ironi
  Format: Kısa, sayısal, kaynaklı
  Frequency: 3-5 / hafta
  Hashtag: minimum (#TR_AI gibi spam değil)

Email (transactional):
  Format: Düz metin + minimal HTML
  Marka: footer'da logo + 1 cümle
  Tone: Sade, bilgilendirici
  Subject: 30-50 char, açıklayıcı

Email (newsletter, opsiyonel Faz 6+):
  Frequency: Aylık max
  Konu: Ürün haberleri + creator ipuçları
  Unsubscribe: 1-tıklama

Landing page:
  Headline: problem → çözüm formülü
  Sub: somut sayı (50+ kaynak, 10K+ üretim)
  CTA: tek primary, alternatif secondary

Blog (Faz 6+):
  Konular: creator workflow, gündem analizi, AI etiği
  Format: 800-1500 word, kaynaklı
  SEO: hafif (forced keyword yok)
```

---

## 13. Referans ve Inspiration

```text
İlham (DEĞİL kopyala):
  - Linear (komponent, tipografi)
  - Vercel (boşluk, sadelik)
  - Anthropic site (mütevazı tone)
  - Substack (publishing-friendly UX)
  - Things 3 (microcopy)

Kaçın:
  - Hubspot (over-formal B2B)
  - "Generic AI startup" (gradient orgy, 3D objects)
  - Bloomberg/Reuters (steril, kurumsal)
  - Crypto/web3 (hype dili)
```

---

## 14. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Komponent kütüphanesi | shadcn/ui (Radix + Tailwind) | Olgun, customizable |
| D2 | Sans serif font | Inter | TR karakter + variable |
| D3 | Marka rengi | Mat lacivert (brand-900) + amber accent | Sakin + canlı |
| D4 | Dark mode | Day 1'den itibaren | Modern beklenti |
| D5 | İkon kütüphanesi | lucide-react | Tutarlı stil |
| D6 | Voice tonalité | Sade · Kaynaklı · Sakin | 3 kelime özet |
| D7 | "Sen" mi "Siz" mi? | Sen (B2C samimi) | TR doğal |
| D8 | Storybook deploy | Staging | Tasarımcı paylaşımı |
| D9 | Animation süre | 150-250ms | Hızlı + algılanabilir |
| D10 | WCAG hedef | AA Faz 6 öncesi audit | Zorunlu min |

---

## 15. Çapraz Referans

```text
Komponent tokens          → Architecture §11.2 (shared-types)
Insufficient data copy    → PRD §2.10, Prompt Contracts §3.3, UX §3.1
Quota uyarıları           → Pricing §4.3, UX §13.2
KVKK consent copy         → Legal §2.3, API §3.1, UX §7
Marka tonu                → Competitive §5.3, Discovery (P1A)
Dark mode tokens          → CSS variables setup
WCAG audit                → UX §15, Faz 6 pre-launch
Storybook                 → Architecture klasör yapısı
İcon size standartları    → IA §11.1 atom seviyesi
"Sen" pronoun (TR)        → Tüm copy tutarlılık kuralı
```

---

**Sonuç:** Marka **mat lacivert + amber accent**, **Inter** UI font, **Sade · Kaynaklı · Sakin** voice. Komponent altyapısı **shadcn/ui (Radix + Tailwind)** üzerine kurulu, **dark mode day-1**, **WCAG AA hedef**. **Insufficient data UX'i** kullanıcıyı suçlamayan + 3 actionable suggestion formülünde. **Quota uyarıları %50/70/90/100** kademeli, sürpriz yok. Marka tonu **AI hype'sız mütevazı uzman**; Türkçe **B1-B2** seviyesinde, "sen" pronoun B2C samimi ürün için.
