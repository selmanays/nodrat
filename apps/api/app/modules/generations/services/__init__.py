"""Module: generations.services

Generations domain service layer (upper layer). Research stream telemetri +
(gelecekte) conversation context + diğer generations iş mantığı.

Public surface (lazy import — paket-init eager değil):
    research_cache_telemetry — record_research_cache_telemetry + classify_segments (#981)
    conversation_context — follow-up relatedness + token budget + windowed context (#793 S2)

T7-4 (2026-05-28): `core/research_cache_telemetry.py` → buraya taşındı
(generations owns ResearchCacheTelemetry observasyonu).
T7-5 (2026-05-28): `core/conversation_context.py` → buraya taşındı
(generations owns Conversation/Message context assembly; read-only).
"""

__all__: list[str] = []
