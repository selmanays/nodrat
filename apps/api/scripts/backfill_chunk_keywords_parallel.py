"""Paralel chunk keywords backfill (#778 hızlandırma).

asyncio.gather + Semaphore ile N concurrent worker. Single-thread script
~16 chunk/dk yaparken paralel 5 worker ~80-100/dk hedefler.

Kullanım:
    docker exec -d nodrat-api bash -c \
      'nohup python /app/scripts/backfill_chunk_keywords_parallel.py --workers 5 > /tmp/bp.log 2>&1 &'
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

from sqlalchemy import text as sa_text

from app.core.db import get_session_factory
from app.core.cost_tracker import track_provider_call
from app.core.prompts_store import prompts_store
from app.providers.base import Message
from app.providers.registry import bootstrap_default_providers, resolve_chat_provider
from app.prompts.chunk_keywords import SYSTEM_PROMPT as DEFAULT_KEYWORDS_PROMPT


def _extract_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```", 2)
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith(("json\n", "json\r")):
                inner = inner[5:]
            inner = inner.strip().rstrip("`").strip()
            if inner.startswith(("{", "[")):
                return inner
    if text.startswith(("{", "[")):
        return text
    for opener, closer in (("{", "}"), ("[", "]")):
        last_close = text.rfind(closer)
        if last_close < 0:
            continue
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


def _coerce_dict(parsed):
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    return parsed if isinstance(parsed, dict) else {}


async def process_chunk(
    *,
    chunk_id: str,
    chunk_text: str,
    provider,
    prompt: str,
    factory,
    sem: asyncio.Semaphore,
    counter: dict,
):
    """Tek chunk için: LLM call + DB update. Kendi session'ını açar."""
    async with sem:
        try:
            async with factory() as db:
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

                data = _coerce_dict(json.loads(_extract_json(result.text)))
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
            counter["success"] += 1
        except Exception as exc:
            counter["failed"] += 1
            counter["last_error"] = str(exc)[:200]


async def main(workers: int = 5, batch_size: int = 100, limit: int | None = None) -> None:
    bootstrap_default_providers()
    factory = get_session_factory()

    async with factory() as db:
        provider = await resolve_chat_provider(db, op_name="ner", tier="free")
        prompt = await prompts_store.get(db, "chunk_keywords", DEFAULT_KEYWORDS_PROMPT)
        total_row = (await db.execute(
            sa_text(
                "SELECT COUNT(*) FROM article_chunks "
                "WHERE keywords IS NULL OR keywords_updated_at IS NULL"
            )
        )).scalar_one()
        print(f"📊 Bekleyen chunk: {total_row}", flush=True)
        print(f"⚙️  Provider: {provider.name}", flush=True)
        print(f"⚡ Workers: {workers}", flush=True)

    counter = {"success": 0, "failed": 0, "last_error": ""}
    sem = asyncio.Semaphore(workers)
    t0 = time.perf_counter()
    offset_done = 0

    while True:
        if limit and offset_done >= limit:
            break

        # Fresh session for selecting next batch
        async with factory() as db:
            rows = (await db.execute(sa_text(f"""
                SELECT id::text, chunk_text FROM article_chunks
                WHERE keywords IS NULL OR keywords_updated_at IS NULL
                ORDER BY created_at DESC
                LIMIT {batch_size}
            """))).mappings().all()

        if not rows:
            break

        # Hazırla
        tasks = []
        for r in rows:
            cid = r["id"]
            txt = (r["chunk_text"] or "")[:3000]
            if len(txt) < 100:
                counter["failed"] += 1
                continue
            tasks.append(process_chunk(
                chunk_id=cid,
                chunk_text=txt,
                provider=provider,
                prompt=prompt,
                factory=factory,
                sem=sem,
                counter=counter,
            ))

        # Paralel çalıştır
        await asyncio.gather(*tasks, return_exceptions=True)
        offset_done += len(rows)

        elapsed = time.perf_counter() - t0
        rate = counter["success"] / elapsed if elapsed > 0 else 0
        print(
            f"  ⏳ done={offset_done} success={counter['success']} "
            f"failed={counter['failed']} rate={rate:.2f}/s "
            f"last_error={counter['last_error'][:80]}",
            flush=True,
        )

    elapsed = time.perf_counter() - t0
    print(f"\n✅ Done in {elapsed:.0f}s — success={counter['success']} failed={counter['failed']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(workers=args.workers, batch_size=args.batch_size, limit=args.limit))
