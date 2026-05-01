# Better Uptime Monitor Konfigürasyonu

> **Issue:** #42 — Monitoring (Sentry + Better Uptime + alarm thresholds)
> **Mimari karar:** docs/engineering/architecture.md §13 D9 (Sentry + Better Uptime free tier)

Bu doküman Better Uptime (https://betteruptime.com) tarafında oluşturulacak
monitor'leri tarif eder. Free tier yeterli olduğundan ekstra abonelik yok;
gerçek monitor'ler kullanıcı tarafından dashboard üzerinden eklenir.

---

## 1. Monitor Listesi

| # | URL | Metod | Interval | Beklenen | Tip | Notlar |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `https://nodrat.com` | GET | 5 dk | HTTP 200 | Public homepage | Cloudflare/CDN canlılığı |
| 2 | `https://nodrat.com/health` | GET | 1 dk | HTTP 200 + JSON `status:"ok"` | API liveness | Container + DB hızlı kontrol |
| 3 | `https://nodrat.com/api/admin/sources` | GET | 5 dk | HTTP 401 | Auth wall | Auth middleware çalışıyor mu |
| 4 | `https://nodrat.com/readiness` | GET | 5 dk | HTTP 200 OR 503 (200 hedef) | API readiness | DB+Redis+MinIO erişimi |

> **Why HTTP 401 for #3?** `/admin/sources` token istiyor; 401 dönmesi auth
> middleware'in canlı olduğunu gösterir. 200 dönerse middleware bypass
> olmuş demektir → kritik incident.

---

## 2. Alarm Politikası

### 2.1 Tetikleme

- **3 ardışık fail** → incident açılır
- **Recovery:** 1 başarılı response sonrası incident kapanır

### 2.2 Bildirim kanalları

| Severity | Kanal | Alıcı |
| --- | --- | --- |
| `warn` | Email | legal@nodrat.com (admin) |
| `critical` | Email + Slack `#nodrat-alerts` | Founder + on-call |
| `down` | Email + Slack + SMS (free tier kapsamında 10/ay) | On-call |

> SMS ve Slack webhook'u Better Uptime UI üzerinden eklenecek; webhook
> URL `SLACK_WEBHOOK_URL` GitHub secret değeriyle aynı kanala bağlı.

### 2.3 Eşikler

- **Up time hedefi:** 99.5% (aylık ~3.6 saat downtime tolerans — MVP-1)
- **Latency hedefi:** Better Uptime "Slow response" eşiği:
  - homepage: 3s
  - /health: 1s
  - /readiness: 2s
- **Maintenance window:** Pazar 04:00–05:00 TRT — alarm muted

---

## 3. Status Page

Better Uptime free tier üzerinde public status page:

- URL: `status.nodrat.com` (Cloudflare CNAME → Better Uptime)
- Component grouping:
  - **Web (frontend)** → Monitor #1
  - **API** → Monitor #2 + #4
  - **Auth** → Monitor #3
- Incident timeline + RSS feed otomatik

---

## 4. Sentry Entegrasyonu

Sentry tarafında (issue #42 §1):

- API: `apps/api/app/main.py` `_init_sentry()` aktif
- Web: `apps/web/sentry.{client,server,edge}.config.ts`
- Alert rules:
  - `event.level >= error` and rate > 1/min → Slack `#nodrat-alerts`
  - Performance issue (p95 > 2s) → email
- Release tracking: deploy workflow'u (`#40`) `release` alanını
  `nodrat-api@${VERSION}` ile dolduracak (gelecek iterasyonda
  `sentry-cli releases` adımı eklenir).

---

## 5. Çapraz Referans

- docs/engineering/architecture.md §10 — Monitoring & Observability
- docs/engineering/alarm-thresholds.md — Alarm threshold detayları
- docs/strategy/risk-register.md — R-OPS-01 outage, R-OPS-02 latency
- .github/workflows/deploy.yml — Slack webhook deploy bildirimi
