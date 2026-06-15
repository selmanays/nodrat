# Nodrat — Kaynak Kullanım Politikası (Scraping Policy)

**Yürürlük tarihi:** [____________________]
**Son güncelleme:** 2026-05-01
**Sürüm:** v0.1

⚠️ **DRAFT — Avukat onayı gerekli.**

---

## 0. Bu Sayfa Kimin İçin?

Bu politika, web sitesi sahipleri ve içerik yayıncıları içindir. Nodrat'ın haber kaynaklarına nasıl erişim sağladığını, hangi etik kurallara uyduğunu ve yayıncıların opt-out / kaldırma talep akışını açıklar.

Aynı sayfa: https://nodrat.com/bot

---

## 1. Nodrat Nedir?

Nodrat, Türkiye odaklı politik/güncel içerik üreticilerine kaynaklı X paylaşımı, özet ve karşılaştırmalı analiz üretmek için tasarlanmış bir SaaS platformudur.

```text
- Nodrat bir haber yayıncısı DEĞİLDİR.
- Haber metinlerinin tamamını yeniden yayınlamaz.
- Sadece kaynak link + kısa özet + türev içerik üretir.
- Kullanıcılarına yayın öncesi doğrulama hatırlatır.
```

---

## 2. NodratBot — Crawler Bilgisi

```text
User-Agent:
  NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)

From header:
  legal@nodrat.com

Accept-Language:
  tr-TR,tr;q=0.9
```

NodratBot'u tanımak için yukarıdaki User-Agent string'i ve `legal@nodrat.com` From header'ı kullanılır. Şüpheli bir User-Agent görüyorsanız bizimle iletişime geçin.

---

## 3. Etik Kurallarımız

### 3.1 Sıfır tolerans politikası

Aşağıdaki ihlaller için **kesin olarak hizmete kaynak eklenmez**:

```text
✗ robots.txt'de "Disallow" işareti olan path'ler
✗ Paywall (ücretli) arkasındaki içerik
✗ Login / hesap gerektiren içerik
✗ CAPTCHA ile korunan içerik
✗ Site sahibinin açık yasaklamış olduğu içerik
✗ Kullanım Şartları'nda scraping yasaklı içerik
```

### 3.2 Erişim sıklığı (rate limiting)

```text
- Kaynak başına max: 10 istek / dakika (varsayılan)
- Kaynak başına concurrent: 1
- HTTP 429 alındığında: exponential backoff + cooldown
- HTTP 5xx üst üste 5 kez: kaynak otomatik durdurulur
- Crawl saat aralıkları: site sahibi belirtirse uygulanır
```

### 3.3 Robots.txt uyumu

Her kaynak ekleme öncesi `robots.txt` parser:
1. `https://[domain]/robots.txt` indirilir
2. `User-agent: *` ve `User-agent: NodratBot` kuralları uygulanır
3. `Disallow` path'leri **mutlaka** uygulanır
4. `Crawl-delay` direktifi varsa uyulur
5. `Sitemap` varsa öncelikli kullanılır

```text
Robots.txt ihlali için ADMIN OVERRIDE YOKTUR.
Disallow → kaynak hizmete eklenmez.
```

**Canlı kaynaklar — geçici hata ayrımı (#1498):** Yukarıdaki sıfır-tolerans, **kaynak ekleme/aktive etme** anında geçerlidir (doğrulanamayan kaynak eklenmez — fail-closed). Zaten aktif bir kaynak için robots.txt'in o an **çekilememesi** (network hatası, timeout, HTTP 5xx veya 4xx-forbidden) **kalıcı bir `Disallow` sayılmaz** ve kaynağı otomatik kapatmaz; aksi halde anlık bir ağ takılması kaynağı sessizce devre dışı bırakırdı. Canlı kaynak yalnız robots.txt başarıyla çekilip **gerçek bir Disallow** kuralı alındığında (fetched=true ama site kökü NodratBot'a yasak) otomatik deaktive edilir ve bu olay görünür bir `failed_jobs(job_type='source.auto_deactivated')` izi bırakır.

### 3.4 Yalnızca kamuya açık içerik

```text
✓ Anasayfa, kategori sayfaları, RSS feed
✓ Login gerektirmeyen makale sayfaları
✓ Açıkça yayımlanmış metinler

✗ Üye arşivi
✗ Ücretli içerik (Premium, Plus, vb.)
✗ Ön izleme arkası içerik
```

### 3.5 Kişisel veri (KVKK)

Nodrat:
- Haberlerde geçen kamuya açık figürlerin (politikacı, sanatçı, kamu görevlisi) adlarını işler.
- Bu veri "alenileşmiş kişisel veri" niteliktedir (KVKK md.5/2-d).
- Haberde geçen sıradan kişiler için "unutulma hakkı" başvuru kanalı vardır (madde 7).
- Özel nitelikli kişisel veri (sağlık, din, etnik köken, siyasi görüş) hassas etiketlenir ve içerik üretiminde ekstra kontrol uygulanır.

---

## 4. Telif Hakkı (FSEK)

```text
Nodrat:
- Tam haber metnini ASLA kullanıcıya yeniden yayınlamaz
- 25 kelimeyi aşan doğrudan alıntı yapmaz
- Her üretim için kaynak listesi sağlar
- Kaynak link, başlık, yayın tarihi gösterir
- "Haber yayıncısı değil, üretim aracı" pozisyonunda

Kullanıcı kaynak atıflarını korumakla yükümlüdür (ToS madde 6.2).
```

---

## 5. Yayıncılar İçin Beklentiler

Eğer içeriğinizi Nodrat'tan kaldırmak istiyorsanız:

### 5.1 Hızlı yöntem — robots.txt

```text
User-agent: NodratBot
Disallow: /

# Veya belirli path'leri:
User-agent: NodratBot
Disallow: /premium/
Disallow: /members-only/
```

NodratBot bu kuralı 24 saat içinde tespit eder ve sitenizi taramayı durdurur.

### 5.2 Resmi kaldırma talebi

```text
Endpoint:  https://nodrat.com/legal/abuse
Endpoint:  https://nodrat.com/legal/copyright (telif için)
Endpoint:  https://nodrat.com/legal/takedown (5651 kapsamı)
E-posta:   legal@nodrat.com

Talebi şu bilgilerle gönderin:
- Kuruluş adı / yetkili kişi
- E-posta
- Hak iddia edilen URL veya tüm domain
- Kaldırma sebebi (telif / 5651 / KVKK / diğer)
- Açıklama
- Yetki belgesi (tüzel kişi ise)

SLA: 24 saat içinde değerlendirme + ön cevap
```

### 5.3 Bizimle ortaklık (lisanslı kullanım)

İçerik lisansı vermek isterseniz bizimle iletişime geçin: legal@nodrat.com. Q3 2026'dan sonra resmi gazete partnership programı planlanmaktadır.

---

## 6. NodratBot'u Engelleme

### 6.1 robots.txt yöntemi (önerilen)

```text
User-agent: NodratBot
Disallow: /
```

### 6.2 IP bazlı engelleme

NodratBot, statik IP havuzundan istek atar. IP listesi: https://nodrat.com/bot/ips (planlı, henüz yayında değil)

### 6.3 HTTP header yönetimi

```text
HTTP/1.1 403 Forbidden
X-NodratBot-Reason: not-allowed
```

NodratBot 403 alırsa siteyi blacklist'e ekler.

---

## 7. Şeffaflık

### 7.1 Kaynak listesi

Aktif olarak hangi kaynakları taradığımız bizim için ticari sır olmamalı. Ancak gizlilik için kullanıcılara açık değiştirilebilir liste sunulmaz; lisanslı / ortak yayıncılar listemiz şeffaftır.

### 7.2 İletişim

```text
NodratBot ile ilgili her türlü soru ve talep için:
  E-posta: legal@nodrat.com
  Form:    https://nodrat.com/legal/abuse
  Bot info: https://nodrat.com/bot
```

### 7.3 SLA

```text
Kaldırma talepleri    : 24 saat (ön cevap), 7 gün (final)
Genel sorular         : 5 iş günü
Teknik bug            : 3 iş günü
KVKK / unutulma       : 30 gün (KVKK md.13)
```

---

## 8. Politika Değişiklikleri

Bu politika değiştirilebilir. Önemli değişiklikler `https://nodrat.com/bot` ve bu sayfada duyurulur. Yayıncılara ek bildirim yapılır (bizimle iletişime geçenlere).

---

## 9. Çapraz Referans

```text
ToS                : docs/legal/tos.md
Privacy Policy     : docs/legal/privacy-policy.md
KVKK Aydınlatma    : docs/legal/kvkk-aydinlatma.md
Compliance Brief   : docs/legal/compliance-brief.md
Opinion Integration: docs/legal/opinion-integration.md
```

---

**v0.1 — DRAFT — Avukat onayı bekleniyor.**

---

**İletişim:** legal@nodrat.com
