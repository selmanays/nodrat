---
type: decision
title: "Global araştırma kümesi modeli — tek sağlayıcı, çok dinleyici"
slug: "global-research-cluster-model"
status: "locked"
decided_on: "2026-05-18"
decided_by: "tech"
created: "2026-05-18"
updated: "2026-06-23"
sources:
  - "Plan rev.12 §3/§7 + S11/S12"
  - "apps/api/app/models/research_cluster.py"
  - "apps/api/app/workers/tasks/cluster_assigner.py (gece batch)"
  - "PR #1025 (#1015 Faz 3) / #1038 (#1020 Faz 6)"
  - "C ops-doğrulama (conv quirky-gates, 2026-05-19 — canlı prod)"
tags: ["locked-decision", "pivot", "clustering", "privacy"]
aliases: ["tek-sağlayıcı-çok-dinleyici", "research-cluster-model", "global-küme"]
---

# Global araştırma kümesi modeli — tek sağlayıcı, çok dinleyici

> **Karar:** Araştırma kümeleri **GLOBAL kanonik düğüm** (`research_clusters`, user_id TAŞIMAZ); kullanıcı görünürlüğü `message_clusters ⋈ WHERE user_id=?` ile **türetilir** (cross-user sızma yok). Atama GECE batch. Hiyerarşi **kullanım deseninden** (df-asimetri), ansiklopediden DEĞİL.
> **Durum:** locked
> **Tarih:** 2026-05-18

## Bağlam

3-katman hafızanın ([[pivot-3-layer-memory]]) küme substratı. "Tek sağlayıcı, çok dinleyici": tek kanonik "CHP" düğümü; içerik user-scoped görünür. Global → depolama/işlem azalır, hiyerarşi aggregate sağlam, trend-sinyal substratı tutarlı.

## Kritik gizlilik kısıtı (S11) — UNUTMA

Küme **çapası YALNIZ haber-korpusu (`entities`) entity'si**. Entity'siz sorgu → embedding-centroid fallback **yalnız MEVCUT aktif küme'ye** bağlanır; **yeni global küme MİNTLEMEZ** → özel-sorgu metni/adı global düğüm yaratmaz, başka kullanıcıya sızmaz. S12: boş aktif küme → async soft-deprecate (`deprecated_at`).

## Çapa seçimi — Trends yapısına hizalandı (#1590)

İlk sürüm (`select_anchor`): query-gram → `entities` eşleşmesi → **en nadir df** çapa, tip-filtresiz + canonicalization'sız. Prod'da kötü öbek üretti: tip-filtresi yok → `number:bir`/`12`/`doğalgaz` + `money:asgari ücret` gürültü kümeleri; canonicalization yok + rarest-wins → "donald trump"(df880) yerine "trump"(df318) (split). **#1590 düzeltme — Trends entity yapısı uygulandı** ([[trend-intelligence-admin-overview-2026-06]] + [[entity-canonicalization-faz1]]):
- **Tip-filtre:** çapa yalnız `person|org|place|event` (`ANCHOR_ENTITY_TYPES`); number/money/misc çapa OLAMAZ.
- **Canonicalization:** `_ENTITY_DF_SQL` artık `entity_aliases`/`canonical_entities` LEFT JOIN (`COALESCE`) → "trump"/"donald trump" tek canonical "donald trump" (display "Donald Trump"); `cluster_key = <type>:<kebab(canonical_normalized)>`.
- **`select_canonical_anchor`:** canonical-eşleşen aday öncelikli → sonra (#1594) **GATE + PROMINENCE**. `canonical_name` = canonical display adı.
- **#1594 — rarest→prominence (TRENDS mantığıyla TAM hizalama):** İlk #1590 sürümü hâlâ **rarest-df** kullanıyordu → yanlıştı. Gerçek-veri kanıtı: küme rarest seçerken trendler **volume** seçiyor → "hürmüz"(df6) "Hürmüz Boğazı"yı(df109) yeniyordu (fragment); "var"(df5) gerçek entity'leri yeniyordu (nadir-wins gürültü). Trendlerde bunlar hacim düşük → görünmez. **Fix:** (1) **GATE** — `df ≥ min_articles` **VE** `kaynak ≥ min_sources` (trends evidence-gate gibi; `_ENTITY_DF_SQL`'e `COUNT(DISTINCT source_id)` + `JOIN articles`) → nadir/tek-kaynak gürültü ("zaman" df1) elenir; (2) **PROMINENCE** — en YÜKSEK df (rarest DEĞİL) → tam/baskın entity kazanır ("Hürmüz Boğazı">"hürmüz", real>rare-noise). Tip-adı senkron: admin `/admin/clusters` Tip kolonu trendlerle aynı localize (Kişi/Kurum/Yer/Olay).
- **#1598 — NER gürültü filtresi (kalan "var" tail'i kaynakta kapandı):** #1594 sonrası kalan "var"(org df5/4kaynak) = gate'i geçecek kadar tutarlı **mis-NER**. Kullanıcı "trend ile küme aynı mantıkla çalışsın" → çözüm consumption-band-aid değil, **NER ingest enforcement**: paylaşımlı [[ner-noise-stopword-filter]] (`core/entity_noise.is_noise_entity`) hem NER ingest'inde (yeni makaleler) hem `select_canonical_anchor` gate'inde (mevcut gürültü çapa-dışı) → trend ve küme tek temiz taban. `entities` tablosu SİLİNMEDİ (RAG-güvenlik; yalnız ingest-filtre + çapa-exclude).
- **#1697 — özgüllük (kelime-sayısı) → REGRESYON (kaldırıldı):** prominence tek başına jenerik yüksek-df yer'i özneye tercih ediyordu ("filenin sultanları almanya maçı" → place:almanya). Geçici fix: çok-kelimeli norm önce. **YANLIŞ sinyaldi** — jenerik çok-kelimeli ifade ("belediye meclisi" 2w) spesifik tek-kelimeli özel-adı ("tuvalu" 1w) yendi. #1705 ile kaldırıldı.
- **#1705 — EVERGREEN jenerik-kategori reddi (corpus-türevli genericlik):** founder "Tuvalu … belediye meclisi bütçe" → çapa "Belediye Meclisi" (jenerik org). Kök: "tuvalu" df=1 gate'i geçemiyor → jenerik fallback; genericlik DİLSEL (df/kelime-sayısı işaretlemez). **Sinyal:** genericlik = bir norm'u BİLEŞEN olarak içeren FARKLI entity sayısı (jenerik "X Belediye Meclisi"→≥22; spesifik özel-ad ~0; eşik `GENERIC_ANCHOR_MAX=15`; prod temiz boşluk ≤6↔≥22). **Kural:** gate → **fragment-elim** (substring; "hürmüz"⊂"hürmüz boğazı") → **jenerik(gn≥15)+tip≠place reddi** → spesifik-kova sort (canonical → `1 if gn≥max else 0` → −df → norm) → **hepsi jenerikse None (küme YOK** — yanlış jenerik küme yerine; [[research-cited-only-hard-invariant|Fix#3]] 0-kaynak akışıyla uyumlu). **Yer (ülke/şehir) MUAF** ("Almanya seçimleri" meşru). Genericlik ayrı tek-round-trip unnest (correlated-CTE grouped-COALESCE'a izin vermez + ~1.4s kötü plan; per-norm `count(DISTINCT)` trigram ~10-30ms). resolver + cluster_assigner **ortak `resolve_anchor`** (drift yok). Deployed prod e2e: Tuvalu→None · voleybol→filenin sultanları · hürmüz→Hürmüz Boğazı · özgür özel+chp→CHP · almanya-seçim→Almanya. **Retrieval critical_entity generic-terim (#1703/#1704) AYRI alt-sistem** (curated denylist; bu = cluster-anchor).
- **#1737 — EVERGREEN çekim-bağışık fallback (kümesiz isabetli sorgu):** founder "12. yargı paketinde neler var" → cevap doğru ama **kümesiz**. Kök: `resolve_cluster_by_entity` HAM sorguyu `query_grams`'lıyor; Türkçe çekim → gram "12 yargı paketinde" (lokatif) ≠ entity "12. yargı paketi" (yalın) → exact `IN grams` kaçıyor → çapa None. **Fix:** query-gram çapa None ise, cevabın **ATIF yaptığı kaynak makalelerin** entity'lerinden çapa çıkar (`ARTICLE_ENTITY_DF_SQL`, `ENTITY_DF_SQL` ile aynı kolon şekli). **Kritik incelik:** cited makalelerde bol bulunan geniş varlıklar (parti/kurum: AKP/AYM/TBMM/CHP — **hepsi canonical'lı**) `has_canonical` sıralamada önde olduğu için özneyi bastırırdı → cited-entity'ler `_query_overlap` ile **yalnız sorgu token'ının PREFIX'i olanlarla** sınırlanır (Türkçe-ek yönü: `paketi`⊂`paketinde`, `yargı`==`yargı`). **Tek-yön kasıtlı** — ters yön (`yargı`⊂`yargıtay`) yanlış-komşu canonical'ı içeri alırdı. Sonra mevcut `resolve_anchor` (GATE + jenerik-reddi) uygulanır. `cluster_assigner` ETKİLENMEZ (yalnız sorgu-anı create-path). Deployed prod e2e (8 cited makale): PRIMARY=None · overlap geniş varlıkları (adalet bakanlığı/akp grubu/akın gürlek…) eler · GATE df1/src1'leri eler → **FALLBACK çapa = "12. Yargı Paketi"** ✓.
- **#1740 — KİMLİK canonical_entity_id'ye DEMİRLENDİ (drift→çift küme önlemesi, PR-1):** Denetimde bulundu: `cluster_key` çalışma anında `COALESCE(canonical_normalized, entity_normalized)`'in kebab'ından türetiliyor; wikidata enrich bir alias'ı canonical'a bağlayınca (`akp`→`Adalet ve Kalkınma Partisi`) **aynı konu** yeni key alır → eski+yeni iki ayrı aktif küme (her biri kendi abonelik/artefaktıyla). `canonical_entity_id` sütunu vardı ama **hiçbir kod doldurmuyordu** (5 dolu = Faz 3 manuel retro-fit). Prod drift=0 (0 trafik) ama mekanizma canlı. **Fix:** ortak `resolve_or_create_cluster` (resolve_cluster_by_entity + cluster_assigner TEK kaynak) — çapanın canonical'ı varsa küme **`canonical_entity_id` VEYA canonical'ın TÜM alias-key'leriyle** çözülür (stranded eski-key kümesi `org:akp` yakalanır) → alias yüzey-formu değişse de drift yok; mevcut NULL canonical_id **fırsatçı backfill**. Canonical yoksa key-only davranış birebir korunur. **Additive + reversible** (key/ad değişmez, silme/reparent yok, migration yok). Prod e2e: "mustafa kemal atatürk" 19 aday-key üretir; "voleybol takımı" canonical_id ile çözülür, mint yok.
- **#1742 — MERGE/REPARENT operatörü + reconcile (mevcut drift iyileştirme, PR-2):** `cluster_merge.merge_clusters(source→target)`: artifacts/message_clusters/subscriptions/parent hedefe **reparent**, source **soft-deprecate** (RESTRICT FK korunur → SİLİNMEZ). UNIQUE çakışmaları: `message_id+cluster_id` dedup; user live-sub partial-unique → taşı/soft-unsub (**opt-out izi korunur**). `training_samples` IMMUTABLE → dokunulmaz. Idempotent. `reconcile_canonical_anchors(dry_run=)`: aktif kümeleri canonical_id'ye çözüp drift gruplarını tek hedefe (max kullanım) merge + NULL canonical_id backfill. Admin: `POST /admin/clusters/merge` + `/reconcile?dry_run=` (require_admin). **Additive + dormant** (otomatik mutasyon yok). Prod reconcile (founder onaylı): drift_groups=0, merge=0, **13 küme backfill** (canonical_id dolu 5→18); drift sonrası 0, hiçbir küme silinmedi.
- **#1751 — KÜME = CEVABIN konusu (sorgu kelimesi DEĞİL):** founder: "geçen hafta ölen genç oyuncu kimdi" → cevap doğru (Ece İrtem) ama küme **"Genç"**. Kök: küme **sorgu kelimelerinden** çözülüyordu; "genç" NER'de gerçek bir `place` entity (**Bingöl Genç ilçesi**, df=7/6src) + yer-tipi olduğu için #1705 jenerik-reddinden **muaf** → query-gram onu çapaladı. Sorgu özneyi adlandırmadığı ("o kimdi") için #1737 cited-fallback de tetiklenmedi (query-gram bir çapa bulmuştu). **Fix (evergreen):** `resolve_cluster_by_entity` çözüm sırası **CEVAP-TARAFI primary** — cited kaynakların **cevap metninde adı geçen** baskın entity'si (`_resolve_answer_anchor`/`_answer_mentions`; `app_research_stream` `answer_content=content` geçer). Sorgu kelimelerinden BAĞIMSIZ → "genç" giremez; cevapta GEÇMEYEN bağlam (Tayland df-baskın olsa bile) elenir; `resolve_anchor` gate+jenerik-reddi+df-sıra uygular. Query-gram + #1737 cited∩sorgu **fallback** olarak korundu (geri-uyum). `cluster_assigner` etkilenmez (yalnız artefakt sorgu-anı). Prod read-only kanıt: aynı sorgu ESKİ→`place:genc 'Genç'`, YENİ→`person:ece-i-rtem 'Ece İrtem'`. 3 unit (_answer_mentions) + 1 integration (genç-collision before/after). **Genel ders: küme/özne tespiti SORGUNUN ifadesinden değil CEVABIN/kaynakların konusundan yapılmalı — sorgu kelimesi yer/özel-ad ile çakışabilir.**
- **#1759 — cevap-tarafı çapanın İKİ kalan kökü (Faz 1; DEM Parti vakası):** founder "dem parti neden gündemde" → cevap DEM Parti/Tülay Hatimoğulları ama küme **"Numan Kurtulmuş"** (cevapta yalnızca seslenilen ikincil). Prod analiz: **(A) alias-körü** — `_answer_mentions` yalnız norm+display'e bakıyordu; DEM Parti'nin canonical adı "Halkların Eşitlik ve Demokrasi Partisi", cevap "DEM Parti" → asıl özne (df=7) aday OLAMADI. **(B) canonical-first sıralama** — kalan adaylarda canonical'lı ikincil (Numan Kurtulmuş df=2) df-baskın özneyi (Tülay df=5) bastırdı. **Fix (additive, şema yok):** (A) `ARTICLE_ENTITY_DF_SQL` += `array_agg(DISTINCT entity_normalized) AS surface_forms` (ham NER yüzey/alias formları); `_answer_mentions` bunları da cevapta arar → "DEM Parti" yüzey-formu eşleşir. (B) `select_canonical_anchor(prefer=)` param: cevap-tarafı yol `prefer="df"` (df-baskın; canonical yalnız df-eşitliğinde tiebreak), query-gram + cluster_assigner yolu `prefer="canonical"` (DEĞİŞMEZ). Prod read-only: DEM Parti sorgusu → `org:halklarin-esitlik-ve-demokrasi-partisi 'Halkların Eşitlik ve Demokrasi Partisi'` (Numan değil). 3 unit + 1 integration. **Genel ders: cevap-eşleşmesi alias/kısaltma-farkında olmalı (canonical adı ≠ cevaptaki yüzey); cevap-tarafı sıralama df-baskın olmalı (canonical'lı ikincil asıl özneyi bastırmaz).** **Faz 2 (çoklu-küme üyeliği) AYRI — bir cevap birden çok kümeye ait olabilir (birincil + ikincil), henüz tek küme.**
- **Prod rebuild** (kullanıcı-onaylı; eski küme+membership sil → assigner re-run → hierarchy): #1590→27, #1594→17/21, **#1598→20 aktif küme**; number/money + low-evidence + common-word gürültü (zaman/elektrik/bugün/hürmüz-fragment/**var**) GİTTİ; `Özgür Özel`(17)/`Donald Trump`(12)/`Cumhuriyet Halk Partisi`(8)/`Merkez Bankası`(8) canonical-birleşik; gerçek yerler (türkiye/abd/küba) kaldı. Yalnızca-gürültü-çapalı sorgular artık doğru şekilde **unclustered** (yeni gürültü küme mintlenmez).

## Hiyerarşi (Faz 6) — kullanım deseni, ansiklopedi DEĞİL

`parent_cluster_id` aggregate co-occurrence + **df-asimetri** ile (#1020): B child-of-A ANCAK asimetrik kapsama (P(A|B)≥hi ∧ P(B|A)≤lo) + A daha genel (df/occ). **Salt birlikte-geçme YETMEZ** → Erdoğan↔Özel simetrik = yanlış-ebeveyn OLMAZ (eşik-korumalı, false-positive yok). Aggregate yalnız COUNT (içerik ifşa olmaz). Idempotent + reversible (düz-küme-önce; flag-off no-op).

## Ops doğrulama (C — 2026-05-19, canlı prod)

Tasarım yalnız teori değil — canlı prod'da kanıtlandı (conv quirky-gates, "C işi"):

- **Flag durumu:** 3 flag prod `app_settings`'te **zaten `true`** (önceki pivot seansında DB-override; default-False kill-switch çalışıyor ama açık). Beat schedule canlı doğru: `research-cluster-assign` 03:50 UTC + `research-hierarchy-refine` 03:55 UTC. `entities` korpusu 169.532 (S11 çapa kaynağı sağlıklı).
- **Gece batch (elle tetik, idempotent/bounded/reversible):** `run_cluster_assigner` → `status=ok, scanned=19, assigned_entity=12, fallback=0, unclustered=7, clusters_created=3, errors=0`. Oluşan 4 küme: `person:trump`/`event:final`/`org:politico`/`person:özel`.
- **S11 KANITLANDI:** her küme `canonical_name` = normalize haber-korpusu entity'si; ham kullanıcı sorgusu ("Trump'ın son açıklaması nedir?") **hiçbir küme adına sızmadı**; çapasız 7 mesaj kasıtla kümelenmemiş (özel-sorgu global'e MİNTLENMEZ).
- **Idempotency KANITLANDI:** 2. tetik → `assigned=0, created=0, errors=0` (UNIQUE + WHERE-NOT-EXISTS; dupe yok).
- **Hiyerarşi false-positive YOK:** `run_hierarchy_refine` ×2 → `clusters=4, pairs=6, edges=0, cleared=0, errors=0` (zayıf veride özel↛trump yanlış-ebeveyn yapılmadı; idempotent).
- **S6 (L2 down-rank YOK):** `apply_l2_affinity_boost` kod-kanıtı — yalnız eşleşen article'a `+boost`, eşleşmeyen satır dokunulmaz; flag/empty/no-match → byte-eş; user-scoped (S11) + deprecated hariç (S12); cache user-agnostik.
- **Cevap invariantı:** #1058/#1059 Playwright testleri bu 3 flag açıkken koştu → kaynaklı doğru cevap + gerçek atıf/URL, halü yok; API eval golden-set yeşil. L2 yalnız chunk sırası → prompt/citation/halü yoluna erişemez.
- **Karar:** flag'ler açık kalır (düzgün/gizlilik-güvenli/geri-alınabilir; pre-launch veri-biriktirme için ideal). **Kod/flag değişikliği gerekmedi — pure verification.**

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Per-user küme | Depolama/işlem ↑, hiyerarşi zayıf, trend-sinyal tutarsız |
| Per-answer atama | Çekişme (S7); gece batch → izole, NER ETL deseniyle hizalı |
| Entity'siz sorgudan yeni küme | S11 ihlali — özel-sorgu adı global'e sızar → fallback yalnız mevcut |
| Ansiklopedik hiyerarşi | Yanlış; kullanım-aggregate + df-asimetri (çıkarım, kesin değil) |

## Sonuçlar

- Şema additive: `research_clusters`/`message_clusters` (mevcut tablo/trigger değişmez). FK: message_id CASCADE, cluster_id RESTRICT, user_id CASCADE (KVKK).
- Cevap-üretim akışı **DOKUNULMAZ** — küme paylaşımlı, içerik user-scoped (sızma yok).
- İlişki: [[pivot-editorial-research-engine]] · [[pivot-3-layer-memory]] · [[research-cited-only-hard-invariant]] (C ops-doğrulamada cevap-invariantı kanıtı — flag'ler açıkken #1058/#1059 kaynaklı doğru) · [[clusters-trends-integration-2026-06]] (#1571 — bu kümeler TALEP sinyali; entity trendleriyle (ARZ) birleştirildi: ilgi-feed/bildirim/boşluk radarı)

## Geri alma maliyeti

> flag (`research.clustering.enabled` / `research.hierarchy_refine_enabled`) kapat → gece job no-op; tablolar additive (mevcut şema bozulmaz). Hiyerarşi reversible (düz-küme recompute). Pre-launch dev → düşük maliyet.
