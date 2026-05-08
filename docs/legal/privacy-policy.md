# Nodrat — Gizlilik Politikası

**Yürürlük tarihi:** [____________________]
**Son güncelleme:** 2026-05-01
**Sürüm:** v0.1

⚠️ **DRAFT — Avukat onayı gerekli.**

---

## 0. Özet (Kısa)

```text
- Adresimiz: [Nodrat — Selman Aytaş, şahıs (Limited Şti. defer #448)]
- E-posta: privacy@nodrat.com
- Toplanan veri: hesap, kullanım, üretim verileri
- Yurt dışı transfer: LLM provider'larına (DeepSeek, Anthropic) + **Lemon Squeezy Inc. (ABD, MoR ödeme sağlayıcısı)**
- Saklama: aktif hesap süresince + 30 gün soft delete
- Haklarınız: KVKK md.11 (görme, düzeltme, silme, taşınabilirlik)
- Çocuklar: 18+ hizmet, 18 altı KULLANILAMAZ
- Çerezler: minimum, opsiyonel banner ile yönetilir
```

---

## 1. Veri Sorumlusu

> **2026-05-08 not (Epic [#448](https://github.com/selmanays/nodrat/issues/448)):** Limited Şti. kuruluşu defer edildi (Lemon Squeezy MoR sayesinde ilk lansmanda gereksiz). Veri sorumlusu **şahıs** olarak Selman Aytaş; MRR >$3K eşiğinde Limited Şti. kuruluşu yeniden değerlendirilecek ve metin güncellenecek.

```text
Unvan       : Selman Aytaş (şahıs — Faz 6 launch öncesi)
Vergi No    : [____________________] (gelir vergisi mükellefiyeti)
Adres       : [____________________]
E-posta     : privacy@nodrat.com (KVKK başvuru)
              legal@nodrat.com (yasal süreç)
Web         : https://nodrat.com
DPO/Uzman   : [____________________] (outsource KVKK)
```

---

## 2. Topladığımız Veriler

### 2.1 Doğrudan sizden aldığımız veriler

```text
A. Hesap bilgisi
   - E-posta adresi (kayıt zorunlu)
   - Ad-soyad (opsiyonel)
   - Şifre (Argon2id hash olarak)
   - Dil/locale tercihi
   - Onay timestamp'leri (KVKK, yurt dışı, pazarlama)

B. Profil bilgisi (opsiyonel)
   - Profil fotoğrafı (Faz 7+)
   - Stil profili (Faz 5 — kullanıcının yazı örnekleri)

C. Ödeme bilgisi (Faz 6+)
   - Fatura adı/adresi
   - VKN veya TC (e-Arşiv için)
   - Kart bilgisi: ÖDEME PROVIDER'INDA, BİZDE TUTULMAZ
   - Subscription token
```

### 2.2 Otomatik olarak toplanan veriler

```text
D. Kullanım verisi
   - Kullanıcı talepleri (request_text)
   - Üretim çıktıları
   - Generation history
   - Save / copy / delete eventleri
   - Provider, model, token sayısı, maliyet

E. Teknik veri
   - IP adresi
   - User-Agent (browser, OS)
   - Cihaz tipi
   - Login zamanı
   - Session token (hash)

F. Çerez verisi (Cookies Policy bölüm 4 ile uyumlu)
   - Zorunlu çerezler (session, CSRF)
   - Analytics çerezleri (opsiyonel)
   - Pazarlama çerezleri yok (MVP'de)
```

### 2.3 Üçüncü taraflardan aldığımız veriler

```text
- Lemon Squeezy MoR (ABD) — abonelik durumu, fatura referansı, ödeme tutarı,
  başarı durumu, customer/subscription ID, variant ID. Lemon Squeezy ödeme
  bilgilerini (kart no, CVV) bizimle paylaşmaz; sadece tokenized referans
  + işlem sonucu döner.
- Email delivery durumu (Resend/Postmark → açıldı/açılmadı)
- Hiçbir 3. taraftan PII satın almıyoruz veya zenginleştirme yapmıyoruz.
```

---

## 3. Verileri Hangi Amaçlarla İşliyoruz?

```text
1. Sözleşmenin kurulması ve ifası (KVKK md.5/2-c)
   - Hesap oluşturma, kimlik doğrulama
   - İçerik üretim hizmeti sunma
   - Kullanım kotası takibi
   - Faturalama ve ödeme

2. Yasal yükümlülük (md.5/2-ç)
   - Vergi mevzuatı: KDV/VAT/sales tax compliance Lemon Squeezy (Merchant
     of Record) tarafından üstlenilmektedir; Hizmet Sağlayıcı e-Arşiv
     fatura kesmez (Epic #448)
   - KVKK güvenlik önlemleri
   - 5651 takedown / abuse bildirimleri
   - Audit log saklama

3. Meşru menfaat (md.5/2-f)
   - Spam / abuse koruması
   - Cost runaway koruması
   - Ürün geliştirme analytics (anonim)
   - Sistem güvenliği

4. Açık rıza (md.5/2-a)
   - Yurt dışı LLM provider'larına veri aktarımı
   - Pazarlama iletileri (opsiyonel)
   - Analytics çerezleri (opsiyonel)
```

---

## 4. Yurt Dışı Veri Aktarımı (KRİTİK)

### 4.1 Hangi veriler yurt dışına gider?

```text
A. LLM provider'larına (DeepSeek, Anthropic, OpenRouter, OpenAI)
   - Kullanıcı talebi (request_text) — PII redaction sonrası
   - İlgili agenda card'lar ve kaynaklar
   - Stil profili kuralları (eğer kullanılıyorsa)

B. Embedding provider'a (NVIDIA NIM)
   - Sorgu metni (PII redaction sonrası)

C. Email provider'a (Resend / Postmark)
   - E-posta adresi
   - Email içerik

D. Ödeme provider'ı: **Lemon Squeezy Inc. (ABD, MoR)** — Epic #448 ile
   2026-05-08'de Iyzico/PayTR/Stripe-direct yerine seçildi
   - Ad, soyad, e-posta, fatura adresi, ülke, IP
   - Ödeme yöntemi token (kart no/CVV bizden geçmez, doğrudan LS)
   - Fatura bilgisi, ödeme tutarı, abonelik durumu
   - **KVKK m.9 yurt dışı transfer:** ABD adequacy decision yok →
     açık rıza zorunlu (kayıt + ödeme akışında ayrı checkbox)
   - LS DPA + SCC imzalı (Lemon Squeezy data processing addendum +
     standart sözleşme hükümleri)
   - LS subprocessor list arşivde: lemonsqueezy.com/legal/subprocessors
   - **Transfer Impact Assessment (TIA)** kayıtları tutuldu (avukat
     şartlı onayı, Epic #448 §3.9 N-09 RESOLVED): KVKK Aydınlatma
     Metni §4.2.1 + ROPA §16.1'de detay (5 maddelik kayıt sistemi —
     veri kategorileri, minimizasyon, sözleşme, teknik tedbirler,
     açık rıza)
   - **Server-side enforcement** ([#470](https://github.com/selmanays/nodrat/issues/470)):
     açık rıza dolu değilse LS checkout, LLM provider çağrısı, email
     ve embedding fallback API'leri 403 Forbidden döner
```

### 4.2 PII redaction (kişisel veri maskeleme)

LLM çağrısı yapılmadan **önce**, prompt'tan otomatik olarak şu bilgiler temizlenir:

```text
- E-posta adresleri        → [email_redacted]
- Telefon numaraları       → [phone_redacted]
- IP adresleri             → [ip_redacted]
- TC kimlik numaraları     → [id_redacted]
- IBAN numaraları          → [iban_redacted]
- Account ID / UUID        → [ref_redacted]
```

Bu, kullanıcının prompt'unda yer alsa bile uygulanır.

### 4.3 Hukuki dayanak

Yurt dışı aktarım için her kullanıcıdan **açık rıza** alınır (kayıt sırasında ayrı checkbox). Provider'larla **DPA / SCC** dokümanları imzalıdır.

### 4.4 Provider listesi ve ülkeler

| Provider | Veri | Ülke | Hukuki dayanak |
|---|---|---|---|
| DeepSeek | Prompt + output | Çin (HK) | Açık rıza + DPA |
| Anthropic | Prompt + output | ABD | Açık rıza + DPA + SCC |
| OpenRouter | Prompt + output | ABD | Açık rıza + DPA |
| OpenAI | Prompt + output (fallback) | ABD | Açık rıza + DPA + SCC |
| NVIDIA NIM | Embedding query | ABD | Açık rıza + DPA |
| Resend / Postmark | Email | ABD | Açık rıza + DPA |
| Stripe (Faz 6) | Ödeme | ABD | Açık rıza + DPA + SCC |
| Backblaze B2 | Backup | ABD | Meşru menfaat + encryption |

### 4.5 Açık rızayı nasıl geri çekersiniz?

`Settings → Hesap` üzerinden **veri aktarım rızasını geri çekebilirsiniz**. Bu, hizmetin **çalışmamasına** sebep olur (LLM provider'a veri gönderilemediği için üretim yapılamaz). Bu durumda hesabınızı kapatmanız önerilir.

---

## 5. Verilerinizi Kimlerle Paylaşırız?

```text
Paylaşılan taraflar:
- Yurt dışı provider'lar (madde 4.4)
- Yurt içi ödeme sağlayıcı (Iyzico/PayTR)
- Vergi mevzuatı kapsamında resmi makamlar (e-Arşiv)
- Mahkeme kararı veya savcılık talebi (yasal zorunluluk)
- Avukat / DPO uzman (gizlilik sözleşmesi altında)
- Backup sağlayıcı (Backblaze, encrypted)

Paylaşılmayan:
- Reklam / pazarlama 3. tarafları (kullanıcı verisi satılmaz)
- Veri brokerleri
- Sosyal medya platformları
```

---

## 6. Saklama Süreleri

| Veri | Saklama süresi |
|---|---|
| Kullanıcı hesap | Aktif süresince + 30 gün soft delete |
| Generations | Sınırsız (kullanıcı silmedikçe) |
| Saved generations | Sınırsız (kullanıcı silmedikçe) |
| Free tier generations | 30 gün |
| Login + IP log | 90 gün |
| Audit log | 1 yıl (yasal min) |
| usage_events | 18 ay |
| Email log | 1 yıl |
| Fatura | 10 yıl (vergi mevzuatı) |
| Subscription | Aktif + 5 yıl (mali müşavir önerisi) |
| Backup | 7 günlük + 4 haftalık + 6 aylık rolling |
| Article (haber) tam metni | 90 gün cleaned, sonra archived |
| Article chunks + embedding | Article ile beraber arşivlenir |

---

## 7. Çerezler

Çerez kullanımı detayı [Çerez Politikası](cookies-policy.md) sayfasındadır.

```text
Zorunlu çerezler (her zaman):
- session_token   : oturum
- csrf_token      : güvenlik
- cookie_consent  : sizin tercihiniz

Opsiyonel (sizin onayınızla):
- analytics_id    : ürün geliştirme (PostHog self-host)

Pazarlama çerezleri kullanmıyoruz.
```

---

## 8. KVKK md.11 Haklarınız

KVKK uyarınca aşağıdaki haklara sahipsiniz:

```text
1. Kişisel verinizin işlenip işlenmediğini öğrenme
2. İşlenmişse bilgi talep etme
3. İşlenme amacını ve uygun kullanılıp kullanılmadığını öğrenme
4. Yurt içinde veya yurt dışında aktarıldığı 3. tarafları bilme
5. Eksik veya yanlış işlenmişse düzeltilmesini isteme
6. KVKK md.7'de öngörülen şartlarda silinmesini veya yok edilmesini isteme
7. Düzeltme, silme, yok etme işlemlerinin aktarıldığı 3. taraflara bildirilmesini isteme
8. Otomatik sistemler ile yapılan analizler sonucu aleyhinize bir sonuç çıkmasına itiraz etme
9. Kanuna aykırı işleme nedeniyle zarar uğrarsanız tazmin edilmesini isteme
```

### 8.1 Başvuru kanalları

```text
A. Self-service (en hızlı):
   - Settings → Profil      : düzeltme
   - Settings → Hesabım     : silme talebi (DELETE /app/me)
   - Settings → Veri İndir  : taşınabilirlik (GET /app/me/data-export)

B. Formal başvuru:
   - https://nodrat.com/legal/privacy-request (Faz 1)
   - E-posta: privacy@nodrat.com
   - Yazılı: [Ulus adresimize]

C. Cevap süresi: 30 gün (KVKK md.13)
   Karmaşık durumlarda 60 güne uzatılabilir, kullanıcıya bildirim
   yapılır.
```

### 8.2 Haberlerdeki kişi verisi

Eğer adınız haberlerimizden birinde geçiyorsa ve kaldırılmasını istiyorsanız:
- /legal/privacy-request endpoint
- privacy@nodrat.com
- 24 saat içinde değerlendirme
- Açık ihlal varsa içerik arşivlenir veya anonimize edilir

### 8.3 KVK Kurul'a başvuru

Şikayetinize 30 günde cevap alamazsanız veya cevabı yetersiz bulursanız KVK Kurul'a başvurabilirsiniz: https://verbis.kvkk.gov.tr

---

## 9. Güvenlik

KVKK md.12 uyarınca aldığımız önlemler:

```text
Teknik önlemler:
- Şifreleme: TLS 1.2+, Argon2id, Fernet
- Backup encryption (restic + age)
- Yetki kontrolü: JWT + role + ownership
- Audit log
- Rate limiting
- 2FA (admin için zorunlu)
- PII redaction (LLM çağrısı öncesi)
- Network izolasyonu (Docker internal network)
- Düzenli backup ve restore drill (aylık)

İdari önlemler:
- DPO/KVKK uzman outsource
- Çalışan gizlilik taahhüdü
- Yıllık KVKK eğitimi
- Incident response runbook (72h)
- ROPA aktif

Fiziksel:
- Veri merkezi: Hetzner (ISO 27001 sertifikalı)
- Backup: Backblaze B2 (US, encrypted)
```

---

## 10. Veri İhlali Durumu

Kişisel veri ihlali durumunda:
1. **72 saat içinde** KVK Kurul'a bildirim yapılır
2. Etkilenen kullanıcılara **24 saat içinde** e-posta ile bildirim
3. Web sitesinde public statement (önemli durumlarda)
4. İhlal raporu /legal/incident-history sayfasında sonradan yayımlanır

Detaylı süreç: [Incident Response Runbook](incident-response.md)

---

## 11. Çocuk Koruması

```text
Hizmet yalnızca 18 yaş ve üzeri kullanıcılar içindir.
18 yaşından küçük olduğunu fark ettiğimiz hesabı derhal kapatırız
ve ilgili kişisel verileri sileriz.

Eğer 18 yaşından küçük bir çocuğun kişisel verisini topladığımızı
düşünüyorsanız privacy@nodrat.com adresinden bize bildirebilirsiniz.
```

---

## 12. Değişiklikler

Bu Gizlilik Politikası'nı değiştirebiliriz. Önemli değişiklikler:
- E-posta ile 30 gün önceden bildirim
- Web sitesinde duyuru

Değişiklik sonrası hizmeti kullanmaya devam etmek, yeni politikayı kabul anlamına gelir.

Önceki versiyonlar: /legal/privacy-history

---

## 13. İletişim

```text
Veri sorumlusu        : [Nodrat Bilişim Ltd. Şti.]
KVKK başvuru          : privacy@nodrat.com
Yasal süreç           : legal@nodrat.com
Genel destek          : support@nodrat.com
DPO / Uzman           : [____________________]
KVK Kurul             : https://www.kvkk.gov.tr
```

---

**v0.1 — DRAFT — Avukat onayı bekleniyor.**
