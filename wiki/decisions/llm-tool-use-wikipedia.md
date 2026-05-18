---
type: decision
title: "LLM Tool-Use Wikipedia — confidence routing/CTA terk edildi"
slug: "llm-tool-use-wikipedia"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-18"
sources:
  - "apps/api/app/api/app_chat_stream.py"
  - "apps/api/app/core/chat_tools.py (#967 _prioritize_canonical + _wiki_norm_title)"
  - "apps/api/app/providers/deepseek.py§125-368 (function calling)"
  - "apps/api/app/prompts/chat_answer.py (TOOL_USE_INSTRUCTION)"
  - "GitHub PR #823→#842 #840 #857(#860 düzeltme) #860 (DSML bulletproof) #863 (Wikidata veri-yolu bulletproof) #968 (#967 exact-title kanonik seçim) #971 (#970 canonical-retry garantisi + msg6 C1 takip-sorusu backstop) #974 (#973 provider lead-only→tam makale extract; CACHE v2)"
tags: ["rag", "chat", "tool-use", "function-calling", "wikipedia", "mvp-1-8", "faz-2"]
aliases: ["tool-use-architecture", "search-wikipedia-tool"]
---

# LLM Tool-Use Wikipedia

> ⚠️ **Orkestrasyon SUPERSEDED (#845):** "Ön-retrieval (haber chunks) → Aşama 1'de search_wikipedia tool" kısmı [[agentic-generate-orchestration]] ile değişti — artık ön-retrieval YOK; haber arşivi de `search_news` tool'u, LLM ikisini orkestre eder. Bu sayfanın **`search_wikipedia` tool spec'i + #840 non-streaming Aşama 1 + #842 entity/grounding/C1 kuralları GEÇERLİ** (yeni mimaride de aynen kullanılıyor). Sadece "her sorguda haber chunks pre-load" framing'i geçersiz.
>
> 🟥 **Ek dead-token (denetim 2026-05-15):** Aşağıdaki akış diyagramındaki **"Aşama 2 STREAMING `generate_text_stream` + `[W1][W2]` citation"** SUPERSEDED. `generate_text_stream` chat akışında **tamamen kaldırıldı** (#848 — final `_simulate_stream`); citation **tek `[n]` namespace** (#851 — `[W]` prefix YOK). Çok-turlu agentic döngü güncel: [[agentic-generate-orchestration]]. (#857/#860 DSML + #863 Wikidata callout'ları aşağıda geçerli.)

> **TL;DR:** Chat'te kaynak yetersizse **LLM kendi kararıyla** `search_wikipedia` tool'unu çağırır (OpenAI-compatible function calling). Confidence-based routing + Wikipedia CTA banner + meta-query resubmit mimarisi (eski #810/#814/#816) **tamamen terk edildi**. #845 sonrası haber arşivi de tool (`search_news`); bkz [[agentic-generate-orchestration]].

## Bağlam — neden eski mimari terk edildi

Faz 2'nin ilk mimarisi (#810 confidence router + #814 Wikipedia CTA + #816 insufficiency banner) production'da defalarca kırıldı:

- "trump kaç yaşında" → bazı haber chunk'ları yüksek RRF skoru aldığı için confidence T_low üstünde kalıyor → Wikipedia CTA tetiklenmiyor → "kaynaklarda yok" cevabı
- CTA tetiklense bile kullanıcı tıklayınca yeni mesaj `meta_query`'e düşüyor → "konuşmamızda bilgi yok" saçma cevabı
- Pattern-matching ile LLM cevabını analiz etme denemesi (#819) anti-pattern — kullanıcı reddetti: "LLM'den gelecek yanıta güvenerek işlem yapamazsın, her zaman farklı cümleyle dönebilir"

Kök içgörü (kullanıcı): *"LLM eğer kullanıcı sorgusunu cevaplayacak bir kaynağa sahip değilse tool kullanma yeteneğiyle geri dönüp wikipedia sürecini tetiklemeli, akışı bozmadan. Bu mimari aslında çok basit."*

## Karar

LLM'e `search_wikipedia` tool'u verilir; **karar verici LLM, planner veya confidence skoru değil.**

### 2-aşamalı akış — non-streaming Aşama 1 (`app_chat_stream.py`, #840 güncel)

```
Step 1.5 (multi-turn): condense_followup_query → effective_query
                        ([[conversational-query-rewriting]])
Aşama 1 (NON-streaming): generate_text(messages=[sys+haber chunks],
                          tools=[search_wikipedia], tool_choice="auto")
   → yapısal decision.tool_calls + decision_text (content YIELD EDİLMEZ)
   ├─ tool YOK → decision_text, _simulate_stream ile yield
   │    (4-kelime grup + 18ms; EKSTRA LLM CALL YOK — text zaten üretildi)
   └─ tool_calls dolu → LLM Wikipedia istedi:
        ├─ execute_search_wikipedia(args) → Wikipedia+Wikidata sonucu
        ├─ messages += [assistant(tool_calls), tool(result)]
        └─ Aşama 2 (STREAMING, TOOLSUZ): generate_text_stream →
             gerçek token streaming + [W1][W2] citation
```

> **#840 — DeepSeek DSML token bug (kritik):** #836'nın "Aşama 1
> streaming" tasarımı production'da kırıldı. DeepSeek
> `generate_text_stream(tools=...)` tool çağıracağında yapısal
> `delta.tool_calls` DÖNMEZ — `<｜DSML｜tool_calls>` özel token'ını
> **content içinde ham XML** olarak yayınlar. Sonuç: kullanıcı ham DSML
> görüyor + "uzun uzun yazıp bir anda kısa yanıta dönme" (content stream
> sonra tool branch'ine atlıyor). Düzeltme: Aşama 1 tekrar **non-streaming
> `generate_text(tools=...)`** → yapısal `decision.tool_calls` doğru parse
> (DeepSeek non-streaming function calling ÇALIŞIR, #825'te doğrulandı).
> Aşama 1 content **yield edilmez** (ham DSML kullanıcıya gitmez). Tool
> varsa Aşama 2 = `generate_text_stream` **TOOLSUZ** (tool param yok → DSML
> token yok → gerçek token streaming sağlam). Tool yoksa `decision_text`
> `_simulate_stream` ile (4-kelime grup + 18ms, ekstra LLM call YOK).
> Ana flow + `_stream_meta_query_answer` ikisine de uygulandı. **Mid-stream
> tool execution DEĞİL** (kullanıcı #823'te reddetti). `generate_text_stream`
> tool param'ları (#836) API'de kalıyor (ileride OpenAI-uyumlu provider
> için; chat flow kullanmıyor).

> **#857 — #840 varsayımı EKSİKMİŞ (kritik düzeltme):** "non-streaming
> `generate_text` HER ZAMAN yapısal `message.tool_calls` döndürür (#825
> kanıt)" tam doğru değil. DeepSeek bazı durumlarda **non-streaming'de
> de** tool-call'u DSML özel-token dizisi olarak `message.content`'e
> basıyor (prod conv "Stargate sg1 yazarları" → ham XML cevaba sızdı,
> 0 kaynak). Doğru çözüm akış değil — **provider adapter** katmanı
> (`deepseek.py:_parse_dsml_tool_calls`): yapısal tool_calls boş +
> content DSML dizisi içeriyorsa parse → `ToolCall`, DSML metinden
> temizlenir (öncesi prose korunur). Agentic loop DEĞİŞMEDİ; adapter
> provider tutarsızlığını (yapısal | DSML-in-content | stream) tek
> standart `GenerationResult.tool_calls`'a normalize eder. Yapısal
> serileştirme parse'ı (JSON tool_calls gibi) — #819 reddine girmez.

> **#860 — #857 yarım kaldı (gerçek format ÇİFT `｜｜`):** #857 deploy'a
> rağmen prod (conv "Stargate Atlantis yönetmenleri") hâlâ ham DSML
> sızdırdı. DB ham byte: gerçek token `<｜｜DSML｜｜tool_calls>` (İKİ
> U+FF5C); #857 cleaner `_DSML_MARKER_RE=[｜|]?` (0/1) tek-`｜`
> varsaymıştı → invoke/param regex'leri toleranslı olduğu için tool
> PARSE oldu ama cleaner çift'i yakalamadı → text temizlenmedi →
> MAX-tur forced-final ham DSML'i cevap servis etti. Fix: MARKER_RE
> `[｜|]+` (1+ ayraç; ｜/｜｜/\|/truncate). **`strip_dsml_markup` SON
> GÜVENLİK AĞI** (`deepseek.py`): format ne olursa olsun ham markup'ı
> söker — parser kaçırsa BİLE kullanıcı ham DSML görmez. forced-final
> (`app_chat_stream.py`): "ARTIK TOOL ÇAĞIRMA, cevap yaz" explicit
> talimatı + `accumulated` sanitize + boşsa scope-aware fallback
> (asla boş ekran/ham XML). Ders: quirk normalize ederken EXACT
> format'ı da varsayma; toleranslı parser + format-agnostik güvenlik
> ağı + dürüst fallback üçlüsü şart.

> **#834 — entity-relevance:** TOOL_USE_INSTRUCTION'a net karar kuralı:
> "Kaynaklar sorudaki ENTITY hakkında değilse — aynı kelime ('ilk
> bölüm') başka bağlamda geçse bile — keyword match cevap sayılmaz,
> sentez yapma, search_wikipedia çağır." Çöp retrieval'ın LLM'i
> yanıltmasını engeller.

> **#835 — tool query bağlamı:** `gen_user_msg` "Soru:" =
> `effective_query` (condense çıktısı), HAM mesaj değil. Yoksa LLM
> tool'u bağlamsız çağırıp Wikipedia çöpü getiriyordu.

> **#842 — entity-only tool query + C1 grounding backstop + meta-leak:**
> Üç kusur (Stargate SG-1 kullanıcı testi). (1) **Yanlış sayfa:** LLM
> `search_wikipedia` query'sine "Stargate SG-1 4. sezon" (İngilizce ad +
> niteleyici) gönderiyordu → TR Wikipedia full-text "200 (Yıldız Geçidi
> SG-1)/Paul Mullie/Atlantis" döndürüyor; temiz Türkçe entity "Yıldız
> Geçidi SG-1" → #1 doğru ana sayfa (canlı API testi). Fix: tool `query`
> param + TOOL_USE_INSTRUCTION → SADECE kanonik Türkçe madde adı, soru/
> sezon/bölüm/niteleyici kelimeleri çıkar (anti-pattern #3 güçlendirme).
> (2) **C1 fabrication (kritik):** Sorulan spesifik detay ("S4E1 adı")
> dönen REST özetinde HİÇ yoktu (ana sayfa = sadece lead; Wikidata
> P-prop'larında da yok) → LLM cevabı kendi belleğinden üretip **sahte
> [W1]** ekledi. Fix: grounding kuralı — her olgu dönen araç metninde
> LİTERAL olmalı; yoksa scope-aware "özette yer almıyor" de, uydurma+
> sahte cite YOK. Output pattern-match DEĞİL (anti-pattern #2; #819
> reddi korunur) — sadece input-side prompt. (3) **Meta-leak:** Aşama 2
> "kaynaklarda yok, bu yüzden Wikipedia'ya başvurdum" iç sürecini
> yazıyordu → cevap biçimi kuralı: iç mekanizma anlatılmaz, sadece
> cevap + citation.

> **#863 — Wikidata veri-yolu bulletproof (knowledge-source delta):**
> #842 sonrası LLM doğru entity/sayfayı buluyordu ama biyografik
> factual sorular (`conv 2c9bb90a` "Robert C. Cooper doğum tarihi")
> hâlâ cevapsızdı. `wikidata_factual` ham sorguyu fuzzy
> `wbsearchentities`'e veriyordu (niteleyici "doğum tarihi" entity
> match'i kırar) + `query.wikidata.org/sparql` prod'da flaky (400/502).
> Fix: SIRALI bulletproof zincir — Wikipedia full-text (doğru SAYFA) →
> `pageprops.wikibase_item` (dil-bağımsız kesin QID) → `wbgetentities`
> Action API (SPARQL elendi). **Tool spec / TOOL_USE_INSTRUCTION
> DEĞİŞMEDİ** — saf veri-yolu onarımı; "doğru kaynağı buldu ama cevap
> veremedi" = veri-yolu kırığı sinyali (prompt değil). Tam mekanizma +
> alternatifler: [[wikipedia-wikidata-knowledge-source]].

> **#967 — exact-title kanonik sayfa önceliklendirme (#842 "(1)
> Yanlış sayfa"nın devamı):** #842 tool query'yi temizledi (kanonik
> Türkçe entity) ama yapısal kusur kaldı: Wikipedia full-text
> (`list=search`, #824) relevance-ranked döner, kanonik maddeyi HER
> ZAMAN #1 vermez. `execute_search_wikipedia` `articles[0]`'ı hem #863
> sitelink-QID hem ilk `[n]` bloğu temsilci alıyor → kanonik sayfa
> kümede 2./3. sıradaysa cevap yan sayfaya (karakter listesi / "200
> (Yıldız Geçidi SG-1)" / film) dayanıyordu (prod conv 3f1ca529:
> "stargate'in ilk dizisi" → cevap TR "Yıldız Geçidi SG-1" maddesinde
> MEVCUT ama bakılmadı). Fix: `_prioritize_canonical` — 3 katmanlı
> **stable** sıralama (0=norm-tam-başlık eşleşme kanonik, 1=normal,
> 2=alt-sayfa/liste/disambig/parantezli), `_qid` çağrısı ÖNCESİNDE
> (articles[0] kanonik → hem #863 QID hem [n] doğru sayfanın).
> **KOŞULLU:** tam-eşleşme yoksa liste DOKUNULMAZ (mevcut relevance
> davranışı; geri uyum, kullanıcı onayı 2026-05-18). `_wiki_norm_title`
> TR-duyarlı ([[turkish-collation-entity-match]] #939 dersi: 'İ'→'i',
> 'I'→'ı', U+0307 strip, tire/boşluk kanonik). **Retrieval-core değil
> tool-sarmalı politikası** (#906/#928/#879 ailesi) — `wikipedia.py`
> generic full-text motoru DEĞİŞMEZ; **LLM tool spec & query
> DEĞİŞMEZ** (#863 ile aynı karakter: saf seçim/veri-yolu onarımı,
> prompt değil — doğru sayfa zaten kümede). #1 entity-belirsizliği
> ("ilk dizisi" → film vs dizi niyet) KAPSAM DIŞI (ayrı/#842 cephesi).
> Prod mechanism smoke (canlı Wikipedia): "Yıldız Geçidi SG-1" →
> [1]=kanonik, yan sayfalar [2]/[3]; "Donald Trump"→[1] regresyon
> yok; no-exact→relevance korunur. PR #968.

> **#970 — canonical-page GARANTİSİ (kademeli trimmed retry) + msg6
> C1 takip-sorusu backstop (#967 yetmedi; conv 75711aa0, deploy'dan
> ~2 dk SONRA re-test):** #967 küme-İÇİ sıralamayı çözdü ama LLM
> follow-up'ta niteleyicili query üretince ("Yıldız Geçidi SG-1 ilk
> bölüm kanal") Wikipedia full-text canonical'ı top-3'e HİÇ koymadı
> (`canonical_in_set=False` kanıt) → `_prioritize_canonical` promote
> edecek aday bulamadı (yalnız DÖNEN kümede sıralar). **(1) Kod —
> `_resolve_canonical`:** tam-başlık eşleşmesi YOKSA query'yi SAĞDAN
> token-token kısalt (LLM entity'yi başa, niteleyiciyi sona koyar —
> tool spec #842) + her prefix'e hedefli arama; prefix başlığı
> norm-tam-eşleşirse canonical'ı kümenin BAŞINA kat, `eff_query=
> prefix` → `_prioritize_canonical(eff_q)` ile `[1]`. Bounded:
> tek-pass eşleşmede ekstra çağrı YOK; aksi `≤_CANON_MAX_RETRY=3`
> (Redis 24h cache → tekrar ~bedava); bulunamazsa mevcut davranış
> (geri uyum). `_qid` (#863) ÖNCESİ; **tool spec & query DEĞİŞMEZ**
> (#967/#863 ailesi deterministik). **(2) Prompt —
> `SYSTEM_PROMPT_NODRAT_AGENT` rule 4 "Takip sorusu tuzağı (C1)":**
> konuşma context'inde varlık net OLSA bile o varlık hakkında YENİ
> olgusal boyut (yıl/sezon/kanal-geçişi/sayı) = YENİ olgu → tool
> zorunlu; "meşhur konu / akıcı sohbet / biliyorum" bellekten kesin
> değer için gerekçe DEĞİL; tool boş/yetersiz → scope-aware,
> uydurma+citation'sız olgu YASAK (msg6: `sources_used=[]` + kesin
> "6.sezon/2002"). Saf reasoning → prompt (#931/#955/#964 deseni;
> veri düşmüyor #906≠). Sorun-1 fix'i canonical'ı getirince LLM
> gerçek kaynağa dayanır (msg6 BİRİNCİL azaltıcı); prompt = artık-
> sızıntı güvenlik ağı (#819 reddi korunur: post-gen pattern-match
> YOK). chat_answer cache'siz → PROMPT_VERSION bump yok
> (SYSTEM_PROMPT_NODRAT_AGENT 9969→10673). Kapsam dışı: İngilizce-ad
> → TR-madde normalize (norm mismatch) — daha derin #842, ayrı.
> Prod mechanism smoke (canlı Wikipedia, deployed): "Yıldız Geçidi
> SG-1 ilk bölüm kanal" → [1]=kanonik (önceden yalnız yan sayfa);
> geri-uyum + "Donald Trump"→[1] regresyon yok; prompt resolved==
> kod default (10673; #854/#270 DB-override YOK). PR #971.

> **#973 — provider lead-only summary → TAM makale extract (içerik
> derinliği; #967 SEÇİM / #970 RETRİEVAL-garantisi'nden FARKLI 3.
> kök; conv b66bf1c2, deploy'dan ~21 dk SONRA, kullanıcı "emin misin"
> + ekran görüntüsü):** #967/#970 doğru kanonik sayfayı SEÇİYOR
> (ekran görüntüsü: [1]=Wikipedia TR "Yıldız Geçidi SG-1") ama cevap
> "kanal bilgisi içermiyor". Kök (canlı kanıt): `_fetch_summary` REST
> `/api/rest_v1/page/summary` = yalnız lead (**333 char**, kanal/
> Türkiye YOK); tam makale `prop=extracts` (**4283 char**) "Türkiye'de
> ilk bölümü TRT 1 / 14 Nisan 2007" içeriyor → cevap doğru kanonik
> sayfanın GÖVDESİNDE'ydi, provider girişi çekiyordu (C1 dürüstçe
> "kaynakta yok"). **Fix:** `_fetch_summary` → `action=query&prop=
> extracts&explaintext=1&exsectionformat=plain&redirects=1` (tam
> makale düz-metin), `_WIKI_EXTRACT_CAP=8000` (dev makale context/
> maliyet; paragraf sınırında kes + "[…]"). URL `{base}/wiki/{title}`
> (`_search_lang` fallback'i zaten aynısı). `CACHE_KEY_VERSION` v1→v2
> (eski lead-only Redis 24h stale kalmasın; #947 PROMPT_VERSION-in-key
> dersi). Lead→full **süperset** (bilgi kaybı yok). Lisans CC BY-SA +
> "25 kelimeden uzun alıntı yapma" C1 kuralı gövdeye de geçerli.
> **LLM tool spec & query DEĞİŞMEZ.** Mekanizma+entity: [[wikipedia-
> provider]] (#973). İtiraf: #970 mechanism smoke yalnız "kanonik
> [1] mı?" (seçim) doğrulamıştı; #973 smoke İÇERİK-doğrulamalı (prod,
> canlı Wikipedia: result_text'te literal "TRT 1"+"14 Nisan 2007"+
> "Türkiye" VAR, sources[0]=kanonik regresyon temiz, cache `wiki:v2:`).
> PR #974.

### News-first STRICT (C2) — tool-level gating

`query_class == 'news_query'` ise tool LLM'e **hiç verilmez** (`offer_tools = wikipedia_enabled and query_class != "news_query"`). "Trump bugün ne dedi?" haber kaynaklarından cevaplanır, Wikipedia'ya düşmez. Brand contamination koruması artık query_class hard-gate routing'i değil, **tool sunum kontrolü**.

### Prompt çelişkisi fix (#824 — kritik)

`SYSTEM_PROMPT_CHAT_ANSWER` "Wikipedia KULLANMA, kaynakta yoksa 'yok' de" diyor — bu tool ile çelişiyordu (LLM tool'u çağırmıyordu). `offer_tools=True` iken sistem prompt'a `TOOL_USE_INSTRUCTION` eklenir: "kaynakta yoksa 'yok' DEME, search_wikipedia çağır". Halüsinasyon koruması korunur (LLM sadece kaynak/tool sonucu kullanır, kendi belleğinden değil — C1).

## Routing tablosu (güncel)

| query_class | Akış | LLM call | Retrieval | Tool |
|---|---|---|---|---|
| `meta_query` | Conversation context (Step 2.5) | 1 | yok | yok |
| `news_query` | Haber retrieval, tool YOK (C2 STRICT) | 1-2 | var | yok |
| `general_knowledge` / `mixed` | Haber retrieval + tool-use | 1-2 | var | search_wikipedia |

> Haber retrieval `general_knowledge`'ta da yapılır — LLM'in "haberde mi Wikipedia'da mı?" kararını **kaynakları görerek** vermesi için (güvenlik ağı, planner accuracy'sine bağımlı değil). Bkz "Vazgeçilen: fast-path".

## Provider değişiklikleri

`base.py`: `ToolCall` dataclass + `Message.tool_calls/tool_call_id` + `GenerationResult.tool_calls` + `generate_text(tools, tool_choice)`.
`deepseek.py`: OpenAI-compatible function calling — tool serialize (hem `generate_text` hem `generate_text_stream`, #825) + `tool_calls` response parse + multi-turn tool message.

## Vazgeçilen yaklaşımlar (anti-pattern kayıtları)

| Yaklaşım | PR | Neden reddedildi |
|---|---|---|
| Confidence-based routing (T_high/T_low → STRICT/hybrid/CTA) | #810 | Planner+RRF skoru "konu geçiyor mu" der, "cevap var mı" demez — yanlış routing |
| Wikipedia CTA + consent card | #814 | Kullanıcı müdahalesi akışı bozuyor; meta_query resubmit saçmalığı |
| Insufficiency banner (hybrid path) | #816 | Aynı CTA problemi; karmaşık UX |
| Post-gen refusal pattern matching | #819 | LLM çıktısı pattern'a güvenmek brittle — kullanıcı reddetti |
| general_knowledge fast-path (retrieval skip) | #826 | Planner topic_query'sini Wikipedia'ya gönderiyordu → soru kelimeleri relevance'ı kirletti ("stargate atlantis kaç sezondu" → "Ronon Dex" sayfası). #828 ile REVERT. Tool-use path'te LLM temiz entity query üretir. **Doğruluk > latency** |

## Trade-off (bilinçli)

`general_knowledge` sorgularında ~2.2s planner + ~7.4s retrieval + 2 LLM call ≈ 10-12s. Latency yüksek ama doğru + planner-bağımsız. Fast-path bunu kesecekti ama Wikipedia query kalitesini bozdu. Latency optimizasyonu gelecekte fast-path hatası tekrarlanmadan ele alınmalı (Aşama 1'in ürettiği temiz entity query'yi kullanarak).

## İlişkiler

- Follow-up bağlam: [[conversational-query-rewriting]] (Step 1.5 condense)
- Wikipedia + Wikidata kaynak: [[wikipedia-wikidata-knowledge-source]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Terk edilen routing: [[confidence-based-routing]] (artık telemetri-only)
- Terk edilen CTA: [[wikipedia-fallback-controlled]] (superseded)
- News leak gating: [[news-first-strict-contamination-guard]]
- Sorgu sınıflandırma: [[query-class-classification]] (routing değil, tool gating + telemetri)
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]] (#967 ders #35: kanonik temsilci seçimi)
- Provider: [[wikipedia-provider]]
- TR normalize/collation dersi (#967 `_wiki_norm_title` yeniden kullanır): [[turkish-collation-entity-match]]

## Kaynaklar

- `apps/api/app/api/app_chat_stream.py` (Step 1.5 condense + 2-aşama: non-streaming Aşama 1 + toolsuz Aşama 2 stream + `_simulate_stream` + meta-query handler)
- `apps/api/app/core/chat_tools.py` (SEARCH_WIKIPEDIA_TOOL + executor)
- `apps/api/app/providers/deepseek.py` (function calling — `generate_text(tools=)` yapısal tool_calls; `generate_text_stream` tool param #836 API'de kalır ama chat flow toolsuz çağırır)
- `apps/api/app/prompts/chat_answer.py` (TOOL_USE_INSTRUCTION — entity-relevance #834)
- `apps/api/app/prompts/query_rewrite.py` (#833 condense)
- GitHub PR #823 (tool-use) #824 (prompt fix) #825 (stream serialize + wiki relevance) #827/#828 (fast-path revert + Wikidata) #831 (meta-query tool) #833 (condense) #834 (entity-relevance) #835 (effective_query) #836 (tool-aware streaming — #840 ile revize) #840 (DeepSeek DSML token bug → non-streaming Aşama 1) #842 (entity-only tool query + C1 grounding backstop + meta-leak fix) #863 (Wikidata veri-yolu bulletproof) #968 (#967 exact-title kanonik sayfa önceliklendirme — `_prioritize_canonical`) #971 (#970 canonical-page garantisi `_resolve_canonical` kademeli trimmed retry + msg6 C1 "Takip sorusu tuzağı" prompt backstop) #974 (#973 provider lead-only summary → `prop=extracts` TAM makale + `_WIKI_EXTRACT_CAP` + CACHE_KEY_VERSION v2)
