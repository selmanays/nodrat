"""Conversation context helpers — relatedness + token budget (#793 S2).

Embedding tabanlı follow-up tespiti:
- Yeni user query embed et (bge-m3)
- Conversation'daki son user message'ın embedding'i ile cosine similarity
- Threshold 0.65 üstü → RELATED (önceki kaynakları reuse aday)
- Altı → NEW TOPIC (fresh retrieval)

Token budget:
- Sustainable conversation history için son N mesaj raw + öncesi summarized
- DeepSeek 64K context içinde messages için ~8K budget
"""

from __future__ import annotations

import logging
import math
import re
import struct
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models import Conversation, Message

logger = logging.getLogger(__name__)


# bge-m3 1024 dim × float32 = 4096 byte
EMBED_DIM = 1024
EMBED_BYTES = EMBED_DIM * 4

# Follow-up relatedness threshold (cosine similarity).
# 0.65: deneyim — Türkçe niş entity'lerde "Trump 6 Mayıs" vs "Trump 7 Mayıs"
# benzeri related, "Trump" vs "Karşıyaka" unrelated ayrımı için iyi denge.
# Settings ile runtime override edilebilir: research.followup_relatedness_threshold
DEFAULT_RELATEDNESS_THRESHOLD = 0.65

# Conversation context — son N mesaj raw, öncesi summary.
# 3 mesaj çifti = ~6K token (typical Türkçe news query + 3-paragraf cevap).
# DEEPSEEK 64K içinde rahat.
DEFAULT_RECENT_MESSAGES = 3


def serialize_embedding(vector: list[float]) -> bytes:
    """list[float] → bytes (float32 array). 1024-dim için 4096 byte."""
    if len(vector) != EMBED_DIM:
        raise ValueError(f"Embedding dim must be {EMBED_DIM}, got {len(vector)}")
    return struct.pack(f"{EMBED_DIM}f", *vector)


def deserialize_embedding(raw: bytes | None) -> list[float] | None:
    """bytes → list[float]. None veya yanlış boyut → None."""
    if raw is None or len(raw) != EMBED_BYTES:
        return None
    try:
        return list(struct.unpack(f"{EMBED_DIM}f", raw))
    except struct.error:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity — sıfır vektör koruması."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    limit: int = DEFAULT_RECENT_MESSAGES * 2,  # N çift = 2N mesaj
) -> list[Message]:
    """Conversation'ın son N mesajını çek (created_at ASC sıralı dön).

    User + assistant pair'lar zaman sıralı — context için doğru sıra.
    """
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


async def get_last_user_message(
    db: AsyncSession,
    conversation_id: UUID,
) -> Message | None:
    """Conversation'ın son user mesajı (en son sorulan soru)."""
    return (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_last_assistant_message(
    db: AsyncSession,
    conversation_id: UUID,
) -> Message | None:
    """Conversation'ın son assistant mesajı (last_user için kaynaklar)."""
    return (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def detect_followup_relatedness(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    new_query_embedding: list[float],
    threshold: float = DEFAULT_RELATEDNESS_THRESHOLD,
) -> tuple[bool, float, Message | None]:
    """Yeni query önceki user query ile related mi tespit et.

    Returns:
        (is_related, similarity_score, prev_user_message_or_None)
    """
    prev_user = await get_last_user_message(db, conversation_id)
    if prev_user is None or prev_user.query_embedding is None:
        return False, 0.0, None

    prev_embed = deserialize_embedding(prev_user.query_embedding)
    if prev_embed is None:
        return False, 0.0, prev_user

    sim = cosine_similarity(prev_embed, new_query_embedding)
    is_related = sim >= threshold
    return is_related, sim, prev_user


def build_context_messages(
    messages: list[Message],
    conversation_summary: str | None,
) -> list[dict[str, str]]:
    """Mesajları DeepSeek/OpenAI-format research messages'a çevir.

    Format: [{role, content}, ...] — son N mesaj raw.
    summary varsa system message olarak başa eklenir.

    NOT: Yeni user message buraya dahil DEĞİL — caller ekler.
    """
    result: list[dict[str, str]] = []
    if conversation_summary:
        result.append(
            {
                "role": "system",
                "content": f"Önceki konuşma özeti: {conversation_summary}",
            }
        )
    for m in messages:
        result.append(
            {
                "role": m.role,
                "content": m.content,
            }
        )
    return result


# =============================================================================
# F2b (#1014) — L1 zaman-pencereli görünmez bağlam (YALNIZ condense'i besler;
# asıl cevap prompt'una GİRMEZ). Flag-gated; default kapalı → davranış
# byte-eş (#854). 5-katman kirlilik-koruması (S5):
#   1+3  select_windowed_context: en-dar-pencere-önce cascade; ilgili
#        aday yoksa BOŞ → condense no-op → ham sorgu (standalone/taze
#        kirlenmez). 2: relatedness kapısı (cosine ≥ eşik, mevcut
#        cosine_similarity reuse). 4: l1_accept_rewrite (rewrite-drift
#        reddi — ham sorgudan kopuksa reddet). 5: saf birim testleri.
# =============================================================================


def format_context_block(rows: list[Message], *, include_sources: bool = False) -> str:
    """Mesajları condense `history` string'ine çevir — `_recent_conversation
    _context` ile BİREBİR aynı format (condense sözleşmesi değişmez;
    legacy ve windowed yol aynı formatter'ı kullanır → drift yok).

    include_sources=False (default): önceki cevabın KAYNAK ADLARI
    bağlama EKLENMEZ. Gerekçe: condense yalnız referansı çözmek için
    önceki Q&A KONUSUNA ihtiyaç duyar; kaynak adı ("Forbes Türkiye")
    gerekmez ve LLM'in 0-kaynak durumunda UYDURMA atıf fabriklemesinin
    kanıtlı kaynağıydı (conv 865e36e3 — prod-audit). True yalnız kaynak
    adı bilinçle istenen yerlerde verilir.

    rows: oldest-first sıralı beklenir (caller `.reverse()` yapar).
    """
    lines: list[str] = []
    for m in rows:
        label = "Kullanıcı" if m.role == "user" else "Asistan"
        snippet = (m.content or "")[:500]
        lines.append(f"- {label}: {snippet}")
        if include_sources and m.role == "assistant" and m.sources_used:
            srcs = []
            for s in (m.sources_used or [])[:8]:
                if not isinstance(s, dict):
                    continue
                title = (s.get("title") or "")[:120]
                sname = s.get("source_name") or ""
                if title or sname:
                    srcs.append(f"{sname} — {title}".strip(" —"))
            if srcs:
                lines.append("  (Bu cevabın kaynakları: " + "; ".join(srcs) + ")")
    return "\n".join(lines)


_L1_WORD_RE = re.compile(r"[\wçğıöşüâîûÇĞİÖŞÜ]+", re.UNICODE)

# Türkçe referans-elips imleçleri: bunlardan biri varsa sorgu KENDİ
# öznesini taşımıyor → antecedent (önceki içerikli araştırma) gerekir.
_L1_REFERENTIAL = {
    "bu",
    "şu",
    "o",
    "bunu",
    "şunu",
    "onu",
    "bunları",
    "şunları",
    "onları",
    "bunun",
    "şunun",
    "onun",
    "buna",
    "şuna",
    "ona",
    "bundan",
    "şundan",
    "ondan",
    "bunlar",
    "şunlar",
    "onlar",
    "böyle",
    "şöyle",
    "öyle",
    "bahsettiğin",
    "dediğin",
    "söylediğin",
    "sözünü",
    "aynı",
}
# Türkçe özel-ad sinyali: kesme-ekli token (Trump'ın, İBB'nin), ya da
# baş-harf-DIŞI büyük harfle başlayan token, ya da 2+ basamak sayı/kod.
_L1_APOSTROPHE_RE = re.compile(r"[^\W\d_]+['’][^\W\d_]+", re.UNICODE)
_L1_NUMCODE_RE = re.compile(r"\b\d{2,}\b")


def _has_proper_noun(text: str) -> bool:
    """Sorgu kendi adlandırılmış öznesini taşıyor mu (özel ad/sayı/kod)."""
    s = text or ""
    if _L1_APOSTROPHE_RE.search(s) or _L1_NUMCODE_RE.search(s):
        return True
    toks = s.split()
    for i, t in enumerate(toks):
        if i == 0:
            continue  # cümle başı büyük harf belirsiz (özel ad değil say)
        if t[:1].isalpha() and t[:1].isupper():
            return True
    return False


# #1064 — bare işaret zamiri (`bu/şu/o`) + kendi-yeterli ZAMANSAL deiktik
# isim ("bu hafta", "bu yıl") → dangling DEĞİL (antecedent gerekmez;
# yanlış-pozitif koruması). Soyut referent isimleri (konu/olay/iddia/
# açıklama/durum/haber...) BURADA YOK — onlar dangling KALIR.
_L1_DEICTIC_TEMPORAL = {
    "hafta",
    "yıl",
    "sene",
    "ay",
    "gün",
    "sabah",
    "akşam",
    "gece",
    "öğle",
    "yaz",
    "kış",
    "sezon",
    "dönem",
    "sefer",
    "kez",
    "defa",
}
_L1_BARE_DEMONSTRATIVE = {"bu", "şu", "o"}


def _has_dangling_referent(toks: list[str]) -> bool:
    """Sorguda antecedent (önceki içerikli araştırma) gerektiren — kendi
    içinde çözülemeyen — bir referans imleci var mı?

    Bare `bu/şu/o` + kendi-yeterli zamansal deiktik isim ("bu hafta")
    → dangling DEĞİL. Çekimli/işaret formları (bunu/şunu/bunun/
    bahsettiğin/sözünü/aynı...) ve bare-demonstrative + soyut referent
    ("bu iddia", "bu konuda") → dangling. Saf/DB'siz.
    """
    for i, w in enumerate(toks):
        if w not in _L1_REFERENTIAL:
            continue
        if w in _L1_BARE_DEMONSTRATIVE:
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if nxt in _L1_DEICTIC_TEMPORAL:
                continue  # "bu hafta/bu yıl" → kendi-yeterli, atla
        return True
    return False


def is_standalone_query(text: str) -> bool:
    """S5 Gate-1 — sorgu KENDİ açık öznesini taşıyor mu?

    True (kendine yeterli) → L1 HİÇ kullanılmaz (yeni konu kirlenmez).
    False (dangling referent: çözülemeyen "bu iddia"/zamir, ör. "nerde
    yaptı bu açıklamayı") → antecedent şart → caller en yakın içerikli
    araştırmayı çapa alır. Saf/DB'siz (S5 Gate-5 birim testi).

    #1064 (prod-teşhis conv quirky-gates): dangling-referent kontrolü
    özel-ad'dan ÖNCE — özel-ad AKTÖRdür, eşzamanlı "bu iddia"yı ÇÖZMEZ
    ("Özgür Özel bu iddiayı" → standalone DEĞİL; eskiden özel-ad
    kısa-devre yapıp L1'i atlıyordu → "hangi iddia?" bağlam kaybı).
    """
    toks = [w.lower() for w in _L1_WORD_RE.findall(text or "")]
    if not toks:
        return True
    if _has_dangling_referent(toks):
        return False
    if _has_proper_noun(text):
        return True
    # özel ad yok & dangling yok → 4+ kelime self-contained, ≤3 elips
    return len(toks) > 3


async def _research_messages(
    db: AsyncSession,
    user_rows: list[Message],
) -> list[Message]:
    """Çapa user mesaj(lar)ının conversation'larındaki TÜM mesajları
    (her conv = 1 araştırma = [user, assistant], #1048) oldest-first
    döndür. Pencere dökümü YOK — yalnız çapa araştırmanın Q&A'i.
    """
    conv_ids: list[UUID] = []
    for m in user_rows:
        if m.conversation_id not in conv_ids:
            conv_ids.append(m.conversation_id)
    if not conv_ids:
        return []
    stmt = (
        select(Message)
        .where(Message.conversation_id.in_(conv_ids))
        .order_by(Message.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def select_windowed_context(
    db: AsyncSession,
    *,
    conv_id: UUID,
    user_id: UUID,
    exclude_msg_id: UUID,
    new_query_text: str,
    user_scope: bool,
    windows_hours: tuple[int, ...] = (6, 24, 72),
    max_msgs: int = 8,
) -> list[Message]:
    """S5 Gate-1 (standalone-yeterlilik) + recency-anchored antecedent.

    Yeni sorgu kendi açık öznesini taşıyorsa (is_standalone_query) →
    BOŞ (L1 yok; yeni konu KİRLENMEZ). Aksi halde (zamir/elips, ör.
    "nerde yaptı bu açıklamayı") → 6s→24s→72s pencere cascade'inde
    EN SON İÇERİKLİ (standalone) araştırmayı ÇAPA al; onun [user,
    assistant] Q&A'ini condense'e ver.

    COSINE YOK (kanıtlı kök neden): belirsiz takip, kendisine en çok
    benzeyen ÖNCEKİ BELİRSİZ TAKİBE yakındır — atıf yaptığı içerikli
    sorguya değil. Çapa = en yakın İÇERİKLİ araştırma (REFERANS
    YAKINLIĞI ilkesi); önceki belirsiz/başarısız takipler çapa OLAMAZ
    (kendileri standalone değil → atlanır). user_scope=True
    cross-conversation (pivot zorunlu). Çıktı oldest-first;
    format_context_block sözleşmesi değişmez.
    """
    if not new_query_text or is_standalone_query(new_query_text):
        return []

    def _scoped(stmt):
        if user_scope:
            return stmt.join(
                Conversation,
                Conversation.id == Message.conversation_id,
            ).where(Conversation.user_id == user_id)
        return stmt.where(Message.conversation_id == conv_id)

    now = datetime.now(UTC)
    for w in windows_hours:  # en yakın/dar pencere önce
        cutoff = now - timedelta(hours=w)
        stmt = (
            _scoped(
                select(Message).where(
                    Message.id != exclude_msg_id,
                    Message.role == "user",
                    Message.created_at >= cutoff,
                )
            )
            .order_by(Message.created_at.desc())
            .limit(max_msgs)
        )
        cands = list((await db.execute(stmt)).scalars().all())
        for m in cands:  # en yeni → eski; ilk İÇERİKLİ = çapa
            if is_standalone_query(m.content):
                return await _research_messages(db, [m])
    return []


def l1_accept_rewrite(raw: str, rewritten: str) -> bool:
    """Gate 4 — rewrite-drift reddi (saf; embedding çağrısı YOK).

    condense çıktısı ham sorguyla HİÇ ortak içerik-token'ı paylaşmıyorsa
    (≥3 harf) = konu tamamen kaymış → REDDET (caller ham sorguyu
    kullanır). Sinyal yetersizse (kısa) muhafazakâr: KABUL (mevcut
    davranışı bozma). Yalnız L1 açıkken uygulanır.
    """
    rt = {t.lower() for t in _L1_WORD_RE.findall(raw or "") if len(t) > 2}
    wt = {t.lower() for t in _L1_WORD_RE.findall(rewritten or "") if len(t) > 2}
    if not rt or not wt:
        return True
    return len(rt & wt) > 0


__all__ = [
    "DEFAULT_RECENT_MESSAGES",
    "DEFAULT_RELATEDNESS_THRESHOLD",
    "EMBED_BYTES",
    "EMBED_DIM",
    "build_context_messages",
    "cosine_similarity",
    "deserialize_embedding",
    "detect_followup_relatedness",
    "format_context_block",
    "get_last_assistant_message",
    "get_last_user_message",
    "get_recent_messages",
    "is_standalone_query",
    "l1_accept_rewrite",
    "select_windowed_context",
    "serialize_embedding",
]
