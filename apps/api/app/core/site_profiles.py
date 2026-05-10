"""Site-specific extraction profile (#304 fix).

Her haber sitesinin kendine özgü DOM yapısı var:
  - BBC: <main> içinde "more stories" <li>'leri var, ana görseller <figure> içinde
  - Evrensel: <article> içinde temiz, ortalama 1 görsel/haber
  - AA / Habertürk / TRT: temiz pattern, generic fallback yeterli

Profile sistemi:
  - `container_selector`: body container override (article tag yok ise vs.)
  - `main_image_selectors`: whitelist — SADECE bu selector'lardaki img'leri al
  - `exclude_selectors`: blacklist — bu elementleri body'den decompose et

Profile yoksa generic fallback (extractor.py'daki _is_non_editorial_image +
_is_recommended_section filter zinciri).

Yeni site eklemek:
  1. PROFILES'a yeni SiteProfile entry ekle
  2. selector'ları test et (extractor unit test'i veya production sample HTML)
  3. unit test ekle

docs/engineering/architecture.md §3 (image_vlm_queue + site_profiles)
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SiteProfile:
    """Site-specific image extraction kuralları."""

    # Eşleşme — hostname == d veya hostname.endswith("." + d)
    domains: tuple[str, ...]

    # Body container CSS selector. None ise generic fallback chain.
    container_selector: str | None = None

    # Whitelist — SADECE bu selector'lardaki <img>'leri al.
    # Boş tuple ise container'daki tüm img'leri al (generic mode).
    main_image_selectors: tuple[str, ...] = ()

    # Blacklist — body_container'dan bu elementleri decompose et.
    # exclude_selectors > main_image_selectors önceliği var; exclude
    # edilen elementlerdeki img'ler whitelist'te bile olsalar alınmaz
    # (decompose edildiklerinden artık DOM'da yok).
    exclude_selectors: tuple[str, ...] = ()

    # Generic fallback aktif mi (filter zincirini de uygula)
    apply_generic_filter: bool = True


# =============================================================================
# Profil tanımları (#304 — production source'larına göre)
# =============================================================================


PROFILES: tuple[SiteProfile, ...] = (
    # ---- BBC (bbc.com / bbc.co.uk) ------------------------------------------
    # Sorun: <main> içinde "more stories" <ul><li>'leri var.
    # Çözüm: container=main, whitelist=<figure>, exclude=<ul>/<aside>/<nav>
    SiteProfile(
        domains=("bbc.com", "bbc.co.uk"),
        container_selector="main",
        main_image_selectors=("figure img",),
        exclude_selectors=(
            "ul",  # öneri haber listesi
            "ol",
            "aside",
            "nav",
            "header",
            "footer",
            "[data-component='related-stories']",
            "[data-component='topic-list']",
            "[data-component='links']",
            "[data-component='mostread']",
            "[data-component='secondary-column']",
        ),
    ),
    # ---- Evrensel (evrensel.net) --------------------------------------------
    # Generic ile temiz çalışıyor (1.00 ortalama). Container hint'i ile
    # gelecekte ek koruma sağlar.
    SiteProfile(
        domains=("evrensel.net",),
        container_selector="article, .haber-detay, .news-detail",
        exclude_selectors=(".related-news", ".other-news", "aside"),
    ),
    # ---- Anadolu Ajansı (aa.com.tr) -----------------------------------------
    SiteProfile(
        domains=("aa.com.tr",),
        container_selector="article, .detay, .haber-detay",
        exclude_selectors=(".other-news", ".ilgili-haberler", "aside"),
    ),
    # ---- Habertürk (haberturk.com) ------------------------------------------
    # Sorun: Sayfada birden fazla <article> tag'i var (asıl + öneri haberler).
    # Asıl görseller: <article class="news-tracker it-main"> içinde
    #                 <div class="widget-image"><img> veya direkt <figure><img>
    # Öneri haberler: <a class="gtm-tracker"><figure><img>
    #                 (URL: /200x200/ thumbnail format)
    SiteProfile(
        domains=("haberturk.com",),
        container_selector="article.it-main",
        main_image_selectors=(
            ".widget-image img",
            "figure:not(a.gtm-tracker figure) img",  # gtm-tracker içindeki figure'ı dışla
            ".cms-container img",
            ".news-content img",
        ),
        exclude_selectors=(
            "a.gtm-tracker",  # öneri haber linkleri
            ".sidebar-wrapper",
            ".sidebar-content-infinite",
            ".sidebar-sticky",
            ".sidebar",
            "aside",
            "nav",
        ),
    ),
    # ---- TRT Haber (trthaber.com) -------------------------------------------
    SiteProfile(
        domains=("trthaber.com",),
        container_selector="article, .news-detail, .haber-detay",
        exclude_selectors=(".related-news", ".other-news", "aside"),
    ),
    # ---- Yeşil Gazete (yesilgazete.org) -------------------------------------
    # WordPress + tagDiv theme — `tdb_*` class prefix'i.
    # Asıl görseller: .tdb_single_featured_image (kapak) + .tdb_single_content (body)
    # Öneri / author / logo: tdb-author-photo, tdb-logo-img-wrap, tdb_*_related
    SiteProfile(
        domains=("yesilgazete.org",),
        container_selector="article",
        main_image_selectors=(
            ".tdb_single_featured_image img",
            ".tdb_single_content img",
            ".td-post-content img",
            ".entry-content img",
            "figure img",
        ),
        exclude_selectors=(
            ".tdb-author-photo",
            ".tdb-logo-img-wrap",
            ".tdb-block-meta",
            ".td_block_template_1",  # WordPress widget block
            ".td_block_related_posts",
            ".td_block_more_articles",
            "aside",
            "nav",
        ),
    ),
    # ---- Hürriyet (hurriyet.com.tr) — bakinazik #585 -------------------------
    # Custom CMS (Demirören). Article body tek section'da, figure kullanılmaz —
    # img'ler doğrudan içerikte. Sidebar widget'ları (logo, social, weather,
    # tag list, breadcrumb) noise olarak hariç tutulur.
    SiteProfile(
        domains=("hurriyet.com.tr",),
        container_selector="section.news-detail-content",
        exclude_selectors=(
            "aside",
            "nav",
            "header",
            "footer",
            ".sidebar__content",
            ".sidebar__logo",
            ".breadcrumb",
            ".news-tags",
            ".social-share",
            "[class*='widget']",
            "[class*='related']",
            "[class*='other-']",
        ),
    ),
    # ---- Webtekno (webtekno.com) — bakinazik #585 ----------------------------
    # Custom Tailwind tabanlı modern stack. Article body `div.detail-content`'te,
    # figure kullanılmıyor — inline img + galeri stage. "Popular topics",
    # "category most read" widget'ları noise.
    SiteProfile(
        domains=("webtekno.com",),
        container_selector="div.detail-content",
        exclude_selectors=(
            "aside",
            "nav",
            "header",
            "footer",
            ".popular-topics-bar",
            ".category-most-read-widget",
            ".ideal-media-widget",
            ".content-tags",
            ".page-detail-breadcrumb",
            "[class*='widget']",
            "[class*='related']",
        ),
    ),
    # ---- Beyaz Perde (beyazperde.com) — bakinazik #585 -----------------------
    # AlloCiné CMS. Hero görsel `figure.article-main-figure`; related sinema
    # listesi `figure.thumbnail` (data-uri tracking pixel — VLM'i kandırmasın).
    # `aside.gd-col-right` aşamalı reklam/related panel.
    SiteProfile(
        domains=("beyazperde.com",),
        container_selector="div.article-content",
        main_image_selectors=(
            "figure.article-main-figure img",
            "figure.article-figure img",
        ),
        exclude_selectors=(
            "aside",
            "nav",
            "header",
            "footer",
            ".article-related-links",
            "figure.thumbnail",
            ".rc-fb-widget",
            ".breadcrumb",
            "[class*='related']",
        ),
    ),
    # ---- Bloomberg HT (bloomberght.com) — bakinazik #585 ---------------------
    # Tailwind tabanlı modern stack. Tek `<article>` element body'i taşır,
    # 24 figure ile görsel-zengin. `aside`, `suggested-news-desktop`,
    # `widget-sticky-ads` noise; transparent.gif tracker pixels generic
    # filter'la elenir (ext denetimi extractor'da).
    SiteProfile(
        domains=("bloomberght.com",),
        container_selector="article",
        main_image_selectors=("figure img",),
        exclude_selectors=(
            "aside",
            "nav",
            "header",
            "footer",
            ".suggested-news-desktop",
            ".widget-sticky-ads",
            ".search-widget-trigger",
            "[class*='widget']",
            "[class*='related']",
        ),
    ),
    # ---- Elle Türkiye (elle.com.tr) — bakinazik #585 -------------------------
    # WordPress benzeri Bootstrap stack. Hero `figure.blog-view_cover`; inline
    # img'ler `img.fr-dib` (Froala editor sınıfı — gerçek içerik). Newsletter
    # box, latest-news-grid, square-img profile thumb'ları noise.
    SiteProfile(
        domains=("elle.com.tr",),
        container_selector="article.blog-view_content",
        main_image_selectors=(
            "figure.blog-view_cover img",
            "img.fr-dib",
        ),
        exclude_selectors=(
            "aside",
            "nav",
            "header",
            "footer",
            ".newsletter-box",
            ".latest-news-grid",
            ".breadcrumb",
            ".square-img",
            "[class*='related']",
            "[class*='widget']",
        ),
    ),
)


def find_profile(article_url: str) -> SiteProfile | None:
    """URL'in hostname'ine göre eşleşen profili döndür.

    Eşleşme: tam domain veya alt-domain (hostname.endswith('.' + domain)).
    Profil yoksa None döner — extractor generic fallback kullanır.
    """
    hostname = (urlparse(article_url).hostname or "").lower()
    if not hostname:
        return None
    # www. öneki strip
    if hostname.startswith("www."):
        hostname = hostname[4:]

    for profile in PROFILES:
        for domain in profile.domains:
            d = domain.lower()
            if hostname == d or hostname.endswith("." + d):
                return profile

    return None
