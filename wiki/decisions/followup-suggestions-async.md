---
type: decision
title: "Cevap-sonrası takip soruları: ayrı non-blocking call (tek-yapısal DEĞİL)"
slug: "followup-suggestions-async"
category: "rag"
status: "locked"
decided_on: "2026-05-18"
decided_by: "tech"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "apps/api/app/prompts/chat_followup.py"
  - "apps/api/app/api/app_chat_stream.py§Step-5.5-followup"
  - "GitHub Issue #961 / PR #962"
tags: ["locked-decision", "chat", "ux", "perplexity-parity", "851-family", "888-family"]
aliases: ["takip-sorulari", "followup-questions", "case-2"]
---

# Cevap-sonrası takip soruları: ayrı non-blocking call (tek-yapısal DEĞİL)

> **Karar:** Her **substantive** cevaptan sonra 5 dinamik takip/keşif sorusu, **ayrı non-blocking hafif LLM call** ile üretilir. Cevap-İÇİ "İstersen … yapabilirim" cümlesi YOK — mevcut #851/#958 motor-tonu AYNEN korunur (devam yalnız bu sorularla; editoryal değil "keşif yardımı").
> **Durum:** locked · **Tarih:** 2026-05-18 · #851/#888 ailesi

## Bağlam

Kullanıcı (ekran görüntüsüyle) Perplexity'nin iki davranışını sordu: (1) cevap sonunda "istersen X" proaktif cümlesi, (2) altta 5 takip sorusu. Mimari danışma sonucu kullanıcı kararı: **yalnız (2)** — (1) #851/#958 ("Nodrat sohbet botu/asistan DEĞİL, haber araştırma motoru; öznel/editoryal ton YASAK") ile gerilimde olduğu için **reddedildi**. Takip soruları bu gerilimi YAŞAMAZ (öneri değil keşif yardımı, motor-kimliğiyle uyumlu).

## Karar — neden ayrı call (tek-yapısal-çıktı DEĞİL)

| Yaklaşım | Sonuç |
|---|---|
| **(seçildi) Ayrı non-blocking hafif call** | `final_text→_simulate_stream` düz-metin omurgası DEĞİŞMEZ; #819/#840 yapısal-parse riski (DeepSeek JSON/DSML güvenilmezliği) ana cevaptan **İZOLE**; cevap zaten stream edildi, call kullanıcı okurken arkada → görünür latency yok; hata/timeout → degrade (ana akış sağlam) |
| Tek yapısal çıktı `{answer, followups[]}` | "Şık" ama final_text→_simulate_stream omurgasını kırar + #819/#840 parse riski ana cevaba taşır; net fayda yok |

**Akış (`app_chat_stream.py` Step 5.5):** agentic loop biter → `accumulated` (final_text) stream edildi → **substantive-gate** → `_generate_followups` (asyncio.wait_for timeout) → SSE `followup_suggestions {questions}` → done (`followup_count`) → persist (`messages.followup_suggestions` JSONB).

- **Substantive-gate:** yalnız `sources_considered` dolu (tool çağrıldı) turlar. Selamlama/kimlik/meta (chat_answer §Karar md1, tool YOK → all_sources boş) → takip sorusu ÜRETİLMEZ (anlamsız; Perplexity de böyle).
- **Degrade (#854 yardımcı-call deseni):** timeout/hata caller'da yutulur → `followups=[]`, event yok, ana cevap akışı ETKİLENMEZ.
- **Parse (#819/#840 dersi):** satır-bazlı tolerant — **önekli-öncelik** (LLM sözleşmesi "- ") + **soru-benzeri fallback** (öneksizse soru-işareti/kelimesi şart) + min 10 char (gürültü ele); JSON DEĞİL (küçük/hızlı model JSON güvenilmez). Ayrı call → ham çıktı ana cevaba sızamaz.
- **Model:** `route_for_tier(operation="chat", tier)` (#778 multi-llm) — condense (#854) ile aynı ucuz/hızlı yol.
- **Prompt:** `chat_followup.SYSTEM_PROMPT` + prompts_store `chat_followup` (admin-tunable, #854 deseni) + kod default. Nodrat tonu: kullanıcı-ağzından NESNEL keşif soruları; asistan-jargonu/editoryal/öznel/imza/emoji YASAK (#851/#958).

## Sonuçlar

- 5 `test_chat_followup` (önekli-öncelik / soru-fallback / edge / payload / ton-güvenli) + 58 chat regresyon yeşil. Migration `20260518_0100` additive (messages.followup_suggestions JSONB nullable; geriye-uyumlu).
- **Prod mechanism smoke:** DB-override YOK (prompts_store resolved == kod default 1296=1296; #854/#270 tuzağı yok); gerçek LLM → 5 kaliteli soru ("19 Mayıs'ın resmi tatil olması hangi kanuna dayanıyor?" vb. — kullanıcı-ağzından, nesnel, dedup, jenerik-yok). Migration DB'ye uygulandı (Message.followup_suggestions kolonu canlı). 2-turlu UI (tıkla→yeni mesaj) prompt/frontend-düzeyi → kullanıcı UI re-test.
- Frontend: serializer expose (app_chat/app_me) → `done`→refresh ile `message.followup_suggestions` ChatMessage'da render (kaynaklardan sonra, action öncesi; tıkla→`submitMessage`). Empty-state statik öneriler KORUNUR.

## Alternatifler

| Alternatif | Karar |
|---|---|
| Cevap-içi "istersen X" cümlesi (Case 1) | reddedildi — #851/#958 motor-kimlik gerilimi (kullanıcı kararı) |
| Tek-yapısal-çıktı | reddedildi — düz-metin omurgası + #819/#840 izolasyon kaybı |
| Deterministik/heuristik soru üretimi | reddedildi — bağlam-duyarlı değil, kalitesiz |
| Her cevapta (greeting dahil) | reddedildi — substantive-gate (greeting'de anlamsız) |

## Geri alma

> `_FOLLOWUP_ENABLED=False` (app_chat_stream module-const) → üretim durur, SSE event/persist olmaz; ana akış etkilenmez. Migration kolonu kalır (zararsız nullable). Tek satır.

## İlişkiler

- [[agentic-generate-orchestration]] — Step 5.5 followup üretimi agentic loop sonrası (final_text); orkestrasyon akışının uzantısı
- [[chat-knowledge-evolution]] — #961 satırı + anti-pattern ders #33
- [[self-identity-canonical-prompt]] — #958; "cevap-içi öneri cümlesi YOK" kararı #851/#958 kimlik-tonuyla aynı omurga
- [[multi-llm-per-op-routing]] — #778; ucuz/hızlı tier followup üretiminde
- [[conversational-query-rewriting]] — condense (#833/#854) ile aynı "yardımcı non-blocking call + degrade" deseni

## Kaynaklar

- [Issue #961](https://github.com/selmanays/nodrat/issues/961) · [PR #962](https://github.com/selmanays/nodrat/pull/962)
- [`apps/api/app/prompts/chat_followup.py`](apps/api/app/prompts/chat_followup.py) · [`app_chat_stream.py`](apps/api/app/api/app_chat_stream.py) Step 5.5
- Mimari danışma + Perplexity hibrit analizi (oturum, 2026-05-18)
