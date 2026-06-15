"""Unit — gündem kaynakları görsel site-profilleri + svg-skip (#1538)."""

from __future__ import annotations

import pytest
from app.shared.extraction._filters import _is_non_editorial_image
from app.shared.extraction.site_profiles import find_profile
from bs4 import BeautifulSoup

# (article_url, beklenen domain)
NEW_SOURCE_URLS = [
    ("https://www.cumhuriyet.com.tr/turkiye/haber-123", "cumhuriyet.com.tr"),
    ("https://halktv.com.tr/ekonomi/haber-1h", "halktv.com.tr"),
    ("https://teyit.org/analiz/x", "teyit.org"),
    ("https://t24.com.tr/haber/x,1", "t24.com.tr"),
    ("https://dokuz8haber.net/x", "dokuz8haber.net"),
    ("https://www.indyturk.com/node/1/haber/x", "indyturk.com"),
]


@pytest.mark.parametrize("url,domain", NEW_SOURCE_URLS)
def test_new_sources_have_profile(url: str, domain: str) -> None:
    prof = find_profile(url)
    assert prof is not None, f"{domain} için profil bulunamadı"
    assert domain in prof.domains


def test_profiles_have_image_targeting() -> None:
    """Her yeni profil container override VEYA whitelist VEYA exclude tanımlar."""
    for url, _ in NEW_SOURCE_URLS:
        p = find_profile(url)
        assert p is not None
        assert p.container_selector or p.main_image_selectors or p.exclude_selectors


def test_cumhuriyet_whitelists_content_not_widget() -> None:
    p = find_profile("https://www.cumhuriyet.com.tr/x")
    assert p is not None
    # hero (aspect) + gövde (articleDetails/prose) whitelist'te
    joined = " ".join(p.main_image_selectors)
    assert "aspect" in joined and "articleDetails" in joined


def _img(src: str):
    return BeautifulSoup(f'<img src="{src}">', "lxml").img


def test_svg_is_non_editorial() -> None:
    assert _is_non_editorial_image(
        _img("https://x.com/assets/print.svg"), "https://x.com/assets/print.svg"
    )
    # query/fragment ile de
    assert _is_non_editorial_image(_img("https://x.com/i.svg?v=2"), "https://x.com/i.svg?v=2")
    assert _is_non_editorial_image(_img("https://x.com/i.svg#a"), "https://x.com/i.svg#a")


def test_real_photo_not_flagged_by_svg_rule() -> None:
    # Gerçek editöryel foto (jpg/webp) svg-kuralına takılmaz
    url = "https://media.cumhuriyet.com.tr/Archive/abc-123.jpg"
    assert _is_non_editorial_image(_img(url), url) is False
    url2 = "https://cdn.dokuz8haber.net/resize/width=1200/haber.webp"
    assert _is_non_editorial_image(_img(url2), url2) is False
