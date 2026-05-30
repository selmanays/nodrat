"""Shared infrastructure: crawl primitives (robots.txt compliance + RSS/Atom feed parsing).

P4.5b (v2): app.core.{robots,rss} → app.shared.crawl.{robots,rss}. Kernel (sources)
kullanıyor → Layer 0 shared (modules/crawler değil; kernel→crawler yasak).
"""
