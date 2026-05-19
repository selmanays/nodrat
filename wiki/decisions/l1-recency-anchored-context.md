---
type: decision
title: "L1 bağlam — recency-anchored içerikli çapa (cosine relatedness terk edildi)"
slug: "l1-recency-anchored-context"
status: "locked"
decided_on: "2026-05-19"
decided_by: "tech"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1049 (L1 v1 — cosine, KANITLI HATALI), #1051 (L1 v2 — düzeltme), #1065 (#1064 Gate-1 sıralama fix)"
  - "apps/api/app/core/conversation_context.py (select_windowed_context, is_standalone_query, _has_dangling_referent)"
tags: ["locked-decision", "pivot", "L1", "memory", "architecture"]
aliases: ["l1-v2", "tier0-reach", "standalone-gate", "recency-anchor"]
---

# L1 bağlam — recency-anchored içerikli çapa (cosine relatedness terk edildi)

> **Karar:** Pivot'ta L1 görünmez bağlamı, "yeni sorgu ↔ önceki sorgu **cosine benzerliği**" ile DEĞİL; **S5 Gate-1 (standalone-yeterlilik)** + **recency-anchored en son İÇERİKLİ araştırma** ile seçilir. Cosine relatedness L1 seçiminden tamamen çıkarıldı.
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam

Pivot (her sorgu = bağımsız conversation, [[research-single-turn-invariant]]) sonrası takip sorusu ("nerde yaptı bu açıklamayı") kendi conversation'ında geçmiş bulamıyor; L1 bunu görünmez `condense`'e besleyip standalone'a çevirmeli. İlk tasarım (v1, #1049) `_rank_related` ile **cosine(yeni_sorgu, önceki_user_sorgu) ≥ 0.65** kullandı.

## Neden v1 başarısız (prod-kanıtlı)

`select_windowed_context` gerçek prod verisiyle replay edildi:

| Çift | cosine |
|---|---|
| "nerde yaptı bu açıklamayı" ↔ "Trump'ın son açıklaması nedir?" (içerikli antecedent) | **0.6055** (< 0.65) |
| "nerde yaptı bu açıklamayı" ↔ eski "bu açıklamayı nerede yaptı" (önceki BELİRSİZ takip) | **0.9851** |

→ v1 condense'e Trump araştırmasını değil **kendi eski başarısız takibini** (çöp) verdi. **Genel ilke:** belirsiz takip, doğası gereği başka belirsiz takiplere yakın, atıf yaptığı içerikli sorguya UZAK → cosine-relatedness L1 için yapısal olarak yanlış.

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| v1: cosine relatedness gate | Kanıtlı: doğru antecedent'i eşik-altı bırakır, eski belirsiz takibi çapa seçer |
| Eşiği düşür (0.65→0.5) | Semptomu örter; belirsiz↔belirsiz hâlâ > belirsiz↔içerikli; kök yanlış |
| Prompt'u suçla (condense reference-resolution) | Denetimde çürütüldü: condense'e zaten çöp bağlam gidiyordu; prompt masum |

## Sonuç (v2 — locked)

- **Gate-1 (standalone-yeterlilik, saf):** sorgu kendi açık öznesini taşıyorsa (özel-ad/kesme-ek/4+ kelime & **dangling referent yok**) → L1 **HİÇ kullanılmaz** (yeni konu kirlenmez). Zamir/elips/kısa **veya çözülmemiş "bu iddia/şu olay" referansı** → antecedent gerekir. ⚠️ #1064: "özel-ad → her zaman standalone" YANLIŞTI; dangling referent özel-ad ile iptal OLMAZ (aşağıdaki 🔧#1064 callout).
- **Recency-anchored çapa:** 6s→24s→72s pencere cascade'inde **en son İÇERİKLİ (standalone) araştırma** çapa alınır; onun [user, assistant] Q&A'i condense'e gider. Önceki belirsiz/başarısız takipler çapa OLAMAZ (kendileri standalone değil → atlanır). **Cosine YOK.**
- `format_context_block`/condense sözleşmesi/Gate-4 (`l1_accept_rewrite`)/cevap çekirdeği DOKUNULMADI. L1 flag kapalıyken byte-eş.

> 🔧 **#1058 Fix C — condense kaynak-adı sızıntısı kapatıldı:** v2'de "DOKUNULMADI" denen `format_context_block` sonradan **gözden geçirildi**: önceki cevabın kaynak ADLARINI ("Forbes Türkiye") condense bağlamına koyuyordu → 0-kaynak halüsinasyonda uydurma atıfın tohumu (prod-audit conv 865e36e3). Fix: `format_context_block(..., include_sources: bool = False)` — varsayılan kaynak-adı satırını ÜRETMEZ (condense yalnız önceki Q&A KONUSUNA muhtaç). **Condense SÖZLEŞMESİ korunur** (legacy birebir format yalnız opt-in `include_sources=True`; çağıran yok → byte-eş). Detay [[research-cited-only-hard-invariant]].
>
> 🔧 **#1064 — Gate-1 sıralama hatası düzeltildi (prod-teşhis conv quirky-gates Q3):** Yukarıdaki Gate-1 maddesi ("özel-ad VARSA → L1 HİÇ kullanılmaz") **fazla agresifti**: `is_standalone_query` `_has_proper_noun`'ı `_L1_REFERENTIAL`'den ÖNCE kontrol edip kısa-devre yapıyordu. "**Özgür Özel** bu iddiayı ne zaman dile getirdi?" → özel-ad → standalone sayıldı → L1 atlandı → "**bu iddia**" çözülmedi → belirsiz retrieval → "Hangi iddiadan bahsettiğinizi netleştiremedim" (bağlam kaybı). **İlke düzeltmesi:** özel-ad AKTÖRdür, eşzamanlı dangling referent'i ("bu iddia") ÇÖZMEZ → `_has_dangling_referent` kontrolü özel-ad'dan ÖNCE. Yanlış-pozitif koruması: bare `bu/şu/o` + ZAMANSAL deiktik isim (`hafta/yıl/gün/sezon…`) → dangling DEĞİL ("Trump bu hafta" standalone kalır); soyut referent (`konu/olay/iddia/açıklama`) + çekimli/işaret formları → dangling. Saf/DB'siz, flag yok, downstream korumalı (çapa-standalone + Gate-4 + condense). Prod-kanıt: ham "Trump'ın **bu** açıklamasını nerede yaptı" → `effective_query`="Trump'ın **son** açıklamasını nerede yaptı" (L1 devreye girdi, eskiden girmiyordu) → grounded WHERE cevabı, "hangi açıklama?" YOK. Detay [[research-cited-only-hard-invariant]] (kardeş 4-sorgu teşhisi).
- Prod replay (v2): aynı takip → cef074a8 "Trump'ın son açıklaması" Q&A çapa; effective_query bağlamlı yeniden yazıldı (ham değil); konu değişiminde kirlenme yok.

## İlişkiler

- [[pivot-editorial-research-engine]] — L1 bu pivotun görünmez-bağlam katmanı
- [[research-single-turn-invariant]] — her conversation tek-mesaj olduğu için conversation-scope L1 ölü; user-scope ZORUNLU
- [[pivot-3-layer-memory]] — L1/L2/L3 üç katman
- [[research-cited-only-hard-invariant]] — #1058 Fix C condense kaynak-adı sızıntısı (L1 besleyici sözleşme)

## Geri alma maliyeti

> `chat.l1_windowed_context_enabled` (rename sonrası `research.l1_windowed_context_enabled`) flag kapat → L1 no-op, ham sorgu. Saf `is_standalone_query` birim-testli; flag-off byte-eş.

## Kaynaklar

- [conversation_context.py](apps/api/app/core/conversation_context.py) — `select_windowed_context`, `is_standalone_query`, `_has_dangling_referent`, `_research_messages`
- PR #1049 (v1 hatalı), #1051 (v2 düzeltme), #1050 (yan: flaky JWT test kök-neden), **#1065 (#1064 Gate-1 sıralama fix — dangling-referent özel-ad ile iptal olmaz; prod-kanıtlı)**
