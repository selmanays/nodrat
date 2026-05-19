---
type: decision
title: "Retrieval şeffaflığı — gözlem-only thinking_step (cascade'in kendisi DEĞİL)"
slug: "research-retrieval-transparency"
status: "locked"
decided_on: "2026-05-19"
decided_by: "founder"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1060 (issue #1059)"
  - "apps/api/app/api/app_research_stream.py (_log_step ek aşamalar)"
  - "apps/web/src/components/research/ThinkingPanel.tsx (PHASE_LABEL/ICON)"
tags: ["locked-decision", "pivot", "observability", "ux", "thinking-step"]
aliases: ["thinking-step-transparency", "retrieval-transparency", "asama-seffaflik"]
---

# Retrieval şeffaflığı — gözlem-only thinking_step (cascade'in kendisi DEĞİL)

> **Karar:** Cevap üretilirken gösterilen `ThinkingPanel`'e, **gerçekten gerçekleşen** retrieval aşamaları **gözlem-only** `_log_step` event'leri olarak yansıtılır. Davranış/akış/cevap/citation invariantı DEĞİŞMEZ. Kullanıcının tarif ettiği "ilk chunk → devamı → yeni search" **3-kademeli cascade'in kendisi BU karara dahil DEĞİL** — eval-gate'li ayrı iş; bu yalnız var olan aşama şeffaflığı.
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam

Kullanıcı: "cevap üretilirken gösterdiğimiz arayüzde retrieval sürecini mevcutla uyumlu gösterebilir miyiz?" Mevcut: backend yalnız `context_check`/`query_rewrite`/`tool_use` yayıyordu; `ThinkingPanel.tsx` PHASE_LABEL yalnız `context_check/planner/retrieve/generating` içeriyordu → `query_rewrite`/`tool_use` ham snake_case görünüyor, `planner/retrieve` hiç yayılmıyor (ölü etiket). Süreç kullanıcıya opak.

İki katman ayrıştırıldı (dürüst kapsam): (1) UI mekanizması zaten var ve genişletilebilir; (2) kullanıcının asıl tarif ettiği kademeli cascade orkestrasyonu **yok** ([[research-cited-only-hard-invariant]] Fix B′ force-retrieval var; derin chunk-scoped T1/T2 cascade eval-gate'li ertelendi). Olmayan bir cascade "gösterilemez".

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| 3-kademeli cascade'i şimdi kur + göster | Retrieval kalite makinesine dokunur; kanıtsız; eval-gate'li AYRI iş (S6/benchmark riski) |
| Hiç gösterme (mevcut opak panel) | Editöryal motor = kaynaklı/şeffaf konumlandırma; "kara kutu" güveni düşürür |
| Yeni SSE event tipi / şema değişikliği | Gereksiz; `thinking_step` JSONB freeform, enum yok → additive yeterli, geri-uyumlu |
| Ham detayları (chunk ID/skor) göster | Gizlilik + UX; kullanıcı-okunur Türkçe etiket yeterli |

## Sonuç (additive, gözlem-only — locked)

- Backend `app_research_stream.py` — 6 ek `_log_step` (yalnız gözlem; kontrol-akışı/cevap DEĞİŞMEZ): `retrieval_forced` (Fix B′ zorunlu retrieval), `grounding_retry` (C1 backstop düzeltici tur), `tool_result` (search_news turu başına bulunan kaynak sayısı), `citation_filter` (cited-only N/M kullanıldı), `cited_only_refused` (#1058 0-kaynak hard-refuse), `generating` (yanıt yazımı — panelde etiket vardı hiç yayılmıyordu).
- Frontend `ThinkingPanel.tsx` — PHASE_LABEL/ICON yayılan TÜM fazları kapsar (`query_rewrite`→"Bağlamlı sorgu" vb.); bilinmeyen faz zaten ham string'e düşer (geri-uyumlu). `thinking_steps` JSONB freeform/enum-suz → geçmiş persist mesajlar da düzgün render.
- **İleriye uyumlu:** panel artık tamamen aşama-güdümlü → kullanıcının istediği 3-kademeli cascade ileride (eval-gate'li) kurulduğunda her aşama kendi `_log_step`'ini yayar, **ekstra UI işi gerekmeden** otomatik görünür.
- **Prod-kanıt (Playwright):** bağlamlı takip → panel açılınca 🔗 Bağlam kontrolü · 🧭 Bağlamlı sorgu · 🎯 Kaynak araması zorunlu · 🔍 Kaynak araması · 📄 Kaynak sonucu: 9 kaynak bulundu · ✍️ Yanıt yazılıyor · ✅ Atıf doğrulama: 2/9 — ham snake_case YOK; cevap hâlâ kaynaklı (davranış invariantı korundu; API eval golden-set yeşil).

## İlişkiler

- [[research-cited-only-hard-invariant]] — gözlemlenen aşamalar (Fix B′ `retrieval_forced`, hard-refuse `cited_only_refused`) bu kararın invariantları
- [[agentic-generate-orchestration]] — `_log_step`'lerin yayıldığı agentic loop (C1 backstop = `grounding_retry`)
- [[pivot-editorial-research-engine]] — şeffaflık editöryal motor konumlandırmasının parçası

## Geri alma maliyeti

> Tek `git revert` (additive, gözlem-only, flag yok). Geri-alma şeffaflığı kaldırır, davranışı etkilemez. `thinking_steps` şeması/event sözleşmesi değişmedi.

## Kaynaklar

- [app_research_stream.py](apps/api/app/api/app_research_stream.py) — 6 ek `_log_step` (gözlem-only)
- [ThinkingPanel.tsx](apps/web/src/components/research/ThinkingPanel.tsx) — PHASE_LABEL/ICON tam kapsam
- PR #1060 (issue #1059)
