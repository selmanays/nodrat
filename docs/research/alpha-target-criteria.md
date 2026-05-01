# Closed Alpha Hedef Kullanıcı Kriterleri (Faz 4)

**Issue:** #50
**Versiyon:** v1.0
**Bağlı doküman(lar):** `docs/validation/research-findings.md` §3, `docs/strategy/discovery-validation.md`, `docs/research/alpha-invite-template.md`

## 1. Amaç

Bu doküman 5-10 kişilik kapalı alfa programı için kullanıcı seçim kriterlerini tanımlar. Hedef: P1A (bağımsız politik creator) primer + P1B (sosyal medya ajansı) secondary segmentlerinde *production-grade* kullanım sinyali toplamak.

`docs/validation/research-findings.md` §3'te onaylanan persona profillerine sadık kalır; alfa whitelist bu kriterlere uyan adaylardan oluşur. Kayıt süresi 30 gün, davet sayısı maksimum 10 (alt sınır 5).

## 2. Persona dağılımı (alfa kompozisyonu)

```text
Toplam:                           5-10 kişi (whitelist)

  P1A — Bağımsız politik creator      4-6 kişi  (primer ağırlık)
  P1B — Sosyal medya ajansı yöneticisi 1-2 kişi (secondary, ajans seat)
  P2A — Yorumcu/akademisyen            0-1 kişi (validation gap)
  P3  — Bağımsız yazar/editor          0-1 kişi (P1A komşu profili)

Süre:                             30 gün (1-30 Mayıs 2026)
Erişim:                           Pro tier ücretsiz (whitelist token)
```

P1A ağırlığı `docs/validation/research-findings.md` Karar §3.3'ten geliyor: primer persona MVP-1 odağı, alfa için de "satın alma cümlesi onaylı" segment.

## 3. Persona detay kriterleri

### 3.1 P1A — Bağımsız politik creator (primer)

**Onaylanan profil (`docs/validation/research-findings.md` §3.1)**

- Sosyal medyada Türkçe gündem üzerine düzenli üretim yapan bağımsız hesap (X / LinkedIn / Substack / kişisel blog)
- Takipçi sayısı 5K-100K arası — kurumsal değil, kişi markası
- Aylık 10-50 üretim (X paylaşımı + thread + zaman zaman analiz)

**MUST kriterler (alfa kabul için)**

| Kriter | Eşik | Doğrulama |
|--------|------|-----------|
| Türkçe içerik üretim sıklığı | Haftada en az 3 paylaşım | Profilden gözlem |
| Aktif kullanılan kaynak sayısı | 4-7 (manuel) | Görüşmeden onay |
| ChatGPT Plus aboneliği | Var (workaround sinyal) | Görüşmeden onay |
| Halüsinasyon hassasiyeti | "Yanlış bilgi paylaştığım takipçi kaybeder" | Görüşmeden cümle |
| 30 gün katılım taahhüdü | Sözlü onay | Davet emaili cevabı |

**SHOULD kriterler (öncelik avantajı)**

- "Sabah brifi" 10 dk pattern'inde olan (research §3.1 onaylı)
- Comparison ("geçen ay vs bu ay") kullanım eğilimi gösteren
- Halu / kaynak güvensizliği daha önce tweet atmış (sinyal: gerçek acı)

### 3.2 P1B — Sosyal medya ajansı yöneticisi (secondary)

**Onaylanan profil (`docs/validation/research-findings.md` §3.2)**

- Müşteri portföyü 3-10 marka olan küçük-orta ajans (kurucu veya senior strateji)
- Junior ekiple çalışıyor; tutarsız çıktı sorunu yaşıyor
- Pazar gecesi kaynak tarama disiplini var

**MUST kriterler**

| Kriter | Eşik | Doğrulama |
|--------|------|-----------|
| Aktif marka sayısı | En az 3 | Şirket profili |
| Junior ekipte 2+ kişi | Var | Görüşmeden onay |
| Multi-seat ihtiyacı | Var (research §3.2 B3) | Görüşmeden cümle |
| Müşteri tonu standardizasyonu acısı | Onay | Görüşmeden cümle |
| 30 gün taahhüt | Sözlü onay | Davet emaili cevabı |

**SHOULD kriterler**

- "Müşteri sunumu için kaynaklı rapor" use-case'i ifade etmiş
- Style profile (per-brand 3+) ile ilgilenen
- Takip ettiği ChatGPT'nin "marka tonunu kaybetmesi" şikayeti kayda geçmiş

### 3.3 P2A — Yorumcu/akademisyen (validation gap)

`docs/validation/research-findings.md` §3.3'te "test sample yetersiz" işaretli. Alfa fırsat: 1 kişi davet edip persona doğrulama sample'ı genişlet.

**Profil:** Akademisyen + köşe yazarı + podcast yapımcısı; haftalık analitik üretim. Halü hassasiyeti çok yüksek (akademik itibar).

### 3.4 P3 — Bağımsız yazar/editor (komşu)

P1A profilinin uzantısı; yayın organlarında editör/araştırmacı rolü. Genelde "haber özetleme + kontekst yazma" use-case ağırlıklı.

## 4. Davet havuzu kaynakları

```text
Kaynak                              Beklenen aday  Conversion %
──────────────────────────────────────────────────────────────
Kişisel network (Selman'ın listesi)       12-15        ~50%
LinkedIn outreach (P1B ağırlık)             8-10       ~30%
X DM kampanyası (P1A profil)               15-20       ~25%
Discovery interview kalanları
   (research-findings'teki onay verenler)   5-8        ~70%
──────────────────────────────────────────────────────────────
Toplam adaylar:                            40-53
Hedef yanıt:                               12-18
Kabul:                                     5-10
```

Outreach öncelik sırası: discovery interview onay verenler → kişisel network → LinkedIn → X DM.

## 5. Diversity (çeşitlilik) gereklilikleri

`docs/validation/research-findings.md` örneklem dengesizliklerini telafi için zorunlu:

| Eksen | Hedef dağılım |
|-------|---------------|
| Cinsiyet | En az 3 farklı cinsiyetten 1+ kişi |
| Coğrafya | En az 2 ayrı şehir (İstanbul + 1) |
| Yaş aralığı | 22-50 arası, en az 3 farklı kohort |
| Politik yönelim | Çeşitli — tek bir kümeden değil |
| Aylık üretim hacmi | Az (10-15) + orta (16-30) + yoğun (31+) karışık |

## 6. Red flag (alfaya alınmayacak profiller)

Aşağıdaki sinyaller davet öncesi *blokerdir*:

- "Bot ile gündem manipülasyonu" geçmişi (etik ve yasal risk; `docs/legal/threat-model.md`)
- Doğrulanmamış iddiayı X'te yaymış kullanıcı (halü riski yüksek; deney bozar)
- KVKK uyumsuz veri saklama isteği (örn: "ben kendi DB'me indireyim")
- Ücretsiz hizmet karşılığında "yorum / sosyal medya postu" beklentisi (içerik manipülasyonu)
- Aylık üretim < 4 (engagement sinyali yetersiz; cohort metric çürür)

## 7. Kayıt restriction (whitelist) teknik gereksinimleri

`docs/research/alpha-invite-checklist.md` §1'de detaylı; özet:

- **Backend flag:** `ALPHA_WHITELIST_ENABLED=true` (Faz 4'te aktif)
- **Whitelist tablosu:** `alpha_invitations(email, token, status, invited_at, redeemed_at)` (Issue #69 ile aynı patern)
- **Token TTL:** 14 gün (davet kabul edilmezse pasifleşir)
- **Limit:** 10 aktif kayıt; 11. kayıt 503 + "kapasite dolu" mesajı
- **Audit log:** her redeem `audit_logs` tablosuna düşer

## 8. Karar logu

| Karar | Gerekçe | Doküman ref |
|-------|---------|-------------|
| 5-10 ölçek | İstatistiksel anlamlılık + 1:1 ilgi balansı | research-findings §12 |
| 30 gün süre | "Alışkanlık" formasyonu için minimum (2-4 hafta) | success-metrics §7.1 |
| P1A primer | Discovery onaylı; satın alma cümlesi var | research-findings §3.3 |
| Pro tier ücretsiz | Friction sıfır; ödeme isteği bağımsız ölçülür | pricing-strategy §3 |
| Whitelist + KVKK | Legal kapı + spam koruma | threat-model §4 |

## 9. Versiyon kaydı

| Versiyon | Tarih | Değişiklik |
|----------|-------|------------|
| v1.0 | 2026-05-01 | İlk yayın — alpha hedef kriterleri (#50) |

---

**Bağlı dokümanlar:**
- `docs/validation/research-findings.md` §3 — persona doğrulama
- `docs/research/alpha-invite-template.md` — davet emaili
- `docs/research/alpha-success-metrics.md` — KS acceptance
- `docs/research/alpha-invite-checklist.md` — operasyon adımları
- `docs/strategy/pricing-strategy.md` — ödeme isteği bağı
