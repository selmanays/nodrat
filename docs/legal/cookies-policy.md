# Nodrat — Çerez Politikası

**Yürürlük tarihi:** [____________________]
**Son güncelleme:** 2026-05-01
**Sürüm:** v0.1

⚠️ **DRAFT — Avukat onayı gerekli.**

---

## 1. Çerez Nedir?

Çerezler ("cookies"), web tarayıcınız ile web sitemiz arasında bilgi alışverişi sağlayan küçük metin dosyalarıdır. Çerezler, kullanıcı oturumunu sürdürme, tercihleri hatırlama ve siteyi geliştirmek için anonim kullanım istatistiği toplamak için kullanılır.

Bu Çerez Politikası, Nodrat ([https://nodrat.com](https://nodrat.com)) web sitesinin hangi çerezleri kullandığını, hangi amaçla kullandığını ve nasıl yönetebileceğinizi açıklar.

---

## 2. Çerez Kullanım Felsefemiz

```text
- Minimum çerez kullanımı (zorunlu olanlar dışında).
- Privacy-preserving default (analytics opt-in).
- Üçüncü taraf reklam çerezi YOKTUR.
- Cross-site tracking YAPILMAZ.
- Pazarlama çerezleri MVP'de kullanılmaz.
```

---

## 3. Kullandığımız Çerez Türleri

### 3.1 Zorunlu çerezler (her zaman aktif)

Bu çerezler hizmetin temel işlevleri için zorunludur. Devre dışı bırakılamaz.

| Çerez | Amaç | Süre | Tip |
|---|---|---|---|
| `nodrat_session` | Kimlik doğrulama (oturum) | 15 dk | HTTP-only, Secure, SameSite=Strict |
| `nodrat_refresh` | Oturum yenileme | 30 gün | HTTP-only, Secure, SameSite=Strict |
| `csrf_token` | CSRF koruması (form güvenliği) | Oturum | HTTP-only, Secure, SameSite=Strict |
| `cookie_consent` | Çerez tercihinizi hatırlama | 1 yıl | First-party |
| `language` | Dil tercihi (tr/en) | 1 yıl | First-party |

### 3.2 Analytics çerezleri (opt-in)

Bu çerezler ürünü geliştirmek için anonim kullanım istatistiği toplar. Kabul etmeniz halinde aktif olur.

| Çerez | Amaç | Süre | Sağlayıcı |
|---|---|---|---|
| `ph_distinct_id` | Benzersiz kullanıcı ID (anonim) | 1 yıl | PostHog (self-host, Türkiye VPS) |
| `ph_session_id` | Oturum bazlı analitik | 30 dk | PostHog (self-host) |

PostHog **self-host** edilir, veriler kendi VPS'imizde kalır, üçüncü tarafla paylaşılmaz.

### 3.3 Pazarlama çerezleri

```text
NODRAT MVP FAZINDA PAZARLAMA ÇEREZİ KULLANMAZ.

Üçüncü taraf reklam ağları (Google Ads, Facebook Pixel vb.)
ÇEREZLERİ YOKTUR.

Sosyal medya entegrasyonları (X, LinkedIn paylaş butonları vb.)
sayfada açıkça belirtilir ve sadece tıklandığında etkinleşir.
```

---

## 4. Çerez Onay Yönetimi

### 4.1 Cookie Banner

Siteyi ilk ziyaret ettiğinizde bir çerez banner'ı görürsünüz:

```text
┌─────────────────────────────────────────────────────────────┐
│  Nodrat zorunlu çerezleri kullanır.                         │
│  Analytics çerezleri opsiyoneldir.                          │
│                                                             │
│  [Sadece zorunlu]  [Hepsini kabul et]  [Detaylar]           │
└─────────────────────────────────────────────────────────────┘
```

Tercihiniz `cookie_consent` çerezinde 1 yıl saklanır. İstediğiniz zaman ayarlardan değiştirebilirsiniz: **Settings → Çerez Tercihleri**

### 4.2 Tercih kategorileri

```text
[Zorunlu]   : Her zaman aktif (devre dışı bırakılamaz)
[Analytics] : Opt-in (varsayılan kapalı)
```

### 4.3 Tarayıcı çerez ayarları

Tarayıcınızdan da çerezleri yönetebilirsiniz:

```text
Chrome    : Ayarlar → Gizlilik ve güvenlik → Çerezler
Safari    : Tercihler → Gizlilik
Firefox   : Ayarlar → Gizlilik ve güvenlik
Edge      : Ayarlar → Çerezler ve site izinleri
```

Tüm çerezleri devre dışı bırakırsanız Hizmet **çalışmayabilir** (zorunlu çerezler gerekli).

---

## 5. Üçüncü Taraf Çerezler

Hizmet, aşağıdaki üçüncü taraf servislerle entegre çalışır:

| Servis | Amaç | Çerez koyar mı? |
|---|---|---|
| Cloudflare | DNS / CDN | Hayır (sadece teknik header) |
| Iyzico / PayTR (Faz 6) | Ödeme | Sadece ödeme sayfasında, geçici |
| Stripe (Faz 6) | Ödeme (yurt dışı) | Sadece ödeme sayfasında |
| Resend / Postmark | E-posta | Web'de çerez koymaz |

---

## 6. Çerez Olmayan Tracking

Çerez kullanmadığımız ama bilgi topladığımız teknolojiler:

```text
- Sunucu logları (IP, User-Agent, request URL)
- Analytics events (PostHog, opsiyonel onaya bağlı)
- Hata izleme (Sentry, anonim stack trace)

Bu veriler Privacy Policy madde 2.2 kapsamında ele alınır.
```

---

## 7. Çocukların Çerezleri

Hizmet 18 yaş ve üzeri kullanıcılar içindir. 18 yaş altı çocuklara özel çerez kullanmıyoruz.

---

## 8. Politika Değişiklikleri

Bu Çerez Politikası'nı güncelleyebiliriz. Önemli değişikliklerde cookie banner yeniden gösterilir ve eski onayınız sıfırlanır.

---

## 9. İletişim

```text
Çerezlerle ilgili sorularınız için:
  E-posta : privacy@nodrat.com
  Form    : https://nodrat.com/legal/privacy-request
```

---

## 10. Çapraz Referans

```text
Privacy Policy  : docs/legal/privacy-policy.md
KVKK Aydınlatma : docs/legal/kvkk-aydinlatma.md
ToS             : docs/legal/tos.md
```

---

**v0.1 — DRAFT — Avukat onayı bekleniyor.**
