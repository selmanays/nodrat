"""Regression: admin observability `generations` tablosu DROP edildi (#800).

`20260514_1700_drop_legacy_generation_tables` migration'ı `generations`
+ `saved_generations` tablolarını düşürdü, ama admin_dashboard/admin_rag
hâlâ `FROM generations` sorguluyordu → /admin/dashboard/hourly +
/admin/rag/{health,ttft-stats,citation-stats,pipeline-comparison}
production'da HTTP 500. Bu test dropped-table sorgusunun geri
gelmesini engeller (denetim 2026-05-15).

NOT: admin modülleri import edilince `pyotp` (yalnız Docker'da) gerekiyor;
bu yüzden kaynak DOSYA metni taranır (import yok) — daha sağlam guard.
"""

from __future__ import annotations

from pathlib import Path

_API = Path(__file__).resolve().parents[2] / "app" / "api"


def _src(name: str) -> str:
    return (_API / name).read_text(encoding="utf-8")


def test_admin_modules_no_dropped_generations_query():
    """admin_dashboard.py + admin_rag.py'de ham DROP-edilmiş tablo
    sorgusu kalmamalı."""
    for name in ("admin_dashboard.py", "admin_rag.py"):
        src = _src(name)
        assert "FROM generations" not in src, f"{name}: FROM generations (DROP'lu tablo)"
        assert "UPDATE generations" not in src, f"{name}: UPDATE generations"
        assert "INTO generations" not in src, f"{name}: INTO generations"


def test_repointed_queries_use_messages():
    """generations → messages repoint'i (assistant cevap + halu_flagged)
    yerinde."""
    dash = _src("admin_dashboard.py")
    assert "FROM messages WHERE created_at >= :since AND role = 'assistant'" in dash

    rag = _src("admin_rag.py")
    # pipeline-quality SQL messages-based
    assert "FROM messages" in rag
    assert "halu_flagged_at IS NOT NULL" in rag
    # TTFT + citation-stats RETIRED short-circuit (kavram emekli)
    assert "RETIRED" in rag
