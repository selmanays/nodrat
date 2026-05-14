---
type: decision
title: "Chat-only migration — form modu/eski geçmiş/kayıtlı sayfaları kaldırma"
slug: "chat-only-migration"
status: "locked"
decided_on: "2026-05-14"
decided_by: "founder"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/product/prd.md§Faz-3"
  - "docs/engineering/data-model.md§5"
tags: ["locked-decision", "mvp-1", "ux", "chat"]
aliases: ["sohbet-tek-noktası", "form-modu-kaldırma"]
---

# Chat-only migration — form modu/eski geçmiş/kayıtlı sayfaları kaldırma

> **Karar:** `/app/generate` (form modu), `/app/generations` (eski geçmiş), `/app/saved` (kayıtlı) sayfaları **tam kaldırılır**; tek erişim noktası `/app/chat` (Perplexity-style sohbet).
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

#793 epic'inde Perplexity-style sohbet UX yayına alındı (5 PR / tek seans, prod: `https://nodrat.com/app/chat`). Form modu paralel olarak korunmuştu — backward compat amaçlı. Ancak kullanıcı görüşü: paralel UX kafa karışıklığı yaratıyor; form modu **deprecated** olarak duruyor olsa bile bakım maliyeti var.

Soru: form/generations/saved UX'i deprecate edip sürdürelim mi, yoksa **tamamen kaldıralım mı**?

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Form modu deprecated-but-available bırak | Power user safe-path | İki UX paralel bakım; data-model'de kalan ölü tablolar | reddedildi |
| Form modu **iframe**'le chat'e ekle | Hibrit | Karmaşık, KVKK audit zor | reddedildi |
| **Form/generations/saved tam kaldır + sohbet'i tek noktaya çıkar** | Tek tutarlı UX; ölü kod yok; parametre özellikleri (tone/length/output_type/max_posts/style_profile) sohbet'e taşınır | KVKK export shape değişir; mevcut generations satırları "anonim" hâlde korunur | **seçildi** |

## Uygulama (5 sprint)

| Sprint | İçerik | PR |
|---|---|---|
| S1A | UI cleanup — `/app/generate`, `/app/generations`, `/app/saved` route'ları + 5360 satır legacy kod kaldırıldı; nav 3 item'a indi (Sohbet/Stil profilleri/Plan) | #800 |
| S1B | DB DROP — `generations` + `saved_generations` tabloları DROP; `messages`'e 11 yeni kolon (halu/action/SFT/DPO); `training_samples`'a `message_id` FK + `sample_type` kolonu | #801 |
| S1C | Halu feedback + action endpoints (POST `/chat/messages/{id}/flag-halu`, POST `/chat/messages/{id}/action`); HaluFlagModal + MessageActions toolbar | #802 |
| S1D | ChatSettingsModal — 6 parametre (output_type, tone, length, max_posts, style_profile_id, show_sources); localStorage `chat-settings-default` + `chat-settings-conv-{id}` | #803 |
| S1E + S1F | SFT pipeline messages source rewrite; admin SFT page sample_type + DPO observability; chat layout responsive (Sheet mobile sidebar, header truncate, full-width chat); `app_me.py` Generation imports → conversations+messages | #805 |

## Sonuçlar

- **UX:** Tek sohbet erişim noktası; `chat-settings-{conv_id}` localStorage per-conversation override pattern'i
- **Data model:** `generations` + `saved_generations` DROP; `messages` tablosuna eklenen 11 kolon (halu/action/SFT/DPO) → bkz. [[chat-message-feedback-columns]]
- **SFT pipeline:** `sft_curator` artık `messages` tablosundan beslenir — 3 sample tipi (sft/dpo_rejected/dpo_chosen) → bkz. [[sft-message-source]]
- **DPO:** Halu işaretli mesajlar `dpo_rejected=true`; kullanıcı önerisi (`dpo_chosen_content`) varsa pair sample → bkz. [[dpo-rejected-samples]]
- **Tarihçe veri korunur:** `training_samples.generation_id` nullable yapıldı (FK kaldırıldı, eski satırlar "anonim" hâlde durur, gelecek SFT için değerli)
- **KVKK:** `/me/export` shape değişti — `generations`/`saved_generations` yerine `conversations` (nested messages 50/conv cap); consent revoke artık `messages.sft_eligible` UPDATE

## Geri alma maliyeti

> Bu karar geri alınırsa:
> - **DB:** generations + saved_generations tabloları yeniden CREATE — migration `20260514_1700` down değil, yeni migration gerek (eski satırlar dönülmez kayıp)
> - **Kod:** ~5400 satır legacy UI/API kodu yeniden yazılır
> - **UX:** Kullanıcı kafa karışıklığı + admin/SFT pipeline farklı tablodan beslenir
>
> Yüksek maliyet — kararı revize etmek 1-2 hafta full-stack iş.

## İlişkiler

- **Bağlı varlıklar:** [[perplexity-ux-redesign]]
- **Bağlı kavramlar:** [[chunks-first-retrieval]], [[chat-message-feedback-columns]]
- **Bağlı decisions:** [[sft-message-source]], [[dpo-rejected-samples]]

## Kaynaklar

- [docs/product/prd.md](../../docs/product/prd.md) §Faz-3 (sohbet UX)
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §5 (conversations + messages)
- [docs/engineering/api-contracts.md](../../docs/engineering/api-contracts.md) §17.5 (/chat/* endpoint'leri)
- PR'lar: [#800](https://github.com/selmanays/nodrat/pull/800), [#801](https://github.com/selmanays/nodrat/pull/801), [#802](https://github.com/selmanays/nodrat/pull/802), [#803](https://github.com/selmanays/nodrat/pull/803), [#805](https://github.com/selmanays/nodrat/pull/805)
