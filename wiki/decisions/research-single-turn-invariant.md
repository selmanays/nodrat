---
type: decision
title: "Tek-tur invariantı — 1 conversation = 1 araştırma (backend-enforced)"
slug: "research-single-turn-invariant"
status: "locked"
decided_on: "2026-05-19"
decided_by: "founder"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1045/#1046 (frontend davranış), #1048 (backend 409 guard)"
  - "apps/api/app/api/app_research_stream.py (post_research_message guard)"
tags: ["locked-decision", "pivot", "no-thread", "architecture"]
aliases: ["no-thread", "single-turn", "1-conv-1-arastirma", "davranissal-pivot"]
---

# Tek-tur invariantı — 1 conversation = 1 araştırma (backend-enforced)

> **Karar:** Her kullanıcı sorgusu **bağımsız bir araştırma**dır: ayrı conversation, tam 1 user + 1 assistant mesajı. Thread (çok-turlu birikim) hem frontend (yeni conversation/sorgu) hem **backend invariantı** (dolu conversation'a 2. POST → 409) ile YAPISAL olarak imkânsız.
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam

"UI değişmez" yanlış-yorumlandı: kullanıcı **layout/bileşenler sabit, DAVRANIŞ değişir** demek istedi ("backend nasıl çalışıyorsa frontend o davranışı göstersin"). Pivot'un özü: sohbet-thread değil, her sorgu editöryal bağımsız araştırma.

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Mevcut chat-thread (sorgu aynı conv'a eklenir) | Kullanıcı açıkça reddetti — pivot'un anti-tezi; "sohbetin devamı gibi geldi" |
| Yalnız frontend-enforced (yeni conv/sorgu) | Yeterli değil; herhangi client dolu conv'a POST'layıp thread kurabilir → veri-katmanı garantisi yok (kullanıcı standardı: "DB katmanından itibaren") |
| Faz 7 fiziksel rename ile birlikte zorla | Ayrıştırıldı: invariant ad-bağımsız; rename ayrı ([[faz7-chat-research-rename]]) |

## Sonuç

- **Frontend (#1045/#1046):** her sorgu/takip → `createResearchConversation()` + yeni `/app/research/{id}`; conversation = tam 1 Q&A. Hotfix #1046: aynı dinamik route param-değişimi remount etmediği için `submittedInitial` ref'i sıfırlanır (boş-sayfa bug'ı).
- **Backend (#1048):** `post_research_message` ownership sonrası — conversation'da zaten mesaj varsa **409 RESEARCH_ALREADY_COMPLETED**. Flag `research.single_turn_enforced` default **True** (pivot standardı; runtime kapatılabilir → legacy thread). Cevap-üretim çekirdeği DOKUNULMADI.
- Oturumlar-arası bağlam görünmez şekilde backend'in işi: [[l1-recency-anchored-context]] (condense) — thread DAYATMAZ.
- Prod-kanıt: ardışık iki sorgu → 2 ayrı conversation, her biri tam 2 mesaj; `effective_query` provenans assistant satırında.

## İlişkiler

- [[pivot-editorial-research-engine]] — bu invariant pivot davranışının çekirdeği
- [[l1-recency-anchored-context]] — bağımsız conversation'lar arası bağlam (user-scope L1)
- [[faz7-chat-research-rename]] — invariant rename'den bağımsız çözüldü

## Geri alma maliyeti

> `research.single_turn_enforced=false` → backend guard no-op (legacy thread davranışı). Frontend her sorguda yeni conversation açmaya devam eder (ayrı revert). Additive; mevcut conversation/messages şeması değişmedi.

## Kaynaklar

- [app_research_stream.py](apps/api/app/api/app_research_stream.py) — `post_research_message` 409 guard
- PR #1045 (davranış), #1046 (boş-sayfa hotfix), #1048 (backend invariant)
