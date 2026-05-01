# Closed Alpha Davet Materyalleri (Faz 4)

**Issue:** #50
**Versiyon:** v1.0
**Bağlı doküman(lar):** `docs/validation/research-findings.md`, `docs/strategy/success-metrics.md`, `docs/research/alpha-target-criteria.md`

## 1. Amaç ve kapsam

Bu doküman, Nodrat kapalı alfa programı (5-10 davetli kullanıcı) için tüm metin/checklist materyallerini tek dosyada toplar. Davet emaili, onboarding adımları, feedback formu ve 14 gün sonu *exit interview* soruları burada şablon olarak yer alır.

Closed alpha hedefi `docs/strategy/success-metrics.md` faz hedefiyle uyumludur (`MVP-1 alpha WSGAU >= 1.5`). 30 gün boyunca whitelist ile sınırlı erişim verilir, kayıt restriction Faz 4'te aktiftir (`docs/research/alpha-invite-checklist.md` operasyon adımları).

## 2. Davet emaili (Türkçe)

### 2.1 Konu satırı (3 varyant — A/B test)

- **A**: Nodrat kapalı alfaya seni davet ediyoruz — sadece 10 kişi
- **B**: Türkçe gündem için ChatGPT'den çıkmanın yolu (alfa daveti)
- **C**: Sabah brifin için kaynaklı 10 dakika — alfaya katıl

### 2.2 Email gövdesi (alıcı: bağımsız creator/editor/agency)

```text
Merhaba {ad},

Türkçe gündemi her sabah 4-7 farklı yerden takip etmek, "geç kaldım"
hissinden kurtulmak ve üretirken kaynak güvensizliği yaşamamak için
Nodrat'ı geliştirdik. Sen profilimizdeki ilk 10 kişi arasında olduğun
için kapalı alfa davetini seninle paylaşmak istedik.

Nodrat ne yapar:
  - Sabah brifin: 10 dakikada Türk gündemini özetler, kaynaklı.
  - X paylaşımı / thread / özet üretimi: senin tonunu koruyarak.
  - "Bu ay vs geçen ay" gibi karşılaştırma: tek tıkla kaynaklı analiz.

ChatGPT yanında nerede duruyoruz:
  - ChatGPT TR gündeminde "bilmiyorum" / yanlış cevap verir;
    Nodrat son 7-30 gün haberlerinden kaynaklı çalışır.
  - Her cümleye eklenen "kaynak" — sadece içerik değil, denetlenebilirlik.
  - Türkçe ton (mizahi, eleştirel, kurumsal, sade) için ayar mevcut.

Alfa programı:
  - Süre: 30 gün (1-30 Mayıs 2026 takvimine göre takvimleyebiliriz)
  - Kullanıcı sayısı: 10 davetli, whitelist üzerinden
  - Maliyet: senin için ÜCRETSİZ (alfa süresi boyunca Pro plan açık)
  - Beklenti: haftada 1+ üretim + kısa form + 30. günde 20 dk görüşme

Davet linki ve KVKK kabulü için:
  https://app.nodrat.com/alpha/{whitelist_token}
  (Bu link {ad} olarak sana özel; başkasıyla paylaşma.)

Sorun olursa direkt ben dönerim:
  Selman — selmanaycom@gmail.com

İlgilenirsen 1-2 satır cevap atman yeterli, takvim önereyim.

Sevgiler,
Selman
```

### 2.3 Davete eşlik eden tek paragraflık LinkedIn DM (alternatif kanal)

```text
Merhaba {ad}, Nodrat'ı (Türkçe gündem RAG) kapalı alfaya çıkarıyoruz.
ChatGPT'nin TR gündemde verdiği "bilmiyorum" cevabı yerine kaynaklı
cevap üreten bir yapı; senin günlük üretim akışına dokunduğunu
düşünüyorum. 10 kişilik ücretsiz alfa için adın bende — ilgilenirsen
mail atayım, 30 gün test edersin. Cevap için baskı yok.
```

## 3. Onboarding checklist (kullanıcıya gönderilen)

### 3.1 İlk 24 saat (registration & ilk üretim)

| Adım | Açıklama | Doğrulama |
|------|----------|-----------|
| 1 | Whitelist link tıkla, kayıt ol (e-mail + şifre) | Aktivasyon e-mail'i geldi mi? |
| 2 | KVKK aydınlatma metnini oku, açık rıza ver | Onay tarihi DB'de görünür |
| 3 | Onboarding turunu izle (5 dk video) | Bitiş yüzdesi >= %80 |
| 4 | İlk üretim: "Bugünkü gündem" → 3 X paylaşımı | Üretim başarıyla kaydedildi |
| 5 | Kaynak panelini incele (sağ kolon, 3+ kaynak) | "Source clicked" event |

### 3.2 İlk 7 gün (kullanım derinleştirme)

| Adım | Açıklama | Doğrulama |
|------|----------|-----------|
| 6 | En az 3 ayrı tonla üretim yap (tarafsız/eleştirel/sade) | 3+ farklı tone parametre |
| 7 | Bir thread üretip "Kopyala" ile X'e taşı | "Thread copy" event |
| 8 | "Veri yetersiz" senaryosunu bilinçli tetikle (egzotik konu) | Quota DÜŞMEMELİ |
| 9 | Geçmiş üretim listesinde 1 üretimi yeniden çalıştır | "Regenerate" event |
| 10 | İlk haftalık feedback formu (3 dk) doldur | Form yanıtı kayıt |

### 3.3 İlk 14 gün (alışkanlık)

- Haftada 1+ üretim devamlılığı (alarm: 7 günden fazla aktif olmamayan kullanıcı için Selman'a otomatik bildirim)
- En az bir karşılaştırma modu denemesi ("geçen hafta vs bu hafta")
- Style profile yüklemesi (Pro tier — 5+ örnek metin)

## 4. Feedback formu (haftalık, 5 soru)

### 4.1 Form gönderim ritmi

- 7. gün: kısa feedback (5 soru, 3 dk)
- 14. gün: orta feedback (yine 5 soru + ek "kullanmaya devam eder misin")
- 30. gün: exit interview (1:1 görüşme — bkz. §5)

### 4.2 5 soru (Likert 1-5 + opsiyonel açıklama)

| # | Soru | Format | KS bağı |
|---|------|--------|---------|
| Q1 | Geçen hafta Nodrat'ı kaç gün kullandın? | 0-7 | Engagement |
| Q2 | Halüsinasyon (uydurma) gördün mü? Kaç kez? | Sayı + örnek metin | Halu rate |
| Q3 | Verilen kaynaklara güveniyor musun? (1=hiç, 5=tamamen) | 1-5 Likert | Kaynak güvenilirliği |
| Q4 | ChatGPT'ye kıyasla bu konuda Nodrat nasıl? (1=daha kötü, 5=çok daha iyi) | 1-5 Likert | Pozisyon |
| Q5 | Aylık 200 TL olsa öder miydin? (1=asla, 5=hemen) | 1-5 Likert | Ödeme isteği |

Q3-Q5 ortalaması alpha success metrics tablosundaki KS-1 acceptance rakamlarına bağlanır (`docs/research/alpha-success-metrics.md`).

### 4.3 Açık uçlu opsiyonel sorular (her formda 1 tane döner)

- "Bu hafta seni en çok zorlayan tek şey neydi?"
- "Ürünü 1 cümlelik hangi tanıtım metniyle bir arkadaşına anlatırdın?"
- "Eklemek istediğin tek özellik nedir?"

## 5. 14 gün exit interview (1:1, 30 dk)

### 5.1 Hazırlık

- Görüşmeyi ZOOM'da kayıt altına al (kullanıcının onayıyla)
- Her görüşmenin başında 30 sn'lik onay scripti oku (KVKK kayıt rızası)
- Görüşme öncesi kullanıcının haftalık form yanıtlarını gözden geçir; en düşük puanlı 2 alanı sor

### 5.2 Soru rehberi (yarı yapılandırılmış)

#### Bölüm A — Genel kullanım (10 dk)

1. Geçen 14 günde Nodrat'ı en çok hangi durumda kullandın? Bir somut örnek anlat.
2. Hangi gün/saat dilimi? Sabah brifi mi, anlık talep mi?
3. ChatGPT veya başka bir araçla aynı işi yapsaydın ne fark olurdu?
4. Kullanmadığın bir gün varsa neden? Hangi engel devreye girdi?
5. "Bu sabah Nodrat'a girdim ama ayrılıp ChatGPT'ye gittim" yaşadın mı? Sebep?

#### Bölüm B — Kalite ve güven (10 dk)

6. Halüsinasyon (uydurma) gördüğün durum oldu mu? Bir örnek paylaşır mısın?
7. Kaynak panelinin sağ tarafta olması işine yaradı mı?
8. "Veri yetersiz" mesajı gördün mü? O an ne hissettin (rahatsız / güvenilir)?
9. Tonu (mizahi, eleştirel) ayarlayabilmek senin gerçek üretim akışına oturdu mu?
10. Bir cümleyi paylaşmadan önce "kaynağa bakmadan paylaşırım" güveni hissediyor musun?

#### Bölüm C — Devamlılık ve ödeme (10 dk)

11. Alfa biterken ücretli versiyon olsa kullanmaya devam eder misin? Hangi fiyatla?
12. Etrafına önerir miydin? Kime, neden?
13. Şu an ÖDEME engeli olan tek konu nedir?
14. 3 ay sonra Nodrat'ta hangi özellik olsa kullanım kararını netleştirirdi?
15. Eklemek isteyeceğin son söz / serbest yorum.

### 5.3 Görüşme sonrası eylem

- 24 saat içinde teşekkür e-mail'i + ücretsiz erişim uzatma teklifi (30 gün ek)
- Görüşme transkripti `docs/validation/research-findings.md` faz güncellemesine input
- Q11 fiyat noktası `docs/strategy/pricing-strategy.md` güncellemesine sinyal

## 6. Versiyon ve değişiklik kaydı

| Versiyon | Tarih | Değişiklik |
|----------|-------|------------|
| v1.0 | 2026-05-01 | İlk yayın — closed alpha invite materyali (#50) |

---

**Bağlı dokümanlar:**
- `docs/research/alpha-target-criteria.md` — kimi davet ediyoruz
- `docs/research/alpha-success-metrics.md` — başarı eşikleri
- `docs/research/alpha-invite-checklist.md` — operasyon checklist
- `docs/strategy/success-metrics.md` — KPI tanımı (WSGAU)
- `docs/validation/research-findings.md` — persona doğrulama
