# Closed Alpha Operations Checklist (Faz 4)

**Issue:** #50
**Versiyon:** v1.0
**Bağlı doküman(lar):** `docs/research/alpha-invite-template.md`, `docs/research/alpha-target-criteria.md`, `docs/research/alpha-success-metrics.md`

## 1. Amaç

Closed alpha programının teknik + iletişimsel + operasyonel adımlarını sıralı liste olarak tutar. Selman tek başına yürütebilecek şekilde; her adım net "kim, ne, ne zaman, doğrulama" ile yazılı.

Toplam süre: 30 gün (T-7 hazırlık → T+30 exit). Aşağıdaki tüm checklist sırayla işaretlenmeli.

## 2. T-7 ile T-1 — Hazırlık fazı (1 hafta)

### 2.1 Backend hazırlığı (whitelist altyapısı)

- [ ] `alpha_invitations` Postgres tablosu Alembic migration eklenmiş (Issue #69 patern referansı; *registration restriction* Faz 4'te aktif)
- [ ] `ALPHA_WHITELIST_ENABLED` env flag staging + prod config'e eklenmiş
- [ ] `/api/auth/register` endpoint'inde whitelist guard aktif (whitelist dışı email → 403 + `alpha_closed` error code)
- [ ] Whitelist token üretici endpoint (admin-only): `POST /api/admin/alpha/invite` → email, token döner
- [ ] Email gönderim entegrasyonu (postmark / mailgun) test edilmiş; sandbox'tan production'a geçildi
- [ ] Audit log: her redeem `audit_logs` tablosuna düşürür (`event_type=alpha_redeem`)
- [ ] Rate limit: 1 token / e-mail; aynı email tekrar redeem deneyemez
- [ ] Token TTL = 14 gün; süre dolunca `status=expired` cron'u eklendi

### 2.2 Frontend hazırlığı

- [ ] `/alpha/{token}` URL pattern Next.js route'a eklenmiş; whitelist token doğrulama UI'sı hazır
- [ ] Onboarding wizard 5 adım: e-mail → KVKK → ad/soyad → kullanım amacı (P1A/P1B/diğer) → ilk üretim
- [ ] "Halü bildir" butonu üretim ekranında sağ üst köşede görünür
- [ ] Feedback form modal'ı (5 soru) 7. ve 14. günde otomatik tetiklenir
- [ ] Header'da "Alpha 30 gün ücretsiz" rozeti gösterilir

### 2.3 İletişim altyapısı

- [ ] Discord/Slack özel kanal kurulu (`#nodrat-alpha-feedback`)
  - Davet linki davet emaili sonunda yer alır
  - Selman pinned welcome mesajı: program kuralları + 1:1 demo nasıl talep edilir
  - Bot integration: yeni redeem → kanal'a otomatik bildirim
- [ ] Calendly bağlantısı kurulu — 1:1 demo + exit interview için 30 dk slot
- [ ] Loom hesabı hazır (5 dk onboarding video kayıt için)
- [ ] Notion / Linear feedback panosu, alfa kanalı için (her geri bildirim ticket'a dönüşür)

### 2.4 Doküman ve legal

- [ ] KVKK aydınlatma metni Türkçe + onay akışı `/alpha/{token}` registration ekranında zorunlu
- [ ] `docs/legal/threat-model.md` §4 alpha audit log madde okunmuş, eksik yok
- [ ] Kullanım sözleşmesi (Terms of Service) alfa süresine özel eki: "alfa süresi boyunca veri analitik amacıyla kullanılabilir, anonimleştirilir"
- [ ] Halü raporu eki KVKK metnine eklendi (kullanıcı bildiriminin saklanması için onay)

### 2.5 Onboarding video script (5 dk Loom)

```text
0:00-0:30   Giriş — "Selman, Nodrat kurucusu, alfa için teşekkür"
0:30-1:30   Demo: kayıt → KVKK → onboarding wizard
1:30-2:30   İlk üretim: "Bugünkü gündem" → 3 X paylaşımı
2:30-3:30   Kaynak panelini gezme + "halu bildir" butonu
3:30-4:30   Style profile yükleme (Pro tier)
4:30-5:00   30 gün takvim + Discord kanal + 1:1 demo daveti
```

- [ ] Video Loom'da kaydedildi
- [ ] Video URL davet emaili template'ine eklendi (`docs/research/alpha-invite-template.md`)
- [ ] CC altyazı eklendi (Türkçe)

## 3. T-1 — Davet havuzu hazırlama

- [ ] `docs/research/alpha-target-criteria.md` §4 listesinden 12-18 aday seçildi
- [ ] Adayların persona profili (P1A / P1B / P2A / P3) işaretlendi
- [ ] Her aday için davet emaili kişiselleştirme verisi hazır (ad, profil, hangi acı noktasıyla bağlanacağı)
- [ ] Çeşitlilik kontrolü (`alpha-target-criteria.md` §5): cinsiyet, coğrafya, yaş, hacim dağılımı dengeli mi?
- [ ] Red flag taraması (`alpha-target-criteria.md` §6) yapıldı; bloker listesinden çıkarıldı

## 4. T+0 — Davet günü

### 4.1 Davet gönderimi

- [ ] 12-18 davet emaili sıralı gönderildi (sabah 09:00-11:00 İstanbul saati)
- [ ] LinkedIn DM kanalı 6-8 P1B adayına paralel açıldı
- [ ] X DM kampanyası 8-10 P1A adayı için tetiklendi
- [ ] Discovery interview onay verenlerin 5-8'i kişisel mesajla bilgilendirildi

### 4.2 Anlık takip

- [ ] İlk 24 saatte yanıt veren adaylar Notion takip panosuna işlendi
- [ ] 48 saat sonunda yanıt vermeyenlere kibar follow-up (1 kez)
- [ ] 72 saat sonunda 5-7 onay; 10 onaya yaklaşana kadar kişisel network'ten 2-3 ek davet

## 5. T+1 ile T+7 — Hafta 1 onboarding

- [ ] Her redeem sonrası 24 saat içinde "hoş geldin" mesajı (Selman'dan kişisel)
- [ ] Onboarding video izleme oranı izlenir; %80 altında kalanlara hatırlatma
- [ ] İlk üretim olmadan 48 saat geçen kullanıcıya 1:1 demo teklifi
- [ ] Discord kanalında Selman günde 1 kez aktif (sabah brifi notu paylaş — pattern modeli)
- [ ] Hafta sonu raporu: kaç redeem, kaç ilk üretim, kaç halü raporu

## 6. T+7 — İlk feedback formu

- [ ] 5 soru formu otomatik tetiklendi (`docs/research/alpha-invite-template.md` §4.2)
- [ ] %80 yanıt hedefi; %50 altında kalırsa 24 saat sonra hatırlatma e-mail'i
- [ ] Q3 (kaynak güveni) ve Q5 (ödeme isteği) ortalamaları KS panele işlendi
- [ ] Q2 (halu) bildirimleri ticket'a dönüştürüldü; her birine içerik analizi

## 7. T+8 ile T+14 — Hafta 2 derinleştirme

- [ ] 1:1 demo planı: 3 kullanıcı seçildi (yüksek aktivite + farklı persona)
  - Demo süresi 30 dk
  - Format: ekran paylaş + soru-cevap + observation
  - Selman not alır, transkript otomatik kaydedilir
- [ ] Comparison modu kullanım rehberi Discord kanalında paylaşıldı (P1B teşvik)
- [ ] Style profile uptake için 1-2 kullanıcıya örnek metin yükleme yardımı sağlandı

## 8. T+14 — Orta dönem feedback formu

- [ ] 5 soru + Q4 ek "kullanmaya devam eder misin?" formu tetiklendi
- [ ] Yanıtlar `docs/research/alpha-success-metrics.md` cohort tablosuna işlendi
- [ ] KS-1 acceptance ara durumu rapor edildi (Selman'a + ileride paydaşlara)
- [ ] Drop-off riski olan (7+ gün aktif değil) kullanıcılara bireysel check-in e-mail'i

## 9. T+15 ile T+29 — Hafta 3-4 weekly check-in

- [ ] Her hafta Pazar akşamı bir e-mail brif (Selman'dan davetlilere):
  - "Bu hafta diğer kullanıcılar şunları yaptı" (anonim)
  - "Yeni özellik: ..."
  - "1:1 görüşme için takvim linki"
- [ ] Hafta 3 sonunda kümülatif WSGAU rakamı `success-metrics.md` §2.3 hedefiyle karşılaştırıldı (1.5 baseline)
- [ ] Hafta 4 başında exit interview takvimi gönderildi (10 davetli için 30 dk slot)

## 10. T+30 — Exit interview ve kapanış

### 10.1 Exit interview turu

- [ ] 10 davetli için 30 dk 1:1 görüşme (`docs/research/alpha-invite-template.md` §5)
- [ ] Görüşmeler ZOOM'da kayıt; transkript otomatik
- [ ] Her görüşme öncesi kullanıcının haftalık form yanıtları gözden geçirildi
- [ ] Görüşme sonrası 24 saat içinde teşekkür e-mail + 30 gün ek erişim teklifi

### 10.2 Veri toplama ve analiz

- [ ] Tüm form + görüşme verisi `docs/validation/research-findings.md` faz güncellemesine sentez edildi
- [ ] KS-1 5 KPI sonuç tablosu (`alpha-success-metrics.md` §2) doldu
- [ ] Go/no-go karar matrisi (`alpha-success-metrics.md` §4) çıkarıldı
- [ ] Pricing sinyali (`pricing-strategy.md` §3 bağı) güncellendi

### 10.3 Kapanış iletişimi

- [ ] Discord kanalında "alfa bitti, teşekkürler" mesajı
- [ ] Tüm davetlilere kişiselleştirilmiş kapanış e-mail'i:
  - Programa katkı için teşekkür
  - 30 gün ek ücretsiz erişim
  - MVP-2 (open beta) çıkışında öncelikli erken erişim
  - Referral linki: 1 arkadaş davet → 60 gün ek
- [ ] Whitelist'i kapat: `ALPHA_WHITELIST_ENABLED=false` veya MVP-2 modu (open beta)

## 11. Risk yönetimi (operasyonel)

| Risk | Tetik sinyali | Mitigation |
|------|---------------|------------|
| Yetersiz katılım | T+3'te 5 redeem altı | Ek 5-7 davet, kişisel ağ aktivasyonu |
| Yüksek halü raporu | T+7'de 5+ rapor | Acil prompt revize, halu trap (#44) review |
| Drop-off | Hafta 2 sonu < %50 active | 1:1 check-in mecburi, friction tespiti |
| KVKK şikayeti | Herhangi bir gün | Legal consult, takedown akışı (#117) tetikle |
| Sosyal medyada negatif feedback | X mention veya yorum | Hızlı yanıt, transparan iletişim |
| Backend down (P0 incident) | Health check fail | `docs/engineering/runbook.md` (gelecek) — şimdilik Selman manuel |

## 12. Sonraki faza geçiş kriterleri

T+30 sonunda aşağıdaki gate'ler `docs/research/alpha-success-metrics.md` §4 kararıyla birlikte değerlendirilir:

- [ ] 5/5 veya 4/5 KPI acceptance → MVP-2 hazırlığa başla (Faz 5)
- [ ] 3/5 KPI acceptance → 30 gün uzatma + prompt/onboarding iterasyonu
- [ ] ≤2/5 → research-findings güncelle, persona/positioning sorgula

## 13. Versiyon kaydı

| Versiyon | Tarih | Değişiklik |
|----------|-------|------------|
| v1.0 | 2026-05-01 | İlk yayın — closed alpha operasyon checklist (#50) |

---

**Bağlı dokümanlar:**
- `docs/research/alpha-invite-template.md` — davet metni + form
- `docs/research/alpha-target-criteria.md` — kim davet ediliyor
- `docs/research/alpha-success-metrics.md` — KS acceptance
- `docs/strategy/success-metrics.md` — KPI tanımı
- `docs/legal/threat-model.md` §4 — alpha audit log
