---
type: decision
title: "Conversational query rewriting — follow-up → standalone (condense step)"
slug: "conversational-query-rewriting"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-06-18 (#1614 — contextualized yalnız sorgu değişince; #1611 Gate-1 emekli)"
sources:
  - "apps/api/app/prompts/query_rewrite.py"
  - "apps/api/app/api/app_chat_stream.py (Step 1.5)"
  - "GitHub PR #833 #835 #838 #851 #855 (#854 carry-forward + timeout) #884 (açık özne istisnası) #931 (#929 itiraz≠parametre)"
tags: ["rag", "chat", "conversational", "query-rewrite", "follow-up", "mvp-1-8", "faz-2"]
aliases: ["condense-question", "standalone-query", "follow-up-rewrite"]
---

# Conversational query rewriting

> **TL;DR:** Multi-turn'de planner'dan ÖNCE izole bir hafif LLM call follow-up mesajı standalone arama sorgusuna çevirir ("ilk bölümün adı neydi" → "Stargate SG-1 ilk bölüm adı"). Bu standalone query planner + retrieval + tool query'ye tutarlı akar. Perplexity/LangChain ConversationalRetrievalChain "condense question" standardı.

## Bağlam — neden gerekli

Follow-up sorular ("ilk bölümün adı neydi", "daha detaylı açıkla", "kaç yıl önce") önceki konuşmaya atıf içerir. Bağlam retrieval'a yansımazsa felaket: production'da "stargate sg-1 ne zaman yayınlandı" → Wikipedia (doğru); follow-up "ilk bölümün adı neydi" → "ilk bölüm" Merdan Yanardağ casusluk davasında / "Daha 17" Türk dizisinde geçtiği için o haberler geldi. "daha detaylı açıkla" → CHP yolsuzluk haberi.

### Başarısız ara çözümler (anti-pattern kayıtları)

| PR | Yaklaşım | Neden yetmedi |
|---|---|---|
| #829 | Follow-up context'i gen_user_msg'e ekle | Cevap-üretim aşamasına context — retrieval hâlâ HAM mesajla |
| #831 | meta-query handler'a tool | Sadece meta_query path; news/general path ham |
| #832 | plan_query user_request'ine context+talimat göm | Planner SYSTEM_PROMPT preserve-first kuralı ad-hoc talimatı EZDİ — topic_query'yi son satırdan üretti, bağlamı ignore etti |

Kök içgörü: planner'ın sabit prompt'una ad-hoc talimat gömmek çalışmaz (system prompt baskın). Standalone query üretimi **ayrı, izole bir adım** olmalı.

## Karar

`apps/api/app/api/app_chat_stream.py` **Step 1.5** — planner'dan önce:

```
_recent_conversation_context VARSA (multi-turn):
  condense_followup_query(provider, history, payload.content)
    → effective_query (standalone)
plan_query(user_request=effective_query)
retrieval query_text = topic (planner'ın effective_query'den ürettiği)
gen_user_msg "Soru:" = effective_query   (#835 — tool query bağlamlı)
```

- `apps/api/app/prompts/query_rewrite.py` (YENİ): `REWRITE_SYSTEM_PROMPT` + `condense_followup_query` — chat-capable provider, `max_tokens=80`, `temp=0.3`, ~300-500ms.
- **is_related embedding'ine GÜVENİLMEZ.** Generic follow-up ("daha detaylı açıkla") önceki mesajla semantic similar değil → embedding kaçırır. Bunun yerine: conversation context VARSA (multi-turn) her zaman condense.
- **#835:** effective_query sadece planner+retrieval'a değil, `gen_user_msg`'deki "Soru:" satırına da gider. Yoksa LLM `search_wikipedia` tool'unu HAM mesajla çağırıp Wikipedia çöpü getiriyordu ("Rolls-Royce Nene", "Viyolonsel").

## Why — neden izole adım (planner'a gömmek değil)

- Planner SYSTEM_PROMPT generic (agenda generation dahil her yerde kullanılır); follow-up kuralı eklemek riskli + preserve-first ile çelişir.
- İzole condense step planner'a dokunmaz; standalone query'de planner'ın preserve-first kuralı zaten DOĞRU çalışır (çatışma yok).
- Evergreen: spesifik pattern yok, LLM standalone üretir. İlk mesajda context boş → ekstra call yok.

## Referans yakınlığı + bağlam kilidi (#838)

Multi-turn 3+ tur derinleşince iki ek kusur çıktı:

1. **Coreference recency:** condense atfı en geniş konuya çeviriyordu ("konusu neydi" → "Stargate SG-1 konusu") oysa en son spesifik özne ("Children of the Gods bölümü") izlenmeli. Prompt'a **en yakın antecedent ilkesi** + **disambiguation** (aynı-ad çakışmasında geçmiş anlamı koru) + multi-turn dayanıklılık eklendi.
2. **Bağlam kilidi (offer_tools gating):** Planner tek-mesaj kararı follow-up'ı eziyordu — "Stargate SG-1 konusu" → planner `news_query` ("Stargate" = güncel AI projesi haberde) → C2 STRICT tool'u kapatıyor → "Stargate AI 500 milyar dolar" çöpü. Kural: **konuşma bir kez Wikipedia/evergreen entity'ye kilitlendiyse** (önceki cevap `prev_sources.source_type=wikipedia`) ve follow-up ise, `news_query` olsa bile tool VER (`app_chat_stream.py` offer_tools). C2 STRICT ilk soru / gerçek haber bağlamında korunur.

## Scope: asistan/kimlik/meta ≠ topic follow-up (#851)

Prod conv 2955ab58: konuşma Kurt Russell hakkındayken "**senin yeteneklerin neler**" → condense "**Kurt Russell yetenekleri**" üretti. Kök: condense her atfı körlemesine konu öznesine çözüyordu; "sen/senin" asistana (Nodrat) yönelikti, konu entity'sine değil. Sonuç: kimlik sorusu Kurt Russell follow-up'ına dönüştü → agentic LLM yanlış özneye editoryal cevap verdi.

**Kural (REWRITE_SYSTEM_PROMPT, evergreen ilke — pattern değil):** ÖNCE ayır — soru KONUYA mı, ASİSTANA/SİSTEME mi? Asistanın kendisine yönelik ("sen kimsin", "senin yeteneklerin/amacın", "ne yapabilirsin") veya konuşmanın kendisi hakkında ("az önce ne dedin", "özetle") sorular **topic follow-up DEĞİLDİR** → "sen/senin"i konuşma öznesine ASLA çözme, mesajı OLDUĞU GİBİ bırak. Downstream agentic Nodrat prompt'u bunu kimlik/meta olarak ele alır (tool yok, kaynaksız konuşma cevabı). Sadece konunun KENDİSİ (kişi/olay/şey) hakkındaki atıflar çözülür.

## Talimat-odaklı follow-up: önceki soruyu taşı (#854)

Prod conv 304bed5b: "...21. Olağanüstü Kurultayda var mıydı" → sonra "**wikipediada araştır**" / "**bu sorumu wikipedia'da bul**". condense bunları jenerik entity araması ("Burhanettin Bulut kimdir") yapıyordu → kullanıcının ASIL sorusu (Kurultay'daki rol) kayboldu (bağlam kopması).

**Kural (REWRITE_SYSTEM_PROMPT, evergreen):** Son mesaj kendi başına yeni bilgi sorusu DEĞİL, önceki SORUYU yeniden yönlendiren/daraltan/biçim veren bir talimatsa ("wikipedia'da ara", "kaynak göster", "daha detay", "özetle", "bu soruyu ... ile araştır") → standalone sorgu = **önceki cevaplanan substantive sorunun** standalone hali; o soruyu TAŞI, jenerik entity araması üretme. Talimatın kısıtı (kaynak tercihi vb.) kısaca eklenir. Genel coreference ilkesi (antecedent = önceki kullanıcı sorusu), pattern değil. #851 scope ile birlikte: asistan/kimlik → değiştirme; talimat-odaklı → önceki soruyu taşı; konu-atfı → özneyi çöz.

## Açık özne istisnası: adlandırılan özne self-anchor (#884)

Prod conv dea54892: konuşma "bu üniversite ne zaman kuruldu" → "Ahi Evran Üniversitesi … 5467 sayılı yasayla kuruldu" akışındayken kullanıcı **"5467 sayılı yasa nedir"** sordu. condense **"Ahi Evran Üniversitesi 5467 sayılı yasa"** üretti (referans-yakınlığı kuralı önceki spesifik özneyi=üniversiteyi öne ekledi) → search_wikipedia üniversite sayfasını getirdi, cevap yasayı DEĞİL üniversiteyi anlattı ("soruyu farklı yorumladı"). Kök: "5467 sayılı yasa" KENDİ açık öznesidir (zamir/elips yok) — önceki cevabın onu yalnızca ANMASI onu üniversitenin alt-konusu yapmaz; referans-yakınlığı yanlış yöne itti.

**Kural (REWRITE_SYSTEM_PROMPT, evergreen — pattern değil):** Son mesaj KENDİ açık öznesini içeriyorsa (özel ad, sayı/numara, kanun/kod no, "X nedir/kimdir") ve bu özne zamir/elips DEĞİLSE → o açık özne standalone sorgunun öznesidir; önceki turun FARKLI entity'sini ÖNE EKLEME. Referans-yakınlığı **yalnız zamir/elips varken** uygulanır — açıkça adlandırılan özne kendi kendine yeterlidir. #851/#854 ile birlikte **3. ayrım:** asistan/kimlik → değiştirme; talimat-odaklı → önceki soruyu taşı; **açık-özneli yeni soru → o özneyi koru (önceki entity'yi ekleme)**; yalnız zamir/elips → en yakın antecedent'i çöz. Prod mechanism smoke (gerçek LLM): Ahi Evran bağlamı + "5467 sayılı yasa nedir" → `'5467 sayılı yasa nedir'` (üniversite EKLENMEDİ) ✓.

> İlgili agent-prompt eşi (#884): cevap üretiminde **"anma ≠ tanım"** (X'i yalnız anan, asıl konusu Z olan kaynak X'i tanımlamaz) + **proaktif tutarlılık** (aynı konuşmada kurulmuş olguyla çelişen yeni iddiayı sessizce kesinmiş sunma). conv dea54892 A12: 5467 (omnibus 15-üniversite kanunu) Burdur MAKÜ/Balıkesir Tıp sayfalarında anılıyordu → LLM "5467 = Burdur MAKÜ kanunu" iddia + A10 (Ahi Evran) ile sessiz çelişti. Bkz [[chat-knowledge-evolution]] ders.

## Öznesi-düşük / kıyaslı takip: dangling cue (#1608)

#884'ün simetriği. Açık özne self-anchor'dır (standalone); ama Türkçe **özne-düşürme (pro-drop)** + kıyas-devam başlatıcıları (`başka/peki/ayrıca/hani`) takibi açık özne taşımadan önceki araştırmaya bağlar. Gate-1 `is_standalone_query` bunları kaçırıyordu: "başka bir yere gitti mi bugün" 6 kelime > 3 → yanlışlıkla standalone → L1 windowed context atlanıyor, bağlam kayboluyordu.

**Prod kök case (2026-06-18):** "özgür özel bugün neredeydi" → takip "başka bir yere gitti mi bugün" yeni-konu sanıldı (condense çağrılmadı; `provider_call_logs`'ta `query_rewrite` izi YOK = kanıt — #1604 loglaması teşhisi mümkün kıldı). `research.l1_windowed_context_enabled` prod'da runtime AÇIK olmasına rağmen Gate-1 önce kesiyordu.

**Fix (#1608/PR#1609):** `_L1_FOLLOWUP_CUE={başka,peki,ayrıca,hani}` → `_has_dangling_referent` dangling sayar (antecedent aranır). `is_standalone_query=False`'un maliyeti DÜŞÜK: antecedent yoksa ham sorgu + yanlış bağlam Gate-4 drift guard'ında elenir → **yetersiz-bağlam < fazla-bağlam** tercihi. Prod container kanıtı (pure-call): "başka bir yere gitti mi bugün"→False, "enflasyon son durum ne oldu"/"Özgür Özel ne dedi"/"5651 sayılı kanun nedir"→True (regresyon korundu). Nazik iki-yönlü kalibrasyon — #1493 (Gate-4 strict drift, TERS yön: fazla bağlam) / #1494 / #1495 ailesi.

## Gate-1 EMEKLİ: dil-bağımsız LLM-judge (#1611)

#1608'in cue-listesi (`başka/peki/ayrıca/hani`) de band-aid'di: her dil/kalıbı kapsayamaz. Prod kanıtı — **"Annesi olay anında ne yapıyordu?"** (öznesi-düşük takip) cue-listesinde olmadığı için yine standalone sanıldı, bağlam kesildi. "annesi/olay/o sırada" gibi dangling kalıpları sonsuz; kelime listesiyle kovalamak kaybedilmiş savaş.

**Çözüm (#1611):** `is_standalone_query` Gate-1 GİRİŞ kapısı `select_windowed_context`'ten **emekliye ayrıldı**. "Yeni sorgu takip mi?" kararı artık dil-bağımsız **condense LLM'e** ait (zaten var olan adım; kelime-listesi gate onu atlıyordu). 3 değişiklik:
- **A** — `select_windowed_context`: Gate-1 erken-return kaldırıldı; çapa yine recency + içerikli-yeterlilik ile seçilir. `is_standalone_query` SİLİNMEZ → çapa-seçici + Gate-4 dangling-backstop rolünde kalır.
- **B** — Gate-4 strict drift (`l1_accept_rewrite`) call-site default `False→True`: Gate-1 gidince yeni-konuya bağlam sızmasını engelleyen tek koruma (admin `research.l1_strict_drift_gate=false` ile geri alabilir).
- **C** — condense prompt: "yeni/ilgisiz konu → AYNEN bırak, önceki bağlamı karıştırma" sözleşmesi güçlendi (artık her takip-olabilecek soruda çalışır).

**Neden embedding/cosine değil:** [[l1-recency-anchored-context]] (#1049) prod-kanıtı — belirsiz takip, içerikli antecedent'e DÜŞÜK (0.60), başka belirsiz takiplere YÜKSEK (0.98) cosine → yapısal yanlış. Maliyet: condense ~$0.0001/sorgu ([[provider-call-logging-coverage]], ihmal edilebilir). Latency +~1s (6s timeout + zarif degrade). **L1 prod'da AÇIK** (`l1_windowed_context_enabled=true`) → davranış canlı; **canary** ile doğrulanır. Test 40/40 L1 suite; `is_standalone_query` unit testleri korundu (fonksiyon değişmedi, rolü değişti). Single-turn pivot mimarisi (kasıtlı) DOKUNULMADI.

**Yan etki düzeltmesi (#1614/PR#1615):** Gate-1 emekli olunca her soru condense'e girdiği için, condense yeni-konuda sorguyu AYNEN döndürse bile (`rewritten==ham`) `_contextualized=True` set ediliyordu → thinking yanlış "Bağlamlı takip sorusu" + gereksiz "kaynak araması zorunlu (bellekten yanıt engellendi)". **Fix:** `_contextualized` + `effective_query` swap SADECE `rewritten.strip() != payload.content.strip()` iken (sorgu gerçekten değişti). Prod canary kanıtı: "bugün dolar kaç TL" yeni konu (cevap doğru, "Özgür Özel" bağlamı karışmadı) ama "Bağlamlı takip" etiketleniyordu → düzeldi. **Karar doğruydu, etiket yalancıydı.** (#1494 thinking-label netliğini de adresler.)

## İtiraz/şikayet follow-up: itiraz ≠ arama parametresi (#929)

**Kural (REWRITE_SYSTEM_PROMPT, evergreen — pattern değil):** Son mesaj önceki cevaba bir İTİRAZ/ŞİKAYET/DÜZELTME ise ("bu son haber olamaz", "çok eski", "neden 14 gün öncesini verdin", "yanlış", "ben bunu istemedim") bir arama PARAMETRESİ DEĞİLDİR. İtiraz kelimeleri ("14 gün öncesi", "eski") sorguya FİLTRE olarak EKLENMEZ (kullanıcı onları İSTEMİYOR, şikayet ediyor); standalone sorgu = önceki SUBSTANTIVE sorunun standalone hali, itiraz yalnız özgün niyeti (güncellik/doğruluk) PEKİŞTİRİR. conv 74eecc15: "Özgür Özel son haberler" + 14g eski cevap + "neden 14 gün öncesini verdin bu son olamaz" → ÖNCE `'Özgür Özel son haberler 14 gün öncesi'` (itiraz filtreye gömüldü → tur 3 yine eski), SONRA `'Özgür Özel son haberler'` ✓. #851/#854/#884 ile birlikte **4. ayrım:** asistan/kimlik → değiştirme; talimat-odaklı → önceki soruyu taşı; açık-özneli yeni soru → o özneyi koru; **itiraz/şikayet → önceki soruyu taşı, itirazı filtreye çevirme**; yalnız zamir/elips → en yakın antecedent. #884 dersi (prompt ancak gerekli sinyal context'te varsa bağlayıcı) → [[agentic-generate-orchestration]] #928 Ç3 `recency_requested` kod-sinyaliyle desteklenir. Prod mechanism smoke (gerçek DeepSeek): 2 itiraz varyantı → `'Özgür Özel son haberler'` (14 gün sızmadı). Bkz [[chat-knowledge-evolution]] ders #27.

## Latency tavanı + zarif degrade (#854)

condense YARDIMCI bir adım (~1s tipik). Prod'da tek DeepSeek latency spike → `condense_followup_query` **42949ms** (43s) tüm stream'i "Bağlam kontrolü"nde bloke etti (provider default 60s timeout, condense'in kendi tavanı yoktu). **Fix:** `asyncio.wait_for(timeout=chat.condense_timeout_s)` (admin-tunable, default 6s) → aşılırsa None → caller `effective_query = ham mesaj` (sistem çalışmaya devam, follow-up doğruluğu o turda düşer ama hang yok). Perplexity/ChatGPT deseni: yardımcı rewrite call'ları aggressive timeout + graceful degrade. Agentic loop generate_text + tool dispatch da aynı şekilde tavanlı (`app_chat_stream.py` #854).

## Trade-off (bilinçli)

Multi-turn'de ~0.5s ek LLM call. Follow-up doğruluğu için kritik (yoksa tamamen alakasız cevap). Kullanıcı ilkesi: doğruluk > latency.

## İlişkiler

- Üst mimari: [[llm-tool-use-wikipedia]] (tool query effective_query ile)
- Tiered mimari: [[tiered-knowledge-architecture]]
- Knowledge source: [[wikipedia-wikidata-knowledge-source]]
- Evrim/anti-pattern: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/prompts/query_rewrite.py` (REWRITE_SYSTEM_PROMPT + condense_followup_query)
- `apps/api/app/api/app_chat_stream.py` (Step 1.5 + effective_query akışı)
- `apps/api/app/core/chat_tools.py` (tool query — entity-relevant)
- GitHub PR #833 (condense step) #835 (effective_query → gen_user_msg) #838 (referans yakınlığı + bağlam kilidi offer_tools)
- docs/engineering/prompt-contracts.md §4.y · api-contracts.md §17.5.6
