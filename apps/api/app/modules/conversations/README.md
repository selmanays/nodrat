# `modules/conversations/`

**Layer:** kernel-data — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3 / §2.4.

**Status:** **T8-10 (2026-05-28)** ile aktive edildi (NEW module scaffold) — `Conversation` + `Message` ORM modelleri `app/models/conversation.py`'den buraya taşındı. #800 S1B sonrası sohbet (conversations + messages) araştırma akışının primary veri modeli.

## Layout

```
modules/conversations/
├── __init__.py   Module facade (lazy; kernel-data docstring, route yok)
├── models.py     Conversation + Message ORM (T8-10: app/models/conversation.py'den taşındı)
└── README.md     Bu dosya
```

## Migration history

- 2026-05-28: **T8-10** — `Conversation` + `Message` ORM modelleri `app/models/conversation.py`'den
  `models.py`'e taşındı (NEW conversations modülü; T8 harvest 5.). T7-5 ile conversation_context
  service zaten generations/services'e taşınmıştı → core/ consumer temiz; model gelince Conv/Message
  modüler düzende. **relationship() back_populates internal** (Conversation.messages ↔ Message.conversation;
  2 class birlikte → mapper-safe). 9 dosya: scaffold (`__init__.py` lazy + README) + git mv + facade
  re-export + 8 caller flip (DIRECT path): `api/_research_stream_context` + `api/app_me` + `api/app_research`
  + `api/app_research_stream` + `modules/generations/services/conversation_context` (T7-5) +
  `modules/generations/tasks/cluster_assigner` + `modules/sft/admin/routes` + `modules/sft/tasks/sft_curator`.
  import-linter 16/16 (conversations NEW modül; generations/sft/api → conversations LEGAL — alt-katman veri).
  ORM birebir (conversations/messages tabloları + index + relationship AYNEN); no migration, no schema change.
  Bkz. [[t8-model-relocation-mini-plan]].

## Boundary

conversations = alt-katman veri modülü (Conversation/Message). Upper layer'lar (generations, sft, api)
OKUR; conversations hiçbir domain'e import etmez. import-linter'da henüz source-contract YOK (Phase 6
genişlemesinde conversations route/service eklenirse boundary contract tasarlanır).
