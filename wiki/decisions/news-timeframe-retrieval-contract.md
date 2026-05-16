---
type: decision
title: "News-query timeframe → retrieval penceresi kontratı"
slug: "news-timeframe-retrieval-contract"
category: "rag"
status: "locked"
decided_on: "2026-05-16"
decided_by: "tech"
created: "2026-05-16"
updated: "2026-05-16"
sources:
  - "apps/api/app/core/chat_tools.py§_since_hours_from_timeframes"
  - "apps/api/app/prompts/query_planner.py§_apply_news_recency_default"
  - "GitHub Issue #906 / PR #907 / PR #909"
tags: ["locked-decision", "rag", "retrieval", "planner", "freshness", "879-family"]
aliases: ["timeframe-since-hours", "news-recency-contract"]
---

# News-query timeframe → retrieval penceresi kontratı

> **Karar:** Planner timeframe'i retrieval zaman penceresini (`since_hours`) sürer; `news_query` için timeframe ASLA boş kalmaz (boşsa deterministik kod son 7 günü enjekte eder) — bu garanti prompt'a DEĞİL koda bağlıdır.
> **Durum:** locked
> **Tarih:** 2026-05-16

## Bağlam — sorun

Prod conv: "günün son gelişmelerini söyle" → 10 kaynaktan 6'sı **>7 gün eski** (en eski 2026-04-04, ~42 gün). Üç kök neden ([[chat-knowledge-evolution]] #906, [[agentic-generate-orchestration]] sarmalı):

1. **A — planner timeframe retrieval'a HİÇ iletilmiyordu.** `execute_search_news` `hybrid_search_chunks(..., since_hours=24*90)` SABİT. #845 agentic geçişinde planner→retrieval timeframe bağı koptu ([[chat-knowledge-evolution]] ders #22 ailesi — tool sarmalı alt-katmanın ürettiği karar-ilgili boyutu=ZAMAN düşürmemeli; #879 ile aynı sınıf).
2. **B — planner örtük güncellik ifadelerini timeframe'e çevirmiyordu.** "günün/son gelişmeler/son dakika" gibi açık tarih içermeyen ama yakın-zaman isteyen sorgularda `timeframes=[]`.
3. **B'nin derin nedeni — prompt yolu atlanıyor:** "günün son gelişmelerini söyle" 4 kelime + soru-marker yok → [[planner-bypass-short-query]] (#785) planner LLM'i HİÇ çağırmaz, `bypass_plan` `timeframes=[]` hardcoded döner. Ayrıca planner prompt'u #270 PR-B ile DB'den runtime override edilebilir (kod-içi `SYSTEM_PROMPT` yalnız fallback). **Prompt değişikliği güvenilmez.**

Prod smoke (PR #907 sonrası, gerçek `plan_query(use_cache=False)`): B-prompt ETKİSİZ — `timeframes_count=0`, `since_h=2160` (daralmadı), buckets `today=0 ≤7g=4 >7g=6`. A doğru çalışıyordu (boşsa default 90g) ama B beslemediği için bug uçtan-uca açık kaldı.

## Karar — iki parça

**A (#907):** `chat_tools._since_hours_from_timeframes(timeframes, now, default_h=24*90)` — planner timeframe'lerinin EN ESKİ `from_iso`'sundan `now-delta` türetir, clamp `[6h, 90g]`. `hybrid_search_chunks` bu dar `since_hours` ile çağrılır; **dar pencere boş dönerse** 90g'ye fallback ("güncelde yoksa genele"; "bulunamadı" riski yok).

**B2 (#909):** `query_planner._apply_news_recency_default(plan, current_time)` — `query_class == news_query` ve `timeframes` boşsa → varsayılan **son 7 gün** TimeframeSpec enjekte. `plan_query`'nin ÜÇ dönüş noktasında uygulanır: **cache-hit** (eski 24h TTL kaydı timeframe'siz olabilir), **bypass** (#785 PR-G), **parsed** (LLM/DB-override prompt'u yok saysa da). `general_knowledge`/`meta_query`/`mixed` ve LLM'in açık aralık ürettiği sorgular ETKİLENMEZ.

> **Neden prompt değil kod:** Prompt talimatı LLM'de olasılıksal; #785 bypass prompt'u tamamen atlar; #270 DB override kod-içi prompt'u runtime değiştirir. "news_query timeframes asla boş" kontratı yalnız deterministik kodda garanti edilebilir. Retrieval kalite makinesi (RRF/top_k/candidate_pool/rerank) DEĞİŞMEZ — yalnız zaman penceresi (`published_at >= since`).

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Sadece prompt (B) — planner'a "boş bırakma" talimatı | Minimal kod | #785 bypass + #270 override prompt'u atlar; LLM olasılıksal → prod'da ETKİSİZ kanıtlandı | reddedildi |
| `since_hours` sabit küçült (ör. 7g) | Basit | Açık-tarihsel/arşiv sorgu kırılır; planner niyeti yok sayılır | reddedildi |
| RRF'ye recency ekle | Ranking'de tazelik | "Kalite makinesi DEĞİŞMEZ" kuralı; kapsam dışı (ayrı risk) | reddedildi |
| **A (timeframe→since_hours + fallback) + B2 (deterministik kod kontratı)** | Planner niyeti onurlandırılır; bypass/override-bağışık; açık-tarihsel kısa sorgu fallback'le kurtulur; kalite makinesi sabit | Açık-tarihsel kısa sorguda +1 retrieval turu (latency) | **seçildi** |

## Sonuçlar

- Etkilenen: [[chunks-first-retrieval]] (90g artık SABİT değil, planner-sürücülü tavan), [[planner-bypass-short-query]] (bypass timeframes=[] artık news_query'de son-7g'ye dönüşür), [[agentic-generate-orchestration]] (search_news sarmalı zaman boyutunu taşır), [[chat-knowledge-evolution]] (ders #22 ailesi yeni örnek).
- Prod re-smoke (B2 sonrası, gerçek DeepSeek+bge-m3+prod DB): `timeframes=1` ("son 7 gün (#906 varsayılan)"), `since_h=168` (narrowed=True), buckets **today=1 ≤7g=9 >7g=0** (önce 6/10 eski) — bug uçtan-uca çözüldü.
- Açık-tarihsel kısa sorgu (örn. "2023 depremi") yanlışlıkla 7g alır → dar pencere boş → A-tarafı 90g fallback → eski içerik yine erişilir (regresyon yok, +1 tur).
- Test: `_since_hours_from_timeframes` 12 case + `_apply_news_recency_default` 8 case + chat_tools/query_planner regresyon = 61/61.

## Geri alma maliyeti

> `chat_tools.execute_search_news`'te `since_h` yerine `since_hours=24*90` sabitlersen A geri alınır (eski-haber bug'ı döner). `query_planner._apply_news_recency_default`'ı no-op yaparsan B2 geri alınır (news_query timeframe boş kalır → A boşsa-default 90g'ye düşer, yine bug). İkisi de evergreen — admin flag GEREKMEZ; geri alma yalnız bug'ı geri getirir.

## İlişkiler

- [[chunks-first-retrieval]] — 90g penceresi artık planner-sürücülü tavan (çapraz-güncellendi)
- [[planner-bypass-short-query]] — bypass `timeframes=[]` artık news_query'de son-7g kontratına uğrar (çapraz-güncellendi)
- [[agentic-generate-orchestration]] — `search_news` tool sarmalı (#845) zaman boyutunu taşımalı
- [[chat-knowledge-evolution]] — #906 satırı + anti-pattern ders #25 (#22/#24 ailesi)

## Kaynaklar

- [Issue #906](https://github.com/selmanays/nodrat/issues/906) · [PR #907](https://github.com/selmanays/nodrat/pull/907) (A) · [PR #909](https://github.com/selmanays/nodrat/pull/909) (B2)
- [`apps/api/app/core/chat_tools.py`](apps/api/app/core/chat_tools.py) — `_since_hours_from_timeframes`
- [`apps/api/app/prompts/query_planner.py`](apps/api/app/prompts/query_planner.py) — `_apply_news_recency_default`
