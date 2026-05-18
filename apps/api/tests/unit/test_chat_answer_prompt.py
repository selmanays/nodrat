"""SYSTEM_PROMPT_NODRAT_AGENT C1/agentic kural koruma testleri.

#970 — "Takip sorusu tuzağı (C1)" reinforcement: konuşma bağlamında
varlık net olsa bile o varlık hakkında YENİ olgusal boyut (yıl/sezon/
kanal-geçişi/sayı) = yeni olgu → tool zorunlu; meşhur konu/akıcı sohbet
bellekten kesin değer vermek için gerekçe değil (prod conv 75711aa0
msg6 C1 sızıntısı). Mevcut #842/#958/#964 kuralları korunmalı.
"""

from __future__ import annotations

from app.prompts.chat_answer import (
    SYSTEM_PROMPT_NODRAT_AGENT,
    render_nodrat_agent_prompt,
)

S = SYSTEM_PROMPT_NODRAT_AGENT


def test_new_followup_trap_rule_present():
    """#970 — yeni takip-sorusu tuzağı C1 kuralı eklendi."""
    assert "Takip sorusu tuzağı (C1" in S
    # özü: context'te varlık olması yeni olgu için kaynak demek değil
    assert "YENİ bir olgu" in S
    assert "meşhur" in S and "akıcı" in S
    # boş sources + olgusal cümle = marka ihlali çerçevesi
    assert "marka ihlali" in S
    # scope-aware (uydurma değil)
    assert "kaynaklarımda" in S and "bulamadım" in S


def test_followup_trap_inside_rule4_before_rule5():
    """#970 — yeni kural rule 4 (Agentic) İÇİNDE, rule 5'ten ÖNCE
    (mantıksal konum; agentic tool-zinciri kuralının uzantısı)."""
    i4 = S.find("Agentic kural (KRİTİK)")
    itrap = S.find("Takip sorusu tuzağı (C1")
    i5 = S.find("Emin değilsen: güncel/olay kokuyorsa")
    assert -1 < i4 < itrap < i5


def test_existing_c1_rules_preserved():
    """#970 — mevcut C1/grounding omurgası KORUNDU (regresyon yok)."""
    # #958 meta-C1 (kendin/sistem halüsinasyon yasağı)
    assert "kendin/sistem hakkında halüsinasyon" in S
    # C1 marka temeli bölümü + bellekten cevap yasağı
    assert "Halüsinasyon koruması (C1" in S
    assert "kendi belleğinden cevap verme" in S
    # #964 ardışıklık/nedensellik temporal kuralı
    assert "ardışıklık" in S.lower()
    # rule 4 agentic tool-zinciri + rule 2/3 search_news/wikipedia
    assert "Agentic kural (KRİTİK)" in S
    assert "search_news" in S and "search_wikipedia" in S
    # citation = kanıt (sahte cite yasağı)
    assert "Citation = kanıt" in S


def test_render_injects_date_and_keeps_rule():
    """#970 — render_nodrat_agent_prompt kod default'u (template=None)
    yeni kuralı taşır + {current_date} enjekte eder (#854 deseni)."""
    out = render_nodrat_agent_prompt("2026-05-18")
    assert "Takip sorusu tuzağı (C1" in out
    assert "{current_date}" not in out
    assert "2026-05-18" in out


# --- F1 / #1012 (pivot Faz 1) — editöryal ton + kapsam-dışı deflection ---


def test_f1_out_of_scope_deflection_rule_present_and_positioned():
    """#1012 — kapsam-dışı/asistan-dışı istek yumuşak yönlendirme kuralı
    Karar bloğunda item 6 (rule 5'ten SONRA, Halüsinasyon bölümü ÖNCESİ)."""
    assert "Kapsam-dışı / asistan-dışı istek" in S
    assert "genel asistana DÖNÜŞME" in S
    assert "haber ve gündem araştırma kapsamı dışında" in S
    i5 = S.find("Emin değilsen: güncel/olay kokuyorsa")
    i6 = S.find("Kapsam-dışı / asistan-dışı istek")
    ihalu = S.find("Halüsinasyon koruması (C1")
    assert -1 < i5 < i6 < ihalu


def test_f1_assistant_pleasantry_ban():
    """#1012 — asistan/sohbet nezaket kalıpları açıkça yasak (editöryal ton)."""
    assert "Asistan/sohbet dili YASAK" in S
    for phrase in (
        "Elbette",
        "Tabii ki",
        "Harika soru",
        "Umarım yardımcı olmuştur",
        "yardımcı olayım",
    ):
        assert phrase in S


def test_f1_optional_editorial_headers_not_forced():
    """#1012 — opsiyonel editöryal başlıklar; ZORUNLU kalıp DEĞİL
    (mevcut 'yapı içeriğe göre' / 'sabit şablon yok' kuralıyla çelişmez)."""
    assert "Öne çıkan gelişme" in S and "Kaynakların aktardığına göre" in S
    assert "ZORUNLU kalıp" in S and "sabit şablon YOK" in S


def test_f1_legacy_chat_answer_not_assistant():
    """#1012 — legacy SYSTEM_PROMPT_CHAT_ANSWER 'asistan' → 'araştırma motoru'."""
    from app.prompts.chat_answer import SYSTEM_PROMPT_CHAT_ANSWER

    assert "araştırmacı asistanısın" not in SYSTEM_PROMPT_CHAT_ANSWER
    assert "araştırma motorusun" in SYSTEM_PROMPT_CHAT_ANSWER


def test_f1_prompt_remains_static_single_placeholder():
    """#1012 — STATIC invariant: yalnız {current_date} placeholder
    (DeepSeek implicit cache prefix bozulmasın — S3)."""
    import re

    assert set(re.findall(r"\{[a-z_]+\}", S)) == {"{current_date}"}
