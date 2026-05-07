---
type: entity
title: "R-FIN-01 — LLM Cost Runaway"
slug: "risk-cost-runaway"
category: "risk"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.5"
  - "docs/strategy/risk-register.md§2.1"
  - "docs/strategy/unit-economics.md§6"
tags: ["risk", "fin", "cost", "llm", "rate-limit", "red"]
aliases: ["R-FIN-01", "cost-runaway", "llm-cost-blowup"]
---

# R-FIN-01 — LLM Cost Runaway

> **TL;DR:** Bir kullanıcı script yazar, API'yi yağmalar. Veya bir bug loop'u her saniye LLM çağrısı yapar. Aylık $1.000+ unbudgeted spend → margin yer, cash flow şoku. Skor **9 🔴**. Mitigation: per-user rate limit + provider hard cap + concurrency limit + cost-per-user alarm + anomaly detection + circuit breaker.

## Tanım

LLM provider'lar (DeepSeek, Anthropic, OpenAI) pay-per-token. Naive bir API fail durumunda retry loop'u veya kötü niyetli kullanıcı bot'u dakikalar içinde 1000+ LLM çağrısı yapabilir. NIM free tier kullanmak DeepSeek için dolaylı kalıcı koruma sağlıyor (cost $0) ama:

1. **NIM rate limit'e takılmak** generation latency artırır → kullanıcı deneyimi bozulur.
2. **Pro/Agency tier'larda** Anthropic native API'ye geçince cost hızla birikir (~$4/1M output token Haiku).
3. **Embedding queue'da** loop bug'ı NIM bge-m3'te de aynı sorunu yaratır.

## Skor

| Boyut | Değer | Açıklama |
|---|---|---|
| **Olasılık** | 3 | Rate limit eksikliğinde yüksek, mevcut kontrollerle azalmış. |
| **Etki** | 3 | Margin yer (tier başına maliyet üst limiti aşar) + cash flow şoku. |
| **Skor** | **9** | 🔴 Kırmızı. |

## Mitigation (risk-register §3.5)

| ID | Önlem | Durum |
|---|---|---|
| M1 | Per-user rate limit (saatlik + günlük) | ✅ implemented (Redis sliding window — architecture.md §5.3) |
| M2 | Provider başına aylık hard cap | 🟡 alarm var, hard kill switch eksik |
| M3 | Concurrent generation limit per user | ✅ tier-based (free=1, starter=2, pro=3, agency=5 — pricing-strategy.md) |
| M4 | Cost-per-user alarm ($5/gün/user) | ✅ alarm-thresholds.md |
| M5 | Anomaly detection (10x normal kullanım flag) | 🟡 partial — tek metric (request rate), full anomaly detection MVP-3 |
| M6 | Circuit breaker pattern | ✅ provider abstraction §4.3 with_fallback |
| M7 | **Pipeline token volume reduction** (prompt cache hit max + context size optimization) | ✅ **MVP-2.1 epic [#391](https://github.com/selmanays/nodrat/issues/391) — 7/7 sub-issue tamamlandı 2026-05-08.** PR [#411](https://github.com/selmanays/nodrat/pull/411) (#394+#395+#397: citation batch + settings paralel + normalize tek nokta), PR [#416](https://github.com/selmanays/nodrat/pull/416) (#396+#398: short query candidate_pool + citation embedding reuse), PR [#418](https://github.com/selmanays/nodrat/pull/418) (#392+#393: prompt prefix stability + content top_k 10→5). Hedef: input token -%34, $/req -%25 — bkz. [[pipeline-performance-baseline]] tracking tablosu. |

## Tetikleyici

```text
Tetikleyici 1: Provider quota cap eksikliği
Senaryo 1:    Kullanıcı script yazar, /app/generate'i her saniye çağırır.
              Per-user rate limit (5/dk default) tetiklenir → 429 döner.
              Eğer rate limit eksik veya tier'a göre yanlış konfigure ise...
              1 saat × 60 dk × 60 sn = 3600 generation × $0.001 cost ≈ $3.6/saat/user
              10 kötü kullanıcı = $36/saat = $864/gün

Tetikleyici 2: Bug loop
Senaryo 2:    Embedding worker bir hata sonrası retry'a düşer.
              Retry config yanlışsa exponential backoff devre dışı.
              Tek bir hatalı article → infinite embedding çağrısı.
              NIM rate limit free tier'ı tüketir, fallback local'e geçer
              (CPU yer ama maliyet sıfır kalır — daha az kötü).
```

## Kontrol checkpoint'leri

```text
Saatlik:  Provider spend rate (alarm-thresholds.md §X)
Günlük:   Top 20 user cost report
Anlık:    Anomaly alarm Slack
Aylık:    Provider invoice reconciliation
```

## Cost-per-user alarm threshold'ları (alarm-thresholds.md)

INDEX §0'da [docs/engineering/alarm-thresholds.md] referansı var. Net threshold'ları orada — bu sayfanın ingest edilmesi gerek (sıradaki TODO).

## Çapraz referanslar

- **Bağlı kararlar:** —
- **Bağlı kavramlar:** [[provider-abstraction]] (with_fallback + circuit breaker), [[risk-scoring]].
- **Bağlı varlıklar:** [[deepseek]], [[claude-haiku-4-5]], [[local-bge-m3]].
- **İlgili topics:** [[risk-catalog]], [[llm-provider-strategy]], [[pipeline-performance-baseline]] (M7 mitigation tracking).
- **İlgili dokümanlar:**
  - [docs/strategy/unit-economics.md §6 (cost tracking)](../../docs/strategy/unit-economics.md)
  - [docs/engineering/alarm-thresholds.md](../../docs/engineering/alarm-thresholds.md) — exact threshold'lar
  - [docs/engineering/architecture.md §4.4 (cost tracking)](../../docs/engineering/architecture.md)

## Açık sorular / TODO

- **M2 hard kill switch:** "Provider başına aylık hard cap" — alarm var ama kullanım limiti aşılırsa servis durdurma otomatik mi? Manuel intervention gerekiyorsa hangi runbook izlenir?
- **M5 anomaly detection MVP-3:** "10x normal kullanım flag" 2026 Q3-Q4 zaman çizelgesinde uygulanacak. Şu an gap: tek metric (request rate) yeterli değil, multi-metric (token volume, cost, latency anomalisi) gerek.
- **Per-tier cost limit dokümanı:** alarm-thresholds.md ingest edilmedi → cost-per-user $5/gün/user değeri tier-bağımsız mı, yoksa Free=$0.5, Pro=$5 gibi mi? Net değil.

## Kaynaklar

- [docs/strategy/risk-register.md §3.5 (R-FIN-01 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md)
- [docs/strategy/unit-economics.md §6 (cost tracking)](../../docs/strategy/unit-economics.md)
- [docs/engineering/alarm-thresholds.md](../../docs/engineering/alarm-thresholds.md)
- [docs/engineering/architecture.md §4.4 (cost tracking)](../../docs/engineering/architecture.md)
