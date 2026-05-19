"""Regression: cited-only `sources_used` cite biçim toleransı (#audit).

Eski filtre `s["cite"] in accumulated` substring'di → `[1,2]` / `[1, 2]`
/ `[1-3]` / `[1–3]` biçiminde cite edilen kaynak DÜŞÜYORDU (provenance
eksik raporlama; C1/güven sinyali). Sayı-temelli ayrıştırma tüm
biçimleri tolere etmeli.

app_research_stream import edilince `pyotp` (Docker-only) gerekiyor; bu
yüzden saf yardımcılar (`_cited_numbers`, `_cite_to_int` + iki regex)
AST ile kaynaktan ÇIKARILIP exec edilir — gerçek kodun mantığı test
edilir, ağır import zinciri olmadan.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "app" / "api" / "app_research_stream.py"
_WANT = {
    "_CITED_GROUP_RE",
    "_CITE_RANGE_RE",
    "_cited_numbers",
    "_cite_to_int",
    "_is_substantive",
    "_parse_faithfulness_verdict",
}


def _load_real_helpers() -> dict:
    tree = ast.parse(_SRC_PATH.read_text(encoding="utf-8"))
    picked: list[ast.stmt] = []
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in _WANT for t in node.targets)
        ) or (isinstance(node, ast.FunctionDef) and node.name in _WANT):
            picked.append(node)
    assert len({getattr(n, "name", None) for n in picked} & _WANT) >= 2, (
        "helper'lar bulunamadı — substring filtre geri mi geldi?"
    )
    mod = ast.Module(body=picked, type_ignores=[])
    ns: dict = {"re": re}
    exec(compile(mod, "<research_helpers>", "exec"), ns)  # noqa: S102
    return ns


_NS = _load_real_helpers()
_cited_numbers = _NS["_cited_numbers"]
_cite_to_int = _NS["_cite_to_int"]
_is_substantive = _NS["_is_substantive"]
_parse_faithfulness_verdict = _NS["_parse_faithfulness_verdict"]


def test_single_and_multidigit():
    assert _cited_numbers("[1] ve [12]") == {1, 12}


def test_comma_forms_not_dropped():
    # Eski substring bug: bunlar DÜŞÜYORDU
    assert _cited_numbers("kaynak [1,2]") == {1, 2}
    assert _cited_numbers("[1, 2] ayrı") == {1, 2}


def test_range_forms_hyphen_and_endash():
    assert _cited_numbers("[1-3]") == {1, 2, 3}
    assert _cited_numbers("[1–3] endash") == {1, 2, 3}


def test_adjacent_and_legacy_w_prefix():
    assert _cited_numbers("[1][2]") == {1, 2}
    assert _cited_numbers("[W1] eski") == {1}


def test_no_citation_empty():
    assert _cited_numbers("hiç cite yok") == set()
    assert _cited_numbers("") == set()


def test_cite_to_int():
    assert _cite_to_int("[12]") == 12
    assert _cite_to_int("[W3]") == 3
    assert _cite_to_int(None) is None
    assert _cite_to_int("yok") is None


def test_filter_semantics_match_by_number():
    """[1,2] cite → cite='[2]' kaynak DÜŞMEMELİ (eski bug)."""
    accumulated = "Cevap [1,2] böyle."
    cited = _cited_numbers(accumulated)
    sources = [{"cite": "[1]"}, {"cite": "[2]"}, {"cite": "[3]"}]
    used = [s for s in sources if _cite_to_int(s["cite"]) in cited]
    assert used == [{"cite": "[1]"}, {"cite": "[2]"}]


def test_provider_contract_tools_param_present():
    """nim_chat + gemini generate_text base.py sözleşmesine uymalı
    (tools/tool_choice kabul et — LSP; gelecekte research→non-DeepSeek)."""
    api = _SRC_PATH.parents[1] / "providers"
    for prov in ("nim_chat.py", "gemini.py"):
        src = (api / prov).read_text(encoding="utf-8")
        assert "tools: list[dict] | None = None" in src, f"{prov}: tools param yok"
        assert 'tool_choice: str = "auto"' in src, f"{prov}: tool_choice yok"


# --- #1058 cited-only HARD guard çekirdeği: _is_substantive (saf) ---


def test_is_substantive_hallucination_answer_is_substantive():
    """Prod-audit conv 865e36e3 — uydurma '[Forbes Türkiye]' cevabı
    UZUN/olgusal → substantive → 0-kaynakta guard tetiklenmeli."""
    hallu = (
        "Trump'ın İran saldırısını erteleme açıklaması Forbes "
        "Türkiye'nin aktardığına göre yapıldı. Haberde Trump'ın, "
        "Körfez ülkelerinin talebiyle planlanan askeri saldırıyı "
        "durdurduğu belirtiliyor. [Forbes Türkiye]"
    )
    assert _is_substantive(hallu) is True


def test_is_substantive_identity_meta_short_excluded():
    """Selamlama/kimlik/meta KISA → substantive değil → guard
    etkilemez (meşru kaynaksız yanıt)."""
    assert _is_substantive("Merhaba! Ben Nodrat.") is False
    assert _is_substantive("Türkçe gündem araştırma motoruyum.") is False


def test_is_substantive_empty_and_whitespace():
    assert _is_substantive("") is False
    assert _is_substantive("   \n  ") is False
    assert _is_substantive(None) is False  # type: ignore[arg-type]


def test_is_substantive_threshold_boundary():
    assert _is_substantive("x" * 119) is False
    assert _is_substantive("x" * 120) is True


# --- #1067 RC3 — dayanak-denetçisi verdict parse (saf, degrade-safe) ---


def test_faithfulness_verdict_clean_tokens():
    assert _parse_faithfulness_verdict("DIRECT") == "DIRECT"
    assert _parse_faithfulness_verdict("INDIRECT") == "INDIRECT"
    assert _parse_faithfulness_verdict("UNSUPPORTED") == "UNSUPPORTED"


def test_faithfulness_verdict_case_and_whitespace_tolerant():
    assert _parse_faithfulness_verdict("  indirect\n") == "INDIRECT"
    assert _parse_faithfulness_verdict("Verdict: UNSUPPORTED.") == "UNSUPPORTED"


def test_faithfulness_verdict_strictest_wins():
    # model birden çok kelime sızdırırsa en katı yorum kazanır
    assert _parse_faithfulness_verdict("DIRECT ama aslında UNSUPPORTED") == "UNSUPPORTED"
    assert _parse_faithfulness_verdict("DIRECT / INDIRECT") == "INDIRECT"


def test_faithfulness_verdict_degrade_safe_default():
    # tanınmayan/boş/None → DIRECT (şüphede orijinali servis et)
    assert _parse_faithfulness_verdict("") == "DIRECT"
    assert _parse_faithfulness_verdict(None) == "DIRECT"
    assert _parse_faithfulness_verdict("anlamsız çıktı") == "DIRECT"
