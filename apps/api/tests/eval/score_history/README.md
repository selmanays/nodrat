# Score History — Niche entity benchmark snapshots (#765)

> ⚠️ **STATUS: Umbrella plan iptal (2026-05-13).** 4-öneri umbrella (#765) sonlandırıldı — sadece Adım 0 (baseline) + Adım 1 (microchunk, **nötr sonuç**) uygulandı. Adım 2/3/4 iptal. Bu klasör altyapı + 2 snapshot olarak **referans halinde korunur**, gelecek deneyler için kullanılabilir.

Bu klasör retrieval/rerank optimization deneylerinin **ölçülmüş skorlarını** kronolojik tutar. Her dosya 1 deney snapshot'ı.

## Format

```
baseline_<YYYY-MM-DD>_<short-desc>.json
step_<N>_<YYYY-MM-DD>_<short-desc>.json
```

Örnekler:
- `baseline_2026-05-13_pre-optimization.json` — 4-öneri öncesi referans state
- `step_1_2026-05-XX_microchunk-on.json` — Adım 1 (microchunk) sonrası
- `step_2_2026-05-XX_ner-numeric-on.json` — Adım 2 (NER numeric) sonrası

## JSON şeması

```json
{
  "snapshot_id": "baseline_2026-05-13",
  "label": "Pre-optimization baseline (post-Jina revert)",
  "captured_at": "2026-05-13T12:46Z",
  "git_sha_main": "<commit>",
  "production_state": {
    "deploy_sha": "<commit on VPS>",
    "active_settings": { "key": "value" }
  },
  "benchmark": {
    "script": "tests.eval.niche_chunks_benchmark",
    "golden_set": "tests/eval/golden_sets/niche_chunks_golden.yaml",
    "n_queries": 11
  },
  "metrics": {
    "recall_at_5": 0.727,
    "recall_at_10": 0.727,
    "mrr_at_10": 0.591,
    "ndcg_at_10_approx": 0.627,
    "avg_latency_ms": 20578,
    "passed_recall5": 8,
    "passed_recall10": 8
  },
  "per_query_rank": {
    "niche_001": 2, "niche_002": 2, "niche_003": 1, "niche_004": 1,
    "niche_005": 2, "niche_006": -1, "niche_007": -1, "niche_008": 1,
    "niche_009": -1, "niche_010": 1, "niche_011": 1
  },
  "delta_vs_baseline": {
    "recall_at_5": 0,
    "notes": "Baseline itself — no delta"
  }
}
```

`-1` = expected article top-10'a girmedi (retrieval miss).

## Kullanım

Yeni deney bittiğinde:
1. Bu klasöre yeni JSON dosyası ekle
2. `git_sha_main` o anki main HEAD
3. `delta_vs_baseline` field'ı baseline ile karşılaştırma
4. Commit + push

Trend görmek için bütün dosyaları kronolojik scan et — gelişme çizgisi.

## Eşik kuralları (her adım için)

- **recall@5 ≥ baseline (0.727)** — ZORUNLU (regresyon olmazsa devam)
- **recall@5 baseline + 5pp** — HEDEF (kalıcı ON kararı için)
- **latency ≤ 25s** — kabul edilebilir üst sınır (production budget 18-22s)

Regresyon varsa: setting flag OFF kalır, kod tutulur (yeni deneyler için altyapı).

## İlişkili

- Issue [#765](https://github.com/selmanays/nodrat/issues/765) — umbrella 4-step plan
- Wiki: [[cross-encoder-rerank-disabled]] — neden cross-encoder rerank denemiyoruz
- Wiki: [[answer-extraction-epic-plan]] — bottleneck analiz, β strategy
- Benchmark script: `apps/api/tests/eval/niche_chunks_benchmark.py`
- Golden set: `apps/api/tests/eval/golden_sets/niche_chunks_golden.yaml`
