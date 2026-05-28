"""Module: conversations

Layer: kernel-data (chat conversation + message ORM; research-only #800 sonrası
sohbet primary veri modeli).

Public API (lazy import — paket-init eager değil):
    `app.modules.conversations.models` — Conversation, Message (T8-10: 2026-05-28)

Boundary: alt-katman veri modülü; generations/sft/api OKUR (import-linter'da
forbidden değil). conversations herhangi bir upper domain'e import ETMEZ.

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3 / §2.4
- wiki/topics/t8-model-relocation-mini-plan.md (T8-10)
"""

# T8-10 (v95): NEW module scaffold; lazy __init__ (route yok, yalnız models).
__all__: list[str] = []
