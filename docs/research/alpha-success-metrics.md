# Closed Alpha Success Metrics — KS-1 Acceptance (Faz 4)

**Issue:** #50
**Versiyon:** v1.0
**Bağlı doküman(lar):** `docs/strategy/success-metrics.md`, `docs/research/alpha-target-criteria.md`, `docs/research/alpha-invite-template.md`

## 1. Amaç

Kapalı alfa programının başarısını ölçecek **KS-1 (Key Success indicator)** seti. 5-10 davetli kullanıcı, 30 gün süre. Bu eşikler ürün karar sürecinin (`go/no-go`) gate'i olarak kullanılır.

KS-1 *acceptance* eşiklerinin altına düşersek MVP-2 (open beta) lansmanını gözden geçiririz; üstüne çıkarsak `docs/strategy/success-metrics.md` Faz 4 hedef trajektorisini yukarı revize edebiliriz.

## 2. KS-1 metrik panosu (5 KPI)

```text
KPI                       Acceptance       Aspirational    Failure
─────────────────────────────────────────────────────────────────
Engagement: weekly        >= %60           >= %80          < %40
   active rate
Quality: halüsinasyon     < %5             < %2            > %10
   raporu (kullanıcı bildirimi)
Retention intent: "kullanmaya  >= %50      >= %70          < %30
   devam ederim" cevabı
Satisfaction: NPS         >= 30            >= 50           < 0
Conversion proxy:         >= %20           >= %40          < %10
   "Aylık 200 TL öder miydim
   ?" Likert >=4
```

Hesap dönemi: 30 günlük alfa süresi sonu (gün 30).

## 3. Metrik tanımları ve hesaplama

### 3.1 Engagement: weekly active rate

```text
Tanım:
  Bir hafta içinde >=1 üretim yapan davetli sayısı / toplam davetli

Hesap (haftalık):
  numerator   = O hafta en az 1 generation oluşturmuş alfa kullanıcısı
  denominator = Aktif (cancel etmemiş) alfa whitelist sayısı

Acceptance:
  Hafta 1: >= %70 (onboarding etkisi)
  Hafta 2: >= %60
  Hafta 3: >= %60
  Hafta 4: >= %60
  4-hafta ortalama: >= %60 (acceptance gate)

Veri kaynağı:
  generations tablosu + alpha_invitations tablosu
```

### 3.2 Quality: halüsinasyon raporu

```text
Tanım:
  Kullanıcının bildirdiği halüsinasyon sayısı / toplam üretim sayısı.

Yakalama:
  - "Halüsinasyon bildir" butonu (üretim ekranında, sağ üst köşe)
  - Haftalık feedback formu Q2 yanıtı
  - Exit interview Bölüm B Soru 6

Acceptance:
  Total reported halu / total generations < %5
  (örn. 200 üretim, en fazla 10 halü raporu)

Aspirational:
  < %2 — `docs/engineering/prompt-contracts.md` §6.6 hedefiyle aynı

Failure:
  > %10 → MVP-2 lansmanı KESİNLİKLE bloklanır;
  prompt revize ve halu trap set'i (#44) güçlendirilir
```

### 3.3 Retention intent: "kullanmaya devam ederim"

```text
Tanım:
  Exit interview / 14. gün formu Q4 yanıtı:
  "Alfa biterken ücretli versiyon olsa kullanmaya devam eder
  misin?" — 1-5 Likert, >=4 sayılır.

Hesap:
  Yanıtı >=4 olan kullanıcı / toplam yanıt veren kullanıcı

Acceptance: >= %50
Aspirational: >= %70
Failure: < %30 → ürün-pazar uyumu yetersiz sinyali
```

### 3.4 Satisfaction: NPS (Net Promoter Score)

```text
Soru:
  "0-10 arası, Nodrat'ı bir arkadaşınıza önerme olasılığınız?"

Hesap:
  NPS = %promoters (9-10) - %detractors (0-6)

Sample size:
  Alfa toplam 5-10 kullanıcı; istatistiksel anlam zayıf,
  ANCAK direksiyonel sinyal olarak kayda alınır.

Acceptance: >= 30
Aspirational: >= 50
Failure: < 0 (negatif NPS — alarmlı)
```

NPS'nin küçük sample'da hassasiyeti zayıf (+1 promoter ~%10 sallar). Bu sebeple NPS *tek başına* karar noktası değil — diğer 4 KPI ile cross-check edilir.

### 3.5 Conversion proxy: ödeme isteği

```text
Soru:
  "Aylık 200 TL olsa Nodrat'a öder miydin?" — 1-5 Likert
  (5 = hemen, 1 = asla)

Hesap:
  Yanıtı >=4 olan kullanıcı / toplam yanıt

Acceptance: >= %20
Aspirational: >= %40
Failure: < %10

Doküman bağı:
  docs/strategy/pricing-strategy.md §3 (Pro tier 199 TL plan)
  Yanıt %20 üstü → pricing onaylanır;
  Altı → pricing review (149 TL'a düşürme analizi)
```

200 TL eşiği `docs/strategy/pricing-strategy.md` Pro tier hedefiyle uyumludur. Conversion *proxy* — gerçek ödeme değil; alfa ücretsiz olduğu için davranışsal değil deklaratif sinyal.

## 4. Toplam karar tablosu (go/no-go)

```text
Sonuç                         Karar
──────────────────────────────────────────────────────────────────
5/5 KPI acceptance             ✅ MVP-2 (open beta) hazır
4/5 KPI acceptance             🟡 MVP-2 başla, eksik KPI'a ek deney
3/5 KPI acceptance             🟠 1 ay closed alpha uzat, prompt
                                  revize + onboarding revize
≤2/5 KPI acceptance             🔴 MVP-2 bloklu — research-findings
                                  güncelle, persona/positioning sor
```

## 5. Cohort takip (haftalık panel)

Alfa süresince haftalık raporlanır:

| Metrik | W1 | W2 | W3 | W4 | Kümülatif |
|--------|----|----|----|----|-----------|
| Active users | 8/10 | 7/10 | 7/10 | 6/10 | — |
| Generations / user | 2.1 | 3.4 | 3.8 | 4.2 | 13.5 |
| Save rate | %35 | %45 | %52 | %58 | %50 |
| Halu reports | 1 | 0 | 2 | 1 | 4 (= %3.0) |
| Source clicks / gen | 1.2 | 1.8 | 2.1 | 2.4 | 1.9 |
| WSGAU equivalent | 0.74 | 1.53 | 1.98 | 2.44 | 1.67 |

(Yukarıdaki rakamlar varsayımsal taban örnek; gerçek veri Selman tarafından haftalık güncellenir.)

WSGAU equivalent `docs/strategy/success-metrics.md` §2.3 alpha hedefi 1.5'e karşılık gelir; kümülatif 1.67 → acceptance üstü.

## 6. Kalitatif sinyaller (sayısal değil ama kayda alınır)

`docs/strategy/success-metrics.md` §8 yöntemiyle uyumlu:

- **"Magic moment" frekansı**: kullanıcının ilk halüsinasyon-sıfır kaynaklı thread'i ürettiği an (kayıt: video / screenshot)
- **Self-explained value cümleleri**: "Nodrat şunu yapıyor:" diye başlayan kullanıcı cümleleri (marketing input)
- **Comparison usage**: en az 3 kullanıcı "geçen ay vs bu ay" özelliğini kendi kendine bulup denemeli (P1B sinyali)
- **Style profile uptake**: en az 2 kullanıcı kendi stil profili yüklemeli (Pro tier value)
- **"Friend referral" istemi**: alfa süresince en az 3 kullanıcı "1 arkadaşımı da davet edebilir miyim?" sorusunu sormalı (organik viral sinyal)

## 7. Risk ve mitigation

| Risk | İhtimal | Etki | Mitigation |
|------|---------|------|------------|
| Sample küçüklüğü → istatistiksel anlam zayıf | Yüksek | Orta | Kalitatif sinyalle cross-check; NPS tek başına karar noktası değil |
| 1-2 power user metrik şişirir | Orta | Yüksek | Median + cohort dağılımı raporla, ortalama yetmez |
| Halü raporu underreport | Orta | Yüksek | Üretim ekranında "halu bildir" butonu görünür konumda |
| Ödeme isteği deklaratif (gerçek değil) | Yüksek | Orta | MVP-2 erken paywall A/B testi planla |
| Alpha drop-off (haftalık aktif düşüşü) | Orta | Yüksek | Hafta 2 sonu 1:1 check-in mecbur, friction noktaları kapat |

## 8. Versiyon kaydı

| Versiyon | Tarih | Değişiklik |
|----------|-------|------------|
| v1.0 | 2026-05-01 | İlk yayın — KS-1 acceptance eşikleri (#50) |

---

**Bağlı dokümanlar:**
- `docs/strategy/success-metrics.md` — WSGAU + KPI ağacı
- `docs/strategy/pricing-strategy.md` — fiyat noktası
- `docs/research/alpha-target-criteria.md` — kullanıcı seçimi
- `docs/research/alpha-invite-template.md` — feedback formu
- `docs/research/alpha-invite-checklist.md` — operasyon
