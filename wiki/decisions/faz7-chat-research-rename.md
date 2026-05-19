---
type: decision
title: "Faz 7 — chat→research fiziksel rename + A/B/false-positive sınırı"
slug: "faz7-chat-research-rename"
status: "locked"
decided_on: "2026-05-19"
decided_by: "founder"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1052 (backend), #1053 (frontend)"
  - "apps/api/alembic/versions/20260519_0100_faz7_chat_to_research_rename.py"
tags: ["locked-decision", "pivot", "rename", "faz7", "architecture"]
aliases: ["faz7", "chat-research-rename", "ab-boundary"]
---

# Faz 7 — chat→research fiziksel rename + A/B/false-positive sınırı

> **Karar:** Pivot tamamlandı — "chat" ifadesi Nodrat **ürün/alan** katmanından (endpoint/dosya/fonksiyon/değişken/DB/settings) tümüyle kaldırıldı, `research` oldu. **B-grup** (LLM-sağlayıcı chat-completions primitifi) ve **dış-standart** terimler (ChatGPT/ChatML/chatcmpl/Trendyol-LLM-7B-chat) bilinçle KORUNDU.
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam

[[pivot-editorial-research-engine]]'de F7 "koşullu-ertelendi" idi (en yüksek blast-radius). Kullanıcı sonradan tam rename talep etti: "chat ifadesi değişken isimleri dahil hiçbir yerde kalmamalı." Kritik sınır kararı gerekti: hangi "chat" Nodrat'ın ürünü, hangisi endüstri-primitifi.

## Sınır (A / B / false-positive)

| Sınıf | Örnek | Karar | Gerekçe |
|---|---|---|---|
| **A — Nodrat ürün/alan** | `app_chat_stream`, `chat_tools`, `chat_cache_telemetry`, `/chat/*`, `post_chat_message`, `chat.*` settings, `task_type 'chat_answer'`, FE `ChatMessage`/`/app/chat` | **research'e RENAME** | Pivotun kimliği; kullanıcının kastı |
| **B — LLM-sağlayıcı primitifi** | `nim_chat`, `deepseek_chat_model`, `operation="chat"`, `provider_log` enum `'chat'`, `_tracked_chat_generate`, `supports_chat` | **KORU** | Endüstri-standardı; dış `/chat/completions` URL zaten değiştirilemez; rename = correctness/açıklık kaybı (kullanıcı onayı: "B'ye dokunma") |
| **false-positive** | `ChatGPT`, `ChatML`/`chatml`, `chatcmpl`, `Trendyol-LLM-7B-chat`, `"chat.completion"` | **KORU** | Dış ürün/format/model adları; rename factually yanlış |

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Hiç rename etme (F7 kalıcı ertele) | Kullanıcı açık talep; pivot kimliği yarım kalır |
| Kör `chat→research` (B/external dahil) | Kanıtlı hata sınıfı: `"chat.completion"` API-contract, `Trendyol-LLM-7B-chat` model-adı, `provider_log` enum bozulur |
| Tek dev PR (BE+FE birlikte) | Yarım-rename = kırık CI; atomik **ayrı** BE/FE PR (BE deploy+migration → sonra FE) |

## Sonuç

- **BE (#1052):** 13 git mv; identifier/endpoint/settings; migration `20260519_0100` (`chat_cache_telemetry`→`research_cache_telemetry` +pkey/fkey, `app_settings chat.*`→`research.*`, `ck_training_samples_task_type` ORM-hizalı). Maskeleme-script + protect-list + ruff F821/grep ile A-leftover=0 doğrulandı.
- **FE (#1053):** route `/app/research`, `components/research/`, tüm `Chat*` identifier/`/research/*` API path (template-literal yakalandı — kritik). ChatGPT/ChatML korundu.
- **Prod E2E doğrulandı (BEN):** tablo/settings/CHECK/constraint `research`; ORM↔tablo eşleşir; L1 v2 + no-thread korundu; `/app/research`→200, `/app/chat`→404.
- **Operasyon dersi:** migration deploy.yml'de sessizce uygulanmadı (kör-nokta) → manuel kurtarıldı + kalıcı fix [[deploy-schema-drift-hardening]] v2.

## İlişkiler

- [[pivot-editorial-research-engine]] — F7 artık TESLİM (ertelenmiş değil)
- [[research-single-turn-invariant]] · [[l1-recency-anchored-context]] — rename davranıştan bağımsız korundu
- [[deploy-schema-drift-hardening]] — rename migration'ı kör-noktayı tetikledi → v2 fix

## Geri alma maliyeti

> Yüksek (rename = geniş). Migration `downgrade()` tam-ters (tablo/constraint/settings); kod git revert. Ama pre-launch dev + atomik PR'lar + prod E2E doğrulandı → geri-alma gereği yok.

## Kaynaklar

- [20260519_0100 migration](apps/api/alembic/versions/20260519_0100_faz7_chat_to_research_rename.py)
- PR #1052 (backend), #1053 (frontend)
