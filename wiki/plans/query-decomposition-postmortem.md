---
type: plan
title: "Query Decomposition Post-Mortem — neden e2e fayda üretmedi? (#619)"
slug: query-decomposition-postmortem
status: live
created: 2026-06-11
updated: 2026-06-11
github_issue: 619
github_issue_url: https://github.com/selmanays/nodrat/issues/619
sources:
  - wiki/plans/query-decomposition-mini-plan.md§4
  - wiki/plans/query-decomposition-pr4-staging-runbook.md§9
  - apps/api/app/api/app_research_stream.py§396
tags: [post-mortem, rag, retrieval, query-decomposition, canary]
aliases: ["619 post-mortem", "decomposition failure analysis"]
---

# Query Decomposition Post-Mortem — #619 neden e2e fayda üretmedi?

## TL;DR

#619 **teknik olarak başarılı, ürün/e2e etkisi nötr** kapandı. Kök neden: prod agent (3b LLM-driven tool-loop) **zaten kendi başına çoklu `search_news` yapıyor**; advisory prompt-hint agent davranışını güvenilir değiştirmedi (7 sorgunun 3'ünde yok sayıldı). Benchmark'ta kazanan `union` (deterministic retrieval-merge) **hiç prod'a taşınmadı**; prod'a taşınan hint **hiç benchmark'la ölçülmedi**. Orijinal issue sinyali (radyasyon/F-16 miss'leri) decomposition'dan çok **query expansion / paraphrase / coverage-miss** ihtiyacına işaret ediyordu. Karar: **rafta / activation-pending; flag OFF; PR-G yapılmaz**; yeniden açma kararı gerçek kullanıcı log verisine bağlı (aşağıda "Only do if").

> Bu sayfa, "#619 neden aktive edilmedi?" sorusunun **ana referansıdır**. Analiz 2026-06-11 oturumunda read-only yapıldı (kod/PR/prod-config/mutation yok); tek yeni veri canary mesajlarının thinking_steps search-adım sayıları (read-only SELECT).

## 1. Executive Summary

- Teknik ark kusursuz: implementation + canary mekanizması + PR-F observability + micro-canary v1/v2 + temiz rollback. Ürün etkisi: **nötr** (baseline↔during citation aynı).
- **Prod agent zaten doğal çoklu search yapabiliyor** — Q2 baseline'da hint'siz **3 arama** (canlı kanıt).
- **Prompt-hint advisory**; agent 7 decomposed sorgunun **3'ünde yok saydı** → davranışı güvenilir değiştirmiyor.
- **Benchmark'ta iyi görünen `union` prod'a taşınmadı** (kasıtlı, ayrı karar olarak); ölçülen ile ship edilen mekanizma farklıydı.
- **Orijinal issue sinyali** ("Azıcık radyasyon" Bianet'te vardı/görülmedi; F-16/C4Defence) tek-niyetli kelime-eşleşme miss'i → ihtiyaç muhtemelen **query expansion/paraphrase**, compound decomposition değil.

## 2. Failure Analysis — canlı kanıt

Micro-canary v2 mesajlarının thinking_steps'inden arama sayıları (tool_use+tool_result çifti = 1 arama; research loop'ta baskın araç `search_news`):

| Sorgu | Hint (sub_query) | Agent araması | Hint'e uydu? | src |
|---|---|---|---|---|
| Q1 asgari ücret (during) | 2 | 2 | ✓ | 4 |
| Q2 elektrik (during) | 2 | 2 | ✓ (ama ↓) | 2 |
| Q4 deprem | 2 | **1** | ✗ | 4 |
| Q5 yapay zeka | 2 | 2 | ✓ | 9 |
| Q6 okullar | 2 | 3 | ✓ (fazlası) | 18 |
| Q7 çevre şehircilik | 2 | **1** | ✗ | 1 |
| Q8 enflasyon (llm, 1312ms) | **3** | **1** | ✗ | 3 |
| **Q2 baseline (hint'siz!)** | — | **3** | — | 2 |

- **Q2 baseline hint'siz 3 arama yaptı** → agentic loop çoklu aramayı zaten yapıyor; hint'li koşumda yalnız 2 (n=1: hint'in agent planını **daraltabildiğine** dair zayıf anchor sinyali).
- **Hint 3/7 yok sayıldı** (Q4, Q7, Q8). En çarpıcısı **Q8: 1312ms LLM decompose maliyeti → 3 alt-sorgu → agent yine tek arama** (maliyet var, etki yok).
- **Q7 known blind spot:** kurum adındaki "ve" yanlış bölündü ("Çevre, Şehircilik **ve** İklim Değişikliği Bakanlığı") → src=1; `mq_005` hiçbir merge-konfigürasyonunda 0.000'dan çıkmadı.
- **Metrik sınırı:** `sources_used` final-answer citation proxy'si — retrieval recall ile birebir aynı değil; cevap-bütünlüğü (iki konunun da yanıtlanması) hiç ölçülmedi; n=3 eşli kıyas. Ayrıca Q2'de 3 arama = 2 arama = aynı 2 kaynak → kısıt corpus tarafında olabilir.

## 3. Benchmark ↔ Prod farkı

| Boyut | Benchmark (union, Validation 4) | Prod canary (3b hint) |
|---|---|---|
| Mekanizma | **Deterministik**: her alt-sorgu zorunlu retrieval → article-level union | **Advisory**: "ayrı ayrı ara" user-mesajı; uymak agent'a kalmış (3/7 uymadı) |
| Baseline | Tek-shot retrieval (çoklu arama **yapamaz**) | Agentic loop (çoklu aramayı **zaten yapıyor**) |
| Ölçülen | retrieval recall@k (golden UUID) | final cevap citation sayısı |
| Sonuç | recall@5/10/20 **+1.0/+11.7/+11.1%** | **nötr** (4→4, 2→2, 2→2) |

Benchmark kazanımı gerçekti ama **iki kez transfer edilemedi**: (1) union hiç ship edilmedi — PR-E kaydında açıkça "alınan şey mevcut prod-3b"; (2) benchmark baseline'ı çoklu-arama yapamayan tek-shot retrieval'dı → +11.7% "tek arama vs dört arama" farkını ölçtü; prod'da o boşluk agent tarafından zaten kapalıydı. **Benchmark, prod'da var olmayan bir kabiliyet boşluğunu ölçtü.** Proxy-dürüstlük uyarısı her kayıtta vardı ve doğru çıktı; hata uyarıyı yazmamak değil, nötr-e2e olasılığına rağmen arkın tamamını yürütmekti.

## 4. Root Causes (önem sırasına göre)

1. **Capability overlap / redundancy** — agentic 3b loop zaten adaptif çoklu arama yapıyor; hint en iyi ihtimalle aynı şeyi söylüyor. *Kanıt: Q2 baseline 3 arama; 3/7 hint-ihlali.*
2. **Problem-solution mismatch** — orijinal kanıt (radyasyon, F-16) tek-niyetli coverage-miss'ti ("multi-query yok" = expansion ihtiyacı); inşa edilen compound decomposition. Gerçek multi-intent oranı hiç ölçülmedi; golden_multi kendi icat ettiğimiz sentetik "X ve Y" sınıfına kalibreydi.
3. **Evidence-transfer yanılgısı** — doğrulanan artefakt (deterministic union) ≠ ship edilen artefakt (prompt-hint); pozitif benchmark, benchmark'ın hiç ölçmediği mekanizmanın canary'sine gerekçe oldu.
4. **Metric/sample sensitivity** — citation-count + n=3 eşli sorgu + insan değerlendirmesi yok → gerçek bir kazanım olsa da görünmeyebilirdi.
5. **Heuristic fragility** — "ve" split'i kurum adlarını bölüyor (Q7); mq_005 decomposition-level 0.000. Aktivasyonda bir sorgu alt-kümesi için net-zarar riski.
6. **Low corpus headroom** — küçük corpus'ta ek arama yeni kaynak getirmiyor (Q2: 3 arama = 2 arama = aynı 2 kaynak).

## 5. What We Learned

1. **Agentic baseline'ın zaten ne yaptığını önce ölç** — feature, baseline'ın yapamadığı şeyi eklemeli. (search_steps telemetry'si artık bunu ölçebiliyor; bu analizde ilk kez kullanıldı ve hipotezi tek sorguda doğruladı.)
2. **Prompt-hint zayıf kontrol mekanizması** — ~%40 yok sayılma ile "feature" değil "öneri". Garanti gereken yerde deterministik orchestration gerekir.
3. **Benchmark yalnız ölçtüğü mekanizma için kanıt sayılmalı** — union'ın kazanımı hint için kanıt değildi.
4. **Motivasyon-kanıtını feature tanımına çevirirken sınıf kontrolü yap** — radyasyon/F-16 örnekleri decomposition değil query-expansion vakasıydı.
5. **Süreç disiplini işledi** — flag-OFF byte-identical, allowlist canary, PII-suz telemetry, temiz rollback, her adım onaylı → başarısızlık ucuz ve geri-dönüşlü oldu. Observability (cohort DB + warning log) kalıcı kazanım.

## 6. Do NOT Do Next

- ❌ **PR-G cost tracking** — flag OFF'ken decompose hiç çağrılmıyor → izlenecek maliyet **sıfır**; PR-G ancak yeni bir canary kararının ön-koşulu olarak anlamlı.
- ❌ Geniş canary / global activation — sinyal nötr, yeni kanıt yok.
- ❌ **3a deterministic union'ı prod'a taşımak** — kök neden 1-2 çözülmeden aynı yanılgının pahalı tekrarı.
- ❌ Q7 heuristic fix / golden genişletme / yeni #619 PR'ları — etkisi nötr feature'ı cilalamak.
- ❌ Kodu hemen silmek — test edilmiş, flag-gated, byte-identical, bakım yükü düşük; silme ayrı/aceleye-gelmez karar (aşağıda koşullu not).

## 7. Only Do If — yeniden açma koşulları

| Sinyal | Kanıt biçimi | Açılacak yol |
|---|---|---|
| Gerçek log'larda multi-intent oranı anlamlı | read-only log analizi (örn. research sorgularının ≥%10-15'i gerçek bileşik) | 3a deterministik union'ı o sınıfla sınırlı yeniden değerlendir |
| Baseline agent multi-intent'te tek arama yapıyor | search_steps telemetry: decomp-yok + 1 arama + düşük coverage paterni | Önce agent prompt iyileştirme; yetmezse 3a |
| Radyasyon-tipi miss tekrarları | coverage_gap/zero-source vakalarında kelime-uyumsuzluğu | **Decomposition değil** → query expansion/paraphrase (ayrı future investigation) |
| Kullanıcı feedback paterni | "iki şey sordum, biri yanıtlandı" thumbs-down/şikâyet | Cevap-bütünlüğü eval + hedefli canary |
| Corpus büyümesiyle recall problemi | kaynak sayısı arttıkça per-arama recall düşüşü ölçülürse | Retrieval-katmanı çözümleri (union dahil) yeniden masada |
| **Hiçbiri gelmezse** (~2026-08'e dek) | sinyalsiz geçen ~2 ay | Housekeeping turunda kodu silmeyi *değerlendir* (ayrı karar) |

## 8. Final Recommendation

- **#619 rafta / activation-pending kalır** — flag OFF, allowlist empty, byte-identical baseline; issue OPEN.
- **PR-G yapılmaz** (OFF durumda cost zaten sıfır).
- **Bir sonraki daha değerli iş:** (1) **gerçek sorgu-dağılımı analizi** (read-only: multi-intent oranı + zero-source/coverage_gap/root-miss örnekleri) — #619'un "only if" sorusunu veriyle kapatır ve sonraki retrieval yatırımının yönünü söyler; (2) corpus coverage işleri (kaynak corpus'ta yoksa hiçbir sorgu-tekniği bulamaz); (3) cevap-kalitesi eval altyapısı (gelecek canary'lerin "nötr mü, ölçemiyor muyuz?" belirsizliğini kaldırır).
- **Query expansion / paraphrase** ayrı bir **future investigation** olarak not edildi — orijinal #619 motivasyonunun (radyasyon/F-16) asıl adresi muhtemelen bu.

## İlişkiler

- **Ana plan + PR arkı:** [[query-decomposition-mini-plan]] §4 (PR-1…PR-F sonuçları + canary kayıtları).
- **Operasyon + canlı instance'lar:** [[query-decomposition-pr4-staging-runbook]] §9 (Validation 1-4 + Micro-Canary v1/v2 + rollback).
- **Mimari bağlam:** [[architecture-final-state-2026-05]] §3 (recall CI-able değil → manuel/staging gate).

## Kaynaklar

- [query-decomposition-mini-plan.md](query-decomposition-mini-plan.md) §4 — PR sonuçları, PR-E/PR-F kayıtları, canary sonuçları.
- [query-decomposition-pr4-staging-runbook.md](query-decomposition-pr4-staging-runbook.md) §9 — benchmark tabloları (Validation 1-4), micro-canary v1/v2 instance'ları.
- [#619](https://github.com/selmanays/nodrat/issues/619) — issue body (orijinal motivasyon: radyasyon/Bianet + F-16/C4Defence miss'leri) + PAUSED yorumu.
- `apps/api/app/api/app_research_stream.py` §396 — `_build_decomposition_hint` (advisory hint mekanizması).
- Canlı kanıt: micro-canary v2 mesajlarının `thinking_steps` search-adım sayıları (read-only SELECT, 2026-06-11 oturumu; PII-suz agregat).
