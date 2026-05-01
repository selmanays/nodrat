"""LLM evaluation framework — golden_sets/ tabanlı.

Kullanım:
    pytest -m eval                          # tüm eval'leri çalıştır
    pytest -m eval -k pii_redaction         # sadece PII testleri

Maliyet: eval testleri provider key gerektirir ($$). CI'da elle tetiklenir.
"""
