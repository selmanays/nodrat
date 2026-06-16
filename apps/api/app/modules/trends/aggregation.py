"""Trend skor fonksiyonları — saf, deterministik (Faz 2 PR-2b, #1505).

Faz 1 (admin_trends.py) ile PAYLAŞILAN kanonik scoring + worker'a özel burst.
DB-bağımsız (unit-testable). admin_trends.py compute_* fonksiyonlarını buradan
import eder (tek doğruluk kaynağı).
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime

# =============================================================================
# Sabitler
# =============================================================================

TRENDS_ALGO_VERSION = 1  # formül değişince bump → eski snapshot'lar korunur
BUCKET_SECONDS = 3_600  # saatlik bucket (refresh-clusters ile hizalı)
SUBJECT_TYPE_TOPIC = "topic"

# trend_state eşikleri (v1 sabit; ileride settings'e taşınabilir) — #1566
BREAKING_MIN_ARTICLES = 3
# A — korpus-normalize relatif momentum (entity'nin korpus-üstü büyüme oranı).
# breaking'i GATE'ler: korpus-riderları (sadece hacim dalgasıyla yükselen) elenir.
REL_BREAKING = 0.25  # korpustan ≥%25 hızlı büyüme → breaking adayı
REL_FADING = -0.25
# B/D — pencere-içi burst z (son üçte-bir vs entity'nin kendi baseline'ı) = grafik yönü.
BURST_BREAKING = 1.0  # son dilim ≥1σ baseline-üstü (grafik belirgin yükseliyor)
BURST_DEVELOPING = 0.3
BURST_FADING = -0.5  # son dilim baseline-altı (grafik düşüyor)

# novelty yarı-ömrü (saat): brand-new ≈1.0, 12sa ≈0.5, 24sa ≈0.25
NOVELTY_HALFLIFE_HOURS = 12.0

# burst (z-score) trailing baseline penceresi + sinyal eşiği
BURST_BASELINE_BUCKETS = 24
BURST_SIGNAL_THRESHOLD = 2.0

# Birleşik trend skoru ağırlıkları (#1518 entity MVP). Öncelik:
# volume + momentum + source_diversity birincil; recency/reliability yardımcı.
# Novelty SKORA GİRMEZ — yalnız sıralamada tie-breaker (kullanıcı kararı).
SCORE_W_VOLUME = 0.40
SCORE_W_MOMENTUM = 0.25
SCORE_W_DIVERSITY = 0.20
SCORE_W_RECENCY = 0.10
SCORE_W_RELIABILITY = 0.05
SCORE_VOLUME_CEIL = 50  # ~50 haber → volume bileşeni ≈ 1.0 (log normalize)
SCORE_DIVERSITY_CEIL = 15  # ~15 distinct kaynak → diversity bileşeni ≈ 1.0
SCORE_NEW_MOMENTUM = 0.5  # prev=0 (baseline yok): orta momentum kredisi


# =============================================================================
# Saf scoring fonksiyonları (Faz 1 ile paylaşılan)
# =============================================================================


def compute_momentum(cur: int, prev: int) -> float | None:
    """Ham (cur-prev)/prev. prev=0 & cur>0 → None ('yeni'). Aksi 0.0. (Display.)"""
    if prev > 0:
        return round((cur - prev) / prev, 4)
    if cur > 0:
        return None
    return 0.0


def compute_relative_momentum(
    cur: int, prev: int, corpus_cur: int, corpus_prev: int
) -> float | None:
    """A (#1566) — korpus-normalize relatif momentum.

    Entity'nin pencere-üstü büyümesini KORPUS-geneli büyümeye böler:
    `(cur/prev) / (corpus_cur/corpus_prev) - 1`.
      >0 → korpustan hızlı büyüyor (gerçek trend) · ≈0 → korpusla aynı (yalnız
      hacim dalgası, trend DEĞİL) · <0 → geri kalıyor.
    'Her şey patlıyor' confound'unun kökü: ham momentum korpus büyümesini trend
    sanıyordu; bu onu böler. prev=0 → None ('yeni'). Korpus baseline'ı yoksa
    (corpus_prev=0) ham orana düşer (degrade-safe).
    """
    if prev <= 0:
        return None
    entity_ratio = cur / prev
    if corpus_prev > 0 and corpus_cur > 0:
        return round(entity_ratio / (corpus_cur / corpus_prev) - 1.0, 4)
    return round(entity_ratio - 1.0, 4)


def compute_window_burst(buckets: list[int]) -> float:
    """B (#1566) — pencere-içi canlı burst z-score (snapshot worker GEREKMEZ).

    Sparkline bucket serisinde (eskiden→yeniye) son üçte-birin ortalama hızını,
    daha eski bucket'ların (entity'nin KENDİ baseline'ı) ortalama+std'sine göre
    z-skorlar. >0 → grafik yükseliyor (son dilim baseline-üstü) · <0 → düşüyor.
    Entity kendine göre normalize → seviye-bağımsız; sparkline'ın GÖRSEL yönünü
    verir → trend_state rozeti grafikle hizalanır (D). <3 bucket → 0.0 (gürültü).
    """
    n = len(buckets)
    if n < 3:
        return 0.0
    recent_n = max(1, n // 3)
    recent = buckets[-recent_n:]
    baseline = buckets[:-recent_n]
    if not baseline:
        return 0.0
    mu = statistics.fmean(baseline)
    sigma = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
    return round((statistics.fmean(recent) - mu) / max(sigma, 1.0), 4)


def compute_novelty(first_seen_at: datetime | None, now: datetime) -> float:
    """Recency tabanlı novelty [0,1]: 0.5 ** (yaş_saat / yarı-ömür)."""
    if first_seen_at is None:
        return 0.0
    age_hours = max(0.0, (now - first_seen_at).total_seconds() / 3_600.0)
    return round(0.5 ** (age_hours / NOVELTY_HALFLIFE_HOURS), 4)


def compute_source_diversity(unique_sources: int, article_count: int) -> float:
    """Basit v1 yayılım proxy'si: benzersiz_kaynak / toplam_haber, [0,1]."""
    if article_count <= 0:
        return 0.0
    return round(min(1.0, unique_sources / article_count), 4)


def compute_trend_score(
    cur: int,
    unique_sources: int,
    reliability: float | None,
    recency: float,
    rel_momentum: float | None,
) -> float:
    """#1518/#1566 — entity trend birleşik skoru [0,1] (varsayılan sıralama).

    volume (log-norm haber) + momentum (#1566: KORPUS-NORMALIZE `rel_momentum` —
    ham büyüme değil korpus-üstü pay) + source_diversity (log-norm distinct kaynak)
    birincil; recency + reliability yardımcı. Novelty BURADA YOK (tie-breaker).
    Momentum'un rel olması skor doygunluğunu kırar: korpusla birlikte büyüyen
    (rel≈0) entity momentum bileşeninden kredi almaz → top artık ayrışır.
    """
    volume = min(1.0, math.log1p(max(0, cur)) / math.log1p(SCORE_VOLUME_CEIL))
    if rel_momentum is None:  # prev=0 (yeni, baseline yok) → orta kredi
        momentum_c = SCORE_NEW_MOMENTUM if cur > 0 else 0.0
    else:
        momentum_c = min(1.0, max(0.0, rel_momentum))
    diversity = min(1.0, math.log1p(max(0, unique_sources)) / math.log1p(SCORE_DIVERSITY_CEIL))
    reli = reliability if reliability is not None else 0.5
    rec = max(0.0, min(1.0, recency))
    return round(
        SCORE_W_VOLUME * volume
        + SCORE_W_MOMENTUM * momentum_c
        + SCORE_W_DIVERSITY * diversity
        + SCORE_W_RECENCY * rec
        + SCORE_W_RELIABILITY * reli,
        4,
    )


def compute_trend_state(
    cur: int,
    prev: int,
    rel_momentum: float | None,
    burst_z: float,
) -> str:
    """Deterministik durum: breaking | developing | stable | fading (#1566).

    İKİ sinyal birleşir → rozet GRAFİKLE hizalı (D) + korpus-confound'suz (A/B):
      • `rel_momentum` (A, korpus-normalize pencere-üstü): breaking'i GATE'ler —
        sadece korpusla büyüyen (rel≈0) entity breaking OLAMAZ.
      • `burst_z` (B, pencere-içi son-dilim vs kendi baseline'ı): sparkline'ın
        görsel yönü → düşen grafik=fading, yükselen=breaking/developing.
    Sonuç: düşüş→fading · yükseliş∧korpus-üstü→breaking · yükseliş→developing ·
    düz→stable. `rel_momentum=None` (yeni/baseline yok veya worker) → yalnız
    burst_z'ye bakılır (kendi-referanslı, degrade-safe).
    """
    if cur == 0:
        return "fading" if prev > 0 else "stable"
    if cur < BREAKING_MIN_ARTICLES:
        # yetersiz kanıt: gürültülü tek/iki haber "patlıyor" olmaz
        return "developing" if burst_z > BURST_DEVELOPING else "stable"
    # pencere-içi düşüş → fading (grafikle uyumlu; rel'den bağımsız)
    if burst_z <= BURST_FADING:
        return "fading"
    # yükseliş ∧ korpus-üstü → breaking (rel=None ise yalnız yükseliş yeterli)
    if burst_z >= BURST_BREAKING and (rel_momentum is None or rel_momentum >= REL_BREAKING):
        return "breaking"
    # yükseliş/yüksek ama breaking değil → developing
    if burst_z >= BURST_DEVELOPING or (rel_momentum is not None and rel_momentum > 0):
        return "developing"
    return "stable"


# =============================================================================
# Worker'a özel — burst (z-score vs trailing baseline)
# =============================================================================


def compute_burst_score(cur: int, baseline_counts: list[int]) -> float:
    """Trailing baseline'a göre z-score: (cur - mean) / max(stddev, 1.0).

    baseline_counts = current bucket'tan ÖNCEKİ (≤ BURST_BASELINE_BUCKETS)
    bucket'ların article_count'ları (aynı subject, aynı algo_version). Boşsa 0.0.
    """
    if not baseline_counts:
        return 0.0
    mu = statistics.fmean(baseline_counts)
    sigma = statistics.pstdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
    return round((cur - mu) / max(sigma, 1.0), 4)


def compute_velocity(cur: int, prev: int | None) -> float | None:
    """Δ count (cur - prev). prev yoksa None."""
    if prev is None:
        return None
    return float(cur - prev)
