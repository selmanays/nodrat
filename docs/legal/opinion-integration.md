# Nodrat — Avukat Ön-Görüşü Entegrasyonu

**Doküman türü:** Legal Opinion Integration (Avukat tavsiyeleri → ürün aksiyonu eşleme)
**Sürüm:** v0.1
**Tarih:** 2026-05-01
**Bağımlılık:** Tüm P0 + P1 dokümanları
**Hedef:** Bilişim hukuku avukatından gelen ön-görüşü mevcut dokümantasyona entegre etmek; yeni gereksinimleri net listelemek; production launch öncesi uyum checklist'ini netleştirmek.

---

## 0. Yönetici Özeti

```text
Avukat görüşünün durumu:
  ✅ Tavsiyelerinin %85'i mevcut dokümantasyonda zaten yer alıyor
  🔴 %15 yeni teknik/operasyonel gereksinim çıkardı

Yeni kritik gereksinimler (3 ana başlık):
  1. PII redaction layer — LLM'e giden payload'da kullanıcı PII otomatik
     temizlenmeli (yeni teknik component)
  2. 4 ayrı takedown endpoint — abuse, takedown, copyright, privacy-request
     (mevcut: 1)
  3. Avukat-onaylı standart copy — generation result, insufficient data,
     veri kullanım, ToS pozisyon cümleleri için tek kaynak

Pozisyon kuralı (cross-cutting):
  "Nodrat HABER KAYNAĞI DEĞİLDİR.
   Nodrat, kamuya açık kaynaklara dayalı içerik üretim ve doğrulama
   destek aracıdır."
  
  Bu cümle landing page, ToS, marka iletişimi ve pricing'de görünür
  olmalı; "haber yayıncısı / haber sitesi" pozisyonundan kaçınılmalı.

Decision lock'ları (avukat onaylı):
  D-LGL-01  Tam haber metni internal RAG'de tutulur, kullanıcıya gösterilmez
  D-LGL-02  Direct quote 25 kelime hard cap (prompt + output validator)
  D-LGL-03  Robots.txt ihlali → ZERO TOLERANCE, admin override yok
  D-LGL-04  Paywall / login arkası kaynak → HARD BAN
  D-LGL-05  Yaş gate 18+ (16+ değil)
  D-LGL-06  Yurt dışı transfer için açık rıza ZORUNLU + ayrı checkbox
  D-LGL-07  PII redaction katmanı LLM çağrısı öncesi ŞART
  D-LGL-08  Takedown 24h SLA + audit log
  D-LGL-09  KDV dahil fiyat + 14 gün iade (paid launch öncesi)
  D-LGL-10  Marka pozisyonu: "haber kaynağı değil, üretim aracı"
```

---

## 1. Avukat Görüşü — 12 Başlık Özeti

```text
1.  Genel hukuki pozisyon → "Üretim aracı" konumlanması
2.  KVKK 3 katmanlı veri (kullanıcı, haber kişi, görsel)
3.  DPO outsource + VERBİS 1K+ kullanıcıda gönüllü
4.  Yurt dışı LLM transfer → açık rıza + DPA + PII redaction
5.  FSEK telif → tam metin internal, kullanıcıya gösterme + 25 kelime cap
6.  Robots.txt → sıfır tolerans + standart UA
7.  5651 → 4 takedown endpoint + 24h SLA
8.  LLM output liability → 3 katmanlı savunma (technical + UI + ToS)
9.  Görsel/biyometrik → process & discard mimarisi (#304 MVP-1.4):
    bytes saklanmaz, sadece NIM VLM metadata. depicts entity'sinde
    politik figür → admin /legal attribution + 25 kelime alıntı cap.
    Embedding YOK (biyometrik tartışması ortadan kalktı).
10. Çocuk koruması → 18+ hard gate
11. Vergi/e-Fatura → KDV dahil + 14 gün iade
12. Karar logu → 12 D1-D12 noktası avukat onaylı
```

---

## 2. Delta Analizi (NEW vs ALREADY HAVE)

### 2.1 ✅ Mevcut dokümantasyonda zaten olan (avukat doğruladı)

| Konu | Doküman + Bölüm |
|---|---|
| KVKK 3 katmanlı veri ayrımı | Legal §2.1 |
| DPO outsource yıl 1 | Legal §2.4 D1, Risk Register §7 |
| VERBİS 1K+ gönüllü kayıt | Legal §10.3 |
| Açık rıza + SCC + DPA | Legal §2.3 M4 |
| Tam metin DB'de saklanır, user'a gösterilmez | Legal §3.3 M2, Risk §3.1 |
| 25 kelime quote cap | Legal §3.3 M1 |
| Robots.txt sıfır tolerans | Legal §4 D9, Risk §3.4 |
| Paywall ban | Legal §4 D11 |
| 18+ yaş gate | Legal §7.4 |
| ToS sorumluluk transferi | Legal §6.2 M3 |
| Audit log 1 yıl | Threat §9 |
| Halüsinasyon prompt kuralları | PRD §12.4, Prompt Contracts §1.2 |
| Source ekleme robots.txt check | API §4.1 |
| Cyber sigorta Faz 6+ | Legal §10.3 |

### 2.2 🔴 Yeni gereksinimler (avukat ekledi, dokümana ekleyeceğiz)

| ID | Gereksinim | Hangi doküman güncellendi |
|---|---|---|
| N-01 | **PII redaction layer** prompt öncesi | Prompt Contracts §1.5 (yeni alt-bölüm) |
| N-02 | **4 ayrı takedown endpoint** | API Contracts §22 (yeni bölüm) |
| N-03 | **Specific User-Agent** `NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)` | Architecture §3, Legal §4.2 |
| N-04 | **5-item source admin checklist** | UX Wireframes §8, API §4.1 |
| N-05 | **Register 4 checkbox** (3 değil): KVKK, kullanıcı veri işleme, yurt dışı, pazarlama | UX Wireframes §7, API §3.1 |
| N-06 | **Generation result UI uyarısı** standart copy | Design System §5.3 (yeni) |
| N-07 | **Hassas kişi/siyasi figür ekstra kontrol** prompt step | Prompt Contracts §4.3 |
| N-08 | **Pricing display rule**: "KDV dahildir. İlk 14 gün iade." | Pricing Strategy §7.1 |
| N-09 | **Pozisyon ifadesi**: "Nodrat haber kaynağı değildir" landing/ToS/marka | Competitive §5, Design System §1.3 |
| N-10 | **Stil profili ham metin** prompt'a göndermeden önce sanitize | Prompt Contracts §5.1 |
| N-11 | **takedown_requests** veritabanı tablosu | Data Model §3.x (yeni) |
| N-12 | **Sensitive entity registry** (politik figür, dini lider, vb.) | Data Model entities tablosu sensitivity_flag (mevcut) |

### 2.3 🟡 Vurgu güçlendirilmesi gereken (mevcut ama netleştirilecek)

| Konu | Aksiyon |
|---|---|
| "Haber kaynağı değil" pozisyon | Tüm marka iletişimi + ToS + landing'de net cümle |
| Her output kaynak listesi taşır | Prompt Contracts'a hard rule |
| Paywall hard ban | Source addition flow'da extra check |
| 25 kelime cap | Output validator'a otomatik kontrol |
| Hassas veri filtresi | KVKK uyumu için politik/dini/sağlık flag |

---

## 3. Yeni Teknik Gereksinimler — Detay

### 3.1 N-01: PII Redaction Layer (KRİTİK)

```text
KAPSAM:
  Her LLM provider çağrısından önce, prompt payload'unda
  PII (kişisel tanımlanabilir bilgi) otomatik maskelenir.

MASKELENECEK ALANLAR:
  - User email
  - User full_name
  - User IP address
  - Account ID / user UUID (eğer prompt'a sızdıysa)
  - Ödeme bilgisi (token referansı bile dahil değil)
  - Generation history içindeki diğer kullanıcı verisi
  - Style profile sample text içindeki PII

UYGULAMA YERİ:
  Yer:        provider katmanı, Provider.generate_text() öncesi
  Sıra:       request → prompt build → pii_redaction → provider call
  Library:    presidio-analyzer (open-source, MIT) tercih edilir
              veya regex tabanlı internal pii.py modülü

REGEX SET (minimum MVP):
  email:       \b[\w.-]+@[\w.-]+\.\w+\b
  TR phone:    \b(\+90|0)?\s?\(?\d{3}\)?\s?\d{3}\s?\d{2}\s?\d{2}\b
  IP:          \b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b
  TC kimlik:   \b\d{11}\b (luhn check)
  IBAN:        \bTR\d{24}\b
  UUID:        \b[\da-f]{8}-[\da-f]{4}-...\b

REPLACEMENT:
  email     → "[email_redacted]"
  phone     → "[phone_redacted]"
  IP        → "[ip_redacted]"
  TC        → "[id_redacted]"
  IBAN      → "[iban_redacted]"
  UUID      → "[ref_redacted]"

LOG:
  Redaction sayısı + tipi loglanır (hangi field'da kaç PII vardı)
  Bu metric monitoring'de tracked → Risk Register R-LGL-01

EDGE CASES:
  - Kullanıcı kendi prompt'unda email yazıyorsa redact (kasıtlı bile olsa)
  - Stil profili ham metin → sanitize before storage
  - Article content (haber metni) PII içerir mi? → Hayır, public alenileşmiş;
    redaction sadece KULLANICI tarafından gelen prompt'a uygulanır

POSTGRES TRİGGER (ek koruma):
  generations.request_text WRITE öncesi soft sanitize (PII flag)
```

### 3.2 N-02: 4 Takedown Endpoint

```text
ENDPOINTS (yeni):

POST /legal/abuse
  Genel kötüye kullanım bildirimi
  
POST /legal/takedown
  İçerik kaldırma talebi (5651)
  
POST /legal/copyright
  Telif hakkı bildirimi (FSEK)
  
POST /legal/privacy-request
  KVKK kapsamında veri silme/erişim/düzeltme talebi

ORTAK ŞEMA:
  request_type, requester_name, requester_email, organization,
  authority_claim, target_url_or_id, reason_category, description,
  evidence_attachment, declaration_truth (boolean)

İŞLEYİŞ:
  1. Submit → ticket ID otomatik oluşur (TKD-2026-001234 format)
  2. Email confirm: requester'a + admin'e
  3. takedown_requests tablosuna yazılır
  4. Admin /admin/legal-requests'te 24 saat SLA görünür
  5. Açık ihlal varsa içerik pasife alınır (status=quarantined)
  6. Resolution: removed | rejected | partial | escalated
  7. Audit log + email notification

STATE MACHINE:
  submitted → triaging → investigating → action_taken | rejected
  Her durum geçişinde audit log + email
```

### 3.3 N-03: Specific User-Agent

```text
ESKI:
  "Nodrat-Bot/1.0; +https://nodrat.com/bot"
  
YENİ (avukat onaylı):
  "NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)"

KOD YERİ:
  /packages/crawler-core/http_client.py
  Tüm scraper request'lerinde header zorunlu
  
HEADER EKLE:
  User-Agent: NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)
  From: legal@nodrat.com  (RFC 2616 § 14.22 transparency)
  Accept-Language: tr-TR,tr;q=0.9
  
LANDİNG /bot SAYFASI (yeni):
  https://nodrat.com/bot
  İçerik:
    - Nodrat'ın ne olduğu
    - Hangi User-Agent kullandığı
    - Hangi sıklıkta crawl yaptığı
    - Robots.txt uyumu
    - İletişim: legal@nodrat.com
    - Opt-out talimatı (kaynak çıkarma talebi)
```

### 3.4 N-04: Source Admin 5-Item Checklist

```text
/admin/sources/new ekranında ZORUNLU:

[ ] robots.txt kontrol edildi ve disallow yok
[ ] Kaynak paywall arkasında DEĞİL
[ ] Kullanım şartları (ToS) okundu, scraping yasaklanmamış
[ ] Kaynak kamuya açık sayfalardan oluşuyor (login gerekmiyor)
[ ] Bu kaynak için ticari kullanım riski değerlendirildi

API'de:
  POST /admin/sources body'sine eklenir:
    "compliance_checklist": {
      "robots_txt_compliant": true,
      "no_paywall": true,
      "tos_reviewed": true,
      "public_only": true,
      "commercial_risk_assessed": true,
      "assessed_by": "<user_id>",
      "assessed_at": "<iso>"
    }

Beşi de TRUE olmadan source.is_active = TRUE OLMAZ.
Audit log'a yazılır (admin_audit_log).
```

### 3.5 N-05: Register Flow — 4 Checkbox

```text
ESKİ (UX Wireframes §7):
  [ ] Üyelik koşullarını + gizlilik
  [ ] Yurt dışı veri transferi
  [ ] Marketing (opsiyonel)

YENİ (avukat onaylı, 4 ayrı):
  [ ] KVKK Aydınlatma Metni'ni okudum.                              (zorunlu)
  [ ] Kişisel verilerimin hizmetin sunulması için işlenmesini       (zorunlu)
      kabul ediyorum.
  [ ] Yurt dışındaki yapay zekâ servis sağlayıcılarına sınırlı      (zorunlu)
      veri aktarımını kabul ediyorum.
  [ ] Pazarlama iletileri almak istiyorum.                          (opsiyonel)

KRİTİK KURAL:
  "Pazarlama rızası zorunlu rıza ile aynı kutuda olamaz."
  Ayrı UI element + gerçek opsiyonellik.

API:
  POST /auth/register body:
    {
      "kvkk_aydinlatma_consent": true,
      "data_processing_consent": true,
      "foreign_transfer_consent": true,
      "marketing_consent": false,
      ...
    }
  Üç zorunlu çekbox FALSE ise 400 VALIDATION_ERROR.

Database (users tablosu — Data Model §2.1):
  Mevcut alan eşlemesi:
    kvkk_consent_at              ← KVKK aydınlatma + işleme (combined)
    foreign_transfer_consent_at  ← yurt dışı (zaten var)
    marketing_consent_at         ← pazarlama (zaten var)

  Önerilen: kvkk_consent_at'i ikiye böl:
    kvkk_acknowledgment_at       ← aydınlatma okundu
    data_processing_consent_at   ← veri işleme rızası
```

### 3.6 N-06: Generation Result UI Uyarısı

```text
HER GENERATION RESULT EKRANINDA görünür:

Standart durum (default):
  ⚠️ Bu içerik kaynaklara dayanarak üretildi.
     Yayınlamadan önce kaynakları kontrol et.

Hassas konu (siyaset, sağlık, suç isnadı, kişilik hakları):
  ⚠️ Bu çıktı kişi veya kurum hakkında iddia içerebilir.
     Yayınlamadan önce kaynakları ayrıca doğrula.

Hassas konu nasıl tespit edilir:
  - Output text'inde sensitive_entity_list ile match
    (politik figür, kamu görevlisi, yargılanan kişi adı)
  - Konu kategorisi: politika, sağlık, hukuk, suç
  - Provider safety classifier sinyali
```

### 3.7 N-07: Hassas Entity Prompt Kuralı

```text
PROMPT CONTRACTS §4 Content Generator EKLENECEK:

KESİN KURAL (madde 16):
  Eğer agenda_cards veya supplementary_chunks içinde hassas entity
  geçiyorsa (sensitivity_flag != NULL — Data Model entities tablosu),
  şu kurallara uy:
  
  1. O kişi/kurum hakkındaki iddiaları SADECE kaynakta açık
     ifadeyle yer alıyorsa kullan.
  2. Yorum, çıkarsama, tahmin yapma.
  3. "Muhtemelen", "büyük olasılıkla" gibi belirsizlik ifadeleri
     bile kaçın — ya kaynakta var ya yok.
  4. Tek kaynak iddiaları "iddia edildi", "açıklandı" gibi attribuasyon
     ile sun, kesin olgu olarak değil.
  5. Output'ta warnings array'ine "sensitive_entity_present" ekle.

Sensitivity flag tipleri (Data Model entities):
  political_figure | religious_leader | health_individual |
  ethnic_subject  | minor             | judicial_subject
```

### 3.8 N-08: Pricing Display Rule (USD primary — Lemon Squeezy MoR, Epic #448)

```text
PRICING SAYFASINDA her tier altında:

Aylık fiyat:    "$24 / ay" (USD primary, ~749 TL display ref)
Vergi bilgisi:   "KDV / VAT Lemon Squeezy tarafından kesilir." (MoR)
İade hakkı:      "İlk 14 gün içinde iade edilebilir." (LS hosted refund)

ÇIKTI ÖRNEK:
  Pro
  $24 / ay
  (~749 TL anlık FX)
  ─────────
  Vergi LS tarafından kesilir.
  İlk 14 gün içinde iade edilebilir.
  Aboneliği istediğin zaman LS portaldan iptal et.

  [Pro'ya Geç]

UYARI:
  Bu kural Lemon Squeezy MoR yapısı için yazılmıştır.
  TL fiyatı sadece display referansıdır — fiili charge USD.
  Eski TR-only Iyzico/e-Arşiv kuralı 2026-05-08 Epic #448 ile reddedildi.
```

### 3.9 N-09: Lemon Squeezy MoR Uyum Kontrolü (yeni — Epic #448)

```text
AVUKAT REVIEW SIRASINDA EK ONAY GEREKLİ:

[ ] LS Merchant of Record yapısı KVKK ve TR e-ticaret hukuku
    açısından uygun mudur?
[ ] LS müşteriye fatura keser → Veri Sorumlusu (Nodrat) e-Arşiv
    yükümlülüğünden muaf mı? (Mali müşavir + avukat çapraz onayı)
[ ] LS DPA + SCC dosyaları KVKK m.9 + GDPR Schrems II için yeterli
    güvence sağlıyor mu?
[ ] Trial/checkout akışında "LS (ABD) açık rıza" checkbox'ı (m.9)
    server-side enforced — ToS ile uyumlu mu?
[ ] LS hosted refund flow + 14 gün cayma hakkı TR e-ticaret kanunu
    uyumlu mu?
[ ] LS account closure / payout delay senaryosu için fallback plan
    gerekli mi (R-FIN-04)?
```

---

## 4. Pozisyon Kuralı — Cross-Cutting

### 4.1 Marka pozisyonu (avukat onaylı)

```text
KULLAN:
  ✓ "Kaynaklı içerik üretim ve doğrulama destek aracı"
  ✓ "Kamuya açık kaynaklara dayalı üretim motoru"
  ✓ "Türkçe gündem üzerinden RAG SaaS"
  ✓ "İçerik üretim ve araştırma yardımcısı"

KAÇIN:
  ✗ "Haber sitesi"
  ✗ "Haber kaynağı"
  ✗ "Haber yayıncısı"
  ✗ "Medya platformu"
  ✗ "Editorial publisher"
```

### 4.2 ToS / Privacy / Landing'de zorunlu cümleler

```text
LANDING + ToS açılış:
  "Nodrat bir haber yayıncısı değildir.
   Hizmet, kullanıcının içerik üretim ve araştırma sürecini
   destekleyen bir yazılım aracıdır."

ToS — kullanıcı sorumluluğu maddesi:
  "Kullanıcı, Nodrat tarafından önerilen içerikleri yayınlamadan
   önce doğrulamak, hukuka uygunluğunu değerlendirmek ve gerekli
   kaynak atıflarını korumakla sorumludur."

Generation result kaynaklı uyarı:
  "Nodrat kamuya açık kaynaklardan elde edilen bilgileri özetler
   ve kaynak bağlantılarıyla birlikte sunar. Haber metinlerinin
   tamamını yeniden yayınlamaz."

Kullanıcı sorumluluğu (UI):
  "Kullanıcı, Nodrat tarafından üretilen içerikleri yayınlamadan
   önce kontrol etmekle yükümlüdür. Nodrat çıktıları otomatik öneri
   niteliğindedir; hukuki, editoryal veya gazetecilik doğrulaması
   yerine geçmez."
```

---

## 5. Avukat-Onaylı Standart Copy Library

Bu kütüphane Design System'in §5'ine eklenecek; tüm UI'da bu varyantlar kullanılacak.

### 5.1 Generation result uyarıları

```text
Standart:
  "⚠️ Bu içerik kaynaklara dayanarak üretildi.
   Yayınlamadan önce kaynakları kontrol et."

Hassas konu:
  "⚠️ Bu çıktı kişi veya kurum hakkında iddia içerebilir.
   Yayınlamadan önce kaynakları ayrıca doğrula."

Halüsinasyon flag sonrası:
  "Bu üretim halüsinasyon olarak işaretlendi. İçerik review için
   admin'e iletildi. Yayınlamamanı öneririz."
```

### 5.2 Veri yetersizliği (avukat onaylı kelime seçimi)

```text
"Bu konu için yeterli güvenilir kaynak bulunamadı.
 Yanlış yönlendirmemek için içerik üretmedik.
 
 Bulduğumuz: [N] kaynak, [M] gündem kartı
 Gereken: en az 2 gündem kartı veya 3 haber
 
 Şunları deneyebilirsin:
 ⏱️  Zaman aralığını genişlet
 🔍 Konuyu daha geniş yaz
 🔄 Yeni bir konu dene
 
 Bu üretim quota'ndan DÜŞÜLMEDİ."
```

### 5.3 Kaynak kullanımı açıklaması

```text
About / How it works / FAQ:
  "Nodrat kamuya açık kaynaklardan elde edilen bilgileri özetler
   ve kaynak bağlantılarıyla birlikte sunar. Haber metinlerinin
   tamamını yeniden yayınlamaz."

Generation result açıklama:
  "Bu üretim {N} kaynak ve {M} gündem kartı kullandı.
   Tam haber metinleri Nodrat'ta saklanmaz; sadece kaynaklı
   özet ve kaynak linkleri."
```

### 5.4 Kullanıcı sorumluluğu (multi-konum)

```text
ToS § Sorumluluk:
  "Kullanıcı, Nodrat tarafından önerilen içerikleri yayınlamadan
   önce doğrulamak, hukuka uygunluğunu değerlendirmek ve gerekli
   kaynak atıflarını korumakla sorumludur. Nodrat çıktıları
   otomatik öneri niteliğindedir; hukuki, editoryal veya gazetecilik
   doğrulaması yerine geçmez."

Settings → "Hukuki uyarılar":
  "Yayınlamadan önce her zaman kaynakları doğrula.
   Halüsinasyon olduğunu düşündüğün üretimi 'Halüsinasyon' butonuyla bildir."

Footer (her sayfada):
  "Nodrat bir haber yayıncısı değildir. Üretilen içerik kullanıcı
   sorumluluğundadır."
```

### 5.5 KVKK / Privacy mesajları

```text
Cookie banner:
  "Nodrat zorunlu çerezleri kullanır.
   Analytics ve pazarlama çerezleri opsiyoneldir.
   [Sadece zorunlu] [Hepsini kabul et] [Detaylar]"

Register flow (avukat metni — değişmez):
  ☐ KVKK Aydınlatma Metni'ni okudum.
  ☐ Kişisel verilerimin hizmetin sunulması için işlenmesini
    kabul ediyorum.
  ☐ Yurt dışındaki yapay zekâ servis sağlayıcılarına sınırlı
    veri aktarımını kabul ediyorum.
  ☐ Pazarlama iletileri almak istiyorum. (opsiyonel)

Settings → Hesabımı Sil:
  "Hesabını silmek için bu işlemi onaylaman gerekir.
   Verilerin 30 gün içinde kalıcı olarak silinecektir.
   Bu süre içinde geri çekme talebi gönderebilirsin.
   Kaydedilmiş üretimlerin de silinir."
```

### 5.6 Pricing / Refund

```text
Tier card altında:
  "KDV dahildir.
   İlk 14 gün içinde iade edilebilir."

Cancel akışı:
  "Aboneliğin iptal ediliyor.
   Pro avantajları {date} sonuna kadar geçerli kalacak.
   İade hakkın varsa otomatik olarak hesabına iade edilir."

Refund policy sayfası (/legal/refund-policy):
  "Yıllık abonelik:
   - Satın alma sonrası 14 gün içinde tam iade hakkı
   - 14 günden sonra iade yapılmaz
   
   Aylık abonelik:
   - Cayma süresi yoktur (kullanılmış)
   - Sonraki yenileme öncesi iptal edilebilir"
```

### 5.7 Source kaldırma (DMCA-style)

```text
/legal/abuse, /legal/takedown, /legal/copyright sayfası:
  "Bu form, Nodrat üzerinde yer alan bir içerik veya kaynak
   ile ilgili hak ihlali bildirmek içindir.
   
   Başvurun 24 saat içinde değerlendirilecek.
   Açık ihlal tespit edilirse içerik kaldırılacak.
   
   Acil durumlar (kişilik hakları, hayati risk) için:
   legal@nodrat.com"
```

---

## 6. Doküman Güncelleme Matrisi

| Doküman | Güncelleme tipi | Değişen bölüm |
|---|---|---|
| `legal/compliance-brief.md` | v0.2'ye bump | §13 Avukat ön-görüş eklenti, PII redaction, 4 endpoint |
| `engineering/prompt-contracts.md` | Major | §1.5 PII redaction (yeni), §4 hassas entity kuralı (madde 16) |
| `engineering/api-contracts.md` | Major | §22 Legal Endpoints (yeni 4 endpoint), §4.1 source compliance checklist |
| `design/ux-wireframes.md` | Medium | §7 register 4 checkbox, §3 result page warning, §8 source admin checklist |
| `design/design-system.md` | Medium | §5 Copy library — avukat-onaylı varyantlar |
| `engineering/data-model.md` | Small | takedown_requests tablosu (yeni) |
| `engineering/architecture.md` | Small | §3 PII redaction module |
| `engineering/threat-model.md` | Small | §4 yurt dışı transfer'de PII redaction |
| `strategy/pricing-strategy.md` | Small | §7.1 KDV + 14 gün display rule |
| `strategy/risk-register.md` | Status | R-LGL-01, R-LGL-02 mitigation status: in-progress → review_complete |

---

## 7. Updated Risk Register Status

```text
R-LGL-01 KVKK ihlali (Skor 9 → hedef 4)
  Mitigation status: ⏳ → 🟡 (avukat review tamamlandı)
  Eksik: KVKK aydınlatma metni final dili, ROPA dokümanı, DPO outsource sözleşme
  
R-LGL-02 Telif (FSEK) (Skor 12 → hedef 6)
  Mitigation status: ⏳ → 🟡
  Eksik: Output validator (25 kelime cap kontrolü), gazete partnership Q3 plan
  
R-LGL-03 Robots.txt (Skor 8 → hedef 4)
  Mitigation status: ⏳ → 🟢 (admin override hard-block kararı net)
  Eksik: Implementation
  
R-LGL-11 Yurt dışı transfer (Skor 8 → hedef 4)
  Mitigation status: ⏳ → 🟡
  Eksik: PII redaction layer implementation, DPA template, SCC dosyaları
  
R-PRD-01 Halüsinasyon liability (Skor 9 → hedef 4)
  Mitigation status: ⏳ → 🟡
  Eksik: Specific UI warning copy, sensitive entity prompt rule, ToS final
```

---

## 8. Faz 0 Sonu Checklist (Pre-Code)

```text
[ ] Avukat ön-görüşü teslim alındı (✓ tamamlandı)
[ ] Bu doküman yayınlandı (legal-opinion-integration.md)
[ ] DPO outsource KVKK uzmanı seçildi
[ ] ROPA hazırlandı (veri envanteri)
[ ] Veri saklama süreleri tablosu (Data Model §12.2)
[ ] Provider listesi + DPA durumu
[ ] İhlal bildirim prosedürü dokümante (Threat §6)
[ ] PII redaction modülü tasarlandı
[ ] /legal/* sayfa wireframe'leri onaylı
```

---

## 9. Faz 1 Sonu Checklist (Pre-Public Launch)

```text
ZORUNLU (avukat onaylı):
[ ] /legal/terms — yayında (avukat final review)
[ ] /legal/privacy — yayında
[ ] /legal/kvkk-aydinlatma — yayında
[ ] /legal/cookies — yayında
[ ] /legal/scraping-policy — yayında
[ ] /legal/abuse — endpoint canlı
[ ] /legal/takedown — endpoint canlı
[ ] /legal/copyright — endpoint canlı
[ ] /legal/privacy-request — endpoint canlı
[ ] /bot — landing sayfası (User-Agent transparency)
[ ] Cookie banner aktif (privacy-preserving default)
[ ] Register 4 checkbox akışı (avukat copy)
[ ] Robots.txt parser zorunlu source ekleme
[ ] Source admin 5-item checklist
[ ] PII redaction layer aktif
[ ] Audit log mandatory tüm admin actions
[ ] takedown_requests tablosu + admin paneli
[ ] Generation result UI uyarısı (standart + hassas)
[ ] Output validator: 25 kelime quote cap
[ ] Sensitive entity prompt rule aktif
[ ] User-Agent: NodratBot/1.0 (...)
[ ] Veri indirme + Hesap silme akışı
[ ] 18+ yaş gate

ÖNERİLİR:
[ ] Penetration test (light, internal)
[ ] Source kaldırma (opt-out) prosedür dokümante
```

---

## 10. Faz 6 Paid Launch Checklist

```text
ZORUNLU:
[ ] e-Arşiv fatura entegrasyonu
[ ] Mali müşavir + ticari yapı netleşti
[ ] KDV dahil pricing display
[ ] 14 gün iade politikası yayında
[ ] Mesafeli satış sözleşmesi
[ ] Refund policy sayfası
[ ] Provider DPA imzalı (DeepSeek, Anthropic, Iyzico, Stripe)
[ ] SCC dosyaları (yurt dışı transfer)
[ ] VERBİS yükümlülük tekrar kontrol (1K+ user'da)
[ ] 2FA admin için zorunlu
[ ] Cyber sigorta poliçesi (opsiyonel ama önerilir)
[ ] External penetration test
```

---

## 11. Karar Logu (D1-D12) — Avukat Onaylı

| ID | Soru | Avukat cevabı | Statüs |
|---|---|---|---|
| D1 | Avukat görüşü ne zaman? | Faz 0'da, koddan önce | ✅ Tamamlandı |
| D2 | DPO atanmalı mı? | İlk yıl outsource | 🟡 Pending sözleşme |
| D3 | Tam haber metni saklansın mı? | Evet, ama kullanıcıya gösterme | ✅ Karar lock |
| D4 | Yurt dışı transfer izni? | Açık rıza + DPA/SCC | 🟡 Pending implementation |
| D5 | Paywall kaynak eklenir mi? | Hayır, hard block | ✅ Karar lock |
| D6 | Robots.txt ihlali toleransı? | Sıfır, admin override yok | ✅ Karar lock |
| D7 | Yaş gate? | 18+ | ✅ Karar lock |
| D8 | Cyber sigorta? | Faz 6 sonrası değerlendir | ⏳ Faz 6'ya |
| D9 | Haber kaynağı pozisyonu? | KAÇIN | ✅ Cross-cutting kural |
| D10 | Direct quote limiti? | 25 kelime hard cap | ✅ Karar lock |
| D11 | Takedown prosedürü? | 4 endpoint + 24h SLA | ✅ Karar lock |
| D12 | VERBİS? | 1K+ user'da gönüllü | ⏳ Faz 6'ya |

---

## 12. Çapraz Referans

```text
PII redaction          → Prompt Contracts §1.5 (yeni), Architecture §3 (yeni modül)
4 takedown endpoint    → API Contracts §22 (yeni)
5-item source checklist → UX §8, API §4.1, Data Model sources tablosu
4 register checkbox    → UX §7, API §3.1, Data Model users tablosu
"Haber kaynağı değil"  → Competitive §5, Design System §1.3, Pricing §7.1
Generation UI uyarısı  → Design System §5.1 (yeni), UX §3
Hassas entity rule     → Prompt Contracts §4.3 madde 16
KDV + 14 gün           → Pricing §7.1, Design System §5.6
takedown_requests      → Data Model §3.x (yeni)
Updated risk status    → Risk Register R-LGL-01..03, R-PRD-01
```

---

## 13. Sonraki Adım Önerileri

```text
Hafta 0 (HEMEN):
  1. DPO/KVKK uzman ofis ile sözleşme
  2. ROPA + veri envanteri hazırlama (DPO yardımıyla)
  3. ToS + Privacy + KVKK Aydınlatma metinleri taslak
     → avukat final review (Faz 1 launch öncesi)
  4. /legal/* sayfa içerikleri yazımı

Hafta 1-2 (Faz 0 altyapı + paralel):
  5. PII redaction modülü implementation
  6. takedown_requests veri modeli + migration
  7. /legal/* ve /bot sayfaları statik build
  
Hafta 3+ (Faz 1 ile):
  8. Source admin 5-item checklist UI
  9. Register 4-checkbox UI
  10. Generation result UI uyarısı
  11. Source ekleme robots.txt parser hard-block
```

---

**Sonuç:** Avukat görüşü %85 mevcut planla uyumlu, **3 yeni teknik gereksinim + 9 copy/UI ince ayarı** ekledi. Hiçbir mimari değişiklik yok; PRD ve ana stack korunuyor. **PII redaction layer en kritik yeni iş**, MVP-1'de mandatory. Faz 0/1/6 launch checklist'leri net; **avukat ToS+Privacy+KVKK Aydınlatma final review** olmadan production'a çıkış yok. R-LGL-01, R-LGL-02 risk skoru azaltma yolda; mitigation %50 tamamlandı.
