"""generations citation + faithfulness-reconstruction pure helpers.

P6.1 (Modular Monolith v2, #1094 P6): app/api/app_research_stream.py'den
çıkarılan SAF (yan-etkisiz) yardımcılar — citation-sayı ayrıştırma + RC3-B v2
geriye-çıkarsama imleci tespiti + faithfulness reframe kararı. Behavior-eş
(orchestrator bunları re-import eder; davranış değişmez).

NOT: `app.core.citation` AYRI bir modüldür (citation validator); bu modül
app_research_stream'in inline helper'larıdır — karıştırma.
"""

from __future__ import annotations

import re

# #audit (2026-05-15) — cited-only `sources_used` filtresi `s["cite"] in
# accumulated` substring'di → `[1,2]` / `[1, 2]` / `[1-3]` / `[1–3]`
# biçiminde cite edilen kaynak DÜŞÜYORDU (provenance eksik raporlama,
# C1/güven sinyali). Sayı-temelli ayrıştırma: tüm cite biçimlerini tolere.
_CITED_GROUP_RE = re.compile(r"\[\s*([0-9W][0-9W,\s–-]*)\s*\]")
_CITE_RANGE_RE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")


def _cited_numbers(text: str) -> set[int]:
    """Cevapta GERÇEKTEN cite edilen sayılar. [1] [12] [1,2] [1, 2]
    [1-3] [1–3] [1][2] hepsini tolere eder."""
    out: set[int] = set()
    for grp in _CITED_GROUP_RE.findall(text or ""):
        for part in grp.replace("W", "").split(","):
            part = part.strip()
            if not part:
                continue
            rng = _CITE_RANGE_RE.match(part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if a <= b and b - a < 100:
                    out.update(range(a, b + 1))
            elif part.isdigit():
                out.add(int(part))
    return out


def _cite_to_int(cite: str | None) -> int | None:
    m = re.search(r"\d+", cite or "")
    return int(m.group()) if m else None


def _is_substantive(text: str) -> bool:
    """Cevap, kaynak gerektiren substantive (olgusal iddia içeren) bir
    yanıt mı? Selamlama/kimlik/meta KISA yanıtlar (kaynak gerektirmez)
    DIŞLANIR. Saf/eşik-temelli (#854 deseni; yanlış-pozitif düşük —
    halüsinasyon cevapları uzun, meta'lar kısa). Cited-only hard guard
    (#1058, prod-audit conv 865e36e3) bunu kullanır."""
    return len((text or "").strip()) >= 120


# #1067 RC3-B v2 (#1076) — geriye-çıkarsama imleci detektörü.
# v1 LLM-verifier yaklaşımı prod'da kanıtlı 4/8 yanlış-pozitif (agenda/
# aggregate/topic-partial/single-direct sınıflarında multi-claim
# modellemiyordu; NLP-faithfulness LLM-only judgment calibration-
# fragile). Çözüm: LLM verifier yerine YAPISAL marker-detect. RC3-A
# prompt anma≠tanım'ı YASAKLIYOR; bu marker'lar prompt'a rağmen sızan
# rekonstrüksiyonun TELL'i (Özel/Çelik be3ae973: "anlaşıldığı kadarıyla").
# 4 yanlış-pozitifin HİÇBİRİNDE marker yoktu = false-positive-resistant.
_RECONSTRUCTION_MARKER_RE = re.compile(
    r"anlaşıldığı kadarıyla"
    r"|anlaşıldığına göre"
    r"|yansıdığı kadarıyla"
    r"|tepkisinden anlaşıl"
    r"|tepkisine bakılırsa"
    r"|tepkisinden çıkarıl"
    r"|olduğu anlaşılıyor"
    r"|olduğu sanılıyor"
    r"|muhtemelen [^.]{0,40}?\b(demiş|söylemiş|iddia etmiş|demişti)",
    re.IGNORECASE | re.UNICODE,
)


def _has_reconstruction_marker(text: str) -> bool:
    """#1067 RC3-B v2 — cevap, dolaylı/tepki-kaynağından geriye-çıkarsama
    imleci içeriyor mu? ("anlaşıldığı kadarıyla", "tepkisinden anlaşıl…").

    Saf/deterministik. RC3-A prompt bu kalıpları zaten yasaklar; bu
    detektör prompt'a rağmen sızan rekonstrüksiyon için son güvenlik
    ağı. v1 LLM-verifier (prod 4/8 yanlış-pozitif) yerine geçer —
    calibration-fragility yok (4 yanlış-pozitif sorgunun hiçbirinde
    marker YOK; Özel/Çelik orijinalinde VAR)."""
    if not text:
        return False
    return bool(_RECONSTRUCTION_MARKER_RE.search(text))


# RC3-B reframe sabit metni — T6 P6 PR-C+4'te orchestrator L1118-1137'den
# çıkarılan saf karar. İmleç tespit edildiğinde cevap bu dürüst kapsam-
# sınırı mesajıyla DEĞİŞTİRİLİR (byte-eş; orijinal inline literal).
_FAITHFULNESS_REFRAME_TEXT = (
    "Bu soruya **doğrudan** dayanak oluşturan bir kaynak "
    "bulunamadı; eldeki kaynaklar konuya yalnız dolaylı "
    "değiniyor (ör. bir tepki/yanıt). Çıkarımsal ya da "
    "dayanaksız cevap vermiyorum — soruyu farklı biçimde "
    "ya da daha belirgin sorabilir misin?"
)


def _maybe_reframe_for_faithfulness(
    final_text: str,
    all_sources: list,
    faithfulness_guard: bool,
) -> str | None:
    """RC3-B reframe KARARI — saf (T6 P6 PR-C+4 extraction; behavior-eş).

    Geriye-çıkarsama (rekonstrüksiyon) imleci gate'i: 4 koşul DA truthy ise
    sabit reframe metnini döner, aksi halde None. **Yan etki YOK** —
    `yield _log_step("faithfulness_reframed", ...)`, `_log_coverage_gap(...)`
    ve `final_text` ataması orchestrator'da KALIR.

    Gate (#1067 RC3-B v2 / #1076; #1058 ile karşılıklı dışlama — o
    `not all_sources`, bu `all_sources`):
      - `faithfulness_guard` (admin flag; kapalıysa hep None → byte-eş)
      - `all_sources` truthy (en az 1 taranan kaynak)
      - `_is_substantive(final_text)` (kaynak gerektiren uzun yanıt)
      - `_has_reconstruction_marker(final_text)` (imleç metne sızdı)
    """
    if (
        faithfulness_guard
        and all_sources
        and _is_substantive(final_text)
        and _has_reconstruction_marker(final_text)
    ):
        return _FAITHFULNESS_REFRAME_TEXT
    return None


# #1484 (S-2) — citation-gap guard nudge sabiti. İki-çıkışlı dürüst-
# netleştirme: kör "cite et" DEĞİL — kaynaklar desteklemiyorsa açıkça
# söylemesi ve kaynaksız iddiaları çıkarması istenir (#1058'in savaştığı
# sahte/gevşek atfa İTMEZ). Sabit metin: kullanıcı verisi İÇERMEZ.
_CITATION_GAP_NUDGE = (
    "Cevabında hiçbir [n] citation yok ama araç sonuçlarında kaynaklar var. "
    "İki seçenekten doğru olanı uygula: (1) Sağlanan kaynaklar cevabındaki "
    "olguları GERÇEKTEN destekliyorsa, her olguya onu içeren kaynağın [n] "
    "citation'ını ekleyerek cevabı yeniden yaz. (2) Kaynaklar bu soruyu "
    "desteklemiyorsa, bunu cevabın başında açıkça söyle ve kaynak "
    "içermeyen iddiaları çıkar. Bir kaynağa içermediği olguyu ASLA atfetme."
)


def _should_force_citation_gap_retry(
    candidate: str,
    all_sources: list,
    *,
    citation_gap_guard: bool,
    forced_once: bool,
) -> bool:
    """#1484 (S-2) — citation-gap guard tetik KARARI (saf, deterministik).

    "Kaynak VAR ama substantive cevapta hiç citation yok" çeyreği için tek
    seferlik dürüst-netleştirme turu gate'i. C1 (#851/#1058) ile karşılıklı
    dışlayan: C1 ``not all_sources``, bu guard ``all_sources``. LLM-judge
    YOK (#1076 calibration-fragility dersi) — yalnız mevcut yapıtaşları:

      - ``citation_gap_guard`` (admin flag; kapalıysa hep False → byte-eş)
      - ``all_sources`` truthy (en az 1 taranan kaynak)
      - ``not forced_once`` (en fazla 1 retry — sarkaç/loop YOK)
      - ``_is_substantive(candidate)`` (selamlama/kimlik/meta dışlanır)
      - ``not _cited_numbers(candidate)`` (hiç [n] yok; kısmi-citation'lı
        cevap tetiklemez)
    """
    return (
        citation_gap_guard
        and bool(all_sources)
        and not forced_once
        and _is_substantive(candidate)
        and not _cited_numbers(candidate)
    )
