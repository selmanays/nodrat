"""Manuel admin script — JSONL dataset → Hugging Face Hub private push (#569).

KVKK güvenlik gereği OTOMATIK değil — admin kasten tetikler. Default
private (kazara public dataset paylaşmamak için).

Kullanım:

    # Önce export endpoint'inden dataset.jsonl al:
    curl -X POST https://nodrat.com/admin/sft/export \\
         -H "Authorization: Bearer $ADMIN_JWT" \\
         -d '{"task_type":"content_generator","sft_split":"train"}' \\
         > nodrat-sft-content_generator-train.jsonl

    # Sonra HF Hub'a push:
    python apps/api/scripts/sft_push_hf.py \\
        --jsonl nodrat-sft-content_generator-train.jsonl \\
        --dataset-name nodrat/turkish-content-generation \\
        --hf-token $HF_TOKEN \\
        --split train

Bağımlılıklar:
    pip install datasets huggingface_hub  # API requirements'a eklenmiş değil — manuel

KVKK uyumu:
    - Default `--private` (zorla public yapmak için --public flag açıkça gerek)
    - Dataset card otomatik oluşturulur (lineage transparency)

Refs: #569
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Nodrat SFT JSONL → Hugging Face Hub private push")
    parser.add_argument(
        "--jsonl",
        type=Path,
        required=True,
        help="Input JSONL dosyası (POST /admin/sft/export çıktısı)",
    )
    parser.add_argument(
        "--dataset-name",
        required=True,
        help="HF Hub dataset adı (ör. 'nodrat/turkish-content-generation')",
    )
    parser.add_argument(
        "--hf-token",
        required=True,
        help="Hugging Face access token (write scope)",
    )
    parser.add_argument(
        "--split",
        default="train",
        help="HF dataset split (train|val|test)",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="DİKKAT: Public yap (default private). KVKK + IP koruması için "
        "default private önerilir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Push etmeden sadece doğrula (lokal datasets cache'e yükle)",
    )
    args = parser.parse_args()

    if not args.jsonl.exists():
        print(f"ERROR: JSONL dosyası bulunamadı: {args.jsonl}", file=sys.stderr)
        return 1

    # Lazy import — sadece script çalıştırıldığında dependency check
    try:
        from datasets import Dataset
    except ImportError:
        print(
            "ERROR: 'datasets' paketi gerekli.\nYüklemek için: pip install datasets",
            file=sys.stderr,
        )
        return 1

    # JSONL → Dataset
    print(f"→ Reading {args.jsonl}...")
    records = []
    with args.jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    print(f"  loaded {len(records)} records")

    if not records:
        print("ERROR: JSONL boş veya geçersiz", file=sys.stderr)
        return 1

    dataset = Dataset.from_list(records)
    print(f"  schema: {list(dataset.features.keys())}")

    if args.dry_run:
        print("\nDRY RUN — push edilmedi.")
        print(f"  dataset.num_rows: {dataset.num_rows}")
        print(f"  dataset[0]['metadata']: {dataset[0].get('metadata', {})}")
        return 0

    print(
        f"\n→ Pushing to '{args.dataset_name}' "
        f"({'PUBLIC' if args.public else 'PRIVATE'}, split={args.split})..."
    )

    dataset.push_to_hub(
        args.dataset_name,
        split=args.split,
        token=args.hf_token,
        private=not args.public,
    )

    print(f"\nOK: pushed {len(records)} records to {args.dataset_name}")
    print(f"  view: https://huggingface.co/datasets/{args.dataset_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
