# Alarm Threshold Tablosu

> **Issue:** #42 — Production stability + alarm thresholds
> **Hedef:** Production'da gerçek anlamda action gerektiren olaylar için
> tek-yer threshold referansı. UI dashboard alarmları, Sentry alert rule'ları,
> Better Uptime ve scheduler health check'leri bu tabloya bakar.
>
> **Severity convention:**
> - `warn` — Engineering tarafının bilgilendirilmesi gerekir; mesai içi triage.
> - `critical` — On-call paged; dakikalar içinde aksiyon gerekiyor.

---

## 1. API Performansı

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| API p95 latency (`/app/*`) | > 2 s | > 5 s | Sentry performance / nginx access log | DB index review, provider timeout düşür |
| API p99 latency (`/app/*`) | > 4 s | > 10 s | Sentry | RAG retrieval cache hit oranını incele |
| API error rate (5xx, son 5 dk) | > 0.5% | > 1% | Sentry / nginx 5xx counter | Son deploy rollback adayı |
| Sentry error/min | > 5 | > 30 | Sentry alert rule | Stack trace incele, hotfix |
| `/health` cevap > 1 s | warn | — | Better Uptime | Container restart adayı |

## 2. Database (PostgreSQL)

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| Connection pool kullanımı | > 80% | > 95% | pg_stat_activity / SQLAlchemy pool | Pool size artır, slow query review |
| Slow query (statement avg > 500 ms) | > 5/dk | > 20/dk | pg_stat_statements | Index ekle / sorguyu yeniden yaz |
| Replication lag (Faz 2+) | > 30 s | > 120 s | pg_stat_replication | Bandwidth / disk IO incele |
| Disk free | < 15% | < 10% | node_exporter | Vacuum + log rotation |
| Lock waits | > 10/dk | > 50/dk | pg_locks | Long transaction kill |

## 3. Redis (Broker + Cache)

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| Memory kullanımı | > 75% | > 90% | `INFO memory` | Eviction policy doğrulama / pool boyutu |
| Connection sayısı | > 200 | > 500 | `INFO clients` | Worker leak araştır |
| Slow log (>10 ms) | > 5/dk | — | `SLOWLOG GET` | Komutu refactor |
| Celery queue backlog | > 500 | > 5000 | `LLEN celery` | Worker ölçekle |

## 4. Worker / Queue Sağlığı

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| DLQ uzunluğu (`dead_letter_jobs`) | > 50 | > 500 | DB tablo / admin /admin/queue | Sebep grupla, replay |
| Failed job rate | > 2% | > 5% | Celery task event | Provider rate limit / kod bug |
| Scheduler beat skew | > 60 s | > 300 s | `celery beat` log | Beat container restart |
| Task duration p95 (scrape) | > 90 s | > 300 s | Worker metric | Site bazlı throttle |
| Task duration p95 (embed) | > 60 s | > 180 s | Worker metric | NIM rate limit / batch boyutu |

## 5. Disk & Sistem

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| Disk kullanımı (root) | > 75% | > 85% | node_exporter / df | Log rotation / Postgres vacuum |
| Disk free buffer | < 10 GB | < 5 GB | df | MinIO snapshot prune |
| RAM kullanımı | > 80% | > 90% | free / docker stats | Container OOM prevention |
| Swap kullanımı | > 25% | > 50% | /proc/swaps | RAM artır / leak araştır |
| CPU sustained 5 dk | > 70% | > 90% | top / docker stats | Profile / scale |

## 6. Provider & Maliyet (Unit-Economics §6)

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| Per-user provider maliyet (gün) | > $5 | > $15 | provider_call_logs aggregator | Rate limit kullanıcıya |
| Per-user provider maliyet (ay) | > $50 | > $150 | aynı | Plan upgrade / suspend adayı |
| Provider monthly cap (deepseek) | 80% | 95% | settings cap (config.py) | Anthropic fallback'e geç |
| Provider error rate | > 5% | > 20% | provider_call_logs | Fallback chain tetikle |
| RAG hallucination rate (eval) | > 2% | > 5% | nodrat-test pipeline | Promp + retrieval review |

## 7. KVKK / Yasal

| Metrik | Warn | Critical | Kaynak | Aksiyon |
| --- | --- | --- | --- | --- |
| Takedown SLA breach | 1 hafta açık | 2 hafta açık | takedown_requests tablo | Manuel triage |
| Audit log gap | > 5 dk yazma yok | > 30 dk | audit_logs INSERT counter | Worker incele |
| Failed login | > 50/saat / IP | > 200/saat | auth.failed_login_attempts | IP block |
| Privacy request SLA (KVKK §15) | 25 gün | 30 gün | privacy_requests | Manuel ekip eskalasyonu |

---

## 8. Bildirim Yönlendirme

| Severity | Kanal | Eskalasyon |
| --- | --- | --- |
| warn | Slack `#nodrat-alerts` (15 dk silenced muted geçer) | 30 dk no-ack → email |
| critical | Slack `#nodrat-alerts` + email + (free SMS quota) | 5 dk no-ack → on-call telefon |
| outage | Status page (Better Uptime) public update | RSS feed + Twitter (manual) |

---

## 9. Alarm Sahipliği (RACI)

| Domain | Owner | Backup |
| --- | --- | --- |
| API performansı | Founder | — |
| DB | Founder | — |
| Worker / queue | Founder | — |
| Provider / maliyet | Founder | — |
| KVKK | Founder + legal@ | — |

> Tek kişilik takım fazı (MVP-1). On-call rotasyonu Faz 2+ için planlanır.

---

## 10. Çapraz Referans

- docs/engineering/architecture.md §10 — Monitoring & Observability
- docs/engineering/architecture.md §13 D9 — Sentry + Better Uptime kararı
- docs/strategy/risk-register.md — R-OPS, R-FIN, R-LEG kalemleri
- docs/strategy/unit-economics.md §6 — Per-user maliyet hesabı
- infra/uptime-monitors.md — Better Uptime specific config
- apps/api/app/main.py `_init_sentry()` — Sentry SDK init
- apps/api/app/config.py — `provider_monthly_cap_*` envs
