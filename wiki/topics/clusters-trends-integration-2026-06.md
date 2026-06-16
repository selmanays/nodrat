---
type: topic
title: "Kümeler × Trendler entegrasyonu — talep × arz (A–G)"
slug: "clusters-trends-integration-2026-06"
status: live
created: 2026-06-16
updated: 2026-06-16
sources:
  - "apps/api/app/modules/trends/cluster_link.py"
  - "apps/api/app/api/admin_clusters.py"
  - "apps/api/app/api/app_me.py"
  - "apps/api/app/modules/trends/tasks/alerts.py"
  - "apps/web/src/app/app/interests/page.tsx"
  - "apps/web/src/components/notification-bell.tsx"
tags: [trends, clusters, demand-supply, pivot, gundem]
aliases: ["talep-arz", "demand-supply", "clusters-trends", "İlgi Alanların"]
---

# Kümeler × Trendler entegrasyonu — talep × arz (A–G)

## TL;DR

Araştırma kümeleri (kullanıcı sorgularından türeyen ilgi alanları = **TALEP**) ile
entity trendleri (haberlerde ne oluyor = **ARZ**) **aynı haber-korpusu entity'sine**
çapalı → tek köprüyle (`cluster_link`, kebab-parity kilitli) birleştirildi. 7 fikir
(A–G) canlı + prod-verified: kullanıcı ilgi-feed'i (canlı trend) · admin talep×arz ·
kişiselleştirme · boşluk radarı · küme detay/timeline · trend-alert bildirim · karşılanmamış-ilgi→kaynak. Epic [#1571](https://github.com/selmanays/nodrat/issues/1571), 13 PR, tek migration (user_notifications).

## Kritik içgörü — ortak entity çapası

Bir araştırma kümesi "CHP" ile bir trend entity'si "CHP" **aynı `entities` korpusu
entity'si**. Köprü anahtarı: `cluster_key = '<type>:<tr_ascii_kebab(entity_normalized)>'`
(`core.research_clustering.canonical_cluster_key`). Trend tarafında `entity_type:
entity_normalized` → `tr_ascii_kebab` **SQL'de birebir** replike edilir (`cluster_link._KEBAB`);
küme anahtarı Python ile basıldığı için iki taraf aynı lossy sonucu üretir (combining-dot
dahil) → join tutarlı. ⚠️ Bu parity kırılırsa join **sessizce boşalır** → `test_kebab_parity_sql_matches_python` (testcontainers) kilitler.

`cluster_link` paylaşımlı yüzey: `trend_metrics_for_clusters` (anahtar→#1566 korpus-normalize
trend) · `rising_entities` (breaking/developing entity'ler) · `cluster_supply_detail`
(timeline+haber+kaynak) · `coverage_sources_for_clusters` (30g tarihsel kaynak).

## 7 fikir (A–G)

- **B — Admin talep×arz** (#1570/PR#1572): `/admin/clusters` listesine her küme için aynı entity'nin canlı `trend_state`+`relative_momentum`+`article_count_window` (arz). Talep (üye/kullanıcı) yanında.
- **A — Kullanıcı "İlgi Alanların"** (#1573/PR#1574): YENİ `/app/interests` — kullanıcının kümeleri + her birinin canlı trend rozeti ("Gelişiyor · son 24s X haber"). `GET /app/me/research-interests` trend ile zenginleşti. user-scoped.
- **D — Kişiselleştirme** (#1575/PR#1576, FE-only): /app/interests'e "Şu an hareketli" öne-çıkanlar bandı + sort toggle (ilgime/hareketliliğe göre).
- **G — Boşluk radarı** (#1577/PR#1578): `GET /admin/clusters/gaps` — karşılanmamış ilgi (talep var, sessiz arz) × ilgisiz yükselen (breaking, küme yok). `rising_entities`.
- **F — Küme detayı + timeline** (#1579/PR#1580): `GET /admin/clusters/{id}` + FE `/admin/clusters/[id]` — talep + arz (trend timeline + son haberler + kaynak). Satır clickable.
- **C — Trend-alert bildirim** (#1581/#1585, PR#1582/#1584/#1585): migration `user_notifications` (raw-SQL, dedupe UNIQUE, FK CASCADE) + beat `detect_trend_alerts` (3sa, breaking/developing, idempotent gün+küme) + flag `notifications.trend_alerts.enabled` (default OFF) + `/app/me/notifications` + FE zil/panel. Karar: [[global-research-cluster-model]] talep katmanı. Prod canary: 35 çift→8 bildirim/2 kullanıcı.
- **E-lite — Karşılanmamış ilgi → kaynak** (#1586/PR#1587): gap `unmet_demand`'e `coverage_sources` (entity'yi 30g hangi kaynaklar kapsadı → admin manuel kaynak ekleme/öncelik). **Crawler scheduling'e dokunulmadı** — tam otomasyon (talep→polling_tier) post-launch'a ertelendi (pre-launch talep zayıf + core-pipeline riski).

## Gizlilik + güvenlik

Kümeler GLOBAL (no user_id), görünürlük `message_clusters.user_id` ile türetilir →
user-facing yüzeyler (İlgi Alanların, bildirim) yalnız kendi kümeleri (cross-user
sızma yok, S11/S12). Trend verisi global/gizli-değil → birleştirmek güvenli. Tüm
endpoint'ler salt-okuma (C beat hariç, o da user-scoped INSERT). Migration additive
(zero-downtime); SSH ile `alembic current==head` doğrulandı (drift yok).

## Küme çapası Trends yapısına hizalandı (#1590)

Köprü çift-yönlü oldu: yalnız kümeler trend'e bağlanmadı, **kümelerin kendi çapa
seçimi de Trends entity yapısını benimsedi** (#1590 + #1594). Eski `select_anchor`
(rarest-df, tip-filtresiz) `number:bir`/`money:asgari ücret` gürültüsü + "trump"(split)
üretiyordu. Fix: `select_canonical_anchor` — (1) tip-filtre (person/org/place/event),
(2) canonicalization ("Donald Trump"/"CHP"/"Merkez Bankası" birleşik), (3) **#1594:
rarest→GATE+prominence** (trends volume mantığı) → "hürmüz"(df6) yerine "Hürmüz Boğazı"(df109);
"zaman"(df1)/tek-kaynak gate'ten elenir. Prod rebuild: 32→27→**17 aktif küme**, gürültü
gitti, canonical-birleşik. Tip-adları trendlerle senkron (Kişi/Kurum/Yer/Olay). Karar:
[[global-research-cluster-model]] §Çapa seçimi. Aynı `entities`+canonical+gate mantığı hem
trend hem küme çapasını besliyor → tutarlı kimlik. (Kalan "var" = tutarlı mis-NER tail'i.)

## Bilinen sınırlama / sonraki

- Per-user bildirim opt-out = v2 (şu an global flag + günde-bir dedupe + cap).
- E tam-otomasyon (talep→crawl tier) post-launch (anlamlı talep + güvenli tasarım gerekir).
- NER gürültüsü (jenerik kelime "var"/"bugün"/"gram" org/person mis-type) = ayrı (extraction tarafı; tip-filtre yakalamaz, #1590 canonical/tip-filtre number/money + split çözdü ama mis-NER common-word kalır).

## İlişkiler

- [[global-research-cluster-model]] — kümelerin (talep) global kanonik modeli (#1015 Pivot).
- [[trend-intelligence-admin-overview-2026-06]] — entity trend katmanı (arz); #1566 korpus-normalize trend_state.
- [[trend-unit-entity-centered]] — entity-merkezli trend birimi (köprünün entity çapası).
- [[entity-canonicalization-faz1]] — canonical entity (aynı korpus; kebab `tr_ascii_kebab`).

## Kaynaklar

- Köprü: `app/modules/trends/cluster_link.py` (kebab parity + 4 paylaşımlı fonksiyon).
- Admin: `app/api/admin_clusters.py` (list/gaps/detail) · FE `admin/clusters` + `[id]`.
- Kullanıcı: `app/api/app_me.py` (research-interests + notifications) · FE `app/interests` + `notification-bell`.
- Bildirim: `app/modules/trends/tasks/alerts.py` (beat) · migration `20260616_0200`.
- Docs: [api-contracts §6d + §13.6-8](../../docs/engineering/api-contracts.md) · [data-model §6.1c](../../docs/engineering/data-model.md).
- Test: `tests/migration/test_cluster_link.py` (kebab parity + e2e + rising + coverage + supply) · `test_notifications.py` (dedupe + endpoint).
