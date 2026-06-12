---
type: topic
title: "L1 / New-Search Context Isolation — retrieval_forced sınıflandırma reality-analysis (2026-06)"
slug: l1-new-search-context-isolation-analysis-2026-06
status: live
created: 2026-06-13
updated: 2026-06-13
sources:
  - apps/api/app/modules/generations/services/conversation_context.py§336-453
  - apps/api/app/api/_research_stream_context.py§123-233
  - apps/api/app/api/app_research_stream.py§514-899
  - apps/web/src/app/app/research/[id]/page.tsx§172-275
  - wiki/decisions/l1-recency-anchored-context.md
tags:
  - analysis
  - rag
  - l1
  - context-isolation
  - retrieval
  - read-only
aliases:
  - "l1 context isolation"
  - "new search context isolation"
---

# L1 / New-Search Context Isolation — retrieval_forced sınıflandırma reality-analysis (2026-06)

## TL;DR / Executive summary

S-2 micro-canary'deki Q5/Q7 anomalileri **tek bir bug değil, üç katmanın üst üste binmesi**: **(i)** L1 user-scope enrichment **tasarım gereği cross-conversation** çalışıyor (pivot kararının bilinçli eşlikçisi — [[l1-recency-anchored-context]] locked); **(ii)** Gate-1 + Gate-4 zinciri **muğlak-yeni-konu ile muğlak-takip'i ayırt edemiyor** ("borsa ne olur" 3-token → standalone değil → önceki konuşmanın konusu çapalanıp taşındı); **(iii)** UI etiketleri farklı scope'lardan beslendiği için **çelişkili** ("Yeni konu" conversation-scope, "Bağlamlı takip sorusu" user-scope `_contextualized`). **Q6→Q7'nin ayrı conversation'a düşmesi bug değil, single-turn pivot tasarımı** (frontend her submit'te yeni conversation; backend `single_turn_enforced` ikinci mesajı 409'la reddeder). **Minimum safe fix: Gate-4 drift sıkılaştırma (flag-gated) + etiket dürüstlüğü. L1'i kapatmak ÖNERİLMİYOR** (gerçek takip deneyimini kırar; kontaminasyon dilimi ~%9.5).

## 1. Root-cause verdict

| Katman | Verdict |
|---|---|
| **Backend L1** | Design boundary (bug değil) — user-scope bilinçli; AMA Gate-4 (`l1_accept_rewrite`, tek-token kesişimiyle kabul) muğlak-yeni-konu sınıfında **yanlış-pozitif enrichment** üretiyor |
| **Client routing** | Pivot tasarımı — same-conv follow-up yapısal olarak yok: thread input'u `startNewResearch`'e bağlı ([id]/page.tsx:273), followup-click de yeni conversation açar (:257); backend `single_turn_enforced` (registry, default true) ikinci mesajı **409** ile reddeder |
| **UI label** | Dürüstlük sorunu — "Bağlamlı takip sorusu" follow-up DOĞRULAMASI değil, yalnız `_contextualized` boolean'ının (condense rewrite oldu) sonucu; `is_related` (conversation-scope cosine) bundan **ortogonal** |

## 2. Q5 kanıt zinciri

"borsa ne olur" → Gate-1 `is_standalone_query` (conversation_context.py:336-357): dangling-referent yok ama **token>3 koşulu sağlanmadı** → standalone DEĞİL → `select_windowed_context` **user-scope**, en-dar-pencere-önce (6/24/72h), ilk standalone Q&A'yı çapalar → dakikalar önceki **Q4 "uzay madenciliği yasası"** → condense → effective_query **"Türkiye 2026 uzay madenciliği yasası borsa etkisi"** → Gate-4 `l1_accept_rewrite` (:441-453) **tek ortak token "borsa" ile KABUL** → `_contextualized=True` → `retrieval_forced` → **3 tur mashup arama** → **23 considered / 0 used** → max_tool_rounds doldu → forced-final → citation'sız substantive cevap.

## 3. Q7 kanıt zinciri

Same-conversation follow-up **test edilemedi** — yapısal olarak mümkün değil: thread input ve followup-click **yeni conversation** açar; backend single-turn guard'ı aynı konuşmaya ikinci mesajı reddeder. Yeni conversation'da context_check "Yeni konu" dedi (conv-scope; önceki mesaj yok); **L1 cross-conv Q6'nın Q&A'sını çapaladı** → effective_query Q6 konularıyla zenginleşti → retrieval_forced → **follow-up GİBİ davrandı** — pivot tasarımının amaçladığı telafi tam olarak bu; sorun davranışta değil, etikette ve kullanıcı-algısında (input thread'in altında durduğu için kullanıcı aynı konuşmada sanıyor).

## 4. L1-ON historical shadow (ölçüldü, read-only)

- `research.l1_windowed_context_enabled` **2026-05-18 21:37 civarı ON** (admin-panel oturumu: 21:17-21:37 arası 12 `settings.update` audit kaydı; flag `updated_at` 21:37:11 ile birebir).
- **Admin yarı-gerçek kohortun tamamı L1-ON döneminde** (kohort 22:25'te başlıyor; öncesi organik admin verisi yok).
- `retrieval_forced` **6/63 (%9.5)** ve **6/6'sı ilk-mesaj conversation** → kohorttaki tüm "contextualized follow-up"lar cross-conv L1 ürünü ([[query-failure-analysis-2026-06]] vaka-11 dahil).
- `query_rewrite` 12/63 (%19); **effective_query ≠ ham sorgu: 11/63 (%17.5)**.
- **Failure-tipolojisi SAYILARI değişmez** (ölçümler davranışı olduğu gibi ölçtü); değişen **yorum katmanı** (örn. "vaka-11 = follow-up dersi" düşer; bazı gündem-dump vakalarının kökeninde L1-mashup sorgular olabilir).

## 5. Risk değerlendirmesi

Retrieval kalitesi **orta** (mashup-konu araması; dilim ≈ eq-diverged %17.5'in alt kümesi) · Source relevance **orta** · Citation davranışı **düşük-orta** (yanlış konu → cite edilemez) · **User trust orta-yüksek** (çelişen etiketler + "yeni aramamda eski konum geliyor" hissi + sessiz yeni-conversation) · Cost/latency **düşük** (gereksiz condense + forced çok-tur, ~%10 dilim).

## 6. Düzeltme seçenekleri karar matrisi

| Seç. | Özet | Karar |
|---|---|---|
| A — L1'i yeni-conv'da kapat | Pivot'ta her mesaj yeni conv → A ≡ L1'i tümden kapatmak → gerçek takipler kırılır | ❌ |
| B — yalnız explicit same-conv follow-up | Same-conv yapısal yok (409); sinyal icadı = pivot'u yeniden açmak | ⏳ ürün kararı |
| C — soft hint (rewrite'a katılmasın) | Ayrı mekanizma ister; etkisi belirsiz | ⚠️ zayıf |
| D — relatedness threshold yükselt | Cosine v1 kanıtla çıkarıldı (belirsiz-takip 0.985 > içerikli 0.605) — kanıtla çelişir | ❌ |
| E — muğlak sorguda netleştirme sor | Değerli ama büyük UX/ürün işi | ⏳ backlog |
| **F — UI label ayrımı** | Davranış-nötr string dürüstlüğü | ✅ kolay/kesin (Issue-2) |
| **G' — client transparency** | Thread-input/followup-click'in yeni araştırma başlattığını görünür kıl; tam G (same-conv garanti) pivot'a dokunur | ✅ hafif (Issue-3); tam hali ⏳ |
| H — L1 geçici OFF | Kontaminasyonu bitirir AMA tüm takip deneyimini kırar; ~%9.5 dilim için orantısız | ❌ önerilmez |

## 7. Önerilen minimum safe fix

**Flag-gated Gate-4 drift gate** — `research.l1_strict_drift_gate`, **default OFF**:
- Ham sorguda **dangling-referent VARSA** (gerçek takip sinyali: bu/şu/o/bahsettiğin…) → mevcut gevşek kabul aynen korunur.
- **YOKSA** (yalnız kısa/muğlak) → rewrite'ın **yeni içerik-token oranına üst sınır**: rewrite token'larının çoğunluğu ham sorgudan türemiyorsa RED → ham sorguyla devam.
- **Q5 golden testi:** "borsa ne olur" + önceki uzay-madenciliği context'i → rewrite'a TAŞINMAMALI ("…uzay madenciliği yasası borsa etkisi" 4/5 yeni-token ile reddedilir).
- **Genuine follow-up koruması:** "Ankara'da ne yapacakmış" → "Özgür Özel Ankara ziyareti" sınıfı dangling-referent kolundan geçer.
- Saf/deterministik/test-edilebilir; schema YOK. Yanına **F** (etiket dürüstlüğü).

## 8. Önerilen issue/PR ayrımı

1. **Issue-1 (backend):** L1 Gate-4 drift sıkılaştırma — bu sayfa reality-analysis'i; küçük flag-gated PR + golden testler.
2. **Issue-2 (label dürüstlüğü):** "Yeni konu" / "Bağlamlı takip sorusu" çelişkisinin giderilmesi (thinking_step detail string'leri backend'de).
3. **Issue-3 (ürün/client):** single-turn UX şeffaflığı — thread-input'un yeni araştırma başlattığının görünür kılınması; tam same-conv follow-up ayrı product decision.

## 9. Hard-stops / belirsizlikler

- Audit `metadata->>'key'` sorgusu boş döndü → "L1'i kim açtı" yalnız zaman-korelasyonuyla bağlı (metadata şekli farklı olabilir).
- Q7 tetikleyicisi (thread-input vs followup-click) DB'den ayırt edilemiyor — davranış kanıtlı, giriş yolu değil.
- `single_turn_enforced` prod override'ı kontrol edilmedi (registry default true).
- Gerçek-kullanıcı N≈4 — oranlar admin trafiği üzerinden; Gate-4 golden seti admin vakalarına kalibre olacak (bias riski not edildi).
- Implementation her adımda ayrı açık onay; kod/flag/canary bu analizde YOK.

## İlişkiler

- [[citation-gap-guard-analysis-2026-06]] — Q5 düzeltmesinin devamı; bu sayfa o düzeltmenin tam kök-neden analizi.
- [[query-failure-analysis-2026-06]] — §3 L1-ON gölgesi notunun nicelleştirilmesi (forced 6/63, eq-diverged 11/63).
- [[search-arg-observability-analysis-2026-06]] — S-1 telemetrisi Q5 kök-nedeninin görülmesini sağladı (searches[] + effective_query).
- [[l1-recency-anchored-context]] — L1 tasarım kararı (locked); bu analiz o kararın yeni-konu sınırını işaretler.

## Kaynaklar

- `apps/api/app/modules/generations/services/conversation_context.py` §336-357 (Gate-1 `is_standalone_query`) · §382-438 (`select_windowed_context` user-scope + pencere cascade) · §441-453 (Gate-4 `l1_accept_rewrite`).
- `apps/api/app/api/_research_stream_context.py` §123-233 (condense zinciri + `_contextualized`).
- `apps/api/app/api/app_research_stream.py` §514-521 ("Yeni konu" etiketi, conv-scope) · §889-899 (`retrieval_forced` tetiği + "Bağlamlı takip" etiketi).
- `apps/web/src/app/app/research/[id]/page.tsx` §172-275 (`startNewResearch` wiring; thread-input + followup-click) · `apps/api/app/api/app_research.py` §103-133 (conversation create).
- Ölçüm: prod DB read-only agregatlar (audit penceresi, forced/rewrite/eq-diverged oranları), 2026-06-12/13.
