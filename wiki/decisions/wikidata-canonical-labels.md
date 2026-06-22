---
type: decision
title: "Wikidata/Wikipedia canonical-etiket ankrajı (küme+trend SENKRON)"
slug: "wikidata-canonical-labels"
status: live
created: 2026-06-22
updated: 2026-06-22
sources:
  - "GitHub #1710 (Faz 1 motor), PR #1711"
  - "GitHub #1712 (Faz 2 sync), PR #1712"
  - "GitHub #1720/#1721/#1722 (Faz 4 canonical-katman + LLM precision gate)"
  - "GitHub #1725/#1726 (Faz 4b builder↔wikidata salınım fix — defer + self-heal)"
tags: [entities, trends, clusters, canonicalization, wikidata]
aliases: ["wikidata canonical", "küme trend senkron"]
---

## TL;DR
Küme + trend etiketleri **her zaman Wikipedia başlığı karşılığı** olur; korpus yüzey formları + Wikidata alias'ları `entity_aliases` olarak yakalanır. Founder isteği (2026-06-21): "Filenin Sultanları" → canonical **"Türkiye kadın millî voleybol takımı"** (alias); "ABD" → **"Amerika Birleşik Devletleri"**. Otorite sırası: **admin > wikidata > seed > token_subset > ham**. [[entity-canonicalization-faz1]]'i harici-otorite ile genişletir.

## Bağlam / neden
Trend ve küme etiketleri **senkron değildi** (founder şikayeti): küme etiketi her zaman canonical'a düşer ([[global-research-cluster-model]] ENTITY_DF_SQL) ama trend `trends.canonical_entities.enabled` flag'ine bağlıydı (default OFF → ham yüzey) + `cluster_link.py` (gaps/radar) canonical'ı hiç kullanmıyordu → aynı varlık kümede "Cumhuriyet Halk Partisi", trendde "CHP". Ayrıca canonical adlar seed-küratör / NER-mode-yüzey'den geliyordu (Wikipedia-otoriter değil).

## Mekanizma (4 faz)

**Faz 1 — zenginleştirme motoru (#1710/PR#1711, CANLI):**
- Offline Celery beat (`tasks.entities.enrich_wikidata`, 6h, ner_queue): `entities`'ten df≥min_freq + çözülmemiş yüzey → mevcut [[wikipedia-provider|WikipediaProvider]] zinciri (full-text → DOĞRU sayfa → `wikidata_qid_for_title` sitelink-deterministik QID → yeni `wikidata_entity_meta` wbgetentities labels|aliases|sitelinks|claims) → **tip-gate** (`wikidata_match.type_matches`: person Q5 ŞART; place/org/event insan/tarih=RED) → `canonical_entities` (canonical_name = Wikipedia TR başlık, source='wikidata') + `entity_aliases` (korpus yüzey + Wikidata TR alias'ları).
- **#997 dersi:** çıplak-keyword `wbsearchentities` QID disambiguation güvenilmez ("15 temmuz"→takvim) → MUTLAKA önce Wikipedia full-text → sayfa → wikibase_item.
- `wikidata_entity_resolutions` tablosu (raw-SQL-only, additive): **'denendi' guard** ([[ner-backfill-cost-loop|#1602 dersi]]) + cache. Flag `entities.wikidata_enrich.enabled` (prod AÇIK).
- Authority guard: alias ON CONFLICT admin+wikidata korur; `build_canonical` WHERE `NOT IN ('admin','wikidata')`.
- **Evergreen iyileştirmeler (#1714/PR#1715, CANLI):** olay **yıl/sıra-öneki sıyrılır** (`strip_event_edition`: "49. G7 zirvesi"→"G7 zirvesi", "2026 Avrupa Tekvando Şampiyonası"→"Avrupa Tekvando Şampiyonası"; spesifik form alias → tüm edisyonlar tek kümede, evergreen) + **EN-fallback** (search tr→en düşerse `articles[0].lang` ile QID + `labels.tr` = TR karşılığı, LLM'siz).
- **⚠️ Jenerik-kavram guard'ı YOK (#1716→#1717 — ÇÖZÜLEMEDİ):** "Merkez Bankası"→jenerik "merkez bankası" tipi yanlış-eşlemeyi otomatik ayırmak için **3 sinyal de BAŞARISIZ**: kapitalizasyon (MediaWiki başlık ilk-harfini DAİMA büyütür + TR cümle-düzeni), Wikidata P279 (spesifik takım da subclass), corpus-N (prominent ÖZEL-ADLAR Türkiye=783/İstanbul=923/NATO=116 yüksek-N → #1716 guard'ı **232 meşru canonical'ı yanlış sildi**, resolution-row'lardan + re-resolve ile geri yüklendi). Guard #1717 ile KALDIRILDI. Jenerik kavram canonical katmanında **zararsız** — küme çapası olması zaten [[global-research-cluster-model|#1705 genericlik-reddiyle]] engelli; nadir görünür yanlış-eşleme → admin Varlık Birleştirme. **Ders: özel-ad↔jenerik-kavram ayrımı bu sinyallerle otomatik çözülemez.**

**Faz 2 — sync (#1712/PR#1712, CANLI):**
- `trends.canonical_entities.enabled` default OFF→**ON** (kill-switch korunur).
- `cluster_link.py` 8 sorgu canonical-aware (`_CANON_JOIN` + `_NORM_EXPR` COALESCE): cluster_key artık `kebab(COALESCE(canonical_normalized, entity_normalized))` → küme resolver ile **BİREBİR** (Wikidata-canonical kümeler trend rozetini kaybetmez).
- Sonuç: küme + trend + radar **tek Wikipedia-temelli canonical**'dan okur.

**Faz 3 — retro-fit (✅ UYGULANDI, manuel script, founder onaylı):** mevcut kümeler Wikipedia başlığına relabel — ABD→Amerika Birleşik Devletleri · Filenin Sultanları→Türkiye kadın millî voleybol takımı · Türk Milli Takımı→Türkiye millî futbol takımı · G7 Zirvesi→G7 zirvesi (event-strip). `cluster_key` UPDATE (küme id SABİT → artefakt/abonelik/üyelik korundu); 0 merge (çakışma yok). Eski hatalı/jenerik kümeler **hard-delete** edildi (Belediye Meclisi+1 test-artefaktı/Borsa/Hüseyin/MVP/belediye — bağımlılıklar bağımlılık-sırasıyla; FK: message_clusters/subscriptions/artifacts RESTRICT → önce sil, parent_cluster_id SET NULL). **NOT:** `ResearchCluster.canonical_name` yazma-anında sabit (yeni kümeler canonical DOĞAR; ongoing oto-retro-fit task'ı YAPILMADI — yeni kümeler zaten canonical olduğundan gerek görülmedi).

**Faz 4 — canonical-katman merge + LLM precision gate (#1720/#1721/#1722, ✅ CANLI, flag AÇIK 2026-06-22):**
- **Sorun:** Faz 1 entity-df taraması düşük-df varyantları AGGREGATE eden **token_subset/seed canonical'larını** kaçırıyor — "15-16 Haziran Direnişi" + "15-16 Haziran Büyük İşçi Direnişi" tek tek df<min_freq, ama agregat Wikipedia'da var ("15-16 Haziran olayları"). Founder: "wikipedide bulunabilecek bazı isimler doğrulanmamış görünüyor … evergreen çöz."
- **#1720 — Pass 2 `_enrich_canonical_layer`:** token_subset/seed + active canonical'ları `canonical_name`'den Wikipedia'ya doğrular (aynı `_resolve_one` zinciri) → wikidata canonical (W) upsert. Aynı normalized → **yerinde-yükseltme** (token_subset/seed satırı source='wikidata' olur, ad Wikipedia başlığı); farklı → **merge** (C'nin alias'ları W'ye re-point [admin korunur] + `C.canonical_normalized` + Wikipedia alias'ları → W, **orphan C DELETE** [admin liste status filtrelemez → orphan bırakılamaz]; `research_clusters.canonical_entity_id` FK SET NULL). **Cluster retro-fit GEREKMEZ** — küme çapaları Faz 2 resolver'da canonical-aware, yeni sorgu W'ye bağlanır.
- **#1721 — LLM precision gate (KRİTİK):** prod **dry-run** (salt-okunur, deploy-öncesi doğrulama) full-text aramasının event/prosedür adlarında **~%50 konu-kayması** ürettiğini ortaya çıkardı (Çölyak Eylem Planı→Şizofreni, A Ligi→A lyga, Aile ve Nüfus On Yılı→Aile hekimliği, 14 maddelik anlaşma→Aydınoğulları Beyliği). **Token-örtüşmesiyle deterministik ayrım YAPILAMIYOR**: doğru vakalar sıfır-örtüşmeli (akronim "2026 YKS"→"Yükseköğretim Kurumları Sınavı"; çeviri "İtalya Kupası"→"Coppa Italia"), yanlışlar örtüşmeli ("Aile"↔"Aile hekimliği"). Doğru sinyal **anlamsal** → tip-gate sonrası tek **v4-flash** çağrısı (`_llm_confirm_same_entity`: "bu Wikipedia maddesi haber-varlığının TAM karşılığı mı? EVET/HAYIR"; yıl/sıra + akronim/çeviri AYNI sayılır). HAYIR/hata → **`llm_reject`** (merge yok, muhafazakâr). cost-log op=`wikidata_verify` (#1604 deseni). YALNIZ canonical-katman'da (entity pass `verifier=None` → davranış değişmez). Sıkılaştırılmış prompt denendi ama birebir-kimlik eşleşmelerini (God of War, Cumhurbaşkanlığı Kupası) kaybetti → orijinal prompt korundu (daha iyi denge). Precision ~%50→~%94.
- **#1722 — worker registry bootstrap:** celery worker provider registry'yi otomatik bootstrap ETMEZ (yalnız app.main lifespan) → gate fail-closed olurdu (217/217 red). Fix: `_enrich_wikidata_async` başında `bootstrap_default_providers()` (idempotent, `build_local` lazy → bge-m3 yüklenmez; agenda/embedding/raptor deseni).
- **Güvenlik:** gerçek merge **DELETE** içerir → ayrı flag **`entities.wikidata_enrich.canon_layer.enabled`** (bool, default OFF → deploy davranışı değiştirmez, canary); `dry_run` flag'i baypas eder (salt-okunur önizleme). [[wikidata-canonical-labels#⚠️ Jenerik-kavram guard'ı YOK|corpus-N dersi]] sonrası: destructive merge önce dry-run ile doğrulanmadan AÇILMAZ.
- **Backfill (prod, founder onaylı 2026-06-22):** flag açıldı + tek seferlik tam koşum → **274 aday: 122 çözüldü (85 merge-DELETE + 37 yerinde-yükseltme) · 101 LLM-red · 51 no_match.** Flag AÇIK kaldı → beat **evergreen** sürdürür.
- **Bilinen sınır:** ~6 junk false-accept (A Ligi→A lyga [Litvanya], "Lig" anlam-ayrımı, Haziran 2026→FIFA) — düşük-değer NER gürültüsü; küme-çapası [[global-research-cluster-model|genericlik-reddi #1705]] bunları etiket yapmaz; gerekirse admin Varlık Birleştirme.

**Faz 4b — builder↔wikidata SALINIM fix (#1725/#1726, ✅ CANLI 2026-06-22):**
- **Sorun (founder admin'de fark etti):** merge edilen varyantlar (15-16 Haziran / YÖK / AK Parti) admin Varlık Birleştirme'de tekrar AYRI canonical görünüyordu. **Kök (prod teşhis, zaman damgası):** `enrich_wikidata` varyantları wikidata'ya merge eder (`:40`) ama `build_canonical` (token_subset/seed üretici beat, `:10`) ~30dk önce/sonra aynı varyantları source='token_subset'/'seed' **GERİ YARATIR** + wikidata alias'larını geri çalardı (token_subset alias guard'ı yalnız `<> 'admin'` idi, wikidata'yı korumuyordu). enrich guard'ı (refresh_days=30) re-merge'i engeller → **salınım** (her 6h ~30dk görünür dup). İki builder koordine değildi.
- **Invariant (kalıcı kural):** **`build_canonical` wikidata/admin otoritesine DEFER eder.** `_wikidata_owner_map` ile bir norm zaten wikidata/admin canonical'ın canonical'ı/alias'ıysa, builder o norm için YENİ (düşük-otoriteli) canonical AÇMAZ → mevcut W'ye yönlendirir. **Hem seed (#1726) hem token_subset (#1725) bölümü.** token_subset alias guard'ı da `NOT IN ('admin','wikidata')` (wikidata alias korunur).
- **Self-heal:** `_reheal_canonical_layer` (#1725) — `resolved` guard'lı (cache'li) token_subset/seed canonical'ı **Wikipedia/LLM çağırmadan** yeniden W'ye katlar (enrich beat'inde, sıfır LLM) → herhangi bir boşlukta otomatik onarım.
- **Prod doğrulandı:** 15-16 Haziran → tek wikidata (build_canonical tekrar koşunca **sticky**); yök/ak parti/tbmm/mhp → 0 token_subset/seed (hepsi wikidata canonical); reheal 85+9 dup cache'den temizledi; build_canonical sonrası seed **1'de kaldı** (fix öncesi 1→10 fırlıyordu). Kalan 6 fix-öncesi split-brain artığı (çoğu junk: Claude Mythos→bira) büyümüyor → admin panelden manuel (founder kararı).
- **Genel ders:** wikidata/admin canonicalization **yapışkan** olmalı; ham-üretici (build_canonical) her zaman daha-yüksek-otoriteli canonical'a defer etmeli, yoksa enrich↔builder salınır.

## Doğrulama (prod e2e)
Faz 1: Filenin Sultanları→Türkiye kadın millî voleybol takımı · ABD→Amerika Birleşik Devletleri · CHP→Cumhuriyet Halk Partisi · 15 temmuz→type_mismatch (red); top-8 korpus 8/8; canary 15→14 resolved+1 no_match. Faz 2: ABD entity → `place:amerika-birlesik-devletleri` (cur=1788), ham `place:abd` eşleşmez; trend tarafı küme ile aynı canonical anahtar. **Faz 4 backfill (274 aday):** 122 çözüldü (85 merge + 37 yükseltme) · 101 llm_reject · 51 no_match. 15-16 Haziran olayları (6 alias, iki direniş varyantı merge) ✓ · YÖK→Yükseköğretim Kurulu / RTÜK→Radyo ve Televizyon Üst Kurulu ✓ · 2026 YKS→Yükseköğretim Kurumları Sınavı ✓ · reddedilen "Aile ve Nüfus On Yılı" token_subset KORUNDU (yanlış silme yok) ✓ · broken FK=0 (küme bütünlüğü) ✓ · kaynak wikidata 742→841, token_subset+seed 293→171.

## Alternatifler ve neden reddedildi
- **Deterministik fuzzy (trigram/word_similarity):** prod'da gürültülü (#1705 anchor genericliğinde de görüldü) — Wikipedia full-text + sitelink-QID daha kesin.
- **Çıplak wbsearchentities:** #997 spike negatif (disambiguation güvenilmez).
- **Faz 2'siz sadece Faz 1:** sync getirmez (trend flag OFF + cluster_link raw) → Faz 2 şart.
- **Deterministik token-gate (canonical-katman precision, #1721):** REDDEDİLDİ — dry-run kanıtı: token-örtüşmesi hem akronimi (YKS↔Yükseköğretim Kurumları Sınavı, sıfır-örtüşme) hem fuzzy'yi (15-16 Haziran Direnişi↔15-16 Haziran olayları) bozar; yanlış-eşleme örtüşmeli olabilir (Aile↔Aile hekimliği). Anlamsal sinyal → **LLM gate** (v4-flash, ~$0.0005/aday) gerekli. Sıkılaştırılmış LLM prompt da reddedildi (birebir-kimlik kaybı).

## İlişkiler
[[entity-canonicalization-faz1]] (genişletir — seed/token_subset/admin) · [[global-research-cluster-model]] (küme çapa/etiket) · [[clusters-trends-integration-2026-06]] (trend↔küme köprüsü) · [[wikipedia-provider]] (HTTP zinciri) · [[finding_research_critical_entity_mvp_filter|#1703]] (voleybol — bu mekanizma destekler).

## Kaynaklar
- GitHub [#1710](https://github.com/selmanays/nodrat/issues/1710) / PR [#1711](https://github.com/selmanays/nodrat/pull/1711) — Faz 1 motor.
- GitHub #1712 / PR [#1712](https://github.com/selmanays/nodrat/pull/1712) — Faz 2 sync.
- GitHub [#1714](https://github.com/selmanays/nodrat/issues/1714) / PR [#1715](https://github.com/selmanays/nodrat/pull/1715) — evergreen (event-strip + EN-fallback).
- PR [#1716](https://github.com/selmanays/nodrat/pull/1716) (corpus-N guard, geri alındı) + PR [#1717](https://github.com/selmanays/nodrat/pull/1717) (guard kaldırma) — jenerik-tespit çözülemez dersi.
- GitHub [#1720](https://github.com/selmanays/nodrat/pull/1720) (canonical-katman merge motoru) + [#1721](https://github.com/selmanays/nodrat/pull/1721) (LLM precision gate) + [#1722](https://github.com/selmanays/nodrat/pull/1722) (worker registry bootstrap) — Faz 4.
- #997 (wikidata retrieval spike — negatif, merge-edilmedi; ders kaynağı).
- docs: data-model §6.1b.1 (`wikidata_entity_resolutions` + Faz 4) + api-contracts §6b.
