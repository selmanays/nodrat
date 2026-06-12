---
type: topic
title: "Search-Arg Observability — reality-analysis (#1483, 2026-06)"
slug: search-arg-observability-analysis-2026-06
status: live
created: 2026-06-12
updated: 2026-06-12
github_issue: 1483
github_issue_url: https://github.com/selmanays/nodrat/issues/1483
sources:
  - apps/api/app/core/research_tools.py§458-726
  - apps/api/app/api/app_research_stream.py§461-972
  - apps/api/app/core/pii.py§118-194
  - apps/api/app/modules/conversations/models.py§147-151
  - wiki/topics/citation-gap-guard-analysis-2026-06.md§7
tags:
  - analysis
  - rag
  - observability
  - telemetry
  - pii
  - read-only
aliases:
  - "search arg observability"
  - "1483 analizi"
---

# Search-Arg Observability — reality-analysis (#1483, 2026-06)

## TL;DR / Executive summary

**Search-arg observability yapılmalı ve ucuz** — gereken verinin çoğu **zaten üretiliyor ama düşürülüyor**: LLM'in tek kontrol ettiği tool argümanı `query` (her iki tool şeması query-only) ve planner'ın dönüştürdüğü arama metni (`topic`) + sayımlar `execute_search_news` meta'sında hazır (7 alan); orchestrator yalnız `query_class`'ı yakalıyor, 6 alan çöpe gidiyor. Önerilen tasarım **B+E**: mevcut `tool_result` thinking_step'ine flag-gated, **redact()+truncate edilmiş** yapılandırılmış `searches[]` metadata'sı — **schema YOK, behavior-neutral**, log-surface'e sıfır arg. Flag `research.search_arg_telemetry_enabled` **default OFF** (flag-OFF byte-identical). **S-1, S-2 citation-gap guard'dan ([#1484](https://github.com/selmanays/nodrat/issues/1484)) önce yapılmalı** — guard canary'sinin sınıf-A/sınıf-D ayrımı bu veri olmadan kör.

> ✅ **DURUM (2026-06-12): Implemented — [#1486](https://github.com/selmanays/nodrat/pull/1486) merged + deployed.** Flag `research.search_arg_telemetry_enabled` **default OFF** → prod davranış **no-op / byte-identical**; telemetri yalnız flag açıkça enable edilirse yazılır. Implementation = bu sayfadaki tasarımın birebiri: `tool_result` thinking_step metadata'sına `searches[]` (redacted+truncated query/topic, PII-safe, sabit key-set); schema/migration YOK; faz-2 alanları (critical_entities/timeframes/Wikipedia-meta) **henüz YOK**. **Flag enablement / canary YAPILMADI** — ayrı açık onay gerektirir. 11 yeni unit test (full suite 1349); prod assert: api'de yeni kod + `app_settings`'te flag satırı 0 + `/health` 200.

> ✅ **MICRO-CANARY SONUCU (2026-06-12): BAŞARILI + rollback tamamlandı.** Flag kullanıcı onayıyla kısa süreli ON yapıldı (SettingsStore.set, raw SQL yok); admin hesabından **5 yeni-konuşma sorgusu** koşuldu. **Sonuç:** 5/5 mesajda `tool_result.searches[]` yazıldı; **11/11 entry key-set doğru** (tool/round/query/topic/query_class/chunk_count/source_count/error); flag OFF iken searches[] yazılmıyordu (BEFORE assert, son 20 mesajda 0). **Bonus gözlem:** S4 (` ve `'li sorgu) **2 tur × 2 arama**, S5 (uzun özet sorgusu) **tek turda 4 paralel arama** — agent'ın doğal çoklu/decompose araması ilk kez **arama-metni düzeyinde** gözlendi (#619 post-mortem bulgusunun ölçülebilir hali). PII/log sızıntısı **0** (api loglarında arg grep=0; `@` işareti 0); behavior-neutral (eski `tool_result` detail korundu, tüm cevaplar cite'lı, sources_used 2-13); error/exception **0**; **stop-condition tetiklenmedi**. **Rollback:** `settings_store.reset` + commit → flag satırı 0 / get_bool False / `/health` 200 / 13 container → **prod baseline (flag unset/OFF)**. Redaction canlıda test edilmedi (sentetik PII bilinçli koşulmadı) — kanıt unit testlerde. **Kalıcı ON ayrı prod-config kararıdır.**

## 1. Current observability map

| Soru | Bugünkü durum |
|---|---|
| Tool adı | ✅ `tool_use` detail (L920-924) |
| Tool argümanları | ❌ persist edilmiyor — `tc.arguments` yalnız `_dispatch`'e gidiyor |
| Search query / planner topic | ❌ persist yok; **ama meta'da üretiliyor** (`research_tools.py` L717-725: query_class, topic, chunk_count, source_count, recency_requested, newest_published_at, freshness_gap_days) — L950-951'de 7 alandan 6'sı **düşürülüyor** |
| Tool round | ⚠️ kısmi — detail'de "tur N" yalnız N>1 |
| Result count | ✅ `tool_result` detail serbest-metin ("N kaynak bulundu") |
| Error/fallback | ❌ ayırt edilemiyor — timeout/hata count=0 ile aynı görünüm; yalnız logger.warning |

Ek: `done` event'i yalnız query_class+sayımlar; Wikipedia meta'sı boş `{}`; `provider_call_logs`'ta arg alanı yok.

## 2. Gap analysis — root-cause için gereken alanlar

Kaynağı **hazır** olanlar: `query` (LLM arg) · `topic` (planner dönüşümü — sınıf-A'nın "planner mı LLM mi" sorusu) · `query_class` · `chunk_count`/`source_count` (arama-başına granül) · `recency_requested`/`freshness_gap_days` · round · error-bayrağı.

**Faz-2'ye ertelenen** (ilk PR kapsamı DIŞI): `critical_entities` + `timeframes` (plan_result'ta var, meta'da yok → `app/core` touch gerektirir) · Wikipedia meta doldurma · `done` event zenginleştirme.

## 3. PII / security analysis

- **Belirleyici emsal:** thinking_steps **zaten** `effective_query[:80]`'i redaksiyonsuz persist ediyor (`query_rewrite` adımı, L498); tam `effective_query` kendi kolonu; ham `content` aynı tabloda. Arama-arg'ları aynı kullanıcı-türevli metnin türevi, aynı satıra yazılır → **yeni PII sınıfı yok**.
- **Yine de sıkılaştırma:** `query`/`topic` alanlarına [pii.py](../../apps/api/app/core/pii.py) `redact()` (email/telefon/TC-luhn/IBAN/IP/UUID) + **200-char truncate** — mevcut emsalden daha sıkı; `api→core.pii` import'u boundary-legal (providers/modules emsali).
- **Log-surface'e arg YAZILMAZ** (DB/SSE-only); user_id/email asla.
- **Erişim yüzeyleri (doğrulandı):** SSE+REST yalnız konuşma sahibine (auth `app_research.py` L239); ThinkingPanel bilinmeyen alanları render etmiyor; **SFT/DPO export raw thinking_steps çıkarmıyor** (yalnız `has_thinking_steps` bool); frontend tipi forward-compat (`topic_query` alanı zaten ön-tanımlı).
- Schema değişikliği YOK (JSONB `_log_step(**extra)` kalıbı — PR-5/PR-F emsali).
- Legal not: opinion-integration §3.1 redaction'ı LLM-transit'e tanımlar; thinking_steps DB-persist sınırı muğlak — redact() uygulamak muğlaklığı lehimize kapatır.

## 4. Design options

| Opt | Tasarım | Karar |
|---|---|---|
| A | Yalnız log (warning/debug) | ❌ retention ~container ömrü; retrospektif analiz imkânsız; log-surface'e user-metin genişletmek en kötü yüzey |
| **B ★** | thinking_steps'e redacted/truncated args | ✅ retrospektif SQL-analiz (bu arkın tüm analizleri thinking_steps'ten yapıldı) |
| C | Hash/fingerprint + count | ❌ metin okunamaz → teşhis yok |
| D | Admin-only debug mode | ❌ observability tam ihtiyaç anında (organik trafik) kapalı kalır |
| **E ★** | Structured telemetry alanları | ✅ B'nin formalize hali — **B+E birlikte kabul** |

## 5. Recommended design

- **Persist yeri:** mevcut `tool_result` thinking_step'ine `searches` extra'sı (turdaki her tool-call için bir kayıt). `sources_considered` yanlış yer (çıktı-kaynak listesi, arama-girdisi değil); `provider_call_logs` uygun değil (arg alanı yok, ops domain'i, mesaja FK yok); **yeni schema GEREKMEZ**.
- **Alan seti (sabit key-set, PII-işlenmiş):** `searches: [{tool, round, query: redact+trunc200, topic: redact+trunc200|null, query_class|null, chunk_count|null, source_count, error: bool}]`.
- **Saf helper:** `_search_telemetry_entry(tc_name, args, meta, round, error)` — redaction+truncation+key-set tek yerde, unit-test edilebilir (PR-F deseni).
- **Davranış:** cevap-yolu her durumda byte-identical (yalnız metadata enrichment); **flag OFF → emit yok → SSE/DB byte-identical**.
- **Flag:** `research.search_arg_telemetry_enabled`, default **False**, requires_restart=False. Runtime-ON = ayrı onaylı prod-config adımı (Redis pub/sub anlık, DELETE ile geri).

## 6. Minimal implementation plan

| # | Dosya | Değişiklik |
|---|---|---|
| 1 | `app/api/app_research_stream.py` | saf helper + flag okuma (+2 satır settings bloğu) + tc-loop'ta flag-gated toplama + `tool_result` `_log_step(..., searches=...)` (~15-20 satır) |
| 2 | `app/modules/settings_admin/routes.py` | registry +1 bool |
| 3 | `tests/unit/` | aşağıdaki set |

Tek küçük PR; **`app/core` dokunulmaz** (ilk PR'da); schema/migration yok; code-PR → FULL deploy.

## 7. Tests

Helper key-set exact-match · redact/truncate (PII'li query → `[*_redacted]`, max 200) · PII-free metadata (user_id/email yok) · flag-OFF: searches emit edilmez + mevcut suite byte-identical · flag-ON shape (round/count/error doğru; helper+composition düzeyi — full-orchestrator mock "first-yield-only" disiplinince atlanır, PR-F emsali) · error:true vakası (timeout ↔ "kaynak bulunamadı" ayrımı) · logger-mock: arg metni logger'a gitmez.

## 8. Hard-stops

Implementation ayrı açık onay · schema/migration ihtiyacı doğarsa DUR · arg log-surface'e yazılırsa / redact atlanırsa DUR · flag default-ON olursa DUR · app behavior değişirse DUR · prod flag ON = ayrı onay · scope `app/core`'a kayarsa DUR · lint-imports 16/16, CI otoriter.

## 9. #1484 (S-2 citation-gap guard) ilişkisi

**S-1 → S-2 sırası doğrulandı.** Guard canary'sinde retry tetiklenen her vakada `query/topic/chunk_count` gerekecek: alakasız-retrieval (sınıf-A; retry'ın "açıkça söyle" kolu doğru davranış) ile model-ihmali (sınıf-D; "cite et" kolu doğru) ancak bu veriyle ayrışır. **S-1'siz S-2 canary'si yalnız faz/sayım görür → kör.**

## İlişkiler

- [[citation-gap-guard-analysis-2026-06]] — §7 S-1 satırının detaylandırılması; S-2'nin ön-koşul analizi.
- [[query-failure-analysis-2026-06]] — §8.4 observability boşlukları (sınıf-A + sınıf-3 ortak kör nokta) bu sayfanın problem tanımı.

## Kaynaklar

- [#1483](https://github.com/selmanays/nodrat/issues/1483) — issue (bu sayfa onun reality-analysis'i); [#1484](https://github.com/selmanays/nodrat/issues/1484) — bağımlı iş.
- `apps/api/app/core/research_tools.py` §458-488/254-288 (tool şemaları query-only) · §521-536 (plan_query extraction) · §714-726 (7-alan meta).
- `apps/api/app/api/app_research_stream.py` §461-471 (`_log_step` **extra → SSE+DB) · §920-972 (tool_use/tool_result emit + tc_meta düşüşü L950-951) · §498 (`effective_query[:80]` persist emsali).
- `apps/api/app/core/pii.py` §118-194 (`redact()` imzası + pattern seti).
- `apps/api/app/api/app_research.py` §239/273 (owner-auth + raw thinking_steps dönüşü); `apps/api/app/modules/sft/` (export'ta yalnız bool).
- Keşif: 3 paralel read-only okuyucu (tool-şema/PII/exposure), 2026-06-12.
