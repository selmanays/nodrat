# Nodrat — ROPA (Records of Processing Activities — Veri İşleme Envanteri)

**Doküman türü:** KVKK md.16 + GDPR Article 30 ROPA
**Sürüm:** v0.1 (taslak)
**Bağımlılık:** Compliance Brief §2, Opinion Integration §2.3, Data Model (tüm tablolar), Privacy Policy
**Hedef:** Nodrat'ın işlediği tüm kişisel veri kategorilerini, amaçlarını, hukuki dayanaklarını, alıcılarını, saklama sürelerini ve güvenlik önlemlerini envanterlemek.

⚠️ **DRAFT — DPO/KVKK uzmanı tarafından final review.** KVK Kurul VERBİS bildirimi yapılırsa bu envanter temel alınır.

---

## 0. Veri Sorumlusu Bilgileri

```text
Unvan       : [Nodrat Bilişim Ltd. Şti.] (kuruluş sonrası güncellenecek)
Vergi No    : [____________________]
MERSIS No   : [____________________]
Adres       : [____________________]
Yetkili     : Selman Ay (Kurucu)
İletişim    : legal@nodrat.com
DPO/Uzman   : [____________________] (outsource)

VERBİS Kayıt: Henüz değil (1.000+ kullanıcı eşiğinde değerlendirilecek)
```

---

## 1. Veri İşleme Aktiviteleri Özeti

```text
Toplam aktivite: 12

#01  Kullanıcı hesap yönetimi
#02  Kimlik doğrulama (login + session)
#03  İçerik üretim (kullanıcı sorgusu → LLM)
#04  Üretim geçmişi ve kayıtlı içerikler
#05  Kullanım kotası ve limit takibi
#06  Haber kaynağı kazıma (haberlerdeki kişi verileri)
#07  Görsel arşivleme ve etiketleme (Faz 4)
#08  Stil profili (Faz 5 — kullanıcı yazı örnekleri)
#09  Faturalama ve abonelik yönetimi (Faz 6 — Lemon Squeezy MoR ABD, KVKK m.9 yurt dışı transfer; detay §11. Eski Iyzico/e-Arşiv planı Epic #448 ile reddedildi)
#10  Email iletişimi (transactional + marketing)
#11  Analytics ve ürün geliştirme
#12  Yasal uyum ve audit log
```

---

## 2. Aktivite #01 — Kullanıcı Hesap Yönetimi

```text
Amaç:
  Kullanıcının ürünü kullanabilmesi için hesap oluşturma, düzenleme,
  kapatma süreçleri.

İşlenen veri kategorileri:
  - Kimlik: ad-soyad (opsiyonel)
  - İletişim: e-posta adresi
  - Kimlik doğrulama: şifre hash (Argon2id)
  - Profil: dil tercihi, locale
  - Onay tarihleri: KVKK aydınlatma, veri işleme, yurt dışı transfer,
                    pazarlama (her biri ayrı timestamp)

Hukuki dayanak (KVKK md.5):
  - md.5/2-c: Sözleşmenin kurulması ve ifası
  - md.5/2-a: Açık rıza (yurt dışı transfer için)

Veri sahipleri:
  - Kayıtlı kullanıcılar (paid + free)
  - Trial kullanıcılar (sınırlı veri)

Alıcılar / aktarım:
  - İçeride: API + DB
  - Dış: e-posta gönderim sağlayıcısı (Resend / Postmark)

Yurt dışı aktarım:
  - E-posta sağlayıcısı (US) — açık rıza ile
  - DPA / SCC zorunlu

Saklama süresi:
  - Aktif hesap süresince
  - Hesap kapatıldıktan sonra 30 gün soft delete
  - Sonra hard delete (audit log + yasal saklama gerekleri hariç)

Güvenlik önlemleri:
  - Şifre Argon2id hash
  - Veritabanı access control
  - HTTPS / TLS 1.2+
  - Audit log (admin actions)
  - Backup şifrelenmiş

Veritabanı tabloları:
  - users
  - sessions

Veri sahibi hakları (KVKK md.11):
  - Görme (settings → profile)
  - Düzeltme (settings → profile edit)
  - Silme (DELETE /app/me)
  - Veri taşınabilirlik (GET /app/me/data-export)
```

---

## 3. Aktivite #02 — Kimlik Doğrulama (Login + Session)

```text
Amaç:
  Kullanıcının her oturumda kimliğini doğrulamak, session yönetimi.

İşlenen veri kategorileri:
  - Kimlik: e-posta + şifre hash karşılaştırma
  - Bağlantı: IP adresi, kullanıcı ajan (User-Agent)
  - Session: JWT token, refresh token hash
  - Tarih: last_login_at

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası

Saklama süresi:
  - JWT access: 15 dakika
  - Refresh token: 30 gün
  - Login log: 1 yıl (güvenlik audit)
  - IP log: 90 gün

Yurt dışı aktarım:
  - Yok (tamamen self-hosted VPS, Türkiye)

Güvenlik:
  - JWT signed (HS256)
  - HttpOnly + SameSite=strict cookie
  - HTTPS only
  - fail2ban (10 fail / 1 saat lockout)
  - 2FA opsiyonel (admin için zorunlu — Faz 6)

Veritabanı tabloları:
  - users (last_login_at, last_login_ip)
  - sessions
  - failed_login_attempts (varsa, Faz 6+)
```

---

## 4. Aktivite #03 — İçerik Üretim (Kullanıcı Sorgusu → LLM)

```text
Amaç:
  Kullanıcının doğal dil gündem talebini LLM provider'ına ileterek
  kaynaklı X içeriği, özet, analiz üretmek.

İşlenen veri kategorileri:
  - Kullanıcı talebi (request_text — serbest metin)
  - Üretim parametreleri (mode, output_type, tone, length)
  - Üretim çıktısı (posts, summary, sources)
  - Kullanılan agenda card ID'leri
  - Provider tracking (model, token sayısı, maliyet)

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası
  - md.5/2-a: Açık rıza (LLM provider'a yurt dışı transfer)

Yurt dışı aktarım — KRİTİK:
  - DeepSeek (HK, varsayımsal)         — açık rıza + DPA
  - Anthropic (US)                     — açık rıza + DPA + SCC
  - OpenRouter (US)                    — açık rıza + DPA
  - OpenAI (US, fallback)              — açık rıza + DPA + SCC
  - NVIDIA NIM (US, embedding)         — açık rıza + DPA

PII Redaction (zorunlu — avukat tavsiyesi):
  Her LLM çağrısı öncesi prompt'tan otomatik temizleme:
    - email                 → [email_redacted]
    - telefon               → [phone_redacted]
    - IP adresi             → [ip_redacted]
    - TC kimlik no          → [id_redacted]
    - IBAN                  → [iban_redacted]
    - account ID / UUID     → [ref_redacted]

Veri sahipleri:
  - Tüm kullanıcılar (free + paid + trial)

Saklama süresi:
  - Generations tablosu: kullanıcı silmedikçe sınırsız
  - Hesap silinince soft delete (30 gün) → hard delete

Güvenlik:
  - PII redaction (zorunlu)
  - Provider'lara HTTPS
  - Kullanıcı kontrolü altında geçmiş
  - Provider DPA'ları aktif

Veritabanı tabloları:
  - generations
  - usage_events
  - provider_call_logs
```

---

## 5. Aktivite #04 — Üretim Geçmişi ve Kayıtlı İçerikler

```text
Amaç:
  Kullanıcının ürettiği içerikleri tekrar erişebilmesi, kaydedebilmesi.

İşlenen veri kategorileri:
  - Generation ID, request_text, output_json
  - Save metadata (note, saved_at)

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası

Yurt dışı aktarım: Yok (sadece DB'de)

Saklama süresi:
  - Free tier: 30 gün (eski kayıtlar otomatik silinir)
  - Paid tier: sınırsız (kullanıcı silmedikçe)

Veritabanı tabloları:
  - generations
  - saved_generations
```

---

## 6. Aktivite #05 — Kullanım Kotası ve Limit

```text
Amaç:
  Tier'a göre aylık quota takibi, rate limiting.

İşlenen veri kategorileri:
  - usage_events: event_type, provider, model, tokens, cost, timestamp
  - Rate limit counter (Redis)

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası
  - md.5/2-f: Meşru menfaat (cost runaway koruması)

Saklama süresi:
  - usage_events: 18 ay (KVKK gerekirse anonimize)
  - Redis rate limit: ephemeral (≤ 1 saat)

Veritabanı tabloları:
  - usage_events
  - Redis (kısa süreli)
```

---

## 7. Aktivite #06 — Haber Kaynağı Kazıma (HABER METNİNDEKİ KİŞİ VERİLERİ)

```text
Amaç:
  Admin tarafından onaylanmış kamuya açık haber kaynaklarını kazıyıp
  RAG sisteminde kullanmak.

İşlenen veri kategorileri:
  - Haber metni (clean_text)
  - Haberde geçen kişi adları (politikacı, sanatçı, kamu görevlisi)
  - Haberde geçen kurum/yer adları
  - Yayın tarihi, kaynak adı, URL

ÖZEL DURUM — Hassas veri:
  Haberlerde "özel nitelikli kişisel veri" geçebilir:
    - Sağlık (hasta haberleri)
    - Din / inanç (dini lider haberleri)
    - Etnik köken (azınlık haberleri)
    - Siyasi görüş (politikacı haberleri)
  
  Hassas veri tespiti → entities tablosunda sensitivity_flag

Hukuki dayanak:
  - md.5/2-d: Alenileşmiş kişisel veri (politikacı, kamuya açık figür)
  - md.6/2: Özel nitelikli veri için açık rıza (alenileşmemiş ise)

Paywall ve robots.txt:
  - Sıfır tolerans (avukat onaylı)
  - Paywall HARD BAN
  - robots.txt disallow → kaynak eklenmez

Yurt dışı aktarım:
  - Haber metni LLM çağrılarında provider'a (DeepSeek, Anthropic)
    - Açık rıza temelli (kullanıcı onayladı)
    - Provider DPA'ları aktif

Saklama süresi:
  - Tam metin: 90 gün cleaned, sonra archived (clean_text → NULL)
  - Chunks + embedding: archived article'larla beraber silinir
  - HTML snapshot: 30 gün

User-facing visibility:
  - Tam metin kullanıcıya GÖSTERİLMEZ
  - Sadece özet + kaynaklı türev içerik + URL link
  - Direct quote 25 kelime hard cap

Veri sahibi haklari:
  - Haberlerde geçen bir kişi "unutulma hakkı" talep ederse:
    /legal/privacy-request endpoint
    24 saat içinde değerlendirme
    İlgili haber + chunk'lar arşivlenir
    Kişiyi referans eden agenda card'lar revize edilir

Veritabanı tabloları:
  - articles
  - article_chunks
  - event_clusters
  - event_articles
  - agenda_cards
  - sources, source_configs (kaynak meta)
```

---

## 8. Aktivite #07 — Görsel Metadata Çıkarma (Process & Discard, #304 MVP-1.4)

```text
Amaç:
  Haber görsellerinin metadata'sını NIM VLM ile çıkarmak.
  GÖRSEL BYTES SAKLANMIYOR — process & discard mimarisi.

İşlenen veri kategorileri:
  - original_url (kaynak haberin <img src>'i — public URL)
  - alt_text, caption (HTML scrape, public DOM içeriği)
  - vlm_caption (NIM Llama 4 Maverick — Türkçe görsel açıklama)
  - ocr_text (görseldeki yazı, varsa)
  - depicts (politik figür / obje listesi, JSONB)
  - position (haber içi sıra)

İŞLEME AKIŞI (process & discard):
  1. ArticleImage row'dan original_url al
  2. HEAD check (404 → 'failed' status)
  3. RAM'e geçici download (max 5 MB, timeout 10s)
  4. NIM VLM API call → caption + ocr + depicts JSON
  5. DB UPDATE (vlm_caption, ocr_text, depicts, processed_at, status='processed')
  6. Image bytes DISCARD (Python GC + explicit del)

BİYOMETRİK DEĞİL:
  - Eski plan image_embeddings (1024-dim vector) — biyometrik tartışmaydı.
  - Yeni mimaride embedding YOK; sadece textual metadata.
  - depicts: kişi adı geçtiğinde admin /legal sayfasında attribution
    + 25 kelime alıntı limiti (FSEK md.35) zorunlu.
  - "Kişi X'tir" KESİN ifadesi yok — VLM prompt'ta "tanımıyorsan boş bırak"
    kuralı var.

Hukuki dayanak:
  - md.5/2-d: Alenileşmiş veri (haber sitesi tarafından yayınlanmış görsel)
  - md.5/2-f: Meşru menfaat (haber görseli analizi public DOM üstünden)
  - FSEK md.35: 25 kelime altı alıntı + kaynak gösterme

Saklama süresi:
  - original_url + metadata: article TTL ile aynı (90 gün cleaned)
  - Image bytes: SAKLANMIYOR (her zaman 0 bayt persistent storage)

Yurt dışı aktarım:
  - VLM provider (NVIDIA NIM, US) — DPA + free tier
  - Image bytes geçici (RAM'de) → NIM API → response → discard
  - Original URL kaynak haber sitesinde zaten public

Veritabanı tabloları:
  - article_images (#304 yeni şema):
      original_url, alt_text, caption, vlm_caption, ocr_text,
      depicts (JSONB), position, status, processed_at, created_at
  - image_embeddings, image_labels, image_analysis, entities tabloları
    KALDIRILDI (#304 PR-1 migration).

Kullanıcıya değer:
  - Generation response'da `suggested_image` field — kullanıcı X post'a
    uygun görseli görüp seçer. URL ile kaynaklanmış, attribution otomatik.
```

---

## 9. Aktivite #08 — Stil Profili (Faz 5)

```text
Amaç:
  Kullanıcının kendi yazı stilini sisteme tanıtması, içerik üretiminde
  bu stilde çıktı alması.

İşlenen veri kategorileri:
  - Style profile (rules JSON: sentence_length, tone, patterns)
  - Style samples (kullanıcının kendi yazıları, örnek metinler)
  - Style summary (LLM analyzer çıktısı)

ÖZEL DURUM:
  Sample text içinde PII olabilir (kullanıcının kendi tweetleri):
    - Diğer kişi mention'ları (@username)
    - Tarihler, yerler
    - Bahsedilen olaylar

PII redaction (Faz 5 zorunlu):
  Style sample DB'ye yazılmadan önce sanitize.
  Style analyzer LLM çağrısında ek redaction.

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası (kullanıcı talep etti)
  - md.5/2-a: Açık rıza (LLM analyzer)

Saklama süresi:
  - Aktif kullanıcı: sınırsız (kullanıcı silmedikçe)
  - Hesap silinince: derhal silinir

Veritabanı tabloları:
  - style_profiles
  - style_samples
```

---

## 10. Aktivite #09 — Faturalama ve Abonelik (Faz 6 — Lemon Squeezy MoR)

> **2026-05-08 revize (Epic [#448](https://github.com/selmanays/nodrat/issues/448)):** Eski plan (Iyzico TR yurt içi + e-Arşiv) reddedildi. **Lemon Squeezy (Merchant of Record, ABD)** seçildi. KVKK m.9 yurt dışı transfer açık rıza zorunlu ([#453](https://github.com/selmanays/nodrat/issues/453)). LS müşteriye fatura keser, KDV/VAT/sales tax compliance LS yönetir.

```text
Amaç:
  USD primary aylık/yıllık abonelik faturalandırması (Lemon Squeezy MoR
  hosted), refund LS portalda yönetilir.

İşlenen veri kategorileri (LS'ye giden):
  - Ad, soyad
  - E-posta
  - Fatura adresi (ülke, şehir, ZIP)
  - IP (anti-fraud)
  - Kart token (kart no/CVV LS'de PCI-DSS, BİZE GELMEZ)
  - Plan/variant bilgisi

Nodrat tarafında saklanan (LS'den dönen referanslar):
  - subscriptions: ls_subscription_id, ls_customer_id, ls_variant_id, seat_count
  - invoices: ls_invoice_id, ls_invoice_url (PDF link), amount_usd, tax_amount_usd
  - webhook_events: idempotency log

KART BİLGİSİ ASLA BİZDE TUTULMAZ — Lemon Squeezy PCI-DSS Level 1.

Hukuki dayanak:
  - md.5/2-c: Sözleşmenin ifası
  - md.9: Yurt dışı aktarım için AÇIK RIZA (LS US-based, KVKK m.9)

Yurt dışı aktarım:
  - Lemon Squeezy Inc. (US) — açık rıza + DPA + SCC
    - LS kendisi adresi, fatura, ödeme yöntemini işleyen veri sorumlusu/işleyen
    - LS müşteriye doğrudan fatura keser (Nodrat e-Arşiv kesmez)

Saklama süresi:
  - LS invoice referans cache: vergi mevzuatı uyarınca 10 yıl
    (gerçek invoice LS'de hosted; Nodrat sadece pointer + meta saklar)
  - subscriptions: aktif süresince + 5 yıl (audit)
  - webhook_events: 1 yıl (idempotency + debug)
  - Payment token: LS'de, Nodrat'ta sadece ls_customer_id ref

Veritabanı tabloları:
  - plans (USD primary, ls_variant_id mapping)
  - subscriptions (ls_subscription_id, ls_customer_id, seat_count)
  - invoices (LS referans cache)
  - webhook_events (idempotency, #450)
  - agency_seats (multi-seat agency, #451)
```

---

## 11. Aktivite #10 — Email İletişimi

```text
Amaç:
  Transactional (verify, password reset, invoice) ve opsiyonel
  pazarlama e-postası.

İşlenen veri kategorileri:
  - E-posta adresi
  - Email içerik (template + dynamic data)
  - Gönderim ve açılma logları (analytics)
  - Marketing consent durumu

Hukuki dayanak:
  - md.5/2-c: Transactional → sözleşmenin ifası
  - md.5/2-a: Marketing → açık rıza (ayrı checkbox)

Yurt dışı aktarım:
  - Resend / Postmark (US) — açık rıza + DPA
  - Tek tıkla unsubscribe link her marketing emailde

Saklama süresi:
  - Email log: 1 yıl
  - Marketing consent: kullanıcı geri çekene kadar

Veritabanı tabloları:
  - users (marketing_consent_at)
  - email_logs (Faz 6'da eklenebilir)
```

---

## 12. Aktivite #11 — Analytics ve Ürün Geliştirme

```text
Amaç:
  Ürün kullanım metriklerini ölçme, North Star (WSGAU) takip.

İşlenen veri kategorileri:
  - Event log (sayfa görüntüleme, generate başlat, save, vs.)
  - Anonim/pseudonym kullanıcı ID
  - User agent, language, device type
  - Funnel ve cohort verisi

PSEUDONYMIZATION:
  PostHog veya self-host analytics → kullanıcı email YOK,
  sadece UUID. Cross-reference admin'de mümkün.

Hukuki dayanak:
  - md.5/2-f: Meşru menfaat (ürün geliştirme)
  - md.5/2-a: Açık rıza (cookie banner aracılığıyla)

Yurt dışı aktarım:
  - PostHog self-host: yok (Türkiye VPS)
  - Plausible self-host: yok

Saklama süresi:
  - Event log: 18 ay
  - Cohort data: 5 yıl (anonim)

Veritabanı / sistem:
  - PostHog self-host (Architecture §10.2)
  - usage_events tablosu (sub-set)
```

---

## 13. Aktivite #12 — Yasal Uyum ve Audit Log

```text
Amaç:
  Tüm admin actions ve kritik işlemler için audit trail tutmak.

İşlenen veri kategorileri:
  - admin_audit_log:
    - Actor (admin user_id)
    - Action (source.create, user.delete, etc.)
    - Target (entity_id)
    - Metadata (JSONB)
    - IP address
    - User agent
    - Timestamp

Hukuki dayanak:
  - md.5/2-ç: Yasal yükümlülük (KVKK md.12 güvenlik)
  - md.5/2-f: Meşru menfaat (incident investigation)

Saklama süresi:
  - 1 YIL (yasal minimum + güvenlik)
  - KVK Kurul talep ederse derhal teslim

Yurt dışı aktarım: Yok (sadece kendi sistemimizde)

Güvenlik:
  - Append-only (immutable)
  - Backup'a dahil
  - Sadece super_admin görebilir

Veritabanı tabloları:
  - admin_audit_log
```

---

## 14. Veri Sahibi Hakları (KVKK md.11)

Kullanıcı/veri sahibi şu haklara sahiptir:

```text
1. Bilgi alma hakkı
   - Hangi verileri işliyoruz?
   - Endpoint: GET /app/me/data-export

2. Düzeltme hakkı
   - Yanlış kişisel veri düzeltme
   - Endpoint: PATCH /app/me

3. Silme hakkı (unutulma)
   - Hesap silme
   - Endpoint: DELETE /app/me (30g soft → hard)
   - Haberlerdeki kişi: /legal/privacy-request

4. Veri taşınabilirlik
   - JSON export
   - Endpoint: GET /app/me/data-export

5. İtiraz hakkı
   - Otomatik karar verme + profilleme
   - Nodrat'ta: stil profili kullanıcı kontrolünde

6. KVK Kurul'a başvuru
   - İhlal durumunda (legal@nodrat.com → çözülmezse Kurul)
```

Tüm haklar **30 gün içinde** cevaplanır (KVKK md.13).

---

## 15. Güvenlik Önlemleri (Cross-cutting)

KVKK md.12 uyarınca:

```text
Teknik:
  - Şifreleme: TLS 1.2+, Argon2id, Fernet (provider keys)
  - Erişim kontrolü: JWT + role + ownership check
  - Audit log: 1 yıl
  - Backup: B2 encrypted (restic + age)
  - Rate limiting: tier'a göre
  - PII redaction: LLM çağrısı öncesi
  - 2FA: admin için zorunlu (Faz 6)
  - Network izolasyonu: Caddy → API → DB
  - DB connection encryption

İdari:
  - DPO outsource (KVKK uzmanı)
  - Çalışan gizlilik taahhütü
  - Yıllık KVKK eğitimi
  - Incident response runbook (72h)
  - ROPA aktif (bu doküman)

Fiziksel:
  - VPS sağlayıcı (Contabo, Almanya — AB GDPR kapsamında) ISO 27001
  - Backup off-server (MVP-1: Backblaze B2 / MVP-1.5+: Contabo Object Storage,
    AB region — aynı sağlayıcı içi transfer)
```

---

## 16. Yurt Dışı Aktarım Özet Tablosu

| Veri | Provider | Ülke | Hukuki dayanak | DPA | SCC |
|---|---|---|---|---|---|
| Prompt + output (PII redacted) | DeepSeek | HK | Açık rıza | ⏳ | ⏳ |
| Prompt + output (PII redacted) | Anthropic | US | Açık rıza | ⏳ | ⏳ |
| Prompt + output (PII redacted) | OpenRouter | US | Açık rıza | ⏳ | ⏳ |
| Embedding query | NVIDIA NIM | US | Açık rıza | ⏳ | ⏳ |
| Email | Resend / Postmark | US | Açık rıza | ⏳ | ⏳ |
| Payment + fatura | Lemon Squeezy MoR | US (Faz 6, Epic #448) | KVKK m.9 açık rıza + DPA + SCC | ⏳ #453 | ⏳ #49 |
| Backup (MVP-1, retired 2026-05-06) | Backblaze B2 | US | Meşru menfaat | ✅ | ✅ |
| Backup (MVP-1.5, ✅ active 2026-05-06) | **Contabo Object Storage** | DE (AB) | Meşru menfaat | ✅ | N/A — AB içi |
| Hosting (MVP-1.5, ✅ active 2026-05-06) | **Contabo Cloud VPS 40 NVMe** | DE (AB) | Meşru menfaat | ✅ | N/A — AB içi |
| Cold tier (raw_html ≥ 30 gün, MVP-1.5) | Contabo Object Storage | DE (AB) | Meşru menfaat | ✅ | N/A — AB içi |
| Analytics | PostHog (self-host) | TR | — | — | — |

⏳ = Faz 0 sonu hedefli, DPO ile birlikte tamamlanacak

---

## 17. Açık İşler ve TODO

```text
[ ] Şirket kuruluşu (Limited Şti.) — vergi no, MERSIS
[ ] DPO/KVKK uzmanı seçimi + sözleşme imza
[ ] Tüm provider'larla DPA imza
[ ] SCC dokümanlarının provider tarafından sağlanması
[ ] Email provider (Resend) DPA
[ ] PII redaction modülü implementasyon (Architecture)
[ ] takedown_requests tablosu + endpoint canlı
[ ] Veri sahibi başvuru akışı (DELETE /app/me, GET /app/me/data-export)
[ ] Cookie banner consent management
[ ] Marketing consent ayrı checkbox
[ ] VERBİS yükümlülük değerlendirmesi (1K+ user)
[ ] Yıllık ROPA review takvimi (DPO ile)
[ ] Çalışan gizlilik taahhüdü şablonu
[ ] Backup encryption test (restore drill)
```

---

## 18. Çapraz Referans

```text
Tüm veri tabloları         → engineering/data-model.md
PII redaction              → legal/opinion-integration.md §3.1
Yurt dışı transfer         → legal/compliance-brief.md §2.3 M4
Veri sahibi başvuru        → engineering/api-contracts.md (privacy-request endpoint)
Audit log                  → engineering/data-model.md §5.4
Saklama süreleri           → engineering/data-model.md §12.2
Güvenlik önlemleri         → engineering/threat-model.md §5
Incident response          → legal/incident-response.md
DPO sözleşme               → legal/dpo-contract-template.md
```

---

**Sonuç:** 12 veri işleme aktivitesi envanterli; her biri için **amaç + hukuki dayanak + alıcı + saklama + güvenlik** dokümante. **Yurt dışı transfer en hassas alan** (LLM provider'lar) — açık rıza + DPA + SCC + **PII redaction** üçlüsü zorunlu. **Hassas özel nitelikli veri** (haberlerdeki politikacı/sanatçı/sağlık) için "alenileşmiş" istisnasına dayanılıyor; itiraz halinde unutulma akışı `privacy-request` endpoint'iyle. **Yıllık review** DPO sorumluluğunda, KVK Kurul incelemesi durumunda derhal teslim edilebilir formatta.
