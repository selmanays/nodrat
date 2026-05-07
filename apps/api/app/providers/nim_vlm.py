"""NIM VLM provider — image caption + OCR + depicts (#300 MVP-1.4 PR-3).

Llama 4 Maverick (multimodal multilingual) — NIM ücretsiz tier üzerinden
chat completions API ile image input. Image bytes asla persistent storage'a
yazılmaz: temp download → VLM call → JSON parse → discard.

Modeller:
    - meta/llama-4-maverick-17b-128e-instruct (default, multilingual)
    - google/paligemma (alternatif, vision-specialized smaller)

NIM endpoint: /chat/completions (OpenAI-compatible vision input)
Free tier rate limit: ~40 RPM (35 RPM safety margin önerilir)

docs/engineering/architecture.md §4
docs/engineering/data-model.md §3.5 (article_images vlm_caption/ocr_text/depicts)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings


logger = logging.getLogger(__name__)


NIM_VLM_DEFAULT_MODEL = "meta/llama-4-maverick-17b-128e-instruct"
NIM_VLM_FALLBACK_MODEL = "google/paligemma"

VLM_PROMPT = (
    "Bu görseli kısa Türkçe analiz et ve SADECE JSON döndür: "
    '{"caption": "1-2 cümle Türkçe betimleme", '
    '"ocr_text": "görseldeki metin (yoksa boş)", '
    '"depicts": ["tasvir edilen kişi/obje listesi"]}. '
    "Markdown veya açıklama EKLEME, sadece geçerli JSON.\n\n"
    "BAĞLAM KAYNAKLARI (güvenilirlik sırasına göre):\n"
    "1. 'Görsel altı açıklama' — varsa EN GÜVENİLİR kaynaktır. Editör "
    "tarafından bu görselin ne olduğunu açıklamak için yazılmıştır. "
    "Caption'da bu bilgiyi kullan ve görseli o şekilde betimle "
    "(örn: 'Bluescat oyunundan bir sahne' diyorsa, caption'a 'Bluescat "
    "oyunundan bir sahne' yansıt; sadece 'iki kişi' deme).\n"
    "2. 'HTML alt metni' — editör yazımı, ama haber içeriği/alıntı olabilir "
    "(görseldeki kişiyle direkt ilgili olmayabilir). Doğrulama referansı.\n"
    "3. 'Haber başlığı' — genel bağlam, görseli bire bir betimlemez.\n\n"
    "KİŞİ TANIMA — DİKKAT:\n"
    "- ÖNCE görseli kendi bilgi tabanınla tanı.\n"
    "- Sen görselden kişiyi TANIYORSAN ve bağlam destekliyorsa → caption'da "
    "ismi kullan.\n"
    "- Sen TANIMIYORSAN: alt/başlıkta isim olsa bile caption'da KULLANMA. "
    "'Bir adam/kadın/kişi' gibi genel ifade kullan.\n"
    "- depicts listesine SADECE görselde net gördüğün ve tanıdığın "
    "kişi/objeyi ekle. Tahmin yapma, alt'tan isim kopyalama.\n"
    "- YANLIŞ KİŞİ atfetmek, 'bir kişi' demekten DAHA KÖTÜDÜR."
)


@dataclass
class VLMResult:
    """NIM VLM call sonucu — DB'ye yazılacak metadata."""

    caption: str
    """Türkçe akıllı caption (1-2 cümle)."""
    ocr_text: str
    """Görseldeki metin (OCR çıktısı)."""
    depicts: list[str]
    """Tasvir edilen kişi/obje listesi."""
    model_used: str
    latency_ms: float
    raw_response: str = ""
    """Debug için ham model çıktısı (JSON parse edilmediğinde)."""


class VLMError(Exception):
    """VLM call başarısız."""


class VLMRateLimitError(VLMError):
    """NIM rate limit aşıldı (429)."""


class VLMTimeoutError(VLMError):
    """NIM timeout."""


class NimVLMProvider:
    """NIM VLM provider — image bytes → caption/OCR/depicts JSON."""

    # Registry/audit name (#364 — provider_call_logs için)
    name = "nim_vlm"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.nim_api_key.get_secret_value()
        self._base_url = (base_url or settings.nim_base_url).rstrip("/")
        self._default_model = default_model or NIM_VLM_DEFAULT_MODEL
        self._timeout = timeout
        self._max_retries = max_retries

        if not self._api_key:
            raise ValueError("NIM_API_KEY env değişkeni gerekli (NimVLMProvider).")

    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        alt_text: str = "",
        article_title: str = "",
        figure_caption: str = "",
        model: str | None = None,
    ) -> VLMResult:
        """Image bytes → caption + OCR + depicts.

        Args:
            image_bytes: Geçici download edilmiş image bytes (max 5 MB).
            mime_type: Content-type — 'image/jpeg', 'image/png', 'image/webp'.
            alt_text: HTML alt attribute (editör yazımı, context).
            article_title: Article başlığı (context).
            figure_caption: <figure> içindeki açıklama metni (figcaption veya
                figure içi text — Evrensel `<span class="small-title">` gibi).
                Editör yazımıdır, görselin doğrudan açıklamasıdır.
            model: Override default model.

        Returns:
            VLMResult — caption, ocr_text, depicts, latency.

        Raises:
            VLMError: Model çağrısı başarısız veya JSON parse fail.
            VLMRateLimitError: 429.
            VLMTimeoutError: Network timeout.
        """
        chosen_model = model or self._default_model

        # Image base64 encode (data URI)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime_type};base64,{image_b64}"

        # Prompt context — editör tarafından yazılmış metinler ipucu olarak
        # eklenir. Sıralama önemli: figure_caption en güvenilir (görseli
        # doğrudan tarif eder), sonra alt_text, en son article_title (genel
        # bağlam).
        context_parts = []
        if figure_caption:
            context_parts.append(f"Görsel altı açıklama: {figure_caption}")
        if alt_text:
            context_parts.append(f"HTML alt metni: {alt_text}")
        if article_title:
            context_parts.append(f"Haber başlığı: {article_title}")
        context_str = ("\n" + "\n".join(context_parts)) if context_parts else ""

        prompt = VLM_PROMPT + context_str

        payload = {
            "model": chosen_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        },
                    ],
                }
            ],
            "max_tokens": 512,
            "temperature": 0.2,
            "stream": False,
        }

        start = time.perf_counter()
        attempt = 0
        max_attempts = self._max_retries + 1
        last_error: Exception | None = None

        while attempt < max_attempts:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code == 429:
                    raise VLMRateLimitError(f"NIM rate limit: {response.text[:200]}")
                if response.status_code >= 500:
                    raise VLMError(
                        f"NIM 5xx (attempt {attempt}/{max_attempts}): "
                        f"status={response.status_code}"
                    )
                if response.status_code >= 400:
                    raise VLMError(
                        f"NIM error: status={response.status_code} body={response.text[:300]}"
                    )
                break
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                if attempt < max_attempts:
                    await asyncio.sleep(2.0 * attempt)
                    continue
                if isinstance(exc, httpx.TimeoutException):
                    raise VLMTimeoutError(f"NIM VLM timeout after {self._timeout}s") from exc
                raise VLMError(f"NIM VLM network error: {exc}") from exc
            except VLMError:
                if attempt < max_attempts:
                    await asyncio.sleep(2.0 * attempt)
                    continue
                raise
        else:
            # Loop tüm attempts tükendi (theoretical, last_error ile yakalanır)
            raise VLMError(f"NIM VLM all retries failed: {last_error}")

        latency_ms = (time.perf_counter() - start) * 1000

        # Parse response
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise VLMError(f"NIM VLM unexpected response: {exc}") from exc

        # JSON parse from content (model bazen markdown code block ekleyebilir)
        json_str = _extract_json(content)
        if not json_str:
            logger.warning(
                "NIM VLM JSON parse fail model=%s content=%s",
                chosen_model,
                content[:200],
            )
            return VLMResult(
                caption=content[:500].strip(),
                ocr_text="",
                depicts=[],
                model_used=chosen_model,
                latency_ms=latency_ms,
                raw_response=content[:500],
            )

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(
                "NIM VLM invalid JSON model=%s json=%s", chosen_model, json_str[:200]
            )
            return VLMResult(
                caption=json_str[:500].strip(),
                ocr_text="",
                depicts=[],
                model_used=chosen_model,
                latency_ms=latency_ms,
                raw_response=json_str[:500],
            )

        depicts_raw = parsed.get("depicts", [])
        if not isinstance(depicts_raw, list):
            depicts_raw = []

        return VLMResult(
            caption=str(parsed.get("caption", ""))[:1000].strip(),
            ocr_text=str(parsed.get("ocr_text", ""))[:5000].strip(),
            depicts=[str(d)[:200] for d in depicts_raw[:20]],
            model_used=chosen_model,
            latency_ms=latency_ms,
        )


def _extract_json(content: str) -> str:
    """Model output'undan JSON object'i çıkar (markdown code block tolere)."""
    content = content.strip()
    # ```json ... ``` veya ``` ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence:
        return fence.group(1)
    # İlk { ile son } arası
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        return content[first_brace : last_brace + 1]
    return ""


def build_nim_vlm_provider(timeout: float | None = None) -> NimVLMProvider | None:
    """Factory — NIM_API_KEY varsa provider döner, yoksa None.

    Args:
        timeout: HTTP timeout (s). None ise class default (30s) kullanılır.
            Async bootstrap (#273) settings_store'dan okuyup geçirir.
    """
    settings = get_settings()
    if not settings.nim_api_key.get_secret_value():
        return None
    if timeout is not None:
        return NimVLMProvider(timeout=timeout)
    return NimVLMProvider()
