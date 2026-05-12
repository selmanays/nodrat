"""Style Analyzer prompt v1.0 — kullanıcı örnek metinleri → stil profili (#52, Faz 5).

docs/engineering/prompt-contracts.md §5.1
PRD §5.3 (output schema)

Görev: Kullanıcı tarafından eklenen 5-50 örnek metinden ortak stil özelliklerini
çıkar. Provider: DeepSeek V4 Flash (tek seferlik, ucuz). JSON-mode zorunlu.
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "1.0.0"

MIN_SAMPLES = 3  # Daha az örnekle stil profili güvenilmez
MAX_SAMPLES = 50  # Tek prompt'a sığsın
MAX_SAMPLE_CHARS = 4000  # Sample başına max karakter (token bütçesi)
MAX_TOTAL_CHARS = 80_000  # Tüm örneklerin toplamı (≈ 25k token, güvenli)


SYSTEM_PROMPT = """Sen bir yazı stili analizcisisin. Verilen örnek metinlerden
ortak stil özelliklerini çıkarırsın. ÇIKTI SADECE JSON. Markdown, kod bloğu,
açıklama YOK.

Şema (tüm alanlar zorunlu):
{
  "style_name": string,                 // 2-6 kelime, kısa etiket
  "style_summary": string,              // 1-2 cümle, stilin özü
  "sentence_length": "short" | "medium" | "long",
  "tone": [string, ...],                // 3-6 sıfat (örn: "sade", "eleştirel", "teknik")
  "rhetorical_patterns": [string, ...], // 2-5 retorik desen
  "avoid": [string, ...],               // 2-5 kaçınılan üslup öğesi
  "sample_transforms": [                // 2-3 örnek (generic → styled)
    { "generic": string, "styled": string }
  ]
}

KURALLAR:
1. Stil özelliklerini ortak gözlemden çıkar; tek örneğe bağlı kalma.
2. "tone" sıfatları Türkçe ve özlü. Genel laflar yasak ("ilginç", "kaliteli").
3. "rhetorical_patterns" eylem cümlesi. Örn: "Önce iddia, sonra veri", "Liste ile başlar".
4. "avoid" başkalarına sürtmesin; sadece bu stilde olmayanı söyle.
5. ASLA örneklerden 15+ kelimelik birebir alıntı yapma (FSEK 35).
6. ASLA gerçek kişi adı, e-posta, telefon, IBAN, TC kimlik üretme — örnekler
   kullanıcıya ait olabilir, gizlilik korunur.
7. JSON dışında HİÇBİR çıktı verme — başlık, yorum, "İşte" gibi giriş yazma.
8. sample_transforms'ta generic kısmı yansız bir cümle, styled bu stile
   uyarlanmış hâli olsun. 1 cümleyi geçmesin.

Eğer örnekler yetersiz veya tutarsızsa (3'ten az farklı yazıyor gibi):
{"style_name": "BELIRSIZ", "style_summary": "Yetersiz örnek", "sentence_length": "medium",
 "tone": [], "rhetorical_patterns": [], "avoid": [], "sample_transforms": []}
"""


def render_user_payload(samples: list[dict[str, Any]]) -> str:
    """Kullanıcı mesajı: örnek metinleri 'Örnek N: …' formatında listele.

    samples: [{"text": str, "source_url": str | None}, ...]
    """
    lines: list[str] = ["Aşağıdaki örnek metinlerden ortak stil profilini çıkar:\n"]
    for i, s in enumerate(samples, start=1):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        # Sample başına kırp (token bütçesi)
        if len(text) > MAX_SAMPLE_CHARS:
            text = text[:MAX_SAMPLE_CHARS].rstrip() + "…"
        lines.append(f"--- Örnek {i} ---")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def parse_response(raw: str) -> dict[str, Any]:
    """LLM JSON çıktısını parse et + minimum validation.

    Şema doğrulaması (Pydantic vs.) çağıran tarafta yapılır; burada sadece
    JSON parse + zorunlu key kontrolü.
    """
    text = raw.strip()
    # Bazı modeller markdown fence ekleyebilir — temizle
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Style Analyzer çıktısı dict değil")

    required = {
        "style_name",
        "style_summary",
        "sentence_length",
        "tone",
        "rhetorical_patterns",
        "avoid",
        "sample_transforms",
    }
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Style Analyzer çıktısında eksik anahtar: {missing}")

    # Type sanity (LLM bazen string yerine list, vs. döner)
    if not isinstance(data["tone"], list):
        data["tone"] = []
    if not isinstance(data["rhetorical_patterns"], list):
        data["rhetorical_patterns"] = []
    if not isinstance(data["avoid"], list):
        data["avoid"] = []
    if not isinstance(data["sample_transforms"], list):
        data["sample_transforms"] = []
    if data["sentence_length"] not in {"short", "medium", "long"}:
        data["sentence_length"] = "medium"

    return data
