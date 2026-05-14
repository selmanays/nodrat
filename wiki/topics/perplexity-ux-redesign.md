---
type: topic
title: "Perplexity-style UX redesign — conversation mode (#793 epic)"
slug: "perplexity-ux-redesign"
status: "in-progress"
created: "2026-05-14"
updated: "2026-05-14"
tags: ["ux", "frontend", "backend", "conversation", "epic"]
aliases: ["conversation-mode", "chat-ux"]
---

# Perplexity-style UX redesign

> **TL;DR:** Mevcut form-based `/app/generate` deneyimi Perplexity tarzı sohbet deneyimine evrilir. Ortada arama input, sol sidebar geçmiş (cevap snippet'leri dahil), expandable "thinking" panel, multi-source yekpare cevap, context-aware follow-up (embedding similarity). X üretim platformu kimliği korunur; sonraki aşama: modal üzerinden bot setup.

## Vizyon

| | Şimdi | Hedef |
|---|---|---|
| Giriş | `/app/generate` form (param dropdown'lar) | `/` ortada input (Perplexity-style) |
| Geçmiş | `/app/generations` (sadece sorular) | Sol sidebar (sorular + cevap snippet'leri) |
| Akış | "Plan hazırlanıyor..." cards | Step-by-step thinking panel (expandable) |
| Cevap | Tek kaynak per paragraf | Multi-source yekpare paragraf |
| Follow-up | Yeni search her seferinde | Embedding similarity → reuse veya new |

## 5-katman mimari

### Katman 1: Database
2 yeni tablo + 1 migration:
- `conversations(id, user_id, title, summary, created_at, updated_at, archived)`
- `messages(id, conversation_id, role, content, generation_id?, sources_used JSONB, sources_considered JSONB, query_embedding vector(1024), thinking_steps JSONB, created_at)`
- `generations` tablosu korundu (backward compat, admin/billing)

### Katman 2: Backend API (yeni endpoint'ler)
```
POST   /chat/conversations              # boş conversation
GET    /chat/conversations              # sidebar list
GET    /chat/conversations/{id}         # full thread
POST   /chat/conversations/{id}/messages # SSE stream + relatedness check + source reuse
PATCH  /chat/conversations/{id}/title
DELETE /chat/conversations/{id}         # archive
```

### Katman 3: Generator prompt — multi-source synthesis
- Tek soru → multi-source yekpare cevap (mevcut: tek-kaynak per paragraf)
- Liste opt-in (sadece explicit istek)
- Minimum 2 kaynak/cümle citation

### Katman 4: Frontend yeni route'lar
- `/` Perplexity-style homepage
- `/c/[conversation_id]` thread view
- ConversationSidebar (sol)
- ThinkingPanel (expandable SSE events)
- `/app/generate` legacy korundu

### Katman 5: SSE thinking events
Yeni event tipleri: `thinking_step`, `source_discovered`, `synthesizing`. Mevcut `chunk` event'i streaming için korundu.

## Sprint sırası

| # | Adım | Süre | PR # |
|---|---|---|---|
| S1 | DB migration + CRUD API | 1 gün | #793 |
| S2 | SSE thinking + context-aware retrieval (relatedness 0.65, source reuse) | 1.5 gün | #794 |
| S3 | Multi-source synthesis prompt | 0.5 gün | #795 |
| S4 | Frontend homepage + sidebar | 2 gün | #796 |
| S5 | Frontend thinking panel + sources | 1 gün | #797 |

## Context-aware follow-up logic

```python
# Pseudo:
prev_msg_embed = last_user_msg.query_embedding
new_query_embed = embed(new_query)
similarity = cosine(prev_msg_embed, new_query_embed)

if similarity > 0.65:  # RELATED
    prev_sources = last_assistant_msg.sources_used + sources_considered
    reusable = filter(source -> relevance(source, new_query) > 0.5, prev_sources)
    if len(reusable) >= 3:
        use chunks = reusable  # tam reuse
    else:
        new_chunks = await hybrid_search_chunks(new_query)
        use_chunks = merge_rrf(reusable, new_chunks)
else:  # NEW TOPIC
    use_chunks = await hybrid_search_chunks(new_query)
```

## Token budget (DeepSeek 64K context)

| Bölüm | Tahmin |
|---|---|
| System prompt | ~2K |
| Conversation context (son 3 mesaj + özet) | ~8K |
| Current chunks (5 article × ~6K) | ~30K |
| Output max | ~2K |
| Safety buffer | ~22K |

## Sustainable approach
- Son 3 mesaj çifti raw (~6K)
- 4+ mesaj varsa: önceki mesajlar → conversation.summary auto-update
- Budget aşılırsa: en eski mesajlar sum'larıyla replace

## Korunan / değişmeyen
- ✅ X içerik üretim kimliği
- ✅ Tüm mevcut UI parametreleri (tone, output_type, style_profile, ...)
- ✅ `/app/generate` legacy form
- ✅ Mevcut RAG pipeline (planner + HyDE + retrieve + critical_entities)
- ✅ Auth + billing + plan tier
- ✅ Bu seansın kazanımları (recall@5 0.818, latency 1s warm)

## Sonraki aşama (bu plan dışı)
- Modal üzerinden bot setup (`/bots/new`): konu + cron + output → autonomous X content
- Conversation ↔ bot köprü: "Bunu otomasyona al" butonu

## Kaynaklar (PR'lar takip için)

- Onay: 2026-05-14 kullanıcı
- Audit (kod temiz, VPS senkron): wiki/log.md 2026-05-14 audit entry
- Refs: gelecek PR'lar #793-#797 burada güncellenir
