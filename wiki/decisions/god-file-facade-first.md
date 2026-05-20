---
type: decision
title: "God-File: Facade + Characterization Test Before Split"
slug: "god-file-facade-first"
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - "wiki/topics/ci-blind-8-months-incident.md"
  - "wiki/decisions/research-cited-only-hard-invariant.md"
  - "wiki/topics/refactor-anti-patterns-do-not-do.md"
tags: ["architecture", "refactor", "god-file", "characterization-test", "locked-decision"]
aliases: ["facade-first", "strangler-fig"]
---

# God-File: Facade + Characterization Test Before Split

> **Karar:** 800+ satırlık veya kritik davranış taşıyan god-file'lara doğrudan parçalama yasak. Sıra: **(1) Modülün public facade'ını oluştur ve eski dosyayı re-export et → (2) tüm çağrı yerlerini facade'a yönlendir → (3) characterization test paketi yaz (golden snapshot) → (4) iç parçalama kademeli olarak yapılır, facade sözleşmesi sabit kalır.**
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

3 ana god-file var:

| Dosya | Satır | Kritiklik | Sessiz regresyon riski |
|---|---|---|---|
| `core/retrieval.py` | 2174 | RAG kalbi | recall@5/10 0.005 puan değişimi eval'de görünmez; production'da sessiz |
| `api/app_research_stream.py` | 1440 | SSE state machine | event sequence, cancellation, reconnect; davranış kayması test edilmez |
| `core/extractor.py` | 1189 | HTML extraction cascade | strategy_used sırası değişirse TR sitelerinde sessiz fail |

Frontend ek god-file: `src/app/admin/rag/page.tsx` (2356), `src/lib/api.ts` (2041).

**Tarihsel kanıt:**
- **RC3-B v1 LLM-verifier prod 4/8 yanlış-pozitif** (log #1076): "test ettiyse tamam mı?" yetersizdi; kullanıcı prod'da yakaladı.
- **Türkçe collation #939** 6 ay kör kaldı; entity-synonym hypothesis yanlıştı, kök sebep PostgreSQL C-locale lowercase.
- **CI 8 ay kör + 11 gizli regresyon** (log #1030): "yeşil sanılan" ≠ "koşuyor"; test seti yokluğunda davranış kayması yıllar sürebilir.

Bu üç ders ortak ipliği: **test seti yetersizdi, davranış sessizce değişti.**

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Doğrudan parçalama (dosyayı 5-9 dosyaya böl) | Hızlı; tek atomik PR | Sessiz regresyon riski yüksek; rollback zor; off-by-one + RRF sırası değişimi eval'de görünmez | **Reddedildi** |
| Bütün god-file'ı tek mega-test ile kapla, sonra böl | Test garantili | Mega-test yazımı kendisi 1-2 hafta; god-file büyürken parçalama gecikiyor | **Reddedildi** |
| **Facade-first + characterization + kademeli iç parçalama (Strangler Fig)** | Sözleşme sabit; characterization snapshot davranış garantisi; PR'lar küçük; rollback atomik | Daha çok PR; toplam süre uzun | **Seçildi** |

## Süreç (3 god-file için ortak)

### Adım 1 — Facade oluştur

`modules/<mod>/__init__.py` veya `modules/<mod>/facade.py` modülün public API'sını expose eder. İlk hali sadece legacy dosyayı re-export:

```python
# modules/rag/__init__.py (Phase 5, ilk PR)
from app.core.retrieval import (
    hybrid_search_chunks,
    hybrid_search_agenda_cards,
    search,
)
```

Bütün çağrı yerleri (admin_rag.py, app_research_stream.py, research_tools.py, workers/tasks/agenda.py) facade'a yönlendirilir.

### Adım 2 — Characterization test paketi

Hangi davranışlar snapshot'lanır (her god-file için):

#### `core/retrieval.py` → `rag/`
- `tests/eval/retrieval_golden_snapshot.py` — 50+ query (niche_007, niche_009, RC3-B v2 verifier query, agenda chunks-first) → top-K result snapshot (article_id sequence + RRF scores).
- `tests/unit/test_ner_idf_match.py` — `_resolve_ner_target_aids` + `_ner_idf_match_aids` izole input/output.
- `tests/unit/test_quote_normalize.py` — Bianet curly-quote fixture (#647).
- **CI gate:** PR'da recall@5/10 baseline'dan delta > 0.5% ise fail.

#### `api/app_research_stream.py` → `generations/`
- `tests/eval/sse_replay_golden.py` — 10 conversation senaryosu (yeni soru, follow-up, RC3-B reframe trigger, citation, multi-turn, cancellation, timeout, quota exceeded). Event_type + payload schema + sequence sabitlenir (timestamp hariç).
- `tests/unit/test_citation_validation.py` — `_cited_numbers`, `_is_substantive`, `_has_reconstruction_marker` regex edge cases.
- `tests/integration/test_tool_loop_timeout.py` — 30s tool-call timeout, MAX_TOOL_ROUNDS=3.
- `tests/integration/test_deepseek_cache_invariant.py` — tool_choice="auto" cache prefix korunur (L21).

#### `core/extractor.py` → `crawler/`
- **Mevcut** `tests/unit/test_extractor.py` (1496 satır, 88 test) — TR sitelerinin HTML fixture'ları.
- **Eklenir:** `tests/unit/test_extractor_strategy_sequence.py` — hangi site hangi tier'da (JSON-LD → readability → fallback) yakalanır, sequence sabitlenir.
- **Eklenir:** Status transition snapshot (`discovered → quarantine → discarded` #904).

### Adım 3 — Kademeli iç parçalama

Snapshot suite **stable yeşil** olduktan sonra dosya parçalanır. Sıra:
- Önce **pure functions** (constants, normalize, scoring helpers) — en güvenli.
- Sonra **stateless logic** (NER resolver, citation validators).
- En son **orchestrator** (hybrid search entry, SSE stream body).

Her PR'da snapshot diff = 0 olmalı; aksi halde merge edilmez.

## Sonuçlar

- God-file parçalama hızlı değil — disiplinli.
- Her god-file için ayrı **bir** characterization paketi PR'ı + 6-10 küçük iç parçalama PR'ı.
- Facade sözleşmesi sabit kaldığı için çağrı yerleri en başta yönlendirilir, sonradan dokunulmaz.

## Geri alma maliyeti

Bu disiplini gevşetip doğrudan parçalama yapılırsa: RC3-B v1 tipi sessiz regresyon; production'da kullanıcı yakalar; rollback için tüm parçalama PR'ları geri alınır; characterization paketi sonradan yazılır. **Çok yüksek maliyet** (kullanıcı güveni + prod retrieval kalitesi).

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]], [[no-internal-backcompat-aliases]]
- **Bağlı topic:** [[refactor-anti-patterns-do-not-do]] (#3, #4)
- **Tarihsel kanıt:** [[ci-blind-8-months-incident]], [[research-cited-only-hard-invariant]], log #939

## Kaynaklar

- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md) §God-File Strategy
- [docs/engineering/testing-strategy.md](../../docs/engineering/testing-strategy.md) §Characterization Tests
