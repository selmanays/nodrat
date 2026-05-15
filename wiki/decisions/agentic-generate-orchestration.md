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
  - "GitHub PR #846 (#845) #849 (#848) #852 (#851) #855 (#854 latency + admin sync)"
tags: ["rag", "chat", "tool-use", "agentic", "faz-2", "mvp-1-8"]
aliases: ["rag-as-tool", "search-news-tool", "nodrat-agent"]
---

# Agentic generate orkestrasyonu

> **TL;DR:** Chat artık **her sorguda ön-retrieval YAPMAZ**. LLM iki tool'u orkestre eder: `search_news` (Nodrat küratörlü haber arşivi — **BİRİNCİL**, mevcut retrieval pipeline sarmalandı) + `search_wikipedia` (haberde olmayan evergreen). Selamlama/kimlik/konuşma-meta → tool çağrılmaz, doğrudan güvenli yanıt. `SYSTEM_PROMPT_NODRAT_AGENT` Nodrat kimliğini (güncel olay araştırma motoru, sohbet botu DEĞİL) + **güncel tarih enjekte** eder. Kaynaklar **cited-only** (cevapta gerçekten geçen) + taranan tümü collapsed. Kullanıcı vizyonu: *"kendi RAG sistemimizden veri almayı da bir tool gibi konumlandırmalıyız"*.

> 🔧 **#879 — temporal grounding tamamlandı (denetim 2026-05-15):** #845
> answer LLM'e "bugünün tarihi"ni enjekte etti ("Nisan 2025" uydurması
> fix) AMA `execute_search_news` chunk serileştirmesi `retrieval.py`'nin
> ürettiği `published_at`'i DÜŞÜRÜYORDU → LLM tarihsiz haberi enjekte
> edilen "bugün"e sabitledi (prod conv 0a097738: 6 gün önceki Rize
> mitingi → "bugün", kullanıcı düzeltince ısrar). Evergreen fix: blok
> `(yayın tarihi: …)` + `sources[].published_at` + result_text yönergesi
> + `SYSTEM_PROMPT_NODRAT_AGENT` genel temporal kural (olay zamanı=yayın
> tarihi; yayın≠bugün→"bugün" deme; "en son"=en yeni tarih; çoklu→
> kronoloji). Retrieval ranking DEĞİŞMEDİ. Ders [[chat-knowledge-evolution]]
> #22: tool sarmalı, alt katmanın ürettiği karar-ilgili boyutları
> (özellikle ZAMAN) çıktıya taşımak ZORUNDA — yalnız "metin" yetmez.

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
system = SYSTEM_PROMPT_NODRAT_AGENT (Nodrat kimlik + GÜNCEL TARİH enjekte)
user   = Soru: effective_query (+ayar/stil/follow-up bağlamı)

#848 ÇOK-TURLU agentic döngü (MAX 3 tur):
  while tur < 3:
    decision = generate_text(convo, tools=[search_news, search_wikipedia],
                              tool_choice="auto")   # NON-streaming (#840 DSML-safe)
    tool YOK → final_text = decision.text ; BREAK
    tool_calls → convo += [assistant(tool_calls)]; her tc execute
        (search_news: planner→embed→hybrid_search→RRF SARMALANDI;
         search_wikipedia: #842 entity+grounding)
        convo += [tool(result)]
    → DÖNGÜ: LLM sonuçlarla TEKRAR karar verir (search_news yetersiz
      → search_wikipedia çağırabilir — #848 tek-tur tuzağı çözümü)
  MAX dolu + hâlâ tool → toolsuz generate_text (zorla cevap)
final_text → _simulate_stream (ekstra LLM call yok; tüm turlar
             non-streaming, generate_text_stream KALDIRILDI #848)
cited-only: sources_used = accumulated'da cite token'ı geçenler;
            sources_considered = taranan tümü (UI collapsed)
```

- **search_news** mevcut retrieval kalite makinesini **sarmalar, değiştirmez** — `plan_query` + topic embed + `hybrid_search_chunks` ([[chunks-first-retrieval]]: top_k=10, candidate_pool=60, since_hours=90g, [[critical-entity-must-match|critical_entities]], rerank=False) production parite. recall@10 0.818 korunur.
- **SYSTEM_PROMPT_NODRAT_AGENT:** kimlik (güncel olay araştırma motoru, sohbet botu/genel asistan DEĞİL), `{current_date}` runtime enjekte (sistem now, TR UTC+3 — zaman bug fix), tool politikası (substantive → search_news birincil; evergreen → search_wikipedia; selamlama/kimlik/meta → doğrudan & güvenli, Wikipedia'yı amaç gibi pazarlama), C1 (substantive → tool zorunlu, LLM belleği YOK), öz-düzeltme (savunmacı değil, mekanik özür yok), grounding (#842 — olgu tool metninde literal yoksa scope-aware), iç-süreç anlatma yasağı (#842).
- **condense (#833) korundu** — multi-turn follow-up bağlamlı standalone query; LLM tool query'sini bağlamlı kurar.

### #848 — tek-tur tuzağı → çok-turlu döngü (C1 + sahte citation fix)

İlk #845 tasarımı **tek-tur**du: Aşama 1 (tools) → execute → Aşama 2 **TOOLSUZ**. Production (conv 377ba71a): "Şi Cinping kaç yaşında" → LLM `search_news` çağırdı (biyografik için yanlış tool) → 10 alakasız Trump-Xi haberi → **search_wikipedia çağırma şansı yoktu** (Aşama 2 toolsuz) → LLM kendi belleğinden "15 Haziran 1953, 72 yaşında" + **sahte `[W1]`** (search_wikipedia hiç çağrılmadı). C1 ihlali + uydurma citation. Kök: tek-tur, kötü tool sonucundan kurtulma yok.

Düzeltme: **MAX 3 turlu agentic döngü.** Her tur `generate_text(tools=)` non-streaming (#840 DSML korunur); LLM tool sonuçlarıyla tekrar karar verir — search_news yetersizse search_wikipedia çağırabilir. Final = LLM'in tool çağırmadan döndüğü tur metni → `_simulate_stream` (`generate_text_stream` tamamen kaldırıldı). Prompt pekiştirmesi: evergreen sabit olgu (yaş/doğum/kuruluş/nüfus/tanım) → search_wikipedia; agentic recovery (tool cevaplamıyorsa diğerini çağır, tahmin etme); **tool çağrılmadan/sonuç gelmeden citation token YAZMA** (sahte kaynak = marka hasarı).

### #851 — global cite + C1 referans-bütünlüğü backstop + condense scope + yorum yasağı

Prod conv 2955ab58, 4 ek kusur:

1. **Cite token çakışması:** `execute_search_*` cite'ı PER-CALL `[1]`/`[W1]` üretiyordu → multi-round'da aynı tool 2 kez çağrılınca iki blok da `[W1]` → LLM karıştırdı, yanlış kaynak attı (tur 4 "başrolde kimler" → doğru bilgi [W2]'deyken [W1] cite). **Fix:** tek `[n]` namespace (W prefix kaldırıldı; `source_type` news/wiki ayrımını taşır → UI badge), döngü boyunca **global cite sayacı** (`cite_start`/`cite_n`); SourcePill gerçek `cite` token'ını gösterir (pozisyonel değil).
2. **C1 belleğe düşme:** "kurt russel hayatta mı" → LLM tool çağırmadan bellekten cevap + sahte `[W1]` + "— Nodrat" imzası (0 kaynak). **Fix (mimari, deterministik invariant):** final cevapta citation token VAR ama `all_sources` BOŞ → kanıtlı sahte → 1 kez `tool_choice="required"` düzeltici tur. Bu **yapısal referans-bütünlüğü** kontrolü (`_CITE_TOKEN_RE`) — #819'daki "serbest-metin ifade eşleştirme" anti-pattern'i DEĞİL (yapısal token ↔ gerçek kaynak kümesi). Selamlama/kimlik (citation yok) etkilenmez.
3. **Condense kimlik kontaminasyonu:** "senin yeteneklerin neler" → condense "Kurt Russell yetenekleri" (asistana yönelik soru konu-follow-up'a dönüştü). **Fix:** [[conversational-query-rewriting]] REWRITE_SYSTEM_PROMPT — asistan/kimlik/meta soruları topic follow-up DEĞİL; "sen/senin" konuşma öznesine çözülmez, mesaj olduğu gibi geçer (downstream kimlik olarak ele alır).
4. **Editoryalleşme/imza:** öznel çıkarım/niteleme ("herkesi ağlatan", "ikonlaştı"), kendi bilgisinden profil dökümü, "— Nodrat" imzası. **Fix:** SYSTEM_PROMPT_NODRAT_AGENT — kaynaktaki olguyu yalın aktar, öznel yargı/çıkarım YASAK, imza YASAK, inisiyatif/genişletme YASAK (haber motoru, asistan değil).

### #854 — latency tavanı (43s hang) + admin agentic uyum auditi

Prod conv 304bed5b "Burhanettin Bulut kimdir" → `query_rewrite:42949ms`: condense (yardımcı adım) timeout'suzdu; provider default 60s; tek DeepSeek latency spike tüm stream'i **43s "Bağlam kontrolü"nde** bloke etti (diğer turlar ~1s). Kök: yardımcı/orkestrasyon LLM/tool çağrıları latency-sınırsızdı.

**Fix (evergreen, Perplexity/ChatGPT deseni):** condense (`asyncio.wait_for`, timeout→ham mesajla devam), agentic loop `generate_text` (her tur timeout, kesilirse eldeki sonuçla cevap), tool dispatch (`asyncio.wait_for`, timeout→boş sonuç, LLM toparlar). Tüm tavanlar **admin-tunable** (`chat.condense_timeout_s`/`tool_round_timeout_s`/`tool_exec_timeout_s`/`max_tool_rounds` settings; kod-constant fallback). Yardımcı adım latency'si SIKI sınırlı + zarif degrade — hung upstream UI'ı asmaz.

**Admin paneli agentic uyum auditi (#854):** (a) Settings — #845'te terk edilen confidence-routing key'leri (`retrieval.confidence_weights/t_high/t_low`) Settings menüsünden KALDIRILDI; agentic tunable'lar eklendi. (b) Prompts — `chat_nodrat_agent` + `chat_query_rewrite` PROMPT_REGISTRY'ye eklendi ve `prompts_store` ile bağlandı (kod default fallback → davranış değişmez, admin görünür/tunable). (c) RAG İzlencesi — retrieval katmanını (planner→hybrid_search→RRF→rerank = `search_news` içi) DOĞRU inceler; agentic orkestrasyon üstte ve izlenceden görünmez (tasarım; kapsam notu eklendi). (d) SFT/DPO/halu — `messages`-based (#800 S1E), yeni agentic format'la **uyumlu** (kullanıcı-aksiyonu flag'leri pipeline-bağımsız; `sources_used` cited-only aynı şekil); değişiklik gerekmedi, `prompt_version` 2.0.0 (agentic provenance).

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
- GitHub PR #846 (#845) #849 (#848) #852 (#851) #855 (#854). docs/engineering/prompt-contracts.md §4.x · api-contracts.md §17.5.6
