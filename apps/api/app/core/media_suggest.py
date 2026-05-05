"""Image suggestion for generations (#305 MVP-1.4 PR-5).

Process & discard mimarisinde her ArticleImage'ın metadata'sı vardır:
    - vlm_caption (Türkçe görsel açıklaması)
    - depicts (politik figür/obje listesi, JSONB)
    - alt_text (HTML <img alt>)
    - ocr_text (görsel üstündeki yazı)

`suggest_image_for_post()` üretilen post text'iyle bu metadata arasında
lexical (Jaccard) similarity hesaplar ve en uygun görseli döndürür.

LLM çağrısı yapmaz — cost-free, latency <10ms, açıklanabilir.

docs/engineering/architecture.md §3.1 (image_vlm_queue + suggest)
docs/engineering/data-model.md §3.5 (article_images.depicts)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article, ArticleImage


logger = logging.getLogger(__name__)


# =============================================================================
# Tokenization (Türkçe odaklı)
# =============================================================================

# Türkçe + İngilizce yaygın stopword'ler — generation post'larında bilgisel
# olmayan kelimeler. Genişletilebilir.
_STOPWORDS = frozenset(
    {
        # tr
        "ve",
        "ile",
        "için",
        "olarak",
        "olan",
        "bir",
        "bu",
        "şu",
        "o",
        "da",
        "de",
        "ki",
        "mi",
        "mı",
        "mu",
        "mü",
        "ama",
        "fakat",
        "ancak",
        "veya",
        "yani",
        "çok",
        "daha",
        "en",
        "her",
        "hiç",
        "ne",
        "nasıl",
        "neden",
        "niçin",
        "kim",
        "kime",
        "kimin",
        "var",
        "yok",
        "oldu",
        "olur",
        "olacak",
        "olmuş",
        "değil",
        "gibi",
        "kadar",
        "böyle",
        "şöyle",
        "öyle",
        "ben",
        "sen",
        "biz",
        "siz",
        "onlar",
        # en
        "the",
        "a",
        "an",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "and",
        "or",
        "but",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "this",
        "that",
        "as",
        "by",
    }
)


_TOKEN_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    """Türkçe-friendly tokenizer — lowercase + stopword filter + len>=3."""
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    # 'i' lower mapping farkı — `İ` → `i̇` olabilir, sorun yaratıyor; basit lower yeterli.
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    if not union:
        return 0.0
    return len(intersection) / len(union)


# =============================================================================
# Result schema
# =============================================================================


@dataclass(frozen=True)
class SuggestedImage:
    image_id: UUID
    article_id: UUID
    original_url: str
    vlm_caption: str | None
    depicts: list[str] | None
    alt_text: str | None
    score: float
    reason: str  # "lexical match: X/Y tokens" — debugging


# =============================================================================
# Public API
# =============================================================================


async def suggest_image_for_post(
    db: AsyncSession,
    *,
    post_text: str,
    article_ids: Iterable[UUID],
    min_confidence: float = 0.15,
    boost_depicts: float = 0.20,
) -> SuggestedImage | None:
    """Verilen post text'i için en uygun görseli öner.

    Args:
        db: Async DB session
        post_text: Üretilen post metni (X post body)
        article_ids: Generation context'indeki article id'ler
        min_confidence: Eşik (Jaccard score). Altındaki match'ler reddedilir.
        boost_depicts: Eğer post text'inde herhangi bir `depicts` entity'si
            geçerse skoru bu kadar artır (entity match güçlü sinyal).

    Returns:
        En yüksek skorlu SuggestedImage, veya threshold altındaysa None.
    """
    article_ids_list = [a for a in article_ids if a is not None]
    if not article_ids_list:
        return None

    post_tokens = _tokenize(post_text)
    if not post_tokens:
        return None

    # Yalnız processed status'lu görseller — VLM metadata gerek
    stmt = select(ArticleImage).where(
        ArticleImage.article_id.in_(article_ids_list),
        ArticleImage.status == "processed",
    )
    result = await db.execute(stmt)
    images = list(result.scalars().all())

    if not images:
        return None

    best: SuggestedImage | None = None
    for img in images:
        # Image metadata'dan token seti
        img_text_parts: list[str] = []
        if img.vlm_caption:
            img_text_parts.append(img.vlm_caption)
        if img.alt_text:
            img_text_parts.append(img.alt_text)
        if img.ocr_text:
            img_text_parts.append(img.ocr_text)

        img_tokens = _tokenize(" ".join(img_text_parts))
        depicts_set = set()
        if img.depicts:
            for entity in img.depicts:
                depicts_set.update(_tokenize(str(entity)))

        # Birleşik token seti
        all_img_tokens = img_tokens | depicts_set
        if not all_img_tokens:
            continue

        score = _jaccard(post_tokens, all_img_tokens)

        # Depicts entity boost — politik figür/obje post'ta geçiyorsa kuvvetli sinyal
        if depicts_set and post_tokens & depicts_set:
            score += boost_depicts
            score = min(score, 1.0)

        intersection_count = len(post_tokens & all_img_tokens)
        if score < min_confidence:
            continue

        if best is None or score > best.score:
            best = SuggestedImage(
                image_id=img.id,
                article_id=img.article_id,
                original_url=img.original_url,
                vlm_caption=img.vlm_caption,
                depicts=list(img.depicts) if img.depicts else None,
                alt_text=img.alt_text,
                score=round(score, 4),
                reason=f"lexical match: {intersection_count} token",
            )

    return best


async def article_ids_from_urls(
    db: AsyncSession, *, urls: Iterable[str]
) -> list[UUID]:
    """Source URL listesinden Article id'lerini çek (canonical_url eşleşmesi).

    Generate response'unda `sources: [{title, source, url}]` döner — bu URL'lere
    karşılık gelen article'ları bulup ID'lerini suggest_image'a iletmek için.
    """
    url_list = [u for u in urls if u]
    if not url_list:
        return []
    stmt = select(Article.id).where(Article.canonical_url.in_(url_list))
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)
