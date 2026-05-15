---
type: decision
title: "Agentic generate orkestrasyonu — RAG-as-tool (ön-retrieval kaldırıldı)"
slug: "agentic-generate-orchestration"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py"
  - "apps/api/app/core/chat_tools.py (SEARCH_NEWS_TOOL + execute_search_news)"
  - "apps/api/app/prompts/chat_answer.py (SYSTEM_PROMPT_NODRAT_AGENT)"
  - "GitHub PR #846 (#845)"
tags: ["rag", "chat", "tool-use", "agentic", "faz-2", "mvp-1-8"]
aliases: ["rag-as-tool", "search-news-tool", "nodrat-agent"]
---

# Agentic generate orkestrasyonu

> **TL;DR:** Chat artık **her sorguda ön-retrieval YAPMAZ**. LLM iki tool'u orkestre eder: `search_news` (Nodrat küratörlü haber arşivi — **BİRİNCİL**, mevcut retrieval pipeline sarmalandı) + `search_wikipedia` (haberde olmayan evergreen). Selamlama/kimlik/konuşma-meta → tool çağrılmaz, doğrudan güvenli yanıt. `SYSTEM_PROMPT_NODRAT_AGENT` Nodrat kimliğini (güncel olay araştırma motoru, sohbet botu DEĞİL) + **güncel tarih enjekte** eder. Kaynaklar **cited-only** (cevapta gerçekten geçen) + taranan tümü collapsed. Kullanıcı vizyonu: *"kendi RAG sistemimizden veri almayı da bir tool gibi konumlandırmalıyız"*.

## Bağlam — neden eski mimari (always pre-retrieve) terk edildi

[[llm-tool-use-wikipedia]] mimarisinde **her** kullanıcı mesajı pipeline'ı tetikliyordu: condense → planner → embed → hybrid_search → confidence → Aşama 1 (haber chunks + search_wikipedia tool). Kullanıcı testinde 4 kök sorun:

1. **Zaman bug:** answer LLM'e güncel tarih HİÇ verilmiyordu (`current_time` sadece planner'a gidiyordu). Model "bugünü" eğitim önbilgisinden uyduruyordu ("Nisan 2025" — gerçek: 15 Mayıs 2026) → yaş/zaman hesapları yanlış, "neden 78 dedin" follow-up'ında hatalı yorum.
2. **Greeting'de retrieval:** "merhaba sen kimsin" bile tam haber retrieval tetikliyordu — yanlış davranış + israf. Nodrat sohbet botu değil ama bu sorular retrieval gerektirmez; model güvenli sınırlarda doğrudan cevaplamalı.
3. **Kaynak gösterimi:** cevapta kullanılan kaynak (örn. Wikipedia [W1]) UI listesinde görünmüyordu, sadece haber chunks; tüm taranan kaynaklar açıkça gösteriliyordu.
4. **Öz-düzeltme / kimlik:** model hatasını fark edip kabul etmiyor; kimliğini sorunca Wikipedia'yı amacı gibi sunabiliyordu (oysa amaç güncel olay araştırması).

Kök içgörü (kullanıcı): *"gerçekten kullanıcının isteği haberlerde olabilecek bir konuysa kendi bilgi sistemine bakmalı... 'merhaba sen kimsin' diye başlayabilir, burada hemen kaynaklara bakması doğru olmaz. mimari iyileştirme gerek, evergreen."*

## Karar

**Haber arşivi (RAG) bir tool'dur.** Pre-retrieval/planner/confidence/meta-handler kaldırıldı; LLM karar verir.

```
Step 1.5 (multi-turn): condense_followup_query → effective_query   (#833 KORUNDU)
Aşama 1 (NON-streaming, #840): generate_text(
   system = SYSTEM_PROMPT_NODRAT_AGENT (Nodrat kimlik + GÜNCEL TARİH enjekte),
   user   = Soru: effective_query (+ayar/stil/follow-up bağlamı),
   tools  = [search_news (BİRİNCİL), search_wikipedia], tool_choice="auto")
   ├─ tool YOK → selamlama/kimlik/meta: decision_text doğrudan
   │             (_simulate_stream, retrieval YOK, ekstra LLM call YOK)
   └─ tool_calls → execute (search_news: planner→embed→hybrid_search→RRF
        SARMALANDI; search_wikipedia: #842 entity+grounding)
        → convo += [assistant(tool_calls), tool(result)]
        → Aşama 2 (STREAMING, TOOLSUZ): final cevap [n]/[Wn] citation
cited-only: sources_used = accumulated'da cite token'ı geçenler;
            sources_considered = taranan tümü (UI collapsed)
```

- **search_news** mevcut retrieval kalite makinesini **sarmalar, değiştirmez** — `plan_query` + topic embed + `hybrid_search_chunks` ([[chunks-first-retrieval]]: top_k=10, candidate_pool=60, since_hours=90g, [[critical-entity-must-match|critical_entities]], rerank=False) production parite. recall@10 0.818 korunur.
- **SYSTEM_PROMPT_NODRAT_AGENT:** kimlik (güncel olay araştırma motoru, sohbet botu/genel asistan DEĞİL), `{current_date}` runtime enjekte (sistem now, TR UTC+3 — zaman bug fix), tool politikası (substantive → search_news birincil; evergreen → search_wikipedia; selamlama/kimlik/meta → doğrudan & güvenli, Wikipedia'yı amaç gibi pazarlama), C1 (substantive → tool zorunlu, LLM belleği YOK), öz-düzeltme (savunmacı değil, mekanik özür yok), grounding (#842 — olgu tool metninde literal yoksa scope-aware), iç-süreç anlatma yasağı (#842).
- **condense (#833) korundu** — multi-turn follow-up bağlamlı standalone query; LLM tool query'sini bağlamlı kurar.

## Why — neden tool, neden ön-retrieval değil

- **Doğru davranış:** araştırma sorusu → kaynak; selamlama → cevap. Karar veri görmeden değil, LLM'in elinde. Greeting'de retrieval israfı + yanlış UX biter.
- **C1 korunur:** substantive sorularda tool zorunlu (prompt), LLM kendi belleğinden cevaplamaz. Selamlama/meta C1 kapsamı dışı (zaten kaynak gerektirmez).
- **Kalite korunur:** retrieval pipeline sarmalandı, yeniden yazılmadı — RagFlow/multi-query/RRF/critical_entities/chunks-first hepsi search_news içinde.
- **Latency:** greeting/meta artık retrieval+planner atlar (hızlı). Substantive: planner+retrieval tool içinde (net nötr).

## cited-only kaynaklar (display, #819 DEĞİL)

`sources_used` = `accumulated` (final cevap) içinde citation token'ı (`[3]`/`[W1]`) geçen kaynaklar. `sources_considered` = taranan tümü → frontend `<details>` collapsed ("Taranan diğer kaynaklar (N)"). Bu **display filtresi** — LLM çıktısından *akış kararı* çıkarma (#819 anti-pattern) DEĞİL; deterministik token eşleştirme.

## Trade-off (bilinçli)

- LLM tool çağırmazsa (yanlış "selamlama" kararı) substantive soru kaynaksız kalabilir → mitigasyon: prompt "emin değilsen haber lehine karar ver, Nodrat'ın işi güncel araştırma".
- Prompt-bağımlı davranış (greeting tespiti, kimlik, öz-düzeltme) unit-test edilemez → production UI smoke gerekir (mechanism: tarih injection + search_news prod DB doğrulandı).

## İlişkiler

- Evrildiği mimari: [[llm-tool-use-wikipedia]] (search_wikipedia tool + #840 non-streaming + #842 grounding — geçerli; "ön-retrieval sonra tool" kısmı SUPERSEDED)
- Follow-up: [[conversational-query-rewriting]] (#833 condense korundu)
- Wikipedia kaynak: [[wikipedia-wikidata-knowledge-source]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]
- C1 (kaynaklı cevap zorunlu): [[tiered-knowledge-architecture]] · [[critical-entity-must-match]]

## Kaynaklar

- `apps/api/app/api/app_chat_stream.py` (agentic akış — ön-retrieval kaldırıldı, dual-tool dispatch closure, cited-only)
- `apps/api/app/core/chat_tools.py` (`SEARCH_NEWS_TOOL` + `execute_search_news` retrieval sarmalı; `SEARCH_WIKIPEDIA_TOOL`)
- `apps/api/app/prompts/chat_answer.py` (`SYSTEM_PROMPT_NODRAT_AGENT` + `render_nodrat_agent_prompt` tarih injection)
- GitHub PR #846 (#845). docs/engineering/prompt-contracts.md §4.x · api-contracts.md §17.5.6
