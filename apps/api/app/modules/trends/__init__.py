"""Trends domain — Trend Intelligence kalıcı katmanı (Faz 2, #1505).

Faz 1 (#1500) transient read-only Trend Overview'ı kalıcı zaman-serisine taşır:
kalıcı `topics` kimliği + `trend_snapshots` (saatlik bucket, algo_version) +
`topic_clusters` (kalıcı topic ↔ transient event_cluster) + `trend_signals`.

PR-2a: yalnız modeller (şema). Aggregation/worker/topic-assignment PR-2b'de.
Cross-domain okuma RAW SQL (api→modules serbest değil; bu domain sibling import
etmez) — import-linter 16/16 korunur.
"""
