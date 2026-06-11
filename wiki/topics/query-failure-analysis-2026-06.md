---
type: topic
title: "Query Failure Analysis — gerçek sorgu dağılımı + retrieval failure tipolojisi (2026-06)"
slug: query-failure-analysis-2026-06
status: live
created: 2026-06-11
updated: 2026-06-11
github_issue: 619
github_issue_url: https://github.com/selmanays/nodrat/issues/619
sources:
  - wiki/plans/query-decomposition-postmortem.md§7
  - apps/api/app/modules/conversations/models.py§Message
  - apps/api/app/api/app_research_stream.py§461
  - apps/api/app/prompts/query_decomposition.py§156
tags:
  - analysis
  - rag
  - retrieval
  - citation
  - failure-analysis
  - read-only
aliases:
  - "query failure analysis"
  - "2026-06 sorgu dagilimi analizi"
---

# Query Failure Analysis — gerçek sorgu dağılımı + retrieval failure tipolojisi (2026-06)

## TL;DR

#619 post-mortem'in "only-do-if" sorularını veriye bağlayan **read-only** analiz (2026-06-11). İki ana sonuç: (1) **multi-intent oranı ≤%4.8** (admin yarı-gerçek kohort N=63; production `decompose_heuristic` ile ölçüldü) → %10-15 eşiğinin altında, **#619 decomposition rafta kalır**; (2) en büyük gözlenen failure yüzeyi retrieval-zero değil **citation-loss**: kaynak bulunup hiç cite edilmeyen mesaj oranı **%19** (found_not_cited 12/63) + faithfulness_reframed %12.7 — **⚠️ Düzeltme (§8 follow-up):** bu %19'un **8/12'si tarihsel RC3-B v1 reframe kümesi** (2026-05-19; #1076 v2 fix 2026-05-20 ile kök neden kapatıldı) → **aktif/organik silent-uncited ≈%6.3 (4/63)**; aktif iki problem retrieval gündem-dump + citation enforcement asimetrisi. Admin-dışı tek zero-source vaka probe'unda içerik **corpus'ta vardı, kelimeler eşleşiyordu, yine de retrieve edilmedi** (sınıf-3) — mekanizma belirsiz çünkü tool-call arama argümanı persist edilmiyor (observability boşluğu). Sonraki en yüksek kaldıraç: **citation-loss teşhisi**, ikinci: **search-arg observability**. Her ikisi ayrı onay bekler.

## 1. Bağlam + metod

[[query-decomposition-postmortem]] (#619) kapanırken iki açık soru bıraktı: gerçek sorgularda multi-intent oranı kaç, ve radyasyon/F-16 tipi miss'lerin asıl failure tipi ne (decomposition / expansion / coverage / agent-davranışı)? Bu analiz o soruları **prod DB read-only agregat** ölçümüyle yanıtladı.

**Metod (2 oturum, 2026-06-11):**
- Tüm DB erişimi `SET default_transaction_read_only = on` oturumunda salt-SELECT; `--persist`/INSERT/UPDATE/flag/allowlist/prod-config **sıfır**.
- **PII sınırı:** dışarıya yalnız agregat sayılar + maskeli sorgu terimleri + (public) haber başlıkları çıktı; raw query / user_id / email hiçbir rapora girmedi. `messages.content`/`effective_query` DB'de redaksiyonsuz olduğundan ham metin yalnız container-içinde işlendi.
- Veri kaynakları: `messages` (content, effective_query, sources_used, sources_considered, thinking_steps JSONB) + `conversations`/`users` (rol filtresi) + `articles`/`article_chunks` (corpus probe). Arama sayısı = thinking_steps `phase='tool_use'` adımı; failure sinyalleri = `cited_only_refused` / `grounding_retry` / `faithfulness_reframed` adımları + sources_used/considered boyutları.
- Multi-intent sınıflandırma iki katman: SQL regex (strong/weak marker) + **production `decompose_heuristic`** (apps/api/app/prompts/query_decomposition.py, PR-B/D2 guard'lı) container-içi koşum — yalnız agregat çıktı.

## 2. Admin-dışı gerçek kullanıcı kohortu — N=4, istatistiksel karar İÇİN YETERSİZ

| | Değer |
|---|---|
| user / assistant mesaj | 4 / 4 |
| distinct user | 1 |
| tarih aralığı | 2026-05-31 → 2026-06-07 |
| multi-intent | 0/4 |
| no_search | 0 (agent her mesajda aradı) |
| zero-source vaka | 1 (3 arama yaptı, 0 kaynak buldu, cited-only refuse) |

Üretim mesajlarının ~%96'sı super_admin trafiği. Admin-dışı örneklem hiçbir oran iddiası taşıyamaz; tek değeri §5'teki mini-probe vakasını sağlaması.

## 3. Admin yarı-gerçek kohortu — N=63

**Filtreleme:** `users.role='super_admin'` trafiğinden #619 kirliliği ayıklandı: 2026-06-09 canary günü dışlandı (48 mesaj; micro-canary v1+v2 + baseline spot-check'lerin tamamı) + `query_decomposition` thinking_step'li mesajlar dışlandı (15; **hepsi canary günü içinde** → gün-dışlaması test-pack'i tamamen kapsıyor). Kalan: **63 user + 63 assistant**, 63 konuşma (hepsi tek-mesajlık, follow-up yok), 2026-05-18 → 2026-06-08. **Sınır: tek kullanıcı** (admin'in doğal kullanımı) → genelleme sınırlı.

### 3.1 Multi-intent sonucu

| Sinyal | Sayı | Oran |
|---|---|---|
| strong marker (ayrıca / bir de / hem…hem) | 0 | %0 |
| weak ` ve ` (regex) | 3 | %4.8 |
| virgül / çoklu `?` | 0 | %0 |
| **production `decompose_heuristic` bölerdi** | **3** (hepsi 2 alt-sorgu) | **%4.8** |

Regex ve production heuristic birebir aynı 3 sorguyu işaretliyor. Bu 3'ün bir kısmı kurum-adı yanlış-pozitifi olabilir (bilinen `heuristic_out_of_scope` kör-noktası; ham metin okunmadığı için ayrıştırılmadı) → **gerçek multi-intent oranı ≤%4.8**. #619 only-do-if eşiği (≥%10-15) **karşılanmıyor** → decomposition rafta kalır.

### 3.2 Search behavior

| Metrik | Değer |
|---|---|
| dağılım | 0 arama: 3 · **1 arama: 54** · 2 arama: 5 · 3 arama: 1 |
| avg / p50 / p90 | 1.06 / 1 / 1 |
| no_search | 3 (%4.8) |

Agent geniş kohortta **baskın şekilde tek arama** yapıyor (canary günü gözlenen doğal çoklu-arama davranışının aksine). Ancak multi-intent oranı düşük olduğu için bu, decomposition lehine kanıt üretmiyor — "multi-intent + tek arama + düşük kaynak" paterni anlamlı hacimde gözlenmedi.

### 3.3 Failure tipolojisi

| Tip | Sayı | Oran |
|---|---|---|
| zero_cited (sources_used=0) | 15 | %23.8 |
| **found_not_cited (kaynak bulundu, cite edilmedi)** | **12** | **%19.0** |
| nothing_found — gerçek aramalı vaka | **0** | %0 |
| low_source (1-2 kaynak) | 23 | %36.5 |
| refused | 0 | — |
| grounding_retry | 2 | %3.2 |
| faithfulness_reframed | 8 | %12.7 |
| no_search | 3 | %4.8 |

**En kritik bulgu:** admin kohortunda gerçek arama yapan hiçbir mesaj 0 sonuçla dönmedi (nothing_found'un tamamı no-search mesajları). Buna karşılık **kaynak bulunup cevabın hiç cite etmediği 12 mesaj (%19)** + reframed 8 (%12.7) → failure yüzeyi retrieval'dan çok **citation/grounding/cevap-üretim** tarafında.

> ⚠️ **Düzeltme (2026-06-11 follow-up, §8):** Bu %19, vaka-düzeyi incelemede **aktif bug yüzeyi olarak okunMAMALI** — 12 vakanın 8'i tarihsel RC3-B v1 reframe kümesi (#1076 ile kapatılmış). Aktif organik oran ≈%6.3. Detay §8.

## 4. Zero-source mini-probe (admin-dışı tek vaka, sınıf-3)

Vaka: 2026-06-07 19:17 UTC, gerçek kullanıcı; **3 arama → sources_considered=0 → cited-only refuse**. Sorgu terimleri maskeli işlendi; corpus tarafı public haber başlığı.

- En nadir iki terimin AND-eşleşmesi: corpus'ta **4 cleaned makale, hepsi sorgu günü yayımlı**, hepsi chunk'lı + embedded.
- **Zamanlama:** 4 makalenin **3'ü sorgudan ÖNCE** pipeline'dan geçmişti (cleaned+chunk 07:15 / 09:33 / 18:30 — sorgu 19:17); 1'i sonra (21:30; ~6 saat ingestion-lag örneği). *(Caveat: chunk'ta embedding-timestamp yok; "sorgudan önce embed edilmişti" çıkarımı chunk-oluşturma zamanı + dakika-ölçekli backfill kadansına dayanır.)*
- Sorgunun kendi kelimeleri corpus'la ILIKE düzeyinde bol eşleşiyor (recent-7d 12-93 makale/terim) → **kelime-uyumsuzluğu (expansion sınıfı) DEĞİL**.
- Corpus sağlığı: 13,924 cleaned / 88 discarded / **0 quarantine**; 23,545 chunk'ın yalnız 9'u embedding'siz → **coverage/quarantine backlog'u yok**.

**Sınıf: 3 — corpus'ta var, kelimeler eşleşiyor, ama retrieve edilmedi** (yüksek güven). Mekanizma belirlenemedi çünkü **agent'ın tool-call'da kullandığı arama metni persist edilmiyor** — aday şüpheliler: planner `topic_query` dönüşümü, `critical_entities` MUST_MATCH filtresi, `since_hours`/skor eşiği. Bu bir **observability boşluğu**: arama argümanı kaydedilmeden bu sınıf vakalar retrospektif teşhis edilemez.

## 5. Karar

| Soru | Karar |
|---|---|
| #619 decomposition yeniden açılmalı mı? | **Hayır** — multi-intent ≤%4.8 < eşik %10-15; post-mortem kararı veriyle teyit edildi. |
| Query expansion/paraphrase investigation? | **Şimdi değil** — eldeki tek zero-source vaka kelime-uyumsuzluğu çıkmadı; radyasyon/F-16 anekdotları doğrulanmadı. Aday listede, önceliği düştü. |
| Corpus coverage / quarantine recovery? | **Öncelik değil** — quarantine 0, embedding %99.96 tam; tek zaaf ~6 saatlik ingestion-lag (1 örnek). |
| Agent search prompt/tool-use tuning? | **Henüz değil** — önce teşhis: citation-loss (%19) ve sınıf-3 retrieval miss mekanizması anlaşılmadan tuning kör olur. |

## 6. Recommended next work (her biri AYRI açık onay)

> Güncellendi (2026-06-11 follow-up): Öncelik-1 olan "citation-loss analysis" **yapıldı** (§8) — öncelikler sonucuna göre revize edildi.

1. **Öncelik 1 — simetrik citation-enforcement guard için reality-analysis:** `all_sources > 0 + substantive + cite-token-yok` durumuna C1'in aynası tek-düzeltici-tur guard'ı (§8 sınıf-D kanıtı). Organik veri küçük (N=4) → **direkt fix değil, önce reality-analysis** (nudge tasarımı: alakasız kaynakta körlemesine "cite et" zorlaması yanlış atıfa itebilir).
2. **Öncelik 2 — search-arg observability micro-PR için reality-analysis:** tool-call arama metninin `thinking_steps` metadata'sına PII-bilinçli persist'i (PR-F deseninin devamı). Hem sınıf-3 retrieval-miss (§4) hem sınıf-A gündem-dump (§8) teşhisinin ortak ön-koşulu.
3. **Ayrı konu/issue disiplini:** 1 ve 2 farklı dosya/risk profili → ayrı issue olmalı; birlikte paketlenmez.
4. **Bu veriyle öncelik OLMAYANLAR:** PR-G / decomposition aktivasyonu / query expansion — multi-intent ≤%4.8 + §8 bulgularıyla desteklenmiyor.
5. **Daha fazla gerçek kullanıcı verisi / eval altyapısı:** gerçek-kullanıcı trafiği N=4; alpha kullanıcıları gelene kadar kohort analizi tek-kullanıcı sınırında kalır.

## 7. Sınırlar / dürüstlük notları

- Admin yarı-gerçek kohort **tek kullanıcı** — davranış dağılımı tek kişinin kullanım stiline kalibre; oranlar yön gösterir, genellemez.
- `coverage_gap` telemetrisi log-only (DB'de yok); log penceresi container-restart'a bağlı (~2 gün) ve **0 satır** döndü — vaka tarihleri pencere dışında olabilir.
- Stream-exception'da mesaj persist edilmediği için hata vakaları DB-görünmez; `messages` tablosu 2026-05-14'te yaratıldı (öncesi veri yok).
- 3 multi-intent adayının arama-sayısı cross-tab'ı koşulmadı (küçük açık detay).
- found_not_cited mesajlarının niteliği (selamlama/meta vs gerçek research) bu turda ayrıştırılmadı — citation-loss analizinin ilk adımı bu ayrım olmalı.

## 8. Citation-loss follow-up / DÜZELTME (2026-06-11, read-only reality-analysis)

12 found_not_cited vakasının tamamı vaka-düzeyinde incelendi (read-only, PII-safe: faz dizileri + sabit-metin eşleşmesi + public başlıklar + redacted query etiketleri; raw query/user_id dışarı çıkmadı).

### 8.1 Merkezi düzeltme — %19 tarihsel artefakt içeriyor

- **12 vakanın 8'i 2026-05-19 tarihli ve hepsinde `faithfulness_reframed` adımı var** — cevap sabit citation'sız reframe metniyle değiştirildiği için sources_used=0 tanım gereği oluşur (reframe `all_sources>0` koşuluyla tetiklenir → her reframe = found_not_cited).
- Bu küme **RC3-B v1 LLM-verifier dönemine** ait (o dönem prod-denetiminde 4/8 yanlış-pozitif tespit edilmişti — kod yorumlarındaki denetim verisinin ta kendisi). **#1076 v2 fix (2026-05-20, d2cd222: LLM-verifier → deterministik marker-detect) ile kök neden kapatıldı**; v2 sonrası kohortta tek reframe vakası yok.
- **Sonuç: önceki %19 found_not_cited metriği aktif bug yüzeyi olarak okunmamalı.** Düzeltilmiş **aktif/organik silent-uncited oranı ≈ 4/63 ≈ %6.3**.

### 8.2 12 vaka sınıflandırma özeti

| Sınıf | Adet | Not |
|---|---|---|
| **C** — historical faithfulness guard/reframe | **8** | Tamamı 2026-05-19 (v1 dönemi); #1076 ile kapatıldı |
| **A** — retrieval false-positive / gündem-dump | 2 primer + 3 katkı | Alakasız sorguya 5-10 karışık güncel haber dönüyor (başlık-örtüşme 0.0); model dürüstçe cite etmiyor |
| **D** — generator kaynak varken citation üretmedi (enforcement asimetrisi) | 2 primer + 1 katkı | Kanıt vakası: retrieval_forced + 4 kaynak + substantive cevap, refuse-wording bile yokken citation'sız servis |
| **B** — citation filter threshold | **0** | Tüm vakalarda cite_tokens zaten boştu — filter hiç yanlış elemedi |
| **E** — cited-only refuse | **0** | Yapısal olarak imkânsız (yalnız all_sources boşken tetiklenir; karşılıklı dışlayan) |
| **G** — parser/mapping | **0** | [n]↔cite eşleşme testi boş küme |
| **F** — freshness | katkı (3 vaka) | 13-32 günlük kaynaklar; primer değil |
| **H** — belirsiz | 1 kısmi | Alakalı görünen kaynak + kısa "bulunamadı"-tarzı cevap; kaynak-içeriği karşılaştırması yapılmadan kapanmaz |

### 8.3 Aktif problem (düzeltilmiş sonuç)

Problem artık "found_not_cited %19" değil. **Aktif iki problem:**

1. **Retrieval false-positive / gündem-dump** — zayıf-alakalı sorgularda search_news yine de karışık güncel haber listesi döndürüyor; sorun citation'da değil retrieval alaka eşiğinde veya arama-metni üretiminde.
2. **Citation enforcement asimetrisi** — 0-kaynak + sahte-citation için iki guard var (C1 grounding_retry + #1058 cited-only); **kaynak VARKEN citation'sız substantive cevap için hiçbir guard yok** (`app_research_stream.py` C1 gate'i yalnız `not all_sources`'ta çalışır) → cevap sessizce kaynaksız servis ediliyor.

`citation_filter` bu veride suçlu değil (cite_tokens hep boştu); `cited_only_refused` da suçlu değil (hiç tetiklenmedi; yapısal olarak bu kümede tetiklenemez).

### 8.4 Observability boşlukları (bu analizde görünenler)

- Search-arg persist edilmiyor → sınıf-A'da "alakasız sonuçları hangi arama metni getirdi" teşhis edilemiyor (sınıf-3 retrieval-miss ile ortak kör nokta).
- found_not_cited metriği kasıtlı guard-refusal ile sessiz citation'sızlığı ayırmıyor → metrik tanımına faz-ayrımı girmeli.
- sources_considered'da retrieval skoru persist edilmiyor → alakasızlık derecesi ölçülemiyor.

## İlişkiler

- [[query-decomposition-postmortem]] — bu analizin tetikleyicisi; §7 "Only do if" tablosunun ilk satırı (gerçek-log multi-intent oranı) burada ölçüldü ve eşik altında çıktı.

## Kaynaklar

- [query-decomposition-postmortem.md](../plans/query-decomposition-postmortem.md) §7-8 — only-do-if koşulları + sonraki değerli iş tanımı.
- [#619](https://github.com/selmanays/nodrat/issues/619) — issue arkı + PAUSED durumu.
- `apps/api/app/modules/conversations/models.py` — Message şeması (sources_used / sources_considered / thinking_steps / effective_query).
- `apps/api/app/api/app_research_stream.py` §461-471 — `_log_step` / thinking_steps taksonomisi; §1069-1107 — cited_only_refused + coverage_gap tetikleyicileri.
- `apps/api/app/prompts/query_decomposition.py` §156 — `decompose_heuristic` (Faz 1b sınıflandırıcı).
- `apps/api/app/modules/generations/citation.py` §96-131 — `_FAITHFULNESS_REFRAME_TEXT` + `_maybe_reframe_for_faithfulness` (§8 sınıf-C mekanizması); `apps/api/app/api/app_research_stream.py` §886-893 — C1 gate'inin `not all_sources` asimetrisi (§8.3 problem-2 kanıtı).
- [#1076](https://github.com/selmanays/nodrat/pull/1076) — RC3-B v2 fix (2026-05-20): v1 LLM-verifier → deterministik marker-detect; §8 tarihsel kümenin kapanış kanıtı.
- Ölçüm: prod DB read-only agregat SELECT'ler + container-içi heuristic koşumu + corpus text-probe + 12-vaka citation-loss incelemesi (2026-06-11; PII-suz agregat).
