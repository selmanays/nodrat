#!/usr/bin/env bash
# RAG retrieval benchmark wrapper (#179)
#
# Local (Docker compose):
#   ./scripts/eval_retrieval.sh
#   ./scripts/eval_retrieval.sh --output baseline.json
#
# Remote (production VPS):
#   ssh -p 443 root@HOST 'cd /opt/nodrat && \
#     docker compose exec -T api python -m tests.eval.retrieval_benchmark --output /tmp/eval.json'

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/.."  # → repo root

ARGS=("$@")
if [[ -z "${ARGS[*]:-}" ]]; then
    ARGS=(--output "tests/eval/.last_report.json")
fi

docker compose exec -T api python -m tests.eval.retrieval_benchmark "${ARGS[@]}"
