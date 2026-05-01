# Nodrat — Veri İhlali ve Olay Müdahale Runbook'u

**Doküman türü:** Incident Response Playbook
**Sürüm:** v0.1
**Bağımlılık:** Compliance Brief §6, Threat Model §6, ROPA, DPO Contract
**Hedef:** Veri ihlali, güvenlik olayı veya kritik kesinti durumunda müdahale prosedürü.
**Yasal dayanak:** KVKK md.12/5 (72 saat KVK Kurul bildirimi), GDPR md.33

⚠️ **Bu doküman INTERNAL'dır.** Ekip ve DPO/uzman tarafından kullanılır. Kullanıcıya yönelik değildir.

---

## 0. Yönetici Özeti

```text
Severity tanımı:
  SEV-1 (Critical) : PII breach, auth bypass, prod outage
                    Yanıt: 1 saat, KVK Kurul 72h
  SEV-2 (High)     : Tek-kullanıcı ifşa, %50+ kesinti, $1K+ cost runaway
                    Yanıt: 4 saat
  SEV-3 (Medium)   : Tek feature outage, cost spike >%50
                    Yanıt: 24 saat
  SEV-4 (Low)      : UI bug, tek kaynak HTML kırılganlığı
                    Yanıt: 7 gün

KVKK md.12/5 zorunlulukları (PII breach durumunda):
  - 72 saat içinde KVK Kurul'a bildirim
  - 24 saat içinde etkilenen kullanıcılara e-posta
  - DPO/uzman ile koordinasyon zorunlu

İlk müdahale ekibi:
  - On-call / founder    : Selman Ay (legal@nodrat.com)
  - DPO / KVKK uzmanı    : [outsource]
  - Avukat               : [outsource, gerektiğinde]
  - Mali müşavir         : [outsource, finansal etki için]
```

---

## 1. Severity Sınıflandırması

### 1.1 SEV-1 (Critical)

```text
Tanım: Hayati risk taşıyan, derhal müdahale gerektiren olay

Örnekler:
  - Müşteri PII breach (≥10 kullanıcı verisi sızıntısı)
  - Auth bypass (yetkisiz admin erişim)
  - Tüm sistem outage
  - Provider API key sızıntısı (cost runaway riski)
  - Database korupt / kayıp
  - Ransomware / kötücül erişim

Müdahale süresi: 1 saat içinde acknowledged
İletişim:        Tüm etkilenen kullanıcılar + KVK Kurul (72h)
Ekip:            Founder + DPO + Avukat
```

### 1.2 SEV-2 (High)

```text
Tanım: Servis yarıdan fazla etkilenmiş, hızlı müdahale lazım

Örnekler:
  - Tek kullanıcı PII ifşa (≤10)
  - Servis %50+ kullanıcı için kesinti
  - Cost runaway > $1.000 (provider quota aşımı)
  - Embedding queue stuck (tüm yeni içerik durmuş)
  - Backup başarısız (3 gün üst üste)

Müdahale süresi: 4 saat
İletişim:        Etkilenen kullanıcılar
Ekip:            Founder
```

### 1.3 SEV-3 (Medium)

```text
Tanım: Tek feature etkilenmiş, kullanıcılar etkili workaround ile devam edebilir

Örnekler:
  - Tek kaynak HTML kırılganlığı (1 source down)
  - Cost spike > %50 normal
  - Generation latency p95 > 10s (10 dk pencerede)
  - Search slow

Müdahale süresi: 24 saat
İletişim:        Status page güncelleme
```

### 1.4 SEV-4 (Low)

```text
Tanım: Çoğu kullanıcı için fark edilmez, planlı çalışma kapsamında

Örnekler:
  - UI bug (cosmetic)
  - Edge-case hata
  - Eski crawler job'ı temizliği

Müdahale süresi: 7 gün
İletişim:        Yok
```

---

## 2. Tespit (Detection)

### 2.1 Otomatik alarm sistemleri

```text
Sentry          : Production exception capture (Critical → Slack)
Better Uptime   : 5 dk ping monitor (down → Slack + email)
Cron alarms:
  - Daily provider spend > 1.5x avg
  - Per-user cost > $5/gün
  - Failed jobs queue > 1000
  - Disk usage > %85
  - Backup başarısız (3 gün)
  - Generation success rate < %85
  - Halüsinasyon flag rate > %5

Slack channel   : #security-alerts (kritik), #ops-alerts (orta)
Email           : on-call e-posta
```

### 2.2 Kullanıcı raporu

```text
Kanallar:
  - support@nodrat.com (genel)
  - privacy@nodrat.com (KVKK / veri)
  - legal@nodrat.com (yasal süreç)
  - /legal/abuse form
  - /legal/privacy-request form

Triage:
  Tüm support e-postası 24h içinde okunur.
  PII / breach iddiası → derhal SEV-1 olarak ele alınır.
```

### 2.3 Dış kaynak tespiti

```text
- Have I Been Pwned bildirimi (email leak)
- Hetzner / Cloudflare abuse raporu
- Provider invoice anomaliisi
- KVK Kurul / mahkeme talebi
```

---

## 3. SEV-1 Müdahale Akışı (PII Breach)

### 3.1 Adım 1 — DETECT (0-15 dk)

```text
1. Alarm geldiği an founder acknowledged eder (Slack ack)
2. Severity onayı: SEV-1 mi gerçekten?
   - Etki kapsamı (kaç kullanıcı, ne tip veri)
   - PII içeriyor mu?
3. Incident ticket aç (Slack thread veya ayrı tool)
4. DPO'yu ara (e-posta + telefon)
5. Saat tutmaya başla (72h KVK Kurul timer)
```

### 3.2 Adım 2 — CONTAIN (15-60 dk)

```text
İlk öncelik: ihlali durdur, daha fazla yayılmasın

Eylemler:
- Etkilenen sistem freeze
  - /admin/* erişim block
  - Auth disable (gerekirse)
  - Compromised provider key DERHAL revoke
  - Şüpheli kullanıcı hesapları pause
  - Suspicious IP block (Cloudflare)
- Backup'tan geri yüklenebilir mi kontrol
- Saldırı vektörü hipotezleri yaz
```

### 3.3 Adım 3 — INVESTIGATE (1-12 saat)

```text
Etki kapsamı netleştirme:
- audit_log incele (admin actions)
- Sentry events incele
- Provider call logs incele
- User session logs incele
- Database query log incele

Kapsam belirle:
- Kaç kullanıcı etkilendi?
- Hangi veri kategorileri?
- Saldırı süresi (başlangıç-bitiş)?
- Saldırı vektörü (auth, SQL injection, prompt injection, vs.)?

Forensik koruma:
- DB snapshot al (incident time)
- Log dosyalarını arşivle
- Provider invoice'ları sakla
```

### 3.4 Adım 4 — ERADICATE (12-24 saat)

```text
Vulnerability fix:
- Patch deploy (test → staging → prod)
- Compromised credential rotation
  - API_SECRET_KEY
  - JWT_SECRET
  - Provider API key'leri
  - Database password
- Backdoor scan (varsa)
- Audit log review (post-fix)
```

### 3.5 Adım 5 — RECOVER (1-3 gün)

```text
Servis geri yükleme:
- Sırayla servis aç (DB → Redis → API → Worker → Web)
- Healthcheck monitör
- Smoke test (login + 1 generation)
- Kullanıcılara bildirim hazırla

Kullanıcı bildirim e-postası (24 saat içinde):
- Subject: "Önemli güvenlik bilgilendirmesi"
- İçerik:
  - Ne oldu (genel olarak)
  - Hangi veriler etkilendi
  - Ne yaptık (containment + fix)
  - Kullanıcının yapması gerekenler (şifre değiştir, vb.)
  - İletişim: privacy@nodrat.com

Public statement (gerekirse):
- /legal/incident-history sayfasında (30 gün sonra)
```

### 3.6 Adım 6 — KVK KURUL BİLDİRİMİ (72 saat içinde)

```text
DPO/KVKK uzmanı ile birlikte bildirim hazırlığı:

Bildirim içeriği (KVKK md.12/5):
1. Kişisel veri ihlalinin gerçekleşme zamanı ve yeri
2. İhlalden etkilenen kişi sayısı (yaklaşık)
3. İhlal edilen kişisel veri kategorileri
4. Olası sonuçları
5. Aldığımız tedbirler ve alınması düşünülenler
6. Bilgi alabilecek kişilerin iletişim bilgileri

VERBİS / Kurul portal:
- https://verbis.kvkk.gov.tr (eğer kayıtlıysak)
- Yazılı bildirim (kayıtlı değilsek)

Bildirim sonrası:
- Onay numarası saklanır
- Kurul takip soruları için hazır olunur
```

### 3.7 Adım 7 — POST-MORTEM (7-14 gün)

```text
Blameless retrospektif (DPO + ekip):
- Olay zaman çizelgesi
- Tespit gecikmesi neydi?
- Containment başarısı
- Müdahale süresi
- İletişim performansı
- Kullanıcı tepkisi
- Kök neden (root cause)

Aksiyon maddeleri:
- Yeni alarm eşikleri
- Threat model güncelleme
- Test cases ekleme
- Runbook güncelleme

Yayın:
- Internal: tam rapor
- External: /legal/incident-history (30 gün gecikme,
            kullanıcıya yönelik dil)
```

---

## 4. SEV-2 Müdahale (Standart)

```text
Adımlar SEV-1 ile aynı, ancak:
- KVK Kurul bildirimi GEREKMEZ (PII yoksa)
- Sadece etkilenen kullanıcı bildirimi
- 4 saat içinde acknowledged
- 24 saat içinde fix + kullanıcı bildirimi
- Post-mortem 7 gün
```

---

## 5. Cost Runaway Müdahale (R-FIN-01)

### 5.1 Trigger

```text
Otomatik alarm:
- Daily provider spend > 1.5x avg
- Single user spend > $5/gün
- Provider monthly cap > %80 kullanım
```

### 5.2 Adımlar

```text
1. ALARM acknowledged (Slack)
2. CONTAIN:
   - Etkilenen provider routing düşür (Haiku → DeepSeek)
   - Top 20 user cost report
   - Anomaly user (10x normal) tespit
   - Suspicious user pause + investigation
3. INVESTIGATE:
   - Hangi kullanıcı / endpoint cost yarattı?
   - Otomasyon mu (bot) mu human?
   - Quota cap aşıldı mı?
4. ERADICATE:
   - Bot ise hesap suspend
   - Human ise tier upgrade önerisi
   - Provider quota cap re-check
5. RECOVER:
   - Provider routing normal
   - Monitor 48 saat
6. POST-MORTEM (>$500 etkili olduysa)
```

---

## 6. Provider Outage Müdahale

```text
Senaryo: DeepSeek API down
Etki:    Üretim akışı durur

Adımlar:
1. Health check provider (5xx persistent)
2. Otomatik failover provider'a geç (OpenRouter)
3. Kullanıcılara status page banner
4. Provider sürpriz outage süresini izle
5. Provider geri gelince trafiği kademeli geri al
6. Monitor 24 saat
```

---

## 7. KVKK Veri Sahibi Başvurusu Müdahale

```text
Trigger: privacy@nodrat.com'a başvuru veya /legal/privacy-request form

İlk 24 saat:
1. Başvuru triage (DPO incele)
2. Kimlik tespiti (TC kimlik / e-imza)
3. Acknowledgment e-posta gönder

7 gün içinde:
4. Talep edilen veriyi topla
5. Hak değerlendirmesi (KVKK md.11)
6. DPO ile final review

30 gün içinde (yasal süre):
7. Cevap gönder:
   - Görme    : tam veri raporu
   - Düzeltme  : işlem onayı
   - Silme     : delete confirmation
   - Taşınabilirlik: JSON export

Audit log:
  - Talep alındı (timestamp)
  - Cevap verildi (timestamp)
  - 1 yıl saklama
```

---

## 8. Kontak Listesi (Acil Durum)

```text
ROL                       İLETİŞİM
─────────────────────────────────────────
Founder / On-call         Selman Ay
                          [tel: ____________]
                          [legal@nodrat.com]

DPO / KVKK Uzmanı         [____________________]
                          7/24 acil hat
                          SLA: 2 saat geri dönüş

Avukat (gerektiğinde)     [____________________]

Mali Müşavir              [____________________]

Provider acil destek:
  DeepSeek                [destek email]
  Anthropic               [destek email]
  Iyzico                  +90 ___
  Stripe                  ___
  Hetzner                 +49 ___
  Cloudflare              ___

KVK Kurul                 https://verbis.kvkk.gov.tr
                          0850 252 22 22

CERT-TR (Siber)          https://www.usom.gov.tr
```

---

## 9. Çağrı Ağacı (On-Call Tree)

```text
SEV-1 detected
   │
   ▼
Founder ack < 1 saat
   │
   ├──→ Slack #security-alerts (otomatik)
   │
   ├──→ DPO çağrısı (e-posta + tel)
   │
   ├──→ Avukat (eğer hukuki süreç riski)
   │
   ├──→ Etkilenen kullanıcı listesi hazırla
   │
   └──→ KVK Kurul timer başlat (72h)
```

---

## 10. Drill ve Test

### 10.1 Aylık prosedürler

```text
[ ] Backup restore drill (R-OPS-03 mitigation)
[ ] Login + ana akış smoke test
[ ] Provider failover test (controlled)
[ ] Alarm thresholds review
```

### 10.2 Çeyreklik prosedürler

```text
[ ] Threat model gözden geçir
[ ] DPO ile incident response simulation
[ ] Top 20 user cost review
[ ] KVK uyum self-audit
[ ] Penetration test (light, internal)
```

### 10.3 Yıllık prosedürler

```text
[ ] External penetration test
[ ] DR drill (full system restore)
[ ] DPO sözleşme renewal
[ ] Provider DPA renewal
[ ] Insurance policy review (cyber liability)
[ ] KVKK compliance audit
```

---

## 11. Şablonlar

### 11.1 Kullanıcı bildirimi (PII breach)

```text
Konu: Önemli güvenlik bilgilendirmesi — Nodrat

Sayın [Kullanıcı Adı],

[Tarih] tarihinde Nodrat sistemlerinde tespit edilen bir güvenlik
olayı sonucunda bazı kullanıcı verilerinin yetkisiz erişime maruz
kalmış olabileceğini bildirmek isteriz.

Etkilenen veriler:
- E-posta adresi
- [Diğer veriler — somut]

Etkilenmemesi muhtemel veriler:
- Şifre (Argon2id hash, kırılması son derece zor)
- Ödeme bilgisi (provider'da, bizde tutulmuyor)

Aldığımız önlemler:
- Olay derhal kontrol altına alındı.
- Sistem güvenlik güncellemesi yapıldı.
- KVK Kurul'a bildirim yapıldı (72 saat içinde).

Sizin için önerilerimiz:
- Şifrenizi değiştirin: [link]
- 2FA aktivasyonunu öneririz: [link]
- Şüpheli aktivite görürseniz: privacy@nodrat.com

Detaylı bilgi için: privacy@nodrat.com
Olay raporu (sonradan): /legal/incident-history

Yaşadığımız kesintiden ötürü özür dileriz.

Saygılarımızla,
Nodrat Ekibi
```

### 11.2 KVK Kurul bildirimi (72h)

```text
[DPO ile birlikte hazırlanır]

KVKK Madde 12/5 — Veri İhlali Bildirimi

Veri Sorumlusu  : [Nodrat Bilişim Ltd. Şti.]
Bildirim tarihi : [____________________]
İhlal tarihi    : [____________________]
İhlal yeri      : [VPS / API / DB]

İhlalin niteliği:
[Kısa açıklama, örn: SQL injection ile DB erişim ihlali]

Etkilenen kişi sayısı (yaklaşık):
[Sayı]

Etkilenen veri kategorileri (KVKK md.6 ışığında):
- E-posta adresi
- [Diğer]

Olası sonuçlar:
[Risk değerlendirmesi]

Alınan tedbirler:
1. [Containment]
2. [Eradication]
3. [User notification]

Alınması düşünülen tedbirler:
1. [Patch deploy]
2. [Audit]

İletişim:
- DPO: [____________________]
- Yetkili: Selman Ay (legal@nodrat.com)
```

---

## 12. Çapraz Referans

```text
Threat Model         : docs/engineering/threat-model.md §6
Audit log            : docs/engineering/data-model.md §5.4
ROPA                 : docs/legal/ropa.md
DPO Contract         : docs/legal/dpo-contract-template.md
Privacy Policy       : docs/legal/privacy-policy.md §10
Risk Register R-FIN-01: docs/strategy/risk-register.md
Risk Register R-LGL-01: docs/strategy/risk-register.md
Backup procedure     : docs/engineering/architecture.md §9
```

---

**Bu runbook 6 ayda bir gözden geçirilmeli ve drill ile test edilmelidir.**

**v0.1 — DRAFT — DPO/KVKK uzmanı ile birlikte finalize edilecek.**
