# Nodrat — DPO / KVKK Uzmanı Hizmet Sözleşmesi (Şablon)

**Doküman türü:** DPO / KVKK Outsource Service Agreement Template
**Sürüm:** v0.1
**Bağımlılık:** Compliance Brief §2 (KVKK), Opinion Integration §6, ROPA, Incident Response
**Hedef:** Bir KVKK danışmanlık ofisi ile dış kaynaklı DPO hizmeti için kullanılacak sözleşme şablonu.

⚠️ **DRAFT — Avukat onayı gerekli.** Bu metin ürün ekibinin ihtiyaç envanteri olarak hazırlanmıştır. KVKK uzman ofisiyle nihai imzadan önce baroya kayıtlı bir avukatın gözden geçirmesi zorunludur.

---

## 0. Tarafların Bilgileri

```text
HİZMET ALAN (Veri Sorumlusu):
  Unvan       : [Nodrat Bilişim Ltd. Şti.]  ← şirket kuruluşu sonrası
  Vergi No    : [____________________]
  Adres       : [____________________]
  Yetkili     : Selman Ay (Kurucu)
  E-posta     : legal@nodrat.com
  Telefon     : [____________________]

HİZMET VEREN (KVKK Uzmanı / DPO):
  Unvan       : [____________________]
  Vergi No    : [____________________]
  Adres       : [____________________]
  Yetkili     : [____________________]
  E-posta     : [____________________]
  Telefon     : [____________________]

Sözleşme tarihi : [____________________]
Yürürlük tarihi : [____________________]
```

---

## 1. Tanımlar

```text
KVKK         : 6698 sayılı Kişisel Verilerin Korunması Kanunu
GDPR         : EU 2016/679 sayılı Genel Veri Koruma Tüzüğü
Kişisel veri : KVKK md.3 uyarınca tanımlanan kişisel veri
İşleme       : KVKK md.3'te tanımlanan veri işleme faaliyeti
Veri sorumlusu : Hizmet Alan (Nodrat)
DPO / Uzman  : Hizmet Veren — KVKK uyum danışmanı
ROPA         : Records of Processing Activities (Veri İşleme Envanteri)
İhlal        : KVKK md.12/5 kapsamında veri ihlali
Kurul        : Kişisel Verileri Koruma Kurulu
VERBİS       : Veri Sorumluları Sicil Bilgi Sistemi
SCC          : Standart Sözleşme Hükümleri (yurt dışı transfer)
DPA          : Data Processing Agreement (provider sözleşmesi)
Sistem       : Hizmet Alan'ın Nodrat ürünü
```

---

## 2. Hizmetin Konusu

Hizmet Veren, Hizmet Alan'a aşağıdaki KVKK uyum danışmanlığı hizmetlerini sağlayacaktır:

### 2.1 Temel hizmetler (zorunlu)

```text
A. Mevzuat takibi ve danışmanlık
   - KVKK + ikincil düzenlemeler güncel takip
   - Aylık 2 saat danışmanlık (telefon/online)
   - Mevzuat değişikliği bildirimi

B. Veri envanteri (ROPA) yönetimi
   - İlk ROPA hazırlama (Hizmet Alan'ın taslağı üzerine)
   - 3 aylık ROPA güncelleme
   - Yeni veri işleme aktiviteleri için ROPA ekleme

C. Aydınlatma ve rıza yönetimi
   - Aydınlatma metni gözden geçirme
   - Açık rıza alanlarının doğruluğu
   - Veri sahibi başvuru cevabı şablonları

D. Veri ihlali müdahalesi
   - 7/24 acil iletişim (SLA: 2 saat içinde geri dönüş)
   - 72 saat KVK Kurul bildirim hazırlığı
   - Etkilenen veri sahiplerine bildirim metni
   - Post-incident rapor

E. VERBİS yönetimi
   - VERBİS yükümlülük değerlendirmesi
   - Gerekirse kayıt + güncelleme

F. Provider DPA / SCC kontrolü
   - Yurt dışı veri transfer dokümanları gözden geçirme
   - DeepSeek, Anthropic, Lemon Squeezy MoR provider DPA review
   - Standart Sözleşme Hükümleri uyum kontrolü
```

### 2.2 Opsiyonel / talep üzerine hizmetler

```text
G. Eğitim
   - Yıllık 1 KVKK farkındalık eğitimi (ekip için)
   - Yeni ekip üyesi onboarding eğitimi (saatlik)

H. Denetim
   - Yıllık 1 iç KVKK uyum denetimi
   - Gerekirse Veri Sorumluları Sicili güncellemesi

I. Dış denetim desteği
   - KVK Kurul incelemesi durumunda hukuki destek
   - Yetki belgesi düzenlenmesi gerekirse avukat yönlendirmesi

J. Politika güncelleme
   - Aydınlatma metni, gizlilik politikası revizyonu
   - Yeni politika dokümanları (örn. veri imha politikası)
```

---

## 3. Sözleşme Süresi ve Yenilenme

```text
Süre:           12 (oniki) ay
Başlangıç:      [____________________]
Bitiş:          [____________________]
Yenilenme:      Her sözleşme döneminin bitiminden 30 gün önce
                taraflar yenileme iradesini yazılı bildirmezse
                aynı koşullarla 1 yıl daha uzar.
Erken fesih:    Her iki taraf 30 gün önce yazılı bildirimle
                fesih hakkını saklı tutar.
```

---

## 4. Ücret ve Ödeme

```text
Aylık sabit ücret:        [____________________] TL + KDV
                          (yıllık ön ödeme indirim:
                          [____] TL → 2 ay bedava)

Saatlik destek (eğitim,
ekstra danışmanlık):       [____________________] TL/saat + KDV

Acil veri ihlali müdahalesi:
- Mesai içi (09:00–18:00): aylık ücrete dahil
- Mesai dışı / hafta sonu: [____________] TL/saat + KDV
- 24+ saat süren incident: tavan [____________] TL

Ödeme:
- Faturalama her ay sonunda
- Ödeme: 14 gün vadeli, banka havalesi
- Vergi: KDV her ödemede ayrıca
- e-Fatura zorunlu

Ücret artışı:
- Yıllık enflasyon (TÜİK TÜFE) oranında artırılabilir
- Taraflar başka bir oran üzerinde anlaşabilir

Sözleşme örneği:
- Aylık standart paket    : 5.000-15.000 TL/ay (DPO ofis ortalaması)
- Saatlik tarife          : 1.500-3.500 TL/saat
- Acil ihlal müdahalesi   : 2.500-5.000 TL/saat (mesai dışı)
```

---

## 5. Çalışma Şekli ve İletişim

```text
Birincil iletişim:
  Hizmet Alan tarafı: Selman Ay (legal@nodrat.com)
  Hizmet Veren tarafı: [____________________]

İletişim kanalları:
  - E-posta (default)
  - Telefon (acil)
  - Slack veya benzeri kanal (opsiyonel)
  - Aylık 2 saat telefon/video toplantı

SLA (Service Level Agreement):
  - Standart soru cevap        : 24 saat
  - Acil durum (veri ihlali)   : 2 saat geri dönüş
  - Veri ihlali bildirim hazırlığı: 24 saat içinde
  - Aylık rapor                : Ay sonundan sonraki 5 iş günü
  - ROPA güncelleme            : Talep alındıktan 14 iş günü
```

---

## 6. Hizmet Veren'in Yükümlülükleri

```text
6.1. KVKK ve ilgili mevzuata uygun hizmet sunmak.
6.2. Hizmet Alan'ın kişisel veri işleme faaliyetlerini değerlendirmek.
6.3. Aylık rapor hazırlamak (uyum durumu, açık iş kalemleri, riskler).
6.4. Veri ihlali durumunda 2 saat içinde geri dönmek.
6.5. KVK Kurul bildirimini 72 saat süresinde hazırlamak.
6.6. Hizmet Alan'ın çalışanlarına eğitim sağlamak (yıllık 1 kez).
6.7. Mevzuat değişikliklerini Hizmet Alan'a bildirmek.
6.8. Gizlilik yükümlülüğüne uymak (madde 9).
6.9. KVK Kurul incelemesi durumunda destek olmak.
6.10. ROPA dokümanını güncel tutmak.
6.11. Sözleşme süresince ulaşılabilir ve duyarlı olmak.
6.12. KVKK alanında deneyimli ve sertifikalı uzman atamak.
```

---

## 7. Hizmet Alan'ın Yükümlülükleri

```text
7.1. Hizmet Veren'e gerekli bilgi ve belgeleri sağlamak.
7.2. Veri işleme faaliyetlerinde değişiklik olduğunda bilgilendirmek.
7.3. Aydınlatma metni ve açık rıza akışını uygulamaya almak.
7.4. Hizmet Veren'in tavsiyelerini gözden geçirmek.
7.5. Aylık ücreti zamanında ödemek.
7.6. Veri ihlali durumunda derhal Hizmet Veren'i bilgilendirmek.
7.7. KVK Kurul incelemesinde Hizmet Veren'e bilgi sağlamak.
7.8. Eğitim oturumlarına ekip katılımını sağlamak.
7.9. Sözleşme süresince yetkili kişiyi güncel tutmak.
```

---

## 8. Veri İşleme Faaliyeti — Hizmet Veren'in Pozisyonu

```text
Hizmet Veren, Nodrat'ın kişisel veri işleme faaliyetlerini
değerlendirir ancak kendisi VERİ İŞLEYEN sıfatıyla hareket etmez.

Hizmet Veren'in Hizmet Alan adına işlediği kişisel veriler:
  - Hizmet Alan çalışanları ile iletişim
  - Veri ihlali durumunda etkilenen veri sahibi listesi
  - VERBİS kayıt için organizasyon bilgileri

Bu veriler için Hizmet Veren:
  - Sadece bu sözleşme amacıyla işler
  - Üçüncü tarafa aktarmaz (yasal zorunluluk hariç)
  - Sözleşme bitiminde imha veya iade eder
  - KVKK md.12 güvenlik önlemlerini uygular
```

---

## 9. Gizlilik

```text
9.1. Hizmet Veren ve çalışanları, sözleşme süresince ve sona ermesinden
     sonraki 5 (beş) yıl boyunca aşağıdakiler hakkında gizlilik
     yükümlülüğü altındadır:

     a. Hizmet Alan'ın iş süreçleri
     b. Müşteri ve kullanıcı bilgileri
     c. Teknik mimari ve sistem detayları
     d. Finansal ve ticari bilgiler
     e. ROPA ve veri envanteri
     f. Veri ihlali olayları ve detayları
     g. Sözleşme şartları (ücret dahil)

9.2. İstisnalar:
     a. Yasal zorunluluk (mahkeme, Kurul, savcılık)
     b. Daha önce kamuya açıklanmış bilgi
     c. Hizmet Veren'in bağımsız geliştirdiği bilgi
     d. Hizmet Alan'ın yazılı izniyle paylaşılan bilgi

9.3. İhlal durumunda Hizmet Alan, sözleşme bedelinin 5 (beş) katı
     tutarında cezai şart talep etme hakkını saklı tutar.

9.4. Çalışan gizliliği: Hizmet Veren, hizmette görev alan tüm
     çalışanlarından bireysel gizlilik taahhüdü alır ve
     Hizmet Alan'a yazılı sunar.
```

---

## 10. Sorumluluk ve Tazminat

```text
10.1. Hizmet Veren, sunduğu hizmetin KVKK ve ilgili mevzuata uygunluğu
      konusunda mesleki standartlarda sorumluluk taşır.

10.2. Hizmet Veren'in açık ihmal veya kasti hatası nedeniyle Hizmet Alan
      KVK Kurul cezasına maruz kalırsa, Hizmet Veren bu cezanın %50'sine
      kadar tazmin eder. Tavan: yıllık sözleşme bedelinin 3 katı.

10.3. Veri ihlali Hizmet Veren'in eylem veya ihmalinden kaynaklanmıyorsa
      sorumluluk Hizmet Alan'da kalır.

10.4. Hizmet Veren, mesleki sorumluluk sigortasına sahip olmalıdır.
      Asgari poliçe tutarı: 1.000.000 TL.

10.5. Hiçbir taraf indirect, consequential veya cezai zararlardan sorumlu
      değildir (manevi tazminat hariç).
```

---

## 11. Mücbir Sebep

```text
11.1. Mücbir sebep durumlarında (deprem, salgın, savaş, siber saldırı,
      vb.) tarafların yükümlülükleri askıya alınır.

11.2. 30 günden uzun süren mücbir sebep durumunda her iki taraf
      sözleşmeyi tek taraflı feshedebilir.
```

---

## 12. Fesih

```text
12.1. Her iki taraf 30 gün önce yazılı bildirimle sözleşmeyi feshedebilir.

12.2. Aşağıdaki durumlarda derhal fesih hakkı doğar:
      a. Diğer tarafın sözleşmeyi esaslı şekilde ihlali (30 gün tebliğ)
      b. Hizmet Veren'in iflası, tasfiyesi
      c. Hizmet Alan'ın 60 gün üst üste ödememesi
      d. Gizlilik ihlali
      e. Yasal mevzuatın değişmesi sonucu hizmetin imkansızlaşması

12.3. Fesih sonrası:
      a. Hizmet Veren, Hizmet Alan'a ait tüm dokümanları 30 gün
         içinde teslim eder veya imha eder.
      b. Devam eden ihlal süreçleri için 90 gün geçiş desteği.
      c. Gizlilik yükümlülüğü 5 yıl boyunca devam eder.
```

---

## 13. Genel Hükümler

```text
13.1. Sözleşmede yapılacak değişiklikler yazılı olmalıdır.

13.2. Sözleşmenin herhangi bir maddesinin geçersiz sayılması diğer
      maddelerin geçerliliğini etkilemez.

13.3. Devir / temlik: Hiçbir taraf, diğer tarafın yazılı izni olmadan
      sözleşmeyi devredemez.

13.4. Bildirim: Tüm yazılı bildirimler taraflar tarafından sözleşmede
      belirtilen e-posta veya posta adreslerine yapılır.

13.5. Bağımsız taraflar: Bu sözleşme taraflar arasında ortaklık,
      acentelik veya işveren-işçi ilişkisi yaratmaz.
```

---

## 14. Uygulanacak Hukuk ve Uyuşmazlık Çözümü

```text
14.1. Bu sözleşme Türkiye Cumhuriyeti hukukuna tabidir.

14.2. Uyuşmazlıklar öncelikle taraflar arasında dostane çözüme
      kavuşturulmaya çalışılır (30 gün).

14.3. Çözülemeyen uyuşmazlıklarda İstanbul Mahkemeleri ve İcra
      Daireleri yetkilidir.
```

---

## 15. Ekler

```text
Ek-1: Veri İşleme Envanteri (ROPA — docs/legal/ropa.md)
Ek-2: Hizmet Veren Çalışan Gizlilik Taahhüdü (ayrı belge)
Ek-3: Mesleki Sorumluluk Sigortası Poliçe Kopyası
Ek-4: KVKK Sertifikası (Hizmet Veren)
Ek-5: Veri İhlali Müdahale Planı (Incident Response)
Ek-6: Aylık Rapor Şablonu
```

---

## 16. İmzalar

```text
HİZMET ALAN                    HİZMET VEREN

Ad-Soyad: ____________         Ad-Soyad: ____________

Unvan:    Kurucu               Unvan:    ____________

Tarih:    ____________         Tarih:    ____________

İmza:     ____________         İmza:     ____________
```

---

## 17. Seçim Kriterleri (Hizmet Alan için Kontrol Listesi)

DPO/KVKK uzmanı seçerken Hizmet Alan'ın değerlendireceği kriterler:

```text
[ ] KVK Kurul nezdinde tanınmış / sertifikalı
[ ] En az 5 yıl KVKK alanında deneyim
[ ] SaaS / yazılım sektörü tecrübesi (referans)
[ ] AI / veri analitiği şirketleri ile çalışma tecrübesi (tercih)
[ ] Mesleki sorumluluk sigortası ≥ 1M TL
[ ] 7/24 acil iletişim sözü
[ ] 24 saat ihlal bildirim hazırlığı taahhüdü
[ ] Aylık ücret 5.000-15.000 TL aralığında (piyasa)
[ ] Ekip büyüklüğü ≥ 3 (tek kişi bağımlılığı yok)
[ ] Avukat ortaklığı / yan kuruluş (uyuşmazlık halinde hukuki destek)
[ ] Türkçe + İngilizce raporlama
[ ] Politika dokümanları örnek paylaşıyor
[ ] Yıllık denetim hizmeti dahil
[ ] Eğitim ve farkındalık materyalleri
```

---

## 18. Çapraz Referans

```text
KVKK uyum gereksinimleri    → docs/legal/compliance-brief.md §2
ROPA → ek-1                 → docs/legal/ropa.md
İhlal müdahale prosedürü    → docs/legal/incident-response.md
Veri sahibi başvuruları     → docs/legal/privacy-policy.md §8
Yurt dışı transfer / DPA    → docs/legal/opinion-integration.md §3
Avukat ön-görüş             → docs/legal/opinion-integration.md
```

---

**Sonuç:** Bu şablon, KVKK uzman ofisi seçimi sonrası fiili sözleşmenin temelini oluşturur. **Avukat onayı olmadan imzalanmamalı.** Faz 0 sonu hedef: 2-3 KVKK ofisinden teklif almak, kriterlere uygun olanı seçmek, sözleşmeyi avukatla finalize edip imzalamak. Aylık ücret aralığı **5.000-15.000 TL**, mesleki sorumluluk sigortası ≥ **1M TL** olmalı.
