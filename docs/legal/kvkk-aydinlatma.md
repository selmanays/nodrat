# Nodrat — KVKK Aydınlatma Metni

**Yürürlük tarihi:** [____________________]
**Son güncelleme:** 2026-05-01
**Sürüm:** v0.1
**KVKK Dayanak:** 6698 sayılı Kanun md.10 (Aydınlatma Yükümlülüğü)

⚠️ **DRAFT — Avukat ve KVKK uzmanı onayı gerekli.** KVK Kurul tip aydınlatma metinlerine birebir uyumlu hale getirilmelidir.

---

## 0. Amaç

6698 sayılı Kişisel Verilerin Korunması Kanunu'nun ("KVKK") 10. maddesi kapsamında, veri sorumlusu olarak Nodrat ("Şirket"), kişisel verilerinizin işlenmesine ilişkin sizi aşağıdaki konularda bilgilendirir:

```text
a) Veri sorumlusunun ve varsa temsilcisinin kimliği
b) Kişisel verilerin hangi amaçla işleneceği
c) İşlenen kişisel verilerin kimlere ve hangi amaçla aktarılabileceği
ç) Kişisel veri toplamanın yöntemi ve hukuki sebebi
d) KVKK md.11'de sayılan diğer haklarınız
```

---

## 1. Veri Sorumlusunun Kimliği

```text
Unvan        : [Nodrat Bilişim Ltd. Şti.]
MERSIS No    : [____________________]
Vergi No     : [____________________]
Vergi Dairesi: [____________________]
Adres        : [____________________]
Telefon      : [____________________]
E-posta      : privacy@nodrat.com
KEP Adresi   : [____________________]
DPO/Uzman    : [____________________]
              (KVKK uzmanlığı outsource edilmiştir)
```

---

## 2. İşlenen Kişisel Veri Kategorileri

Şirket, Hizmet kapsamında aşağıdaki kişisel veri kategorilerini işler:

```text
A. Kimlik bilgileri
   - Ad, soyad (opsiyonel)

B. İletişim bilgileri
   - E-posta adresi
   - Telefon numarası (varsa, ödeme veya destek için)
   - Fatura adresi (paid tier'da)

C. Hesap güvenliği bilgileri
   - Şifre (Argon2id hash olarak)
   - Session token (hash)
   - 2FA gizli anahtar (varsa, admin için)

D. Kullanım bilgileri
   - Hizmet kullanım kayıtları
   - Üretim talepleri (request_text)
   - Üretim çıktıları (saved generations)
   - Tıklama, tarama, oturum verileri (analytics)

E. İşlem bilgileri
   - Subscription bilgileri
   - Ödeme tutarları
   - Fatura bilgileri (e-Arşiv)

F. Teknik veriler
   - IP adresi
   - User-Agent (cihaz, tarayıcı bilgisi)
   - Çerez tanımlayıcıları
   - Login zamanları

G. Müşteri işlem bilgileri
   - Talep ve şikayet kayıtları
   - Destek e-posta yazışmaları
```

### 2.1 Özel nitelikli kişisel veriler

Şirket, doğrudan özel nitelikli kişisel veri toplamaz. Ancak:

```text
- Haber kaynaklarında (kazınan içerikte) sağlık, din, etnik köken,
  siyasi görüş gibi konularla ilgili haberler geçebilir.
- Bu veriler "alenileşmiş" niteliktedir (kamuya açık haberler).
- Kullanıcı kendi prompt'unda özel nitelikli veri yazarsa,
  PII redaction süreci kişisel tanımlayıcıları temizler.
```

---

## 3. Kişisel Verilerin İşlenme Amaçları

```text
1. Hizmet'i sağlamak ve sürdürmek
   - Hesap yönetimi
   - Kimlik doğrulama
   - İçerik üretimi
   - Üretim geçmişi sunma
   - Kullanım kotası takibi

2. Sözleşme yükümlülüklerini yerine getirmek
   - Hizmet Koşulları'nda belirtilen şartların ifası
   - Faturalama ve ödeme (**Lemon Squeezy MoR** üzerinden — ABD merkezli ödeme sağlayıcısı; aşağıda §3 madde 9 yurt dışı transfer)

3. Yasal yükümlülükleri yerine getirmek
   - Vergi Mevzuatı: KDV/VAT/sales tax compliance Lemon Squeezy (Merchant of Record) tarafından üstlenilir; Veri Sorumlusu **e-Arşiv fatura kesmez** (2026-05-08, Epic #448)
   - 5651 İçerik Yükümlülükleri (takedown)
   - KVKK 12. madde güvenlik önlemleri
   - Mahkeme/Savcılık talepleri

4. Hizmet kalitesini geliştirmek
   - Kullanım analytics (anonim/pseudonym)
   - Hata ayıklama, performans iyileştirme
   - A/B test ile özellik geliştirme

5. Güvenlik ve fraud önleme
   - Spam, abuse, bot tespiti
   - Cost runaway koruması
   - Hesap güvenliği denetimi
   - Audit log

6. İletişim
   - Transactional email (verify, password reset, fatura)
   - İsteğe bağlı pazarlama bültenleri (açık rıza ile)
   - Destek yazışmaları
```

---

## 4. Kişisel Verilerin Aktarıldığı Taraflar ve Aktarım Amacı

### 4.1 Yurt içi aktarım

```text
Alıcı                   : Aktarım amacı                : Hukuki dayanak
─────────────────────────────────────────────────────────────────────────
Contabo VPS (DE)       : VPS hizmeti                  : Sözleşmenin ifası
                         (Almanya AB ülkesi —
                         adequacy decision benzeri)
Mali müşavir           : Vergi mevzuatı               : Yasal yükümlülük
KVKK Uzmanı / DPO      : KVKK uyum hizmeti            : Yasal yükümlülük
Resmi makamlar         : Mahkeme/Savcılık talepleri   : Yasal yükümlülük

Not: Iyzico/PayTR (TR ödeme provider'ları) Epic #448 ile reddedildi —
yerine yurt dışı Lemon Squeezy MoR (§4.2'de listelendi).
```

### 4.2 Yurt dışı aktarım — KRİTİK

KVKK md.9 uyarınca **AÇIK RIZANIZ** ile aşağıdaki yurt dışı kuruluşlara veri aktarımı yapılır:

```text
Alıcı                : Veri kategorisi          : Ülke    : Hukuki dayanak
──────────────────────────────────────────────────────────────────────────
DeepSeek             : Prompt + output (PII     : Çin     : Açık rıza + DPA
                       redaction sonrası)        (HK)
Anthropic            : Prompt + output          : ABD     : Açık rıza + DPA + SCC
OpenRouter           : Prompt + output          : ABD     : Açık rıza + DPA
OpenAI               : Prompt + output          : ABD     : Açık rıza + DPA + SCC
                       (yedek)
NVIDIA NIM           : Embedding query          : ABD     : Açık rıza + DPA
Resend / Postmark    : E-posta gönderim         : ABD     : Açık rıza + DPA
Lemon Squeezy (MoR)  : Ad, soyad, e-posta,      : ABD     : ❗ AYRI AÇIK RIZA
(Faz 6 — Epic #448)    fatura adresi, ülke,                + DPA + SCC
                       IP, kart token (kart                (R-LGL-13, #453)
                       no/CVV LS'de PCI-DSS)
Contabo Object       : Encrypted backup         : DE (AB) : Meşru menfaat + şifreleme
Storage              :                          :         : (AB adequacy)
Cloudflare           : DNS + CDN                : Global  : Meşru menfaat (PII yok)
```

> **Lemon Squeezy yurt dışı transferi için ek açık rıza ([#453](https://github.com/selmanays/nodrat/issues/453)):** Ödeme akışında (trial/checkout başlatma) "Lemon Squeezy (ABD) ödeme servisinin verilerimi işlemesini açık rıza ile kabul ediyorum" checkbox'ı ayrı olarak alınır. Bu rıza KVKK m.9 uyumu için server-side enforced'tur; reddedilirse paid plan satın alma işlemi gerçekleşmez. Reddetmek Free tier kullanımını engellemez.

### 4.2.1 Transfer Impact Assessment — TIA (avukat şartlı onayı, Epic #448)

> **Avukat görüşü (2026-05-08):** "DPA + SCC gereklidir, fakat 'yeterli' dosya seti için ayrıca açık rıza kaydı, aydınlatma metni güncellemesi, ROPA güncellemesi ve transfer risk notu gerekir." Aşağıdaki 5 maddelik kayıt sistemi her yurt dışı transfer için tutulur (Schrems II + KVKK m.9 transfer impact assessment mantığı).

```text
TIA — her yurt dışı alıcı için tutulan kayıt:

(i)   Veri kategorileri (LS örneği: e-posta, fatura adresi, IP,
      kart token, ülke/locale, plan bilgisi)
(ii)  Veri minimizasyonu kanıtı (LS örneği: kart no/CVV LS PCI-DSS
      Level 1, Nodrat'a ulaşmaz; webhook payload minimum)
(iii) Sözleşmesel güvence: DPA + SCC + alt-işleyen (subprocessor) listesi
      (LS subprocessor list: lemonsqueezy.com/legal/subprocessors)
(iv)  Teknik/organizasyonel tedbirler: erişim logları, webhook payload
      minimizasyonu, saklama süresi, kullanıcı silme/dışa aktarma akışı
(v)   Açık rıza kaydı: timestamp, IP, metin sürümü, hangi checkbox
      ile alındığı (server-side enforced — Issue #470 backend gate)

Dosya konumu: docs/legal/transfer-impact-assessments/<provider>.md
              (provider başına ayrı dosya — LS, Anthropic, DeepSeek,
              Resend, NIM, OpenRouter)
```

> Mali müşavir + DPO outsource'un ortak sorumluluğu: yıllık review (LS subprocessor değişimi, yeni provider eklenmesi, açık rıza metin sürüm bumpı).

### 4.3 PII Redaction (Kişisel Veri Maskeleme)

Yurt dışı LLM provider'larına veri gönderilmeden ÖNCE, **otomatik olarak** aşağıdaki kişisel veriler temizlenir:

```text
- E-posta adresleri        → [email_redacted]
- Telefon numaraları       → [phone_redacted]
- IP adresleri             → [ip_redacted]
- TC kimlik numaraları     → [id_redacted]
- IBAN numaraları          → [iban_redacted]
- Account ID / UUID        → [ref_redacted]
```

Bu, kullanıcının kendi prompt'unda yazsa bile uygulanır.

---

## 5. Kişisel Verilerin Toplanma Yöntemi ve Hukuki Sebebi

### 5.1 Toplama yöntemi

```text
- Web sitesi üzerinden (https://nodrat.com)
- Mobil uygulama üzerinden (gelecekte)
- API üzerinden (Faz 7+)
- E-posta yoluyla (destek talepleri)
- Çerezler aracılığıyla (zorunlu + opsiyonel)
- Üçüncü taraf entegrasyonlarından (ödeme provider)
```

### 5.2 Hukuki sebep (KVKK md.5)

```text
md.5/2-a (Açık rıza):
  - Yurt dışı LLM provider'larına veri aktarımı
  - Pazarlama iletileri
  - Opsiyonel analytics çerezleri

md.5/2-c (Sözleşmenin kurulması ve ifası):
  - Hesap yönetimi
  - Hizmet sunumu
  - Faturalama

md.5/2-ç (Yasal yükümlülük):
  - Vergi mevzuatı (e-Arşiv)
  - 5651 takedown
  - KVKK 12 güvenlik

md.5/2-d (Alenileşmiş veri):
  - Haber kaynaklarındaki kamuya açık kişi adları (politikacı,
    kamu görevlisi, kamuya açık figürler)

md.5/2-f (Meşru menfaat):
  - Spam / abuse koruması
  - Sistem güvenliği
  - Ürün geliştirme analytics
  - Cost runaway koruması
```

---

## 6. KVKK md.11 Haklarınız

Kanunun 11. maddesi uyarınca aşağıdaki haklara sahipsiniz:

```text
a) Kişisel verilerinizin işlenip işlenmediğini öğrenme

b) Kişisel verileriniz işlenmişse buna ilişkin bilgi talep etme

c) Kişisel verilerinizin işlenme amacını ve bunların amacına uygun
   kullanılıp kullanılmadığını öğrenme

ç) Yurt içinde veya yurt dışında kişisel verilerinizin aktarıldığı
   üçüncü kişileri bilme

d) Kişisel verilerinizin eksik veya yanlış işlenmiş olması hâlinde
   bunların düzeltilmesini isteme

e) KVKK 7. maddede öngörülen şartlar çerçevesinde kişisel verilerinizin
   silinmesini veya yok edilmesini isteme

f) Düzeltme, silme veya yok etme işlemlerinin, kişisel verilerinizin
   aktarıldığı üçüncü kişilere bildirilmesini isteme

g) İşlenen verilerinizin münhasıran otomatik sistemler vasıtasıyla
   analiz edilmesi suretiyle aleyhinize bir sonucun ortaya çıkmasına
   itiraz etme

ğ) Kişisel verilerinizin kanuna aykırı olarak işlenmesi sebebiyle
   zarara uğramanız hâlinde zararın giderilmesini talep etme
```

---

## 7. Hak Kullanımı ve Başvuru

### 7.1 Self-service (anlık)

```text
Hizmet üzerinden:
  - Settings → Profil      : Düzeltme
  - Settings → Hesabım     : Silme talebi (DELETE /app/me)
  - Settings → Veri İndir  : Taşınabilirlik (GET /app/me/data-export)
```

### 7.2 Formal başvuru

```text
A. Online form:
   https://nodrat.com/legal/privacy-request

B. E-posta:
   privacy@nodrat.com
   (Konu: KVKK md.11 Başvurusu)

C. Yazılı:
   [Şirket Adresi]

D. KEP üzerinden (Kayıtlı Elektronik Posta):
   [____________________]

Başvuruda bulunması gereken bilgiler:
  - Ad, soyad
  - T.C. kimlik no (Türk vatandaşları için)
  - Yabancı uyruklu için pasaport numarası
  - Tebligat adresi veya e-posta
  - Talep konusu (madde 6'daki haklardan hangisi)
  - Kimlik tespit belgesi (e-imza, kimlik kopyası, vb.)
```

### 7.3 Cevap süresi

KVKK md.13 uyarınca başvurunuza:
- **30 gün** içinde ücretsiz olarak cevap verilir
- Karmaşık durumlarda 60 güne uzatılabilir (size bildirim yapılır)
- Yazılı başvurularda kimlik tespiti yapılır
- Üyelik süreci sırasında self-service için anlık

### 7.4 KVK Kurul başvuru

Cevap alamadığınız veya cevabı yetersiz bulduğunuz takdirde:
- 30 gün içinde Şirket'in cevabını aldığınızı varsayarak
- 60 gün içinde Kurul'a başvurma hakkı

```text
Kişisel Verileri Koruma Kurulu
Web    : https://www.kvkk.gov.tr
VERBİS : https://verbis.kvkk.gov.tr/Forms/Sikayet.aspx
Adres  : [Resmi adres]
```

---

## 8. Saklama Süreleri

KVKK md.7 uyarınca veriler işleme amacının ortadan kalkmasıyla silinir:

| Veri Kategorisi | Saklama Süresi |
|---|---|
| Hesap | Aktif süresince + 30 gün soft delete |
| Generations | Sınırsız (kullanıcı silmedikçe) |
| Login + IP log | 90 gün |
| Audit log | 1 yıl (yasal min) |
| Email log | 1 yıl |
| Fatura | 10 yıl (vergi mevzuatı) |
| Subscription | Aktif + 5 yıl |
| Backup | 6 ay rolling |
| Article tam metni | 90 gün cleaned, sonra archived |

---

## 9. Veri Güvenliği Önlemleri

```text
Teknik:
  - Argon2id şifre hash
  - TLS 1.2+ HTTPS
  - Veritabanı erişim kontrolü
  - Backup encryption (restic + age)
  - Audit log
  - Rate limiting + abuse detection
  - PII redaction (LLM çağrısı öncesi)
  - 2FA (admin için zorunlu)

İdari:
  - DPO/KVKK uzman outsource
  - Çalışan gizlilik taahhüdü
  - Yıllık KVKK eğitimi
  - Veri ihlali müdahale planı (72h)

Fiziksel:
  - VPS sağlayıcı: ISO 27001 sertifikalı (Hetzner)
  - Backup off-server (Backblaze B2, encrypted)
```

---

## 10. Veri İhlali Bildirimi

Olası bir veri ihlali durumunda:
- **72 saat** içinde KVK Kurul'a bildirim
- **24 saat** içinde etkilenen kullanıcılara e-posta bildirimi
- Ciddi durumlarda public statement

---

## 11. Çocukların Verisi

Hizmet **18 yaş ve üzeri** kullanıcılar içindir. 18 yaş altı kullanıcı verisini işlemiyoruz. Eğer 18 yaş altı bir kişinin verisini topladığımızı tespit edersek derhal sileriz.

---

## 12. Aydınlatma Metni Değişiklikleri

Bu Aydınlatma Metni'ni değiştirebiliriz. Önemli değişikliklerde:
- E-posta ile 30 gün önceden bildirim
- Web sitesinde duyuru

---

## 13. Onay (Kullanıcı Tarafından)

Hizmet'e kayıt olurken aşağıdaki onayları **ayrı ayrı** vermeniz gerekir:

```text
[ ] KVKK Aydınlatma Metni'ni okudum.                            (zorunlu)

[ ] Kişisel verilerimin hizmetin sunulması için
    işlenmesini kabul ediyorum.                                  (zorunlu)

[ ] Yurt dışındaki yapay zekâ servis sağlayıcılarına
    sınırlı veri aktarımını kabul ediyorum.                      (zorunlu)

[ ] Pazarlama iletileri almak istiyorum.                         (opsiyonel)
```

Üç zorunlu onay olmadan hizmet kullanılamaz. Pazarlama onayı opsiyoneldir ve ayrı bir kutuda yer alır (zorunlu rızalarla bir arada gösterilmez).

---

## 14. Yürürlük

Bu Aydınlatma Metni [Yürürlük Tarihi] tarihinden itibaren yürürlüğe girer.

---

## 15. İletişim

```text
Veri Sorumlusu : [Nodrat Bilişim Ltd. Şti.]
Adres          : [____________________]
E-posta        : privacy@nodrat.com
Telefon        : [____________________]
KEP            : [____________________]

DPO / Uzman    : [____________________]

Üst Otorite    : Kişisel Verileri Koruma Kurulu
                 https://www.kvkk.gov.tr
```

---

**v0.1 — DRAFT — Avukat ve KVKK uzmanı (DPO) onayı bekleniyor.**
