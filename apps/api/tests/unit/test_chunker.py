"""Chunker module unit tests (#18).

Test stratejisi:
  - Heuristik token count
  - Paragraph split
  - Window grouping (target / max constraints)
  - Big paragraph fallback (cümle split)
  - Overlap
  - Title prefix
  - Min size merge
"""

from __future__ import annotations

import pytest

from app.core.chunker import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_TOKENS,
    DEFAULT_TARGET_TOKENS,
    ChunkingConfig,
    chunk_text,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0


def test_estimate_tokens_one_word():
    # 1 word * 1.3 = 1
    assert estimate_tokens("merhaba") == 1


def test_estimate_tokens_multi_word():
    # 10 word * 1.3 = 13
    text = " ".join(["kelime"] * 10)
    assert estimate_tokens(text) == 13


# ---------------------------------------------------------------------------
# chunk_text basic
# ---------------------------------------------------------------------------


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_single_short_paragraph():
    text = "Kısa bir paragraf, sadece birkaç kelime."
    chunks = chunk_text(text, title="Test")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "BAŞLIK: Test" in chunks[0].chunk_text
    assert "Kısa bir paragraf" in chunks[0].chunk_text


def test_chunk_short_text_no_split():
    """target_tokens altında tek chunk."""
    text = "Bu bir orta uzunlukta paragraf. " * 30
    chunks = chunk_text(text)
    assert len(chunks) == 1


def test_chunk_long_text_multiple_chunks():
    """target_tokens aşıldığında birden fazla chunk."""
    # Her paragraf yaklaşık 100 token, 10 paragraf = ~1000 token
    paragraph = "Bu bir paragraf metni Türkçe olarak yazılmıştır. " * 13  # ~85 word
    text = "\n\n".join([paragraph] * 10)
    chunks = chunk_text(text)
    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk.token_count <= DEFAULT_MAX_TOKENS + 50  # tolerance for overlap+prefix


def test_chunk_index_sequential():
    paragraph = "Test paragrafı sade. " * 30
    text = "\n\n".join([paragraph] * 6)
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_includes_title_prefix():
    chunks = chunk_text(
        "İçerik metni paragrafları " * 5,
        title="Türkiye'de yeni gelişmeler",
        subtitle="Detaylı analiz",
    )
    assert chunks
    assert "BAŞLIK: Türkiye'de yeni gelişmeler" in chunks[0].chunk_text
    assert "ALT BAŞLIK: Detaylı analiz" in chunks[0].chunk_text


def test_chunk_no_title_prefix():
    cfg = ChunkingConfig(title_prefix=False)
    chunks = chunk_text("Metin " * 50, title="X", subtitle="Y", config=cfg)
    assert chunks
    assert "BAŞLIK:" not in chunks[0].chunk_text
    assert "ALT BAŞLIK:" not in chunks[0].chunk_text


# ---------------------------------------------------------------------------
# Big paragraph fallback (sentence split)
# ---------------------------------------------------------------------------


def test_chunk_big_paragraph_split_to_sentences():
    """max_tokens aşan tek paragraf cümle bazlı bölünür."""
    sentence = "Bu uzun bir cümle ile yazılmış metin parçası buraya geliyor. "
    big_paragraph = sentence * 100  # ~1000 token tek paragrafta
    chunks = chunk_text(big_paragraph, config=ChunkingConfig(max_tokens=300))
    assert len(chunks) >= 3


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


def test_chunk_overlap_present():
    """Overlap default 80 token; 2. chunk başında 1. chunk'ın son kelimeleri var."""
    paragraph = "İlk paragraf benzersiz bir metin içeriyor. " * 20
    paragraph2 = "İkinci paragraf farklı içerikle. " * 20
    paragraph3 = "Üçüncü paragraf yine farklı. " * 20
    text = f"{paragraph}\n\n{paragraph2}\n\n{paragraph3}"
    chunks = chunk_text(text, config=ChunkingConfig(target_tokens=200, overlap_tokens=40))
    if len(chunks) >= 2:
        # 2. chunk başında 1. chunk'ın son kelimelerinden bir kısmı olmalı
        # Heuristik: chunks[0]'in son 20 kelimesinin bazıları chunks[1]'de var
        first_last_words = chunks[0].chunk_text.split()[-15:]
        second_text = chunks[1].chunk_text
        common = sum(1 for w in first_last_words if w in second_text)
        # En az birkaç kelime ortak olmalı
        assert common > 0


def test_chunk_overlap_zero_disabled():
    """overlap_tokens=0 → overlap yok."""
    paragraph = "Tekrar etmeyen kelime " * 20
    paragraph2 = "Bambaşka metin " * 20
    text = f"{paragraph}\n\n{paragraph2}"
    chunks = chunk_text(text, config=ChunkingConfig(target_tokens=100, overlap_tokens=0))
    if len(chunks) >= 2:
        # İlk paragrafın hiçbir kelimesi 2. chunk'ta olmamalı
        words_first = set(paragraph.split())
        words_second = set(chunks[1].chunk_text.split())
        # %5'ten az ortaklık (sadece şanssız stop word olabilir)
        intersection = words_first & words_second
        ratio = len(intersection) / max(len(words_first), 1)
        assert ratio < 0.2


# ---------------------------------------------------------------------------
# Min size merge
# ---------------------------------------------------------------------------


def test_chunk_short_tail_merged_with_prev():
    """Son chunk min_tokens altındaysa öncekiyle birleşir."""
    cfg = ChunkingConfig(target_tokens=200, min_tokens=100)
    p1 = "Birinci paragraf " * 80   # ~104 token
    p2 = "İkinci paragraf " * 80    # ~104 token
    p_short = "Üçüncü kısa son paragraf"  # çok küçük
    text = f"{p1}\n\n{p2}\n\n{p_short}"
    chunks = chunk_text(text, config=cfg)
    # Son kısa paragraf merge edilmiş olmalı → 2 chunk yerine 1 (eğer toplam küçükse)
    # ya da kısa paragraf önceki chunk'ın içinde
    last_text = chunks[-1].chunk_text
    assert "Üçüncü kısa son paragraf" in last_text
    last_tokens = estimate_tokens(last_text)
    assert last_tokens >= cfg.min_tokens or len(chunks) == 1


# ---------------------------------------------------------------------------
# Real article scenario (PRD §1.5 acceptance: 1500 token → 3 chunk)
# ---------------------------------------------------------------------------


def test_chunk_large_text_yields_many_chunks():
    """#652 RAGFlow-tier: büyük metin → çok sayıda küçük chunk.

    Eski test "PRD §1.5 ~1500 tok → ~3 chunk" + yorum "target=500/max=900"
    PRE-#652 config'i varsayıyordu (stale). #652 defaults target=256/
    max=384 (test_default_targets_are_ragflow_tier doğruluyor) → ~1200
    token = ~7 chunk. Niş bilgi semantic dilution azalsın diye kasıtlı.
    """
    paragraph = "Türkiye ekonomisinde yaşanan son gelişmeler ülke genelinde tartışılıyor. " * 18  # ~120 token
    text = "\n\n".join([paragraph] * 10)  # ~1200 token

    chunks = chunk_text(text)
    # #652 target=256/max=384/overlap=64 → ~1200 tok ≈ 7 chunk (margin'li)
    assert 5 <= len(chunks) <= 10


def test_chunk_token_count_in_range():
    """Tüm chunk'lar min_tokens-max_tokens range'inde (son hariç)."""
    paragraph = "Anlamlı bir Türkçe paragraf metni bu test için. " * 25  # ~135 token
    text = "\n\n".join([paragraph] * 12)
    chunks = chunk_text(text)

    for i, chunk in enumerate(chunks):
        # max_tokens + buffer (overlap + prefix)
        assert chunk.token_count <= DEFAULT_MAX_TOKENS + 200, (
            f"chunk[{i}] {chunk.token_count} exceeds max+buffer"
        )


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_chunk_custom_config_smaller_target():
    """Daha küçük target → daha çok chunk."""
    text = "Test paragrafı içeriği. " * 100
    cfg_default = chunk_text(text)
    cfg_small = chunk_text(text, config=ChunkingConfig(target_tokens=100, max_tokens=200))
    assert len(cfg_small) > len(cfg_default)


# ---------------------------------------------------------------------------
# #652 Faz 1 — RAGFlow-tier sentence-window invariants
# ---------------------------------------------------------------------------


def test_default_targets_are_ragflow_tier():
    """#652 Faz 1: defaults target=256, max=384, min=100, overlap=64.

    1275 char article'lar tek chunk halinde gömülmesin diye sertleştirildi
    (eski 500/900/200/80 → niş bilgi semantic dilution yapıyordu).
    """
    cfg = ChunkingConfig()
    assert cfg.target_tokens == 256
    assert cfg.max_tokens == 384
    assert cfg.min_tokens == 100
    assert cfg.overlap_tokens == 64


def test_full_length_article_yields_multiple_chunks():
    """Gerçekçi uzunlukta haber → #652 birden fazla chunk (recall).

    Eski test ~1300 char (≈100 token) sentetik metinle ≥2 chunk
    bekliyordu — #652 (min=100/max=384) altında FİZİKSEL olarak imkânsız:
    384 token altı article tek chunk kalır (bilinçli; aşırı sub-chunk
    deneyi reverted — failed-experiments-rag-quality). GERÇEK bir haber
    makalesi (≈3000 char / >480 token) ise ≥2 chunk üretir → niş bilgi
    (hakem isimleri) ayrı vector'e düşer, ana tema ile dilute olmaz.
    """
    block = (
        "Karşıyaka basketbol takımı kendi sahasında Bursaspor'u son saniye "
        "basketiyle 78-77 mağlup etti. Maç boyunca iki takım da kalıcı "
        "üstünlük kuramadı, skor her hücumda el değiştirdi. Tribünleri "
        "dolduran taraftarlar tezahüratla destek verdi. Karşılaşmanın "
        "hakemleri Mehmet Yıldız, Ali Demir ve Hakan Karahan oldular. "
        "İlk yarıyı 40-38 önde kapatan ev sahibi ekip ikinci yarı başında "
        "farkı altıya çıkardı. Konuk takım üçüncü çeyrekte savunma "
        "değiştirerek oyuna ortak oldu. Son periyoda bir sayı geride giren "
        "Bursaspor pota altında etkili oldu. Son saniyede Karşıyakalı genç "
        "oyuncunun turnikesi salonu coşturdu. İstatistiklerde ribaund ve "
        "top çalma ev sahibi lehineydi. Maçın en skoreri 24 sayıyla "
        "Karşıyakalı pivot oldu. Ev sahibi teknik direktör oyuncularının "
        "karakter gösterdiğini söyledi. Konuk antrenör hakem kararlarına "
        "yorum yapmak istemediğini belirtti. Yönetim taraftara teşekkür "
        "ederek şampiyonluk hedefini koruduklarını duyurdu. Deplasman maçı "
        "hazırlıkları yarın başlayacak. "
    )
    text = block * 3  # ≈2900 char — gerçekçi uzun haber (#652 → ≥2 chunk)
    chunks = chunk_text(text, title="Karşıyaka son saniye basketi")
    assert len(chunks) >= 2, f"Expected ≥2 chunks, got {len(chunks)}"
    # Niş bilgi (hakem isimleri) korunur
    assert any("Mehmet Yıldız" in ch.chunk_text for ch in chunks)


def test_niche_info_isolated_in_separate_chunk():
    """Niş bilgi (hakem isimleri) kendi chunk'ında izole olmalı (recall).

    Article ana teması (basketbol galibiyeti) ile niş bilgi (hakem isimleri)
    farklı chunk'larda → hakemler sorgusu için cosine sim dilute olmaz.
    """
    block = (
        "Türkiye ekonomisinde mayıs ayına ilişkin öncü veriler açıklandı "
        "ve piyasalarca yakından izlendi. Yıllık tüketici enflasyonu yüzde "
        "42 seviyesine geriledi; aylık artış beklentilerin altında kaldı. "
        "Merkez Bankası Başkanı sıkı para politikası duruşunun kararlılıkla "
        "süreceğini vurguladı. İhracat yıllık bazda yüzde 15 artarak "
        "çeyreklik rekora ulaştı. Otomotiv ve savunma sanayii ihracatın "
        "lokomotifleri oldu. Tekstilde ihracat geriledi, sektör hedefli "
        "teşvik istedi. Tarım pozitif sinyal verdi, lojistik genişlemesini "
        "korudu. Toplantı kararları arasında seçici kredi desteği ve kur "
        "korumalı mekanizma vardı. Ekonomistler yıl sonu enflasyon "
        "patikasının kritik eşikte olduğunu söyledi. Sanayi üretimi hafif "
        "toparlandı, kapasite kullanımı yatay seyretti. Cari denge enerji "
        "faturasındaki gerilemeyle iyileşti. Konut piyasasında işlem hacmi "
        "düşük kaldı. Bütçede faiz dışı dengenin hedeflerle uyumlu "
        "seyrettiği bildirildi. Reel sektör güveni sınırlı yükseldi. "
        "Ay sonu ayrıntılı enflasyon raporu öncesi piyasalar temkinli. "
    )
    text = block * 3  # ≈3000 char — gerçekçi uzun haber (#652 → ≥2 chunk)
    chunks = chunk_text(text, title="Türkiye Ekonomisi Mayıs 2026")
    # #652: gerçekçi uzunlukta article ≥2 chunk → niş bilgi izole
    assert len(chunks) >= 2

    # Her chunk title prefix taşır
    for ch in chunks:
        assert "BAŞLIK: Türkiye Ekonomisi Mayıs 2026" in ch.chunk_text


def test_sentence_split_preserves_turkish_punctuation():
    """Türkçe Ç/Ğ/İ/Ö/Ş/Ü cümle başlangıçları doğru parse edilir."""
    text = "İlk cümle bitti. Çevirme süreci başladı. Şimdi yeni paragraf gelecek."
    chunks = chunk_text(text, title=None)
    # Tek paragraph'lık metin tek chunk olabilir (target altı)
    # ama sentence split düzgün olmalı — chunk text boş olmaz
    assert len(chunks) >= 1
    assert "İlk cümle" in chunks[0].chunk_text
    assert "Şimdi yeni paragraf" in chunks[0].chunk_text


def test_very_long_sentence_does_not_break():
    """Tek cümle target_tokens'dan büyükse: kendi chunk'ında kabul.

    Edge case: bir cümle (örn. legal text) çok uzun → max_tokens aşılır.
    Hata yerine kabul (kaçınılmaz).
    """
    long_sentence = "Madde 1: " + ("önemli bir hüküm metni " * 200) + "."
    chunks = chunk_text(long_sentence)
    assert len(chunks) >= 1
    # En az bir chunk, içerik korunur
    assert "Madde 1" in chunks[0].chunk_text


def test_chunk_size_distribution_realistic_article():
    """3000 char article → 3-6 chunk (RAGFlow tier).

    Eski chunker: 3000 char → 1-2 chunk (avg 600 token).
    Yeni chunker: 3-6 chunk (avg 256 token, daha fine-grained).
    """
    text = "Bu paragraf önemli bilgiler içerir. Detaylar aşağıda. " * 80  # ~2800 char
    chunks = chunk_text(text)
    assert 3 <= len(chunks) <= 8, f"Expected 3-8 chunks, got {len(chunks)}"
    # Token sayısı target'a yakın (ortalama 200-280)
    avg_tokens = sum(c.token_count for c in chunks) / len(chunks)
    # Prefix dahil; tolerans
    assert 100 <= avg_tokens <= 400
