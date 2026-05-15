---
type: topic
title: "Chat knowledge source mimari evrimi — #809→#828 karar/vazgeçiş zinciri"
slug: "chat-knowledge-evolution"
category: "retrospective"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "wiki/decisions/llm-tool-use-wikipedia.md"
  - "wiki/decisions/tiered-knowledge-architecture.md"
  - "GitHub PR #810→#828"
tags: ["rag", "chat", "retrospective", "anti-pattern", "faz-2", "tool-use"]
aliases: ["faz2-evolution", "wikipedia-fallback-history"]
---

# Chat knowledge source mimari evrimi

> **TL;DR:** Chat'in "haber kaynağı yetersizse genel bilgi getir" yeteneği tek seansta **5 mimari iterasyon** geçirdi. Confidence-routing → CTA banner → pattern-matching → fast-path hepsi production'da kırıldı veya kullanıcı tarafından reddedildi. Doğru çözüm en başta basitti: **LLM tool-use** (LLM kaynak yetersizse kendi karar verir). Bu sayfa neyin neden başarısız olduğunun anti-pattern kataloğudur — [[failed-experiments-rag-quality]] benzeri.

## Bağlam

Faz 1 chat-only migration (#800-#807) sonrası kullanıcı sohbeti "general assistant" gibi kullanmaya başladı ("trump kaç yaşında", "stargate atlantis kaç sezondu"). Sistem haber arşivinde arayıp "kaynaklarda yok" diyordu. Çözüm: haber yetersizse Wikipedia/Wikidata'ya başvur. Ama "nasıl?" sorusu 5 iterasyon sürdü.

## Zaman çizelgesi (karar → vazgeçiş)

| PR | Yaklaşım | Sonuç |
|---|---|---|
| #810 (2A) | **Confidence Router** — 5-signal score, T_high/T_low routing | ❌ Skor "konu geçiyor mu" der, "cevap var mı" demez. "trump kaç yaşında" → Trump haberlerde geçtiği için skor T_low üstü → Wikipedia tetiklenmedi |
| #814 (2B) | **Wikipedia CTA + consent card** — kullanıcı onayı | ❌ Kullanıcı tıklayınca yeni mesaj `meta_query`'e düşüp "konuşmamızda bilgi yok" saçma cevabı. Akış bozuk |
| #816 (2D) | **Insufficiency banner** — hybrid path UI teklifi | ❌ Aynı CTA problemi, karmaşık UX |
| #818 | confidence gate'inden query_class kaldır (ara fix) | ⚠️ Hâlâ confidence skoru güvenilmez |
| #819 | **Post-gen refusal pattern matching** — LLM "kaynakta yok" cevabını regex'le yakala | ❌ Kullanıcı reddetti: *"LLM'den gelecek yanıta güvenerek işlem yapamazsın, her zaman farklı cümleyle dönebilir"* — anti-pattern, ROLLBACK (#820) |
| #820 | **Stream chunk bug** keşfi — `accumulated += stream_chunk` (StreamChunk objesi, str değil) | 🐛 Faz 1'den beri broken; fallback path her zaman tetikleniyordu. Tüm Faz 2 mimarisi gerçekte hiç test edilmemişti |
| #823 | **LLM tool-use** — `search_wikipedia` function calling, confidence routing/CTA/banner KALDIRILDI | ✅ Doğru mimari (kullanıcı: "bu aslında çok basit, sen kompleks bir noktaya getirdin") |
| #824 | tool-use prompt çelişkisi fix — `TOOL_USE_INSTRUCTION` | ✅ Sistem prompt "Wikipedia KULLANMA" diyordu, tool'la çelişiyordu; LLM tool'u çağırmıyordu |
| #825 | stream tool serialize + Wikipedia `opensearch`→`list=search` | ✅ generate_text_stream tool_call_id düşürüyordu (400→fallback); opensearch yanlış sayfa ("Donald Trump" → "Trump karşıtı protestolar") |
| #826 | **general_knowledge fast-path** — retrieval+tool-turn skip | ❌ Planner topic_query'sini Wikipedia'ya gönderiyordu; "stargate atlantis kaç sezondu" → "kaç sezondu" relevance'ı kirletti → "Ronon Dex" sayfası. REVERT (#828) |
| #827/#828 | #826 REVERT + **Wikidata fact kombine** | ✅ Doğruluk > latency; REST extract infobox içermez → Wikidata P-property (P569 doğum vb.) |

### Faz 2.1 — conversational retrieval + streaming (#829→#836)

Tool-use mimarisi oturduktan sonra **çok-turlu (follow-up) sohbet** kırıldı + streaming UX kaybı:

| PR | Yaklaşım | Sonuç |
|---|---|---|
| #829 | gen_user_msg'e sources_used context + content_top_k citation tutarlılık + markdown render + editoryal prompt | ⚠️ Cevap aşamasına context — retrieval hâlâ HAM mesaj (kısmi) |
| #831 | meta-query handler'a tool (dead-end fix) | ⚠️ Sadece meta_query path düzeldi |
| #832 | plan_query user_request'ine bağlam+talimat göm | ❌ Planner preserve-first kuralı ad-hoc talimatı EZDİ ("ilk bölüm adı" → Daha 17 dizisi) |
| #833 | **İzole condense step** — planner'dan önce ayrı LLM call → standalone query | ✅ [[conversational-query-rewriting]] (Perplexity/LangChain standardı) |
| #834 | TOOL_USE_INSTRUCTION entity-relevance kuralı | ✅ Çöp chunk "ilk bölüm" keyword'ü LLM'i yanıltmıyor → tool çağırıyor |
| #835 | gen_user_msg "Soru:" = effective_query | ✅ LLM tool'u bağlamlı çağırır (yoksa "Rolls-Royce Nene" çöpü) |
| #836 | **tool-aware streaming** — Aşama 1 generate_text_stream(tools=) | ✅ Gerçek token streaming geri (eski non-streaming → tek parça idi) |
| #838 | **bağlam kilidi + referans yakınlığı** — 3+ tur derinlikte patladı | ✅ Konuşma Wikipedia entity'ye kilitliyse follow-up news_query olsa bile tool ver (C2 ilk soruda korunur); condense en-yakın-antecedent + disambiguation |

## Çıkarılan dersler (anti-pattern listesi)

1. **Retrieval skoru ≠ "cevap var mı".** RRF/semantic skoru konunun *geçtiğini* ölçer, *cevaplandığını* değil. Confidence-based routing bu yüzden temelden kusurlu (#810).
2. **LLM çıktısını pattern-match etme.** "Kaynakta yok" cevabını regex'le yakalamak brittle — LLM her zaman farklı cümle kurabilir (#819, kullanıcı reddetti).
3. **Planner-generated query Wikipedia için kötü.** topic_query haber-retrieval'e optimize (genişletilmiş, soru kelimeli). Wikipedia entity araması ister; LLM'in ürettiği temiz entity ("Yıldız Geçidi Atlantis") doğru (#826 fast-path revert).
4. **Karar verici LLM olmalı, heuristik değil.** Kaynakları gören LLM "yeter mi" kararını verir — planner accuracy'sine veya skora bağımlı değil. Bu güvenlik ağı.
5. **Latency optimizasyonu doğruluğu bozmamalı.** fast-path ~3.7s kazandırıyordu ama yanlış sayfa getiriyordu. Doğruluk öncelikli.
6. **REST summary ≠ structured data.** Wikipedia extract prose'dur, infobox (doğum/nüfus) ayrı katman → Wikidata gerekli.
7. **Latent bug tüm mimariyi maskeler.** #820 stream bug Faz 1'den beri vardı; fallback path her zaman çalıştığı için Faz 2 mimarisi gerçekte hiç test edilmemişti. Yeni mimari eklerken alt-katman sağlığı doğrulanmalı.
8. **Conversational retrieval = ayrı condense adımı.** Follow-up bağlamını planner'ın sabit prompt'una gömmek çalışmaz (system prompt baskın, #832). Standalone query üretimi izole bir LLM call olmalı (#833 — sektör standardı).
9. **Bağlam tüm pipeline'a tutarlı akmalı.** effective_query sadece planner'a değil retrieval + tool query + gen_user_msg'e de gitmeli; bir yerde HAM mesaj kalırsa o noktada bağlam kopar (#829 retrieval, #835 tool query).
10. **Tool-use streaming UX'i bozmamalı.** Tool-decision için non-streaming gerekli sanılır ama `generate_text_stream(tools=)` + final-chunk tool_calls ile gerçek streaming korunur (#836). Mid-stream execution gerekmez.

## Sonuç mimari (güncel)

[[llm-tool-use-wikipedia]] — 2-aşamalı tool-use. LLM haber chunks + `search_wikipedia` görür; yetersizse tool çağırır; Wikipedia ([[wikipedia-wikidata-knowledge-source]]) + Wikidata kombine sonuçla `[W1]` citation cevap. news_query → tool yok (C2 STRICT tool gating). Tek akış, kullanıcı müdahalesi yok.

## İlişkiler

- Güncel mimari: [[llm-tool-use-wikipedia]]
- Conversational rewrite: [[conversational-query-rewriting]]
- Knowledge source: [[wikipedia-wikidata-knowledge-source]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Terk edilen routing: [[confidence-based-routing]] · [[wikipedia-fallback-controlled]]
- Benzer anti-pattern kataloğu: [[failed-experiments-rag-quality]]

## Kaynaklar

- GitHub PR #810 #814 #816 #818 #819 #820 #823 #824 #825 #826 #827/#828 #829 #831 #832 #833 #834 #835 #836
- `apps/api/app/api/app_chat_stream.py`, `apps/api/app/core/chat_tools.py`, `apps/api/app/prompts/query_rewrite.py`
