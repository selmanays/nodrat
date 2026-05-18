"""Backfill chunk keywords + question_keywords for all existing chunks (#778 Faz 3).

Tüm article_chunks rows için LLM çağrısı yaparak keywords/question_keywords
doldurur. RagFlow adaptation: BM25 retrieval'da yüksek ağırlık.

Çalıştırma:
    docker cp /tmp/backfill_chunk_keywords.py nodrat-api:/tmp/
    docker exec nodrat-api python /tmp/backfill_chunk_keywords.py
    docker exec nodrat-api python /tmp/backfill_chunk_keywords.py --limit 50  # test

Cost (~12K chunk):
    - DeepSeek: ~$2.40 (12000 × $0.0002)
    - Gemma free: $0 (admin /settings'ten llm.routing.ner='gemini' set et)
Süre:
    - DeepSeek: ~3 saat (12K × 0.9s)
    - Gemma free: ~14 saat (rate limit 15 req/min)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path("/app")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.cost_tracker import track_provider_call
from app.core.db import get_session_factory
from app.core.prompts_store import prompts_store
from app.prompts.chunk_keywords import SYSTEM_PROMPT as DEFAULT_KEYWORDS_PROMPT
from app.providers.base import (
    Message,
    ProviderRateLimitError,
)
from app.providers.registry import (
    bootstrap_default_providers,
    registry,
    resolve_chat_provider,
)
from sqlalchemy import text as sa_text


def _extract_json(text: str) -> str:
    """JSON'u response'tan çıkar — Gemma 4 CoT reasoning + sonda JSON pattern'ini handle eder.

    Sıra:
    1) Code fence ```json ... ``` varsa içeriği al
    2) Yoksa son `{` ile dengeleyici `}` arasını bul (last balanced object)
    3) Hiçbiri yoksa text'i olduğu gibi döndür (DeepSeek temiz JSON üretir)
    """
    text = text.strip()

    # 1) Code fence
    if "```" in text:
        # Find first code fence content
        parts = text.split("```", 2)
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith("json\n") or inner.startswith("json\r"):
                inner = inner[5:]
            inner = inner.strip().rstrip("`").strip()
            if inner.startswith(("{", "[")):
                return inner

    # 2) Last balanced JSON object/array — Gemma CoT için
    if text.startswith(("{", "[")):
        return text
    for opener, closer in (("{", "}"), ("[", "]")):
        last_close = text.rfind(closer)
        if last_close < 0:
            continue
        # Find matching opener (count brackets backwards)
        depth = 0
        start = -1
        for i in range(last_close, -1, -1):
            if text[i] == closer:
                depth += 1
            elif text[i] == opener:
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start >= 0:
            return text[start : last_close + 1]

    return text


def _strip_fence(text: str) -> str:
    """Geriye dönük uyumluluk için ince wrapper — _extract_json kullan."""
    return _extract_json(text)


def _coerce_dict(parsed):
    """Provider'a göre {...} veya [{...}] dönebilir → tek dict'e indirge.

    DeepSeek: {"keywords": [...], "questions": [...]}
    Gemini/Gemma: bazen [{"keywords": [...], ...}] (tek elemanlı array)
    """
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    return parsed if isinstance(parsed, dict) else {}


async def main(limit: int | None = None) -> None:
    bootstrap_default_providers()
    factory = get_session_factory()

    async with factory() as db:
        provider = await resolve_chat_provider(db, op_name="ner", tier="free")
        prompt = await prompts_store.get(db, "chunk_keywords", DEFAULT_KEYWORDS_PROMPT)

        # Count remaining
        total_row = (await db.execute(
            sa_text(
                "SELECT COUNT(*) FROM article_chunks "
                "WHERE keywords IS NULL OR keywords_updated_at IS NULL"
            )
        )).scalar_one()
        print(f"📊 Bekleyen chunk: {total_row}", flush=True)
        print(f"⚙️  Provider: {provider.name}", flush=True)

    success = 0
    failed = 0
    t0 = time.perf_counter()
    batch_size = 50
    offset = 0

    async with factory() as db:
        while True:
            limit_clause = f"LIMIT {batch_size}"
            if limit and offset >= limit:
                break

            rows = (await db.execute(
                sa_text(f"""
                    SELECT id::text, chunk_text FROM article_chunks
                    WHERE keywords IS NULL OR keywords_updated_at IS NULL
                    ORDER BY created_at DESC
                    {limit_clause}
                """)
            )).mappings().all()

            if not rows:
                break

            for r in rows:
                chunk_id = r["id"]
                chunk_text = (r["chunk_text"] or "")[:3000]
                if len(chunk_text) < 100:
                    failed += 1
                    continue

                try:
                    async with track_provider_call(
                        db=db,
                        provider=provider.name,
                        operation="chunk_keywords",
                    ) as tracker:
                        result = await provider.generate_text(
                            messages=[
                                Message(role="system", content=prompt),
                                Message(role="user", content=chunk_text),
                            ],
                            max_tokens=250,
                            temperature=0.1,
                            json_mode=True,
                        )
                        tracker.record(
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            cached_tokens=getattr(result, "cached_input_tokens", 0),
                            model=result.model,
                            cost_usd=float(result.cost_usd or 0),
                        )

                    data = _coerce_dict(json.loads(_strip_fence(result.text)))
                    keywords = data.get("keywords") or []
                    questions = data.get("questions") or []
                    keywords = [
                        str(k).strip().lower()
                        for k in keywords[:5]
                        if isinstance(k, str) and 1 <= len(str(k).strip()) <= 80
                    ]
                    questions = [
                        str(q).strip()
                        for q in questions[:3]
                        if isinstance(q, str) and 5 <= len(str(q).strip()) <= 200
                    ]

                    await db.execute(
                        sa_text("""
                            UPDATE article_chunks
                            SET keywords = :kw,
                                question_keywords = :qkw,
                                keywords_updated_at = NOW()
                            WHERE id = :cid
                        """),
                        {
                            "kw": keywords if keywords else None,
                            "qkw": questions if questions else None,
                            "cid": chunk_id,
                        },
                    )
                    await db.commit()
                    success += 1
                except ProviderRateLimitError as exc:
                    # Tüm modeller (cascade) tükendi — DeepSeek'e geç ve sürdür
                    if provider.name != "deepseek" and "deepseek" in registry._providers:
                        print(
                            f"\n⚠️  {provider.name} quota exhausted ({exc}) — "
                            f"switching to deepseek for remaining chunks\n",
                            flush=True,
                        )
                        provider = registry._providers["deepseek"]
                        # Bu chunk'ı yeniden dene (DeepSeek ile) — failed sayma
                        try:
                            async with track_provider_call(
                                db=db,
                                provider=provider.name,
                                operation="chunk_keywords",
                            ) as tracker:
                                result = await provider.generate_text(
                                    messages=[
                                        Message(role="system", content=prompt),
                                        Message(role="user", content=chunk_text),
                                    ],
                                    max_tokens=250,
                                    temperature=0.1,
                                    json_mode=True,
                                )
                                tracker.record(
                                    input_tokens=result.input_tokens,
                                    output_tokens=result.output_tokens,
                                    cached_tokens=getattr(result, "cached_input_tokens", 0),
                                    model=result.model,
                                    cost_usd=float(result.cost_usd or 0),
                                )
                            data = _coerce_dict(json.loads(_strip_fence(result.text)))
                            keywords = data.get("keywords") or []
                            questions = data.get("questions") or []
                            keywords = [
                                str(k).strip().lower()
                                for k in keywords[:5]
                                if isinstance(k, str) and 1 <= len(str(k).strip()) <= 80
                            ]
                            questions = [
                                str(q).strip()
                                for q in questions[:3]
                                if isinstance(q, str) and 5 <= len(str(q).strip()) <= 200
                            ]
                            await db.execute(
                                sa_text("""
                                    UPDATE article_chunks
                                    SET keywords = :kw,
                                        question_keywords = :qkw,
                                        keywords_updated_at = NOW()
                                    WHERE id = :cid
                                """),
                                {
                                    "kw": keywords if keywords else None,
                                    "qkw": questions if questions else None,
                                    "cid": chunk_id,
                                },
                            )
                            await db.commit()
                            success += 1
                        except Exception as inner:
                            failed += 1
                            print(f"  ⚠️ deepseek retry fail chunk={chunk_id}: {inner}", flush=True)
                            continue
                    else:
                        failed += 1
                        print(f"  ⚠️ rate-limit fail chunk={chunk_id}: {exc}", flush=True)
                        continue
                except Exception as exc:
                    failed += 1
                    print(f"  ⚠️ fail chunk={chunk_id}: {exc}", flush=True)
                    continue

                offset += 1
                if offset % 50 == 0:
                    elapsed = time.perf_counter() - t0
                    rate = offset / elapsed
                    print(
                        f"  ⏳ {offset}/{total_row} — success={success} failed={failed} "
                        f"rate={rate:.1f}/s",
                        flush=True,
                    )

                if limit and offset >= limit:
                    break

            if not rows:
                break

    elapsed = time.perf_counter() - t0
    print(f"\n✅ Done in {elapsed:.0f}s — success={success} failed={failed}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
