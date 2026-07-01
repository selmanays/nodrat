"""Claim-level grounding eval harness (#1805).

Cevabı atomik iddialara böler ve her iddiayı kaynak metne karşı
``SUPPORTED | INFERRED | FABRICATED`` olarak yargılar; ``grounding_rate`` +
``hallucination_rate`` üretir. Bu, ``docs/engineering/prompt-contracts.md``
§6.3 (``check_hallucination``) sözleşmesinin runtime implementasyonudur —
``framework.run_hallucination_traps`` STUB'ının docstring'inde (framework.py)
işaret edilen "``..._runtime``" runner.

TASARIM KISITI (#1076 dersi — KRİTİK)
-------------------------------------
Bu harness bir **offline ÖLÇÜM aracıdır, runtime guard DEĞİL** — canlı cevabı
asla değiştirmez, yalnız skorlar. #1067/#1076'de runtime LLM-verifier
(``_verify_primary_grounding``) prod'da 4/8 yanlış-pozitif verip kaldırıldı
("genel-amaçlı LLM faithfulness-judgment calibration-fragile"). Bu harness o
hatayı **tekrarlamamak** için:

1. **multi-claim modelleme** — her iddia ayrı yargılanır (v1'in "tek-iddia"
   varsayımını kırar; aggregate/çok-kaynak özetleri tek-iddia sanılmaz);
2. **adversarial çok-lens oylama** — her iddia birden çok bakış açısıyla
   yargılanır, oylar toplanır;
3. **düşük-mutabakat → ``manual_review``** — belirsizlikte FABRICATED'a
   ZORLAMA yok (v1 FP kaynağı), nötr ortaya (INFERRED) düşer + insan işaretlenir;
4. **ölçüm-only** — skor üretir, cevaba/pipeline'a dokunmaz.

Saf çekirdek (``split_sentences_fallback`` + ``aggregate_votes`` +
``build/score``) LLM'siz test edilebilir; LLM ``splitter``/``judge`` sarmalları
``@pytest.mark.eval`` opt-in koşumda (``NODRAT_GROUNDING_EVAL=1``) çalışır.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Etiketler (prompt-contracts.md §6.3 ile birebir)
# ---------------------------------------------------------------------------
SUPPORTED = "SUPPORTED"  # iddia kaynakta doğrudan var
INFERRED = "INFERRED"  # kaynaktan makul çıkarılabilir
FABRICATED = "FABRICATED"  # kaynakta yok, çıkarılamaz → halüsinasyon
_VALID_LABELS = frozenset({SUPPORTED, INFERRED, FABRICATED})

# Oy mutabakatı bu eşiğin altındaysa iddia insan-incelemesine düşer.
# 3 lens'te 2/3 (=0.66) altı → lensler net anlaşamadı.
MANUAL_REVIEW_CONFIDENCE = 0.67

# Adversarial oylama lensleri — her biri aynı iddiayı farklı katılıkta yargılar.
DEFAULT_LENSES: tuple[str, ...] = ("literal", "inference", "skeptic")


# ---------------------------------------------------------------------------
# Veri tipleri
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Claim:
    """Cevaptan çıkarılmış tek atomik iddia."""

    text: str
    index: int


@dataclass
class ClaimVerdict:
    """Bir iddianın çok-lens oylaması sonrası kararı."""

    claim: Claim
    label: str  # SUPPORTED | INFERRED | FABRICATED
    confidence: float  # 0..1 — oy mutabakatı
    votes: list[str] = field(default_factory=list)  # her lens'in ham oyu
    rationale: str = ""

    @property
    def needs_review(self) -> bool:
        """Düşük mutabakat VEYA halüsinasyon → insan bakmalı."""
        return self.confidence < MANUAL_REVIEW_CONFIDENCE or self.label == FABRICATED


@dataclass
class GroundingReport:
    """Bir cevabın tam grounding raporu."""

    answer: str
    verdicts: list[ClaimVerdict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.verdicts)

    def _rate(self, label: str) -> float:
        if not self.verdicts:
            return 0.0
        return sum(1 for v in self.verdicts if v.label == label) / len(self.verdicts)

    @property
    def grounding_rate(self) -> float:
        """SUPPORTED iddia oranı."""
        return self._rate(SUPPORTED)

    @property
    def inferred_rate(self) -> float:
        return self._rate(INFERRED)

    @property
    def hallucination_rate(self) -> float:
        """FABRICATED iddia oranı (prompt-contracts §6.4 halu_rate)."""
        return self._rate(FABRICATED)

    @property
    def faithfulness(self) -> float:
        """1 - halu_rate (prompt-contracts §6.4)."""
        return 1.0 - self.hallucination_rate

    @property
    def manual_review(self) -> bool:
        """Herhangi bir iddia insan-incelemesi gerektiriyor mu?"""
        return any(v.needs_review for v in self.verdicts)

    @property
    def unsupported(self) -> list[ClaimVerdict]:
        """FABRICATED veya düşük-güven iddialar (raporun 'dikkat' listesi)."""
        return [v for v in self.verdicts if v.label == FABRICATED or v.needs_review]

    def summary_lines(self) -> list[str]:
        """İnsan-okunur özet (stdout/pano)."""
        lines = [
            f"grounding_rate={self.grounding_rate:.2%}  "
            f"inferred={self.inferred_rate:.2%}  "
            f"halu_rate={self.hallucination_rate:.2%}  "
            f"faithfulness={self.faithfulness:.2%}  "
            f"manual_review={self.manual_review}  claims={self.total}",
        ]
        for v in self.unsupported:
            lines.append(
                f"  ⚠ [{v.label} conf={v.confidence:.2f} votes={','.join(v.votes)}] "
                f"{v.claim.text[:120]}"
            )
        return lines


# ---------------------------------------------------------------------------
# Saf çekirdek — LLM'siz, deterministik, CI-test edilebilir
# ---------------------------------------------------------------------------
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CITATION_RE = re.compile(r"\[\d+\]|\[[A-Za-zÇĞİÖŞÜçğıöşü ]+\]")


def split_sentences_fallback(text: str) -> list[str]:
    """LLM claim-split başarısızsa deterministik cümle/madde bölme.

    Markdown madde işaretlerini soyar, atıf token'larını (``[1]``) temizler,
    cümle sınırında böler. Çok kısa parçaları atar.
    """
    parts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line:
            continue
        for sent in _SENT_SPLIT_RE.split(line):
            cleaned = _CITATION_RE.sub("", sent).strip()
            if len(cleaned) > 3:
                parts.append(cleaned)
    return parts


def format_context(context_articles: Sequence[dict[str, Any]]) -> str:
    """Kaynak makaleleri judge'a verilecek tek metne çevirir.

    Farklı fixture şemalarını (golden ``clean_text_excerpt`` / retrieval
    ``chunk_text``) toleranslı okur.
    """
    blocks: list[str] = []
    for i, art in enumerate(context_articles, 1):
        title = art.get("title") or art.get("article_title") or ""
        source = art.get("source_name") or art.get("source_slug") or ""
        published = art.get("published_at") or "bilinmiyor"
        body = art.get("clean_text_excerpt") or art.get("chunk_text") or art.get("text") or ""
        blocks.append(f"[{i}] {source} — {title} (yayın tarihi: {published})\n{body}".strip())
    return "\n\n---\n\n".join(blocks)


def aggregate_votes(votes: Sequence[str]) -> tuple[str, float]:
    """Çok-lens oylarını tek etikete + mutabakat güvenine indir.

    #1076 dersi: belirsizlikte (beraberlik) FABRICATED'a ZORLAMA yok — bu v1'in
    yanlış-pozitif kaynağıydı. Beraberlikte nötr ortaya (INFERRED) düşülür ve
    düşük güven ``manual_review``'a taşınır (insan karar verir).

    Returns:
        (label, confidence) — confidence = kazanan_oy / geçerli_oy_sayısı.
    """
    counts = Counter(v for v in votes if v in _VALID_LABELS)
    if not counts:
        return INFERRED, 0.0

    ranked = counts.most_common()
    best_n = ranked[0][1]
    tied = [label for label, n in ranked if n == best_n]

    if len(tied) > 1:
        # Belirsizlik → nötr orta; needs_review zaten confidence ile flag'lenir.
        best_label = INFERRED
    else:
        best_label = tied[0]

    confidence = best_n / sum(counts.values())
    return best_label, confidence


# Enjekte edilebilir protokoller — test/mock için LLM'den bağımsız.
ClaimSplitter = Callable[[str], list[str]]
ClaimJudge = Callable[[str, str, str], str]  # (claim_text, context_text, lens) -> label


def run_grounding_report(
    answer: str,
    context_articles: Sequence[dict[str, Any]],
    *,
    splitter: ClaimSplitter,
    judge: ClaimJudge,
    lenses: Sequence[str] = DEFAULT_LENSES,
) -> GroundingReport:
    """LLM'siz orkestratör — ``splitter`` ve ``judge`` enjekte edilir.

    Gerçek koşum ``run_llm_grounding_report`` üzerinden; bu fonksiyon aynı
    çekirdek mantığı mock'lanabilir hâlde tutar (harness'in kendi doğruluğunu
    LLM olmadan kanıtlamak — #1076 self-calibration disiplini).
    """
    context_text = format_context(context_articles)
    claims = [Claim(text=t, index=i) for i, t in enumerate(splitter(answer)) if t.strip()]

    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        votes = [judge(claim.text, context_text, lens) for lens in lenses]
        label, confidence = aggregate_votes(votes)
        verdicts.append(
            ClaimVerdict(claim=claim, label=label, confidence=confidence, votes=list(votes))
        )
    return GroundingReport(answer=answer, verdicts=verdicts)


# ---------------------------------------------------------------------------
# LLM sarmalı — provider gerektirir (@pytest.mark.eval / scheduled)
# ---------------------------------------------------------------------------
_SPLIT_SYSTEM = (
    "Bir metni bağımsız, atomik olgusal iddialara bölen bir ayrıştırıcısın. "
    "Her iddia tek bir doğrulanabilir olgu içermeli. Yorum/görüş cümlelerini "
    "de iddia say. Sadece JSON döndür."
)
_SPLIT_USER = (
    'Aşağıdaki cevabı atomik iddialara böl. JSON: {{"claims": ["...", "..."]}}\n\nCEVAP:\n{answer}'
)

_LENS_INSTRUCTION = {
    "literal": (
        "Katı ol: iddia SADECE kaynakta LİTERAL geçiyorsa SUPPORTED. En küçük "
        "çıkarım gerekiyorsa INFERRED. Kaynakta hiç yoksa FABRICATED."
    ),
    "inference": (
        "Makul çıkarıma izin ver: kaynaktan mantıken çıkıyorsa INFERRED (ya da "
        "açıkça yazılıysa SUPPORTED). Yalnızca kaynakla ÇELİŞEN veya hiçbir "
        "dayanağı olmayan iddia FABRICATED."
    ),
    "skeptic": (
        "Şüpheci ol: iddianın kaynakta desteklendiğini kanıtlayamıyorsan "
        "FABRICATED'a yaklaş. ANCAK birden çok olayı/kaynağı özetleyen bir "
        "cevabı tek-iddia sanma; her iddiayı yalnız kendi dayanağına göre yargıla."
    ),
}

_JUDGE_SYSTEM = (
    "Bir olgu-denetçisisin. Verilen KAYNAK metne göre tek bir İDDİA'yı "
    "SUPPORTED / INFERRED / FABRICATED olarak etiketle. Kaynağı aşan bilgi "
    "kullanma. Sadece JSON döndür."
)
_JUDGE_USER = (
    "{lens_instruction}\n\n"
    "KAYNAK:\n{context}\n\n"
    "İDDİA: {claim}\n\n"
    'JSON: {{"label": "SUPPORTED|INFERRED|FABRICATED", "rationale": "kısa"}}'
)


def _safe_json(text: str) -> dict[str, Any]:
    """LLM çıktısından JSON çıkar (ham metne gömülü olsa bile)."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def default_provider_and_model() -> tuple[Any, str]:
    """Registry'den chat provider + default model (free tier → DeepSeek)."""
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()
    provider = registry.route_for_tier(operation="chat", tier="free")
    model = getattr(provider, "_default_model", None) or "deepseek-v4-flash"
    return provider, model


async def llm_split_claims(
    answer: str, *, provider: Any, model: str, max_claims: int = 24
) -> list[str]:
    """LLM ile cevabı atomik iddialara böl; başarısızsa cümle-fallback."""
    from app.providers.base import Message

    result = await provider.generate_text(
        messages=[
            Message(role="system", content=_SPLIT_SYSTEM),
            Message(role="user", content=_SPLIT_USER.format(answer=answer)),
        ],
        model=model,
        temperature=0.0,
        max_tokens=1500,
        json_mode=True,
    )
    data = _safe_json(result.text)
    raw = data.get("claims")
    claims = (
        [c.strip() for c in raw if isinstance(c, str) and c.strip()]
        if isinstance(raw, list)
        else []
    )
    return (claims or split_sentences_fallback(answer))[:max_claims]


async def llm_judge_claim(
    claim_text: str, context_text: str, lens: str, *, provider: Any, model: str
) -> tuple[str, str]:
    """Tek iddiayı tek lens ile yargıla → (label, rationale)."""
    from app.providers.base import Message

    result = await provider.generate_text(
        messages=[
            Message(role="system", content=_JUDGE_SYSTEM),
            Message(
                role="user",
                content=_JUDGE_USER.format(
                    lens_instruction=_LENS_INSTRUCTION.get(lens, _LENS_INSTRUCTION["literal"]),
                    context=context_text,
                    claim=claim_text,
                ),
            ),
        ],
        model=model,
        temperature=0.0,
        max_tokens=300,
        json_mode=True,
    )
    data = _safe_json(result.text)
    label = str(data.get("label", "")).strip().upper()
    if label not in _VALID_LABELS:
        label = INFERRED  # parse belirsizliği → nötr, needs_review'a düşer
    return label, str(data.get("rationale", ""))


async def run_llm_grounding_report(
    answer: str,
    context_articles: Sequence[dict[str, Any]],
    *,
    provider: Any = None,
    model: str | None = None,
    lenses: Sequence[str] = DEFAULT_LENSES,
) -> GroundingReport:
    """Gerçek LLM koşumu: claim-split → çok-lens judge → skorla.

    Aynı iddianın lensleri eşzamanlı yargılanır. Provider verilmezse registry'den
    free-tier chat provider'ı alınır (DeepSeek).
    """
    import asyncio

    if provider is None:
        provider, model = default_provider_and_model()
    assert model is not None

    context_text = format_context(context_articles)
    claim_texts = await llm_split_claims(answer, provider=provider, model=model)
    claims = [Claim(text=t, index=i) for i, t in enumerate(claim_texts)]

    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        lens_results = await asyncio.gather(
            *(
                llm_judge_claim(claim.text, context_text, lens, provider=provider, model=model)
                for lens in lenses
            )
        )
        labels = [label for label, _ in lens_results]
        label, confidence = aggregate_votes(labels)
        verdicts.append(
            ClaimVerdict(
                claim=claim,
                label=label,
                confidence=confidence,
                votes=labels,
                rationale=lens_results[0][1] if lens_results else "",
            )
        )
    return GroundingReport(answer=answer, verdicts=verdicts)
