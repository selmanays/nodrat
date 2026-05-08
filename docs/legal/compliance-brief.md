# Nodrat — Yasal & Uyumluluk Risk Brief

**Doküman türü:** Legal & Compliance Risk Assessment (Türkiye odaklı)
**Sürüm:** v0.3 (2026-05-08 — Avukat + Vergi Danışmanı görüşü integrated, Epic [#448](https://github.com/selmanays/nodrat/issues/448) §3.9 N-09 + §3.10 N-10 RESOLVED)
**Bağımlılık:** PRD v0.2, IA v0.1, Discovery v0.1, Pricing v0.2

> **v0.3 değişikliği (2026-05-08):** Avukat görüşü (LS MoR şartlı uygun, 7 ön-launch maddesi) ve vergi danışmanı görüşü (TR e-Arşiv yok, şahıs ticari kazanç, Limited threshold $5K MRR) integrated. Yeni canonical dokümanlar: `refund-policy.md`, `mesafeli-satis-sozlesmesi.md`, `payment-fallback-plan.md`. Detaylı entegrasyon: `opinion-integration.md` §3.9 + §3.10.
**Hedef:** Nodrat'ın Türk hukuku altında çalışırken karşılaşacağı yasal risklerin envanteri ve teknik/operasyonel hafifletmeler.

⚠️ **Disclaimer:** Bu doküman ürün ekibinin **risk farkındalığı** için hazırlanmıştır. **Hukuki görüş yerine geçmez.** Production launch öncesi mutlaka bilişim hukuku alanında bir avukatla **review yapılmalıdır**. Kritik kararlar (KVKK aydınlatma metni final dili, scraping ToS uyumu) avukat onayı ile sonlandırılmalı.

---

## 0. Yönetici Özeti

```text
Yüksek riskli alanlar (öncelikli):
  R1. KVKK uyumluluğu (kullanıcı verisi + haberlerdeki kişi verisi)
  R2. Telif hakkı / FSEK (haber metinlerinin kullanımı)
  R3. Robots.txt + ToS (scraping etiği ve hukuki sınırı)
  R4. 5651 (içerik kaldırma yükümlülükleri, 24 saat)
  R5. Üretilen içerikten kullanıcı sorumluluğu (LLM output liability)

Orta riskli:
  R6. Basın Kanunu (haber kaynağı statüsü)
  R7. RTÜK (görsel/yayın platformu olmadığımız için düşük)
  R8. X (Twitter) Developer Policy (otomatik gönderme yapmadığımızdan düşük)
  R9. Çocuk koruması (yaş kontrolü, içerik filtreleme)

Düşük riskli (şimdilik):
  R10. Vergi / e-Fatura / e-Arşiv → MoR ile büyük ölçüde mitigated (Epic #448, 2026-05-08)
       Lemon Squeezy MoR fatura keser, KDV global handling. Nodrat e-Arşiv kesmez.
  R11. KVKK transfer (yurt dışı LLM provider'a veri akışı)
  R12. Tüketici Mevzuatı (refund, cooling-off period)

Önerilen toplam yatırım:
  Avukat ön-görüş (10-15 saat)         : 40.000–80.000 TL
  KVKK uzmanı (DPO atama / outsource)  : 20.000–40.000 TL/yıl
  ~~e-Fatura entegrasyonu (Faz 6)~~    : 0 TL ✅ (Lemon Squeezy MoR keser, Epic #448)
  ToS + Privacy + KVKK metinleri       : 25.000–50.000 TL (LS pivot sonrası v0.2 review)
  Toplam ön-yatırım                     : ~85.000–170.000 TL (e-Fatura ~$30/ay sabit maliyet kalktı)
```

---

## 1. Türkiye Yasal Çerçevesi (Bağlam)

### 1.1 İlgili mevzuat haritası

```text
KVKK (6698 sayılı Kişisel Verilerin Korunması Kanunu)
  → Kullanıcı verisi + haberlerdeki kişi adları
  → Açık rıza, aydınlatma, ROPA, VERBİS

FSEK (5846 sayılı Fikir ve Sanat Eserleri Kanunu)
  → Haber metinleri telifli sayılır mı?
  → md.35: Atıflı kısa alıntı (haber özeti, kaynaklı türev)
  → md.36-37: Basın özetleri istisnası (sınırlı)

5651 (İnternet Ortamında Yapılan Yayınların Düzenlenmesi)
  → İçerik kaldırma yükümlülüğü (24 saat)
  → BTK / hakim kararı uyumu
  → Uyarı sistemi (notice-and-takedown)

Basın Kanunu (5187)
  → Haber kaynağı statüsü (biz "haber yayıncısı" değiliz)
  → Tekzip hakkı (üretilen içerik için kullanıcı sorumlu)

TBK (Türk Borçlar Kanunu) + TKHK (Tüketici Kanunu)
  → Mesafeli sözleşmeler (online satış)
  → 14 gün cayma hakkı
  → Refund kuralları

Vergi Mevzuatı
  → KDV %20 (B2C dahil fiyat)
  → e-Fatura / e-Arşiv zorunluluğu
  → Stopaj (yurt dışı provider ödemeleri için %15)

Hizmet Sağlayıcı statüsü (5651 md.5)
  → "Yer sağlayıcı" mı, "içerik sağlayıcı" mı?
  → Önerim: hibrit; üretim user-generated, kaynak admin küratör
```

### 1.2 KVKK kurumsal yükümlülükler

```text
- Veri Sorumlusu kayıt: VERBİS (50K+ kullanıcı eşiği yoksa opsiyonel)
- Aydınlatma metni (madde 10)
- Açık rıza (madde 5/2)
- ROPA (Records of Processing Activities)
- Veri ihlali bildirimi (72 saat)
- DPO ataması (büyük veri sorumluları için)
- Yurt dışı veri aktarımı: KVK Kurulu kararı veya BCR
```

---

## 2. Risk #1 — KVKK Uyumluluğu

### 2.1 Risk tanımı

Nodrat üç tür kişisel veri işler:

```text
A. Kullanıcı verisi (doğrudan)
   - email, isim, fatura adresi (Lemon Squeezy MoR ABD'de işler — Epic #448; kart bilgisi LS PCI-DSS Level 1, Nodrat'ta yok)
   - kullanım logu, IP, cihaz bilgisi
   - üretilen içerikler, stil profilleri

B. Kazınan haberlerdeki kişi adları (dolaylı)
   - politikacı, sanatçı, iş insanı isimleri
   - "Özel nitelikli" kategoriye girenler (sağlık, etnik, siyasi)
   - Bu veri "hukuken alenileşmiş" sayılabilir mi? (md.5/2-d)

C. Görsellerdeki yüzler (Faz 4)
   - Biyometrik veri sayılabilir
   - PRD §4.2 kritik prensip: kesin tanımlama YOK
   - Suggested + admin verified ayrımı şart
```

### 2.2 Etki ve yaptırım

```text
Olası ihlaller:
  - Açık rıza eksikliği                : İdari para cezası 50K-2.5M TL
  - Aydınlatma yükümlülüğü ihlali       : 5K-225K TL
  - Yurt dışı transfer izinsiz          : 50K-2.5M TL
  - Veri ihlali bildirim gecikmesi      : 18K-1.8M TL
  - Özel nitelikli veri ihlali          : ~%50 üst sınır

Reputational impact: Yüksek (basın haber yapar)
Operational impact:  Yüksek (geçici durdurma)
```

### 2.3 Hafifletme stratejileri

```text
M1. Kullanıcı verisi (Tier A)
    [ ] Kayıt akışında aydınlatma metni link
    [ ] Cookie banner (privacy-preserving default)
    [ ] Açık rıza checkbox (newsletter, analitik ayrı)
    [ ] Settings → "Veri indir" + "Hesabı sil" (GDPR-style)
    [ ] Password hash: Argon2 (PRD §8.2 uyumlu)
    [ ] Session: secure cookie + HttpOnly + SameSite
    [ ] Audit log (kim, ne zaman, hangi veri)

M2. Haberlerdeki kişi verisi (Tier B)
    [ ] Sadece "alenileşmiş" haber metni saklanır (gazete kaynağı)
    [ ] Kullanıcı talebine göre kişi-bazlı veri silme
    [ ] "Unutulma hakkı" başvuru endpoint'i
    [ ] Article TTL politikası (eski haber arşivlenir, anonim)
    [ ] Özel nitelikli veri filtresi:
        - Sağlık verisi geçen haberler ayrı kategoriye
        - Etnik/dini referans uyarısı
        - Gerekirse otomatik anonimizasyon (Faz 4+)

M3. Görsel/biyometrik (Tier C)
    [ ] Yüz tanıma SİSTEM HEDEFİ DEĞİL (PRD §4.2)
    [ ] Sadece "benzerlik" + admin onayı (verified)
    [ ] Auto-label asla "kesin" olarak sunulmaz
    [ ] Image embedding biyometrik mi? → KVK Kurul yorumu belirsiz
        → Önlem: image_embeddings tablosu salt-encrypted
    [ ] Kişi etiket silme talep akışı (audit log'lu)

M4. Yurt dışı veri transferi (LLM provider)
    [ ] Kullanıcı sorgusu → DeepSeek/Anthropic/OpenAI
    [ ] Bu transfer: KVKK md.9 (yurt dışı aktarım)
    [ ] Çözümler:
        - Açık rıza alma (en temiz yol)
        - Yeterli korumaya sahip ülke listesi (US çoğu için OK değil)
        - Standart sözleşme hükümleri (SCC) provider ile
    [ ] Lemon Squeezy MoR (ABD) ödeme verisi → KVKK m.9 ek açık rıza checkbox + LS DPA + SCC + TIA (Epic #448 §3.9 N-09 RESOLVED, #470 server-side enforcement)
    [ ] DPA (Data Processing Agreement) her provider ile
    [ ] Privacy policy'de net belirtim
```

### 2.4 Karar gereken noktalar

```text
D1. DPO atanacak mı, outsource mu? (50K+ kullanıcıda zorunlu)
    Önerim: İlk 1 yıl outsource (KVKK uzman ofis)

D2. VERBİS kayıt olacak mı?
    Önerim: 1.000+ kullanıcı eşiğinde gönüllü kayıt

D3. Yurt dışı transfer için açık rıza zorunlu mu?
    Önerim: Evet, register flow'da net checkbox

D4. Çocuk koruması (16+ yaş)
    Önerim: ToS'ta 18+ kuralı, register'da yaş onayı
```

---

## 3. Risk #2 — Telif Hakkı (FSEK)

### 3.1 Risk tanımı

Haber metinleri eser sayılır mı?

```text
FSEK md.4: "İlim ve edebiyat eserleri"
  → Yazılı haber metni eser sayılır (özgün ifade varsa)
  → Ham bilgi (olay, tarih, sayı) korunmaz; ifade biçimi korunur

FSEK md.35: Atıf şartlı kısa alıntı
  → Haber özeti yapılırken kaynak gösterilirse OK
  → "Maksat ve ölçü" kuralı (orantılılık)
  → Tam metin reproduction → ihlal

FSEK md.36-37: Basın özetleri istisnası
  → "Günlük olaylar"a ilişkin yazıların basın özeti yapılabilir
  → Çok dar yorumlanır, garanti değil

Soru: Nodrat ne yapıyor?
  - DB'de: tam metin saklanır (RAG için gerekli)
  - Kullanıcıya: özet + kaynaklı türev içerik gösterilir
  - Tam metin son kullanıcıya yeniden yayınlanmıyor (PRD §3.1, 3.2)
```

### 3.2 Etki

```text
Yaptırımlar (FSEK md.71):
  Manevi-mali tazminat (yayıncı zararı)
  Hapis 1-5 yıl (kasıtlı, ticari amaçlı)
  Adli para cezası

Pratik:
  Çoğu gazete tek tek dava açmaz
  Toplu lisans talebi gelir (Reuters/AA modeli)
  Reputational damage yüksek

Türkiye spesifik:
  Telif derneği yok haber için
  Bireysel gazeteler dava açar (örn. Sabah, Sözcü)
```

### 3.3 Hafifletme stratejileri

```text
M1. "Tam metin son kullanıcıya yeniden yayınlanmaz"
    [ ] PRD §12.4 kuralı zorunlu (telif riski madde)
    [ ] Generation prompt'unda "uzun alıntı yapma" kuralı
    [ ] Output kalite kontrol: 25+ kelimelik doğrudan alıntı flag
    [ ] Kaynak linki her zaman gösterilir (fair use destek)

M2. RAG context vs user output ayrımı
    [ ] Internal RAG'de tam metin OK (içerik üretim için)
    [ ] Kullanıcıya sadece özet + linkli kaynak
    [ ] DB'de tam metin → encrypted at rest opsiyonel

M3. Kaynak gösterimi standart
    [ ] Her üretim kaynak listesi içerir
    [ ] Kaynak adı + URL + (opsiyonel) tarih
    [ ] X paylaşımında gerekirse "Kaynak: [link]" zorunlu
    [ ] Kullanıcı kaynak gizleme yapsa bile dahili olarak saklanır

M4. Kaynak listesi gözlemi
    [ ] "Toplam metin kullanım oranı" metrik
    [ ] Eğer bir kaynak için toplam reproduction > eşik → flag
    [ ] Gazete partnership'leri uzun vadeli plan (Q3 2026+)

M5. ToS şart
    [ ] Kullanıcı ToS'unda: "Üretilen içeriği yayınladığında kaynak göster"
    [ ] Bu transfer eder sorumluluğu kullanıcıya (defansif)
    [ ] AAA güvenlik için: DMCA-style takedown procedure

M6. Kaynak içerik girişi politikası
    [ ] Sadece kamuya açık RSS/web sayfası (admin onaylı)
    [ ] Paywall arkası içerik HARAM
    [ ] Robots.txt'e saygı (etik göstergesi)
```

### 3.4 Karar noktaları

```text
D5. Tam metin DB'de tutulsun mu, sadece chunks?
    Önerim: Tam metin TUTULUR (reprocess + audit için)
            Encryption at rest opsiyonel

D6. Output'ta direct quote uzunluk limiti?
    Önerim: 25 kelime hard cap, prompt level

D7. Gazete ile partnership yaklaşımı?
    Önerim: 1.000+ paid sonra, "lisanslı kaynaklar" tier'ı dene

D8. DMCA-style takedown procedure?
    Önerim: ToS'a 24-48h response promise, manual review
```

---

## 4. Risk #3 — Robots.txt ve ToS Uyumluluğu

### 4.1 Risk tanımı

```text
robots.txt:
  - Hukuken bağlayıcı DEĞİL
  - "Etik gereği" + good-faith göstergesi
  - hiQ Labs vs LinkedIn (US) → public data scraping legal
  - Türkiye'de net case law yok

Web sitesi ToS:
  - Sözleşme niteliğinde olabilir (browse-wrap iddiası tartışmalı)
  - Hızlı request rate → "DDoS-like" iddiası riski
  - Türkiye'de mahkemeye gitmiş örnek nadir

Pratik durum:
  - Çoğu gazete robots.txt'te haber kategorilerini açar
  - Sabah, Sözcü, Hürriyet, NTV → genel olarak izinli
  - Aşırı request → rate limit / IP block
  - Ban yenebilir, ama PR riski var
```

### 4.2 Hafifletme

```text
M1. Robots.txt parser zorunlu (PRD §8.3)
    [ ] Source ekleme akışında robots.txt fetch + parse
    [ ] Disallow path → admin uyarı, kabul ederse "biz uyumlu değiliz" flag
    [ ] User-Agent gerçek (Nodrat-Bot/1.0; +https://nodrat.com/bot)

M2. Rate limiting per source domain
    [ ] Source başına max req/dk (varsayılan 10)
    [ ] HTTP 429 → exponential backoff + cooldown
    [ ] Crawler iyi vatandaş protokolü

M3. ToS-aware politika
    [ ] Source eklerken admin "ToS okudum" checkbox
    [ ] Üst düzey kaynaklar için lisans araştırma (manuel)
    [ ] Reuters / AP / AA gibi kaynaklar → API tercih edilmeli

M4. Public source whitelist
    [ ] Yalnızca kamuya açık, paywall olmayan sayfalar
    [ ] Premium/login-required içerik kapsam dışı

M5. Source health monitoring
    [ ] HTTP 4xx/5xx oranı yüksek → kaynak pasifleşir
    [ ] CAPTCHA detect → durdurma
    [ ] IP ban → admin alarmı
```

### 4.3 Karar noktaları

```text
D9. Robots.txt'i ihlal eden kaynak admin manuel onaylayabilir mi?
    Önerim: Hayır, hard block. Risk değer.

D10. User-Agent gerçek mi yoksa generic mi?
    Önerim: Gerçek + sender e-mail header
            (transparency = good faith göstergesi)

D11. Premium kaynak (paywall) eklenebilir mi?
    Önerim: Asla. Hard rule.
```

---

## 5. Risk #4 — 5651 İçerik Yükümlülükleri

### 5.1 Risk tanımı

```text
5651 sayılı kanun:
  - "Yer sağlayıcı" tanımı
  - Bildiren içeriği 24 saatte değerlendirme
  - Hakim/BTK kararı → kaldırma
  - Kaldırmama → kanal engelleme

Nodrat'ın statüsü:
  - Üretilen X paylaşımı → kullanıcı yayınlar (X üzerinde)
  - Saved generations → bizde saklanır
  - Generated content → potential olarak kişilik haklarına aykırı olabilir
  - Hakaret, iftira, ayrımcılık → kullanıcı sorumlu, ama biz hosted
```

### 5.2 Hafifletme

```text
M1. Notice-and-takedown procedure
    [ ] /legal/abuse veya /legal/dmca endpoint
    [ ] form: kim, hangi içerik, hangi hak
    [ ] 24h SLA admin review
    [ ] Kaldırma logu, audit trail

M2. Output kalite kontrolü (PRD §3.4 önerisi)
    [ ] Generation pipeline'da nefret söylemi filter
    [ ] Belirli kişi adlarına yönelik agresif içerik flag
    [ ] Kullanıcı bilgilendirme: "İçerik kişilik haklarını ihlal edebilir"

M3. Audit log
    [ ] Hangi kullanıcı hangi sorguyu ne zaman çalıştırdı
    [ ] 1 yıl saklama (yasal süre)
    [ ] Mahkeme talep ederse hazır

M4. ToS şart
    [ ] Kullanıcı yasadışı içerik üretmeyeceğine taahhüt
    [ ] Üretilen içeriğin sorumluluğu kullanıcıya
    [ ] Hesap kapatma hakkı saklı
```

---

## 6. Risk #5 — LLM Output Liability (Halüsinasyon)

### 6.1 Risk tanımı

```text
Senaryo: Nodrat "X kişisi şunu söyledi" diye halüsinasyon
         Kullanıcı bunu Twitter'da paylaşıyor
         X kişisi tekzip + tazminat talep ediyor

Sorumluluk dağılımı:
  - Kullanıcı (yayıncı) primary sorumlu
  - Nodrat (araç sağlayıcı) secondary
  - LLM provider neredeyse hiç sorumlu (ToS muafiyeti)

Olası dava tipleri:
  - Kişilik hakları
  - Tekzip
  - Manevi/maddi tazminat
  - 5237 md.125 (hakaret), md.299 (Cumhurbaşkanı)
```

### 6.2 Hafifletme (PRD §12.4 ile uyumlu)

```text
M1. Halüsinasyon koruması (teknik)
    [ ] Sadece RAG context kullanılır (PRD §12.4)
    [ ] Kaynakta olmayan kişi/tarih/olay uydurulmaz
    [ ] Veri yetersizse içerik üretilmez (insufficient_data)
    [ ] Verified label dışında kişi etiketi kesin değil
    [ ] Output'ta "kaynaklar" bölümü mandatory

M2. Kullanıcı uyarıları
    [ ] Generation result'ta "Yayınlamadan kontrol edin" disclaimer
    [ ] Hassas konularda (siyaset, sağlık) extra uyarı
    [ ] Kaynak doğrulama vurgulu UI

M3. ToS / EULA
    [ ] "Üretilen içerik kullanıcı sorumluluğunda"
    [ ] "AI çıktısı doğrulanmalı, garantisi yoktur"
    [ ] "Yayınlama öncesi kontrol zorunlu"
    [ ] "Hizmet 'as-is' verilir"

M4. İçerik filtreleme
    [ ] Sensitive entity list (politik figürler, dini liderler)
    [ ] Bu kişiler hakkında "agresif" ton output flag
    [ ] Kullanıcı isterse ekstra kalite kontrol

M5. Sigorta
    [ ] Cyber liability + professional indemnity sigortası değerlendir
    [ ] 1-2M TL kapsam ~10-25K TL/yıl
    [ ] Faz 6 paid launch sonra alınmalı
```

---

## 7. Risk #6-12 — Diğer Yasal Alanlar

### 7.1 R6 — Basın Kanunu

```text
Risk:    Nodrat "haber yayıncısı" mı sayılır?
Çözüm:   ToS'ta "Nodrat haber kaynağı değildir, içerik üretim aracıdır"
         Editoryal kontrol kullanıcının
Karar:   Nodrat haber kaynağı pozisyonundan KAÇINIR
```

### 7.2 R7 — RTÜK

```text
Risk:    Görsel/video yayın platformu olmadığımız için düşük
Çözüm:   Sadece text + (ileride) kazınmış görsel
         Kullanıcı kendi yayın platformuna yönlendirilir (X)
Karar:   RTÜK kapsam dışı
```

### 7.3 R8 — X Developer Policy

```text
Risk:    Otomatik X gönderme yapmadığımızdan düşük
         (PRD §3.2 — out of scope MVP)
Çözüm:   Kullanıcı manuel kopyalar, kendi X hesabından paylaşır
         Faz 7+ entegrasyon kurulursa X API ToS'a tam uyum
Karar:   MVP'de X API kullanımı yok → risk minimal
```

### 7.4 R9 — Çocuk koruması

```text
Risk:    16 yaş altı KVKK md.5 (veli rızası), 18+ ToS yaygın
Çözüm:   Register flow'da yaş confirm (≥18)
         Çocuk içeriği detection (output'ta "minor" geçerse flag)
Karar:   Hard age gate 18+ ToS
```

### 7.5 R10 — Vergi / e-Fatura ✅ MITIGATED (Epic #448, 2026-05-08)

```text
Risk:    B2C abone faturalama, KDV %20 dahil zorunlu
Çözüm:   Lemon Squeezy MoR keser (KDV/VAT/sales tax global handling).
         Nodrat e-Arşiv kesmez. Vergi danışmanı onayı: TR müşteriye
         Nodrat e-Arşiv yok; LS payout şahıs ticari kazanç olarak
         beyan (#473 mali müşavir 4 yazılı teyit).
Karar:   ✅ Lemon Squeezy MoR locked decision (Epic #448), threshold
         $5K MRR plan / $10K convert Limited Şti. (vergi danışmanı eşiği)
```

### 7.6 R11 — Yurt dışı veri transferi

```text
Risk:    LLM provider (Anthropic, DeepSeek, OpenAI) US/HK
         KVK Kurul'un "yeterli koruma" listesi yok
Çözüm:   Açık rıza (kayıt akışında)
         Standart Sözleşme Hükümleri (SCC) ile DPA
         Privacy policy net açıklama
Karar:   Açık rıza + SCC zorunlu
```

### 7.7 R12 — Tüketici Mevzuatı

```text
Risk:    14 gün cayma hakkı (mesafeli sözleşme)
         Refund prosedürü
Çözüm:   Pricing strategy'de tanımlandı (§10.1)
         /legal/refund-policy sayfası
Karar:   14 gün full refund yıllık subs için
```

---

## 8. Politika Dokümanları (taslak liste)

### 8.1 MVP launch öncesi şart (Faz 0-1)

```text
[ ] /legal/terms (Hizmet Koşulları) — TR + EN
[ ] /legal/privacy (Gizlilik Politikası) — KVKK uyumlu
[ ] /legal/kvkk-aydinlatma (KVKK aydınlatma metni)
[ ] /legal/cookies (çerez politikası)
[ ] /legal/scraping-policy (kaynak kullanım politikası)
[ ] Cookie banner (consent management)
[ ] Register flow → açık rıza checkbox
[ ] Settings → "Verilerimi indir" + "Hesabı sil"
```

### 8.2 Paid launch öncesi şart (Faz 6)

```text
[ ] /legal/refund-policy (iade politikası)
[ ] /legal/dmca (telif uyarı prosedürü)
[ ] /legal/abuse (kötüye kullanım bildirimi)
[ ] e-Arşiv fatura entegrasyonu
[ ] DPA template (provider'lar ile)
[ ] Cyber sigorta poliçesi (opsiyonel ama önerilir)
```

### 8.3 Internal politikalar

```text
[ ] Kaynak ekleme onay matrisi (admin)
[ ] Veri silme prosedürü (kullanıcı talep)
[ ] İhlal bildirim prosedürü (KVKK 72h)
[ ] Audit log retention politikası
[ ] Backup ve recovery prosedürü (KVKK uyum)
[ ] Incident response runbook
```

---

## 9. Risk Matrisi (Özet)

| ID | Risk | Olasılık | Etki | Skor | Faz |
|---|---|---|---|---|---|
| R1 | KVKK ihlali (kullanıcı verisi) | Orta | Yüksek | 🔴 9 | F0 |
| R2 | Telif hakkı (FSEK) tazminat | Orta-yüksek | Yüksek | 🔴 12 | F1 |
| R3 | Scraping etik/teknik ban | Yüksek | Orta | 🟡 6 | F1 |
| R4 | 5651 takedown gecikmesi | Düşük | Orta | 🟢 3 | F3 |
| R5 | Halüsinasyon → kullanıcı dava | Orta | Yüksek | 🔴 9 | F2 |
| R6 | Basın kanunu yanlış statü | Düşük | Düşük | 🟢 1 | F1 |
| R7 | RTÜK | Çok düşük | Düşük | 🟢 1 | — |
| R8 | X Developer Policy | Çok düşük | Düşük | 🟢 1 | F7+ |
| R9 | Çocuk koruması | Düşük | Orta | 🟢 3 | F3 |
| R10 | Vergi/e-Fatura | Düşük | Yüksek | 🟡 6 | F6 |
| R11 | Yurt dışı transfer | Yüksek | Orta | 🟡 6 | F0 |
| R12 | Tüketici mevzuatı | Düşük | Orta | 🟢 3 | F6 |

Skor = Olasılık (1-3) × Etki (1-3)
🔴 7-9 = Yüksek öncelik | 🟡 4-6 = Orta | 🟢 1-3 = Düşük

---

## 10. Aksiyon Planı

### 10.1 Faz 0 — Avukat ön-görüşü (kritik)

```text
[ ] Bilişim hukuku avukatıyla 2-3 oturum
    Konular:
      - KVKK uyum stratejisi
      - FSEK md.35 yorumu (haber özet kapsamı)
      - Yurt dışı transfer SCC
      - ToS / Privacy / Aydınlatma metni final dili

[ ] KVKK uzmanı (DPO outsource) anlaşma
    Aylık 2-4K TL, ROPA + denetim + ihlal bildirim

[ ] Politika dokümanları taslak → avukat review → final
```

### 10.2 Faz 1 sonu — pre-public launch

```text
[ ] /legal/* sayfaları yayında
[ ] Cookie banner aktif
[ ] Register flow KVKK aydınlatma + açık rıza
[ ] Audit log altyapısı çalışır
[ ] DMCA-style takedown endpoint canlı
[ ] Source ekleme robots.txt + ToS check
```

### 10.3 Faz 6 sonu — paid launch

```text
[ ] e-Arşiv fatura entegrasyonu
[ ] Refund prosedürü
[ ] Provider DPA imzalı
[ ] Cyber sigorta poliçesi (opsiyonel)
[ ] VERBİS gönüllü kayıt (1K+ kullanıcıda)
```

---

## 11. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Avukat görüşü zaman | Faz 0'da, kod yazımı öncesi | Tasarım etkiler |
| D2 | DPO atama | Yıl 1 outsource | Maliyet kontrolü |
| D3 | Tam haber metni saklansın mı? | Evet, encrypted at rest | RAG için şart |
| D4 | Yurt dışı transfer izni | Açık rıza + SCC | Kullanıcı flow |
| D5 | Premium gazete (paywall) eklenir mi? | Asla | Hard rule |
| D6 | Robots.txt ihlali toleransı | Sıfır | Etik + teknik ban |
| D7 | Çocuk koruması yaş gate | 18+ ToS | Conservative |
| D8 | Cyber sigorta | Faz 6 sonra değerlendir | Maliyet |
| D9 | "Haber kaynağı" pozisyonu | KAÇIN — "üretim aracı" | Basın kanunu |

---

## 12. Çapraz Referans

```text
KVKK aydınlatma     → Discovery: register akışı tasarımı
Telif (FSEK)        → PRD §12.4: hallucination prompt rules
Robots.txt parser   → IA §13 Faz 1: source ekleme akışı
SCC + DPA           → Unit Economics: provider seçim kriteri
Halüsinasyon        → Risk Register: ürün riski R-PRD-01
e-Arşiv             → Pricing: Faz 6 paid launch
DMCA takedown       → IA §5.4: /legal/abuse endpoint
Audit log retention → Success Metrics: operasyonel KPI
Cyber sigorta       → Risk Register: financial mitigation
```

---

**Sonuç:** Türkiye yasal çerçevesi Nodrat için kritik 5 alan içerir: **KVKK + Telif + Scraping etik + 5651 + Halüsinasyon liability**. Her biri için **teknik mitigation hazır** (PRD'de büyük çoğunluk var). Eksik olan: **avukat ön-görüşü** (özellikle FSEK md.35 yorumu ve KVKK aydınlatma metni final dili). Faz 0'da 40-80K TL avukat yatırımı, ileride yaşanabilecek 100K+ tazminat/cezayı engeller. **Production launch öncesi ToS + Privacy + Aydınlatma metinleri avukat onaylı olmadan canlıya çıkmamalı.**
